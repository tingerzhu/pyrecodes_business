"""
Unit tests for ResidualEmployeeDistributionModel: the resource-aware variant of
UtilityDistributionModel that reassigns RESIDUAL (spare) employees and

  1) runs check_employees per business,
  2) two-pass-distributes the Employee resource (collect every supplier BEFORE meeting
     any demand, so random-priority recipients are never starved by ordering),
  3) routes the received employees back to the demand-contributing businesses.

The class behavior is tested both through a smoke __init__ on the existing test
Alameda config and via narrow direct tests on the new methods using `__new__` plus
hand-rolled stubs so we can isolate each pass.
"""
import numpy as np
import pytest

from pyrecodes import main
from pyrecodes.utilities import read_json_file
from pyrecodes.business.business import Business
from pyrecodes.component.r2d_component import R2DBuilding, R2DBuildingWithBusiness
from pyrecodes.resource_distribution_model.residual_employee_distribution_model import (
    ResidualEmployeeDistributionModel,
)
from tests.test_business.test_business_inputs import BUSINESS_PARAMETERS

MAIN_FILE = './tests/test_inputs/test_inputs_Alameda_Main.json'
RESOURCE_NAME = 'Employee'


class _StubResource:
    """Mirror of Resource for the supply/demand resource slots that the Employee
    accumulators write to. Exposes only what UtilityDistributionModel touches:
    `current_amount` and `update_based_on_consumption` (called when a supplier's
    consumption is reconciled at the end of distribute)."""
    def __init__(self, current_amount: float = 0.0):
        self.current_amount = float(current_amount)

    def update_based_on_consumption(self, consumed_amount: float) -> None:
        self.current_amount = max(0.0, self.current_amount - consumed_amount)


class _StubSystemMatrix:
    """Bare-minimum stand-in for SingleResourceSystemMatrixCreator that exposes the
    two columns (DEMAND, DEMAND_MET) read by _route_received_employees."""
    DEMAND_COL_ID = 2
    DEMAND_MET_COL_ID = 4

    def __init__(self, matrix):
        self.matrix = np.array(matrix, dtype=float)


def _make_building_with_business(num_employees: int, building_id: int, business_id: int,
                                 reason_for_drop_prev=None, employees_available_prev: float = 1.0):
    """Construct an R2DBuildingWithBusiness with one Business pre-staged at t=1."""
    building = R2DBuildingWithBusiness()
    building.aim_id = str(building_id)
    building.set_locality([1])  # needed by SingleResourceSystemMatrixCreator
    building.supply['Supply']['Employee'] = _StubResource()
    building.demand['OperationDemand']['Employee'] = _StubResource()

    params = dict(BUSINESS_PARAMETERS)
    params['NumEmployees'] = num_employees
    business = Business(str(business_id), params, building)
    business.reason_for_drop = {1: reason_for_drop_prev or []}
    business.employees_available = {1: employees_available_prev}
    building.businesses = [business]
    return building, business


def _new_model_with(components, matrix=None):
    """Build an ResidualEmployeeDistributionModel via __new__ (bypassing the heavy
    constructor) and seed it with only the attributes the tested methods touch."""
    model = ResidualEmployeeDistributionModel.__new__(ResidualEmployeeDistributionModel)
    model.resource_name = RESOURCE_NAME
    model.components = components
    model.transfer_service_distribution_models = []
    model.transfer_service_distribution_model = None
    if matrix is not None:
        model.system_matrix = _StubSystemMatrix(matrix)
    return model


# ---------------------------------------------------------------------------
# Smoke tests via the real constructor
# ---------------------------------------------------------------------------

