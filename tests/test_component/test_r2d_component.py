import pytest
from pyrecodes.component.r2d_component import R2DPipe, R2DComponent, R2DBuilding, R2DBuildingWithBusiness
from pyrecodes.business.business import Business
from test_component_inputs import COMPONENT_NAME, COMPONENT_PARAMETERS
from tests.test_business.test_business_inputs import BUSINESS_ID, BUSINESS_PARAMETERS

class TestR2DComponent:

    @pytest.fixture
    def r2d_component(self):
        return R2DComponent()
    
    def test_update_r2d_dict(self, r2d_component):
        r2d_component.general_information = {}
        r2d_component.general_information['OperationDemand'] = {}
        r2d_component.general_information['RecoveryDemand'] = {}
        r2d_component.update_r2d_dict()
        assert r2d_component.general_information['OperationDemand'] == {}
        assert r2d_component.general_information['RecoveryDemand'] == {}  

        r2d_component.construct(COMPONENT_NAME, COMPONENT_PARAMETERS)
        r2d_component.update_r2d_dict()
        assert r2d_component.general_information['OperationDemand'] == {'DemandResource1': 1, 'DemandResource2': 5}
        assert r2d_component.general_information['RecoveryDemand'] == {} 

        DUMMY_RESOURCE_DICT = {"DemandResource3": {"Amount": 100,
                                                "FunctionalityToAmountRelation": "Linear",
                                                "UnmetDemandToAmountRelation": "Constant"
                                                                }}
        r2d_component.add_resources('demand', 'RecoveryDemand', DUMMY_RESOURCE_DICT)
        r2d_component.update_r2d_dict()
        assert r2d_component.general_information['OperationDemand'] == {'DemandResource1': 1, 'DemandResource2': 5}
        assert r2d_component.general_information['RecoveryDemand'] == {'DemandResource3': 100}

        r2d_component.demand['OperationDemand']['DemandResource1'].current_amount = 0
        r2d_component.update_r2d_dict()
        assert r2d_component.general_information['OperationDemand'] == {'DemandResource1': 0, 'DemandResource2': 5}
        assert r2d_component.general_information['RecoveryDemand'] == {'DemandResource3': 100}
          
class TestR2DPipe:

    @pytest.fixture
    def r2d_pipe(self):
        return R2DPipe()
    
    def test_init(self, r2d_pipe):
        assert r2d_pipe.damage_information == {'Location': [], 'Type': []}

    def test_update_r2d_dict(self, r2d_pipe):
        r2d_pipe.general_information['Status'] = 'OPEN'        
        r2d_pipe.update_r2d_dict()
        assert r2d_pipe.damage_information == {'Location': [], 'Type': []}
        assert r2d_pipe.general_information['Status'] == 'OPEN'

        r2d_pipe.functionality_level = 0.0
        r2d_pipe.update_r2d_dict()
        assert r2d_pipe.general_information['Status'] == 'CLOSED'

        r2d_pipe.functionality_level = 1.0
        r2d_pipe.update_r2d_dict()
        assert r2d_pipe.general_information['Status'] == 'OPEN'
        assert r2d_pipe.damage_information == {'Location': [], 'Type': []}
        
class TestR2DBuilding:
    
    @pytest.fixture
    def r2d_building(self):
        return R2DBuilding()
    
    def test_init(self, r2d_building):
        assert r2d_building.general_information == {'PopulationRatio': 1.0}
    
    def test_update_r2d_dict(self, r2d_building):
        r2d_building.functionality_level = 0.5
        r2d_building.update_r2d_dict()
        assert r2d_building.general_information['PopulationRatio'] == 0.5

        r2d_building.functionality_level = 1.0
        r2d_building.update_r2d_dict()
        assert r2d_building.general_information['PopulationRatio'] == 1.0

    def test_add_employee_supply_on_plain_building(self, r2d_building):
        # Residential homes are plain R2DBuilding; they must be able to hold residual
        # Employee supply for the ResidualEmployeeDistributionModel. No-op without slot.
        r2d_building.add_employee_supply(5)  # no Employee slot yet -> silently ignored
        assert r2d_building.supply['Supply'].get('Employee') is None
        r2d_building.supply['Supply']['Employee'] = _StubResource()
        r2d_building.add_employee_supply(2)
        r2d_building.add_employee_supply(1)
        assert r2d_building.supply['Supply']['Employee'].current_amount == 3