class TestResidualEmployeeDistributionModelInit:
    """Sanity-check that the full constructor wiring works on the test config."""

    @pytest.fixture
    def system(self):
        return main.create_system(read_json_file(MAIN_FILE))

    @pytest.fixture
    def resource_parameters(self):
        # Mirrors the Employee resource block used in production; random priority over
        # OperationDemand is what the redistribution model is designed for.
        return {
            'DistributionPriority': {
                'FileName': 'random_priority',
                'ClassName': 'RandomPriority',
                'Parameters': {
                    'Seed': 42.0,
                    'DemandType': ['OperationDemand'],
                },
            },
        }

    def test_init_constructs_required_state(self, system, resource_parameters):
        model = ResidualEmployeeDistributionModel(RESOURCE_NAME, resource_parameters, system.components)
        assert model.resource_name == RESOURCE_NAME
        # The constructor's set_components filters to employee homes (components with
        # Employee supply) and business buildings, so model.components is a subset of
        # the system components (possibly empty for minimal test configs).
        assert all(component in system.components for component in model.components)
        # Both transfer-service slots exist with the right shape: a list (used by the
        # check_employees pass) and a singular None (used by parent path-functionality).
        assert model.transfer_service_distribution_models == []
        assert model.transfer_service_distribution_model is None
        # System matrix and priority were set by the parent UtilityDistributionModel constructor.
        assert hasattr(model, 'system_matrix')
        assert hasattr(model, 'priority')

    def test_set_transfer_service_distribution_model_appends(self, system, resource_parameters):
        model = ResidualEmployeeDistributionModel(RESOURCE_NAME, resource_parameters, system.components)
        marker_a = object()
        marker_b = object()
        model.set_transfer_service_distribution_model(marker_a)
        model.set_transfer_service_distribution_model(marker_b)
        assert model.transfer_service_distribution_models == [marker_a, marker_b]
        # The singular slot stays None: Employee is gated by per-business accessibility,
        # not by locality-path functionality used in plain UtilityDistributionModel.
        assert model.transfer_service_distribution_model is None


# ---------------------------------------------------------------------------
# Direct method tests using __new__ + stubs
# ---------------------------------------------------------------------------

class TestReduceComponentSupplyOverride:
    """The override exists so the parent's partial-meet path does not run
    update_supply_based_on_unmet_demand on demander buildings (Employee inflow
    bumps business labor instead, in _route_received_employees)."""

    def test_reduce_component_supply_is_noop(self):
        # Sentinel component whose update_supply_based_on_unmet_demand would explode
        # if called -- proves the override does not delegate.
        class _Boom:
            def update_supply_based_on_unmet_demand(self, *_args, **_kwargs):
                raise AssertionError('parent path must not run for Employee')

        model = _new_model_with(components=[_Boom()])
        # No exception -> override is the intended no-op.
        model.reduce_component_supply(component_row_id=0, percent_of_met_demand=0.5)


class TestRouteReceivedEmployees:
    """_route_received_employees reads (demand, met) per row from the system matrix
    and forwards the product to distribute_received_employees on each
    R2DBuildingWithBusiness, skipping any other component types."""

    def test_routes_partial_and_full_demand_only_to_labor_only_recipients(self):
        # Row 0: full demand met (matrix default 1.0). Row 1: 50% met. Row 2: non-building.
        recipient_full, biz_full = _make_building_with_business(
            num_employees=4, building_id='R1', business_id=1,
            reason_for_drop_prev=[{'Name': 'Labor', 'Level': 0.5}],
            employees_available_prev=0.5,
        )
        recipient_partial, biz_partial = _make_building_with_business(
            num_employees=4, building_id='R2', business_id=2,
            reason_for_drop_prev=[{'Name': 'Labor', 'Level': 0.5}],
            employees_available_prev=0.5,
        )

        class _NotABuilding:
            pass

        # Prime t=2 state for the recipients (so apply_received_employees has a
        # baseline to mutate, just like the real flow does after check_employees).
        for biz in (biz_full, biz_partial):
            biz.update(time_step=2)
            biz.employees_available[2] = 0.5
            biz.update_current_business_functionality(2, 0.5, 'Labor')

        components = [recipient_full, recipient_partial, _NotABuilding()]
        # Columns: [start_loc, end_loc, demand, supply, demand_met_fraction]
        matrix = [
            [0.0, 0.0, 2.0, 0.0, 1.0],  # 4*1 = 4 demanded? actually 2 demanded fully met -> 2 inflow
            [0.0, 0.0, 2.0, 0.0, 0.5],  # 2 demanded, 50% met -> 1 inflow
            [0.0, 0.0, 0.0, 0.0, 1.0],  # non-building row, no routing
        ]
        model = _new_model_with(components=components, matrix=matrix)
        model._route_received_employees(time_step=2)

        # Full-meet recipient went from 0.5 (assigned 2 of 4) to (2+2)/4 = 1.0.
        assert biz_full.employees_available[2] == 1.0
        # Partial-meet recipient went from 0.5 (assigned 2 of 4) to (2+1)/4 = 0.75.
        assert biz_partial.employees_available[2] == 0.75

    def test_skips_rows_with_zero_inflow(self):
        # A row with demand>0 but met=0 should not invoke distribute_received_employees.
        recipient, biz = _make_building_with_business(
            num_employees=4, building_id='R', business_id=1,
            reason_for_drop_prev=[{'Name': 'Labor', 'Level': 0.5}],
            employees_available_prev=0.5,
        )
        biz.update(time_step=2)
        biz.employees_available[2] = 0.5
        matrix = [[0.0, 0.0, 2.0, 0.0, 0.0]]  # 0% met -> 0 inflow
        model = _new_model_with(components=[recipient], matrix=matrix)
        model._route_received_employees(time_step=2)
        assert biz.employees_available[2] == 0.5  # unchanged