class TestR2DBuildingWithBusiness:

    @pytest.fixture
    def r2d_building_with_business(self):
        return R2DBuildingWithBusiness()

    @pytest.fixture
    def business(self, r2d_building_with_business):
        return Business(BUSINESS_ID, BUSINESS_PARAMETERS, r2d_building_with_business)

    def test_update_supply_based_on_unmet_demand(self, r2d_building_with_business, business):
        r2d_building_with_business.businesses = [business]
        r2d_building_with_business.functionality_level = 1.0
        business.update(time_step=1)
        r2d_building_with_business.update_supply_based_on_unmet_demand(percent_of_met_demand=0.75, time_step=1)
        assert business.business_functionality_level == 0.75
        # update_reason_for_drop records every contributing reason, including Level 1.0
        # rows: business.update wrote Home Component Functionality at 1.0 first, then
        # update_supply_based_on_unmet_demand appended Infrastructure at 0.75.
        assert business.reason_for_drop == {1: [
            {'Name': 'Home Component Functionality', 'Level': 1.0},
            {'Name': 'Infrastructure', 'Level': 0.75},
        ]}


class _StubResource:
    """Minimal stand-in for Resource exposing only `current_amount`."""
    def __init__(self, current_amount: float = 0.0):
        self.current_amount = float(current_amount)


def _make_business(num_employees: int, building, business_id: int = 1):
    """Build a Business with the BUSINESS_PARAMETERS fixture, but override NumEmployees."""
    params = dict(BUSINESS_PARAMETERS)
    params['NumEmployees'] = num_employees
    return Business(str(business_id), params, building)