class TestTwoPassDistribute:
    """_two_pass_distribute must collect every supplier BEFORE meeting any demand.
    A single-pass loop in random priority can starve a recipient row that comes
    before any donor row; the two-pass form is the fix."""

    def test_donor_first_then_recipient_in_priority(self):
        # Two donors, one recipient. We force a priority order where the recipient
        # row appears FIRST -- the single-pass code would leave its demand unmet.
        donor1, _ = _make_building_with_business(
            num_employees=4, building_id='D1', business_id=1,
            reason_for_drop_prev=[{'Name': 'Infrastructure', 'Level': 0.0}],
            employees_available_prev=1.0,
        )
        donor2, _ = _make_building_with_business(
            num_employees=4, building_id='D2', business_id=2,
            reason_for_drop_prev=[{'Name': 'Infrastructure', 'Level': 0.0}],
            employees_available_prev=1.0,
        )
        recipient, biz_r = _make_building_with_business(
            num_employees=4, building_id='R', business_id=3,
            reason_for_drop_prev=[{'Name': 'Labor', 'Level': 0.5}],
            employees_available_prev=0.5,
        )
        biz_r.update(time_step=2)
        biz_r.employees_available[2] = 0.5
        biz_r.update_current_business_functionality(2, 0.5, 'Labor')

        components = [donor1, donor2, recipient]

        # Hand-rolled priority that lists the recipient first.
        class _PriorityRecipientFirst:
            def get_component_priorities(self):
                # Components by index: recipient=2, donor1=0, donor2=1.
                return [2, 0, 1], ['OperationDemand', 'OperationDemand', 'OperationDemand']

        from pyrecodes.resource_distribution_model.single_resource_system_matrix_creator import (
            SingleResourceSystemMatrixCreator,
        )

        # Push donor employees onto the building Employee supply slots so the matrix
        # picks them up.
        donor1.supply['Supply']['Employee'].current_amount = 4
        donor2.supply['Supply']['Employee'].current_amount = 4
        recipient.demand['OperationDemand']['Employee'].current_amount = 2

        model = _new_model_with(components=components)
        model.priority = _PriorityRecipientFirst()
        model.system_matrix = SingleResourceSystemMatrixCreator(components, RESOURCE_NAME)

        model._two_pass_distribute()

        # Recipient's row should have full demand met now (suppliers were collected
        # FIRST), even though it was ordered earliest in priority.
        recipient_row = 2
        met = model.system_matrix.matrix[recipient_row, model.system_matrix.DEMAND_MET_COL_ID]
        assert met == 1.0


# ---------------------------------------------------------------------------
# End-to-end test through the REAL constructor + REAL system matrix
# ---------------------------------------------------------------------------

class _AlwaysAccessible:
    """Stub transfer-service model: every building reaches every other building.
    Accessibility has its own dedicated tests; here we want to exercise the real
    redistribution machinery without coupling to a traffic/island model. (No
    `od_trip_checker` attribute, so set_transfer_service_distribution_model skips
    the OD-matrix seeding branch.)"""
    def is_building_accessible(self, time_step, origin_building_id, destination_building_id):
        return True


def _make_employee_home(home_id) -> R2DBuilding:
    """A functional residential building that can host residual Employee supply."""
    home = R2DBuilding()
    home.aim_id = str(home_id)
    home.set_locality([1])
    home.supply['Supply']['Employee'] = _StubResource(0.0)
    return home