class TestR2DBuildingWithBusinessEmployeeAccumulators:
    """
    Tests for add_employee_supply, add_employee_demand, and distribute_received_employees
    -- the three methods that let Employee flow as a regular utility resource through
    a building that hosts businesses.
    """

    @pytest.fixture
    def building(self):
        building = R2DBuildingWithBusiness()
        building.aim_id = '42'
        # Inject the Employee supply/demand resource objects the component library
        # would normally create.
        building.supply['Supply']['Employee'] = _StubResource()
        building.demand['OperationDemand']['Employee'] = _StubResource()
        return building

    # ---- add_employee_supply / add_employee_demand -------------------------

    def test_add_employee_supply_accumulates(self, building):
        building.add_employee_supply(3)
        building.add_employee_supply(2)
        assert building.supply['Supply']['Employee'].current_amount == 5

    def test_add_employee_demand_accumulates(self, building):
        building.add_employee_demand(1)
        building.add_employee_demand(4)
        assert building.demand['OperationDemand']['Employee'].current_amount == 5

    def test_add_methods_noop_when_resource_absent(self):
        # Building without the Employee resource slot should not raise -- it just
        # records nothing. This guards against component libraries that omit Employee.
        bare = R2DBuildingWithBusiness()
        bare.add_employee_supply(5)
        bare.add_employee_demand(5)
        # No assertion target other than "no exception raised" -- explicit check below.
        assert bare.supply['Supply'].get('Employee') is None
        assert bare.demand['OperationDemand'].get('Employee') is None

    # ---- distribute_received_employees -------------------------------------

    def test_distribute_routes_only_to_labor_only_businesses(self, building):
        # Building hosts two businesses: one labor-only at t-1 (recipient), one
        # blocked by Infrastructure at t-1 (donor). Inflow must reach only the
        # labor-only one.
        recipient = _make_business(num_employees=4, building=building, business_id=1)
        donor = _make_business(num_employees=4, building=building, business_id=2)
        building.businesses = [recipient, donor]

        # Stage previous-step state used by is_short_on_labor_but_can_operate and
        # get_assigned_employees inside distribute_received_employees.
        recipient.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5}]}
        recipient.employees_available = {1: 0.5}  # assigned = 2 of 4 -> need 2
        donor.reason_for_drop = {1: [{'Name': 'Infrastructure', 'Level': 0.0}]}
        donor.employees_available = {1: 1.0}     # all 4 idle in the pool

        # Prime t=2 baseline so apply_received_employees has something to mutate.
        recipient.update(time_step=2)
        donor.update(time_step=2)
        # check_employees-equivalent: recipient still at 0.5 because homes
        # unchanged; for the test we set it directly.
        recipient.employees_available[2] = 0.5
        donor.employees_available[2] = 1.0
        # Stamp a Labor reason on recipient as check_employees would have.
        recipient.update_current_business_functionality(2, 0.5, 'Labor')

        building.distribute_received_employees(time_step=2, n_extra=2)

        # Recipient absorbed both extra workers; donor was untouched.
        assert recipient.employees_available[2] == 1.0
        assert donor.employees_available[2] == 1.0

    def test_distribute_reaches_recipient_with_reduced_customer_base(self, building):
        # A business short on labor AND with a reduced customer base can still operate,
        # so it is a valid recipient: a hard blocker would disqualify it, a soft one
        # (Customer Base) does not.
        recipient = _make_business(num_employees=4, building=building, business_id=1)
        building.businesses = [recipient]
        recipient.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5},
                                         {'Name': 'Customer Base', 'Level': 0.3}]}
        recipient.employees_available = {1: 0.5}  # assigned 2 of 4 -> need 2
        recipient.update(time_step=2)
        recipient.employees_available[2] = 0.5
        recipient.update_current_business_functionality(2, 0.5, 'Labor')

        building.distribute_received_employees(time_step=2, n_extra=2)

        # 2 extra on top of 2 assigned -> fully staffed.
        assert recipient.employees_available[2] == 1.0

    def test_distribute_proportional_to_demand_when_multiple_recipients(self, building):
        # Two labor-only recipients in the same building: needs 1 and 3 -> total 4.
        # With n_extra = 2, they get 0.5 and 1.5 respectively.
        small_recipient = _make_business(num_employees=4, building=building, business_id=1)
        big_recipient = _make_business(num_employees=4, building=building, business_id=2)
        building.businesses = [small_recipient, big_recipient]
        small_recipient.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.75}]}
        small_recipient.employees_available = {1: 0.75}  # assigned = 3 -> need 1
        big_recipient.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.25}]}
        big_recipient.employees_available = {1: 0.25}    # assigned = 1 -> need 3

        small_recipient.update(time_step=2)
        big_recipient.update(time_step=2)
        small_recipient.employees_available[2] = 0.75
        big_recipient.employees_available[2] = 0.25
        small_recipient.update_current_business_functionality(2, 0.75, 'Labor')
        big_recipient.update_current_business_functionality(2, 0.25, 'Labor')

        building.distribute_received_employees(time_step=2, n_extra=2)

        # small_recipient: assigned 3 + 0.5 = 3.5 -> ratio 0.875
        # big_recipient:   assigned 1 + 1.5 = 2.5 -> ratio 0.625
        assert small_recipient.employees_available[2] == pytest.approx(0.875)
        assert big_recipient.employees_available[2] == pytest.approx(0.625)

    def test_distribute_noop_when_no_recipients(self, building):
        # Building has businesses but none is labor-only at t-1 -> nothing to do.
        donor1 = _make_business(num_employees=4, building=building, business_id=1)
        donor2 = _make_business(num_employees=4, building=building, business_id=2)
        building.businesses = [donor1, donor2]
        donor1.reason_for_drop = {1: [{'Name': 'Infrastructure', 'Level': 0.0}]}
        donor1.employees_available = {1: 1.0, 2: 1.0}
        donor2.reason_for_drop = {1: []}
        donor2.employees_available = {1: 1.0, 2: 1.0}

        donor1.update(time_step=2)
        donor2.update(time_step=2)
        # Snapshot pre-distribute state.
        pre = {donor1.business_id: donor1.employees_available[2],
               donor2.business_id: donor2.employees_available[2]}

        building.distribute_received_employees(time_step=2, n_extra=10)

        # No employees_available should be mutated.
        assert donor1.employees_available[2] == pre[donor1.business_id]
        assert donor2.employees_available[2] == pre[donor2.business_id]

    def test_distribute_noop_when_n_extra_zero_or_negative(self, building):
        recipient = _make_business(num_employees=4, building=building, business_id=1)
        building.businesses = [recipient]
        recipient.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5}]}
        recipient.employees_available = {1: 0.5}
        recipient.update(time_step=2)
        recipient.employees_available[2] = 0.5

        building.distribute_received_employees(time_step=2, n_extra=0)
        assert recipient.employees_available[2] == 0.5

        building.distribute_received_employees(time_step=2, n_extra=-5)
        assert recipient.employees_available[2] == 0.5

    def test_distribute_noop_when_no_businesses(self, building):
        # Building with no businesses must not raise.
        building.businesses = []
        building.distribute_received_employees(time_step=2, n_extra=10)
        # Implicit: no exception. Resource amounts untouched.
        assert building.supply['Supply']['Employee'].current_amount == 0