# Resource block mirroring production: random priority over OperationDemand is the
# regime the redistribution model is designed for.
_RESOURCE_PARAMETERS = {
    'DistributionPriority': {
        'FileName': 'random_priority',
        'ClassName': 'RandomPriority',
        'Parameters': {'Seed': 42.0, 'DemandType': ['OperationDemand']},
    },
}


class TestEndToEndRedistribution:
    """Drive the whole pipeline on a hand-built minimal system using the REAL
    constructor, the REAL SingleResourceSystemMatrixCreator and the REAL
    distribute(): a blocked business frees its still-reachable employees, and a
    labor-short-but-operational business should absorb them.

    Topology (all in locality 1, so matrix path functionality is 1.0):
      H1, H2          -- residential homes of the BLOCKED donor business
      donor_building  -- business that could not operate last step (Infrastructure down)
      recipient_building -- operational business that was short on labor last step
    The donor has 2 reachable employees; the recipient demands 1 (it was assigned 1
    of 2 at t-1). So 1 employee should move H1/H2 -> recipient.
    """

    def _build(self, donor_blocked: bool):
        time_step = 2
        home_1 = _make_employee_home('H1')
        home_2 = _make_employee_home('H2')

        donor_blocker = [{'Name': 'Infrastructure', 'Level': 0.0}] if donor_blocked else []
        donor_building, donor_business = _make_building_with_business(
            num_employees=2, building_id='DONOR', business_id=1,
            reason_for_drop_prev=donor_blocker, employees_available_prev=1.0,
        )
        recipient_building, recipient_business = _make_building_with_business(
            num_employees=2, building_id='RECIPIENT', business_id=2,
            reason_for_drop_prev=[{'Name': 'Labor', 'Level': 0.5}],
            employees_available_prev=0.5,
        )

        # Wire each business to its homes (set_employee_homes runs in the constructor).
        donor_business.parameters['EmployeeLocations'] = ['H1', 'H2']
        recipient_business.parameters['EmployeeLocations'] = []  # stays unstaffed on its own at t

        components = [home_1, home_2, donor_building, recipient_building]
        model = ResidualEmployeeDistributionModel('Employee', _RESOURCE_PARAMETERS, components)
        model.set_transfer_service_distribution_model(_AlwaysAccessible())

        # System update phase (runs before distribute in the real loop): sets the
        # recipient's Employee operation demand from its t-1 labor shortfall.
        donor_business.update(time_step)
        recipient_business.update(time_step)

        model.distribute(time_step)
        return model, home_1, home_2, recipient_building, recipient_business

    def test_blocked_business_employees_move_to_labor_short_business(self):
        model, home_1, home_2, recipient_building, recipient_business = self._build(donor_blocked=True)

        recipient_row = model.components.index(recipient_building)
        met = model.system_matrix.matrix[recipient_row, model.system_matrix.DEMAND_MET_COL_ID]

        # 1) The recipient's labor demand was fully met from the donor's homes.
        assert met == pytest.approx(1.0)
        # 2) The received employee was applied: 0 of its own + 1 received = 1/2 = 0.5.
        assert recipient_business.employees_available[2] == pytest.approx(0.5)
        # 3) Exactly one employee was consumed from the freed residual supply
        #    (2 registered across H1+H2, 1 consumed -> 1 remaining).
        remaining = (home_1.supply['Supply']['Employee'].current_amount
                     + home_2.supply['Supply']['Employee'].current_amount)
        assert remaining == pytest.approx(1.0)

    def test_no_redistribution_when_donor_not_blocked(self):
        # Same topology, but the donor CAN operate -> it registers no residual supply,
        # so there is nothing to redistribute and the recipient stays unstaffed.
        model, home_1, home_2, recipient_building, recipient_business = self._build(donor_blocked=False)

        recipient_row = model.components.index(recipient_building)
        met = model.system_matrix.matrix[recipient_row, model.system_matrix.DEMAND_MET_COL_ID]

        assert met == pytest.approx(0.0)               # demand unmet, no supply existed
        assert recipient_business.employees_available[2] == pytest.approx(0.0)
        assert home_1.supply['Supply']['Employee'].current_amount == pytest.approx(0.0)
        assert home_2.supply['Supply']['Employee'].current_amount == pytest.approx(0.0)
