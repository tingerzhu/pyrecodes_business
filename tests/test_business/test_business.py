import pytest
import pandas as pd
from pyrecodes import main
from pyrecodes.utilities import read_json_file
from pyrecodes.business.business import Business, is_building_accessible
from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model import ResidualDemandTrafficDistributionModel
from tests.test_business.test_business_inputs import BUSINESS_ID, BUSINESS_PARAMETERS
from tests.test_resource_distribution_model.test_resource_distribution_model_inputs import MAIN_FILE_RESIDUAL_DEMAND, RESOURCE_NAME_RESIDUAL_DEMAND, RESOURCE_PARAMETERS_RESIDUAL_DEMAND
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness, R2DBuilding


def make_travel_setup(tsm, od_pairs):
    """
    Helper to configure travel times on a distribution model for testing.
    od_pairs: list of (origin_nid, destin_nid, travel_time, change_factor)
    Sets travel_times, travel_time_change_factors, travel_time_change_index, trip_index, and
    clears isolated_nodes so manually assigned test nodes are never filtered out.
    """
    records = [
        {'agent_id': float(i + 1), 'origin_nid': o, 'destin_nid': d, 'travel_time_used': t}
        for i, (o, d, t, _) in enumerate(od_pairs)
    ]
    df = pd.DataFrame(records)
    trip_index = {(r['origin_nid'], r['destin_nid']): i for i, r in enumerate(records)}
    change_index = {float(i + 1): cf for i, (_, _, _, cf) in enumerate(od_pairs)}
    change_factors = [{'agent_id': float(i + 1), 'travel_time_change': cf} for i, (_, _, _, cf) in enumerate(od_pairs)]
    tsm.travel_times = [df]
    # trip_index is a list parallel to travel_times (one (origin,destin)->row dict per step).
    tsm.trip_index = [trip_index]
    tsm.travel_time_change_index = [change_index]
    tsm.travel_time_change_factors = [change_factors]
    tsm.od_trip_checker.isolated_nodes = set()


OFF_ISLAND_ORIGIN = '__off_island__'


class _IslandStub:
    """Stand-in for the island connectivity model. is_building_accessible returns a fixed
    verdict for trips originating at the off-island proxy origin and abstains (None) for
    on-island origins, matching IslandConnectivityDistributionModel's dispatch."""
    def __init__(self, reachable: bool, off_island_origin_id: str = OFF_ISLAND_ORIGIN):
        self.reachable = reachable
        self.off_island_origin_id = off_island_origin_id

    def is_building_accessible(self, time_step, origin_building_id, destination_building_id):
        if origin_building_id == self.off_island_origin_id:
            return self.reachable
        return None  # on-island origin: abstain, let the traffic model answer

    def is_reachable_from_mainland(self, time_step, business_id):
        return self.reachable


class TestBusiness:

    @pytest.fixture
    def home_component(self):
        component = R2DBuildingWithBusiness()
        component.aim_id = '5'
        return component

    @pytest.fixture
    def business(self, home_component):
        return Business(BUSINESS_ID, BUSINESS_PARAMETERS, home_component)

    @pytest.fixture
    def transfer_service_distribution_model(self):
        input_dict = read_json_file(MAIN_FILE_RESIDUAL_DEMAND)
        system = main.create_system(input_dict)
        return ResidualDemandTrafficDistributionModel(RESOURCE_NAME_RESIDUAL_DEMAND, RESOURCE_PARAMETERS_RESIDUAL_DEMAND, system.components)

    def test_is_building_accessible_dispatch(self):
        # The module-level is_building_accessible polls each transfer-service model in
        # order and returns the first non-None verdict; a model with no opinion on the
        # pair (e.g. a building outside its scope) returns None and is skipped. With no
        # decisive model (or none at all) the building is treated as not accessible.
        class _Abstains:
            def is_building_accessible(self, *_):
                return None

        class _Says:
            def __init__(self, verdict):
                self.verdict = verdict

            def is_building_accessible(self, *_):
                return self.verdict

        assert is_building_accessible([_Abstains(), _Says(True)], 0, 'a', 'b') is True
        assert is_building_accessible([_Abstains(), _Says(False)], 0, 'a', 'b') is False
        assert is_building_accessible([_Abstains(), _Abstains()], 0, 'a', 'b') is False
        assert is_building_accessible([], 0, 'a', 'b') is False

    def test_init(self, business):
        assert business.employees_available == {}
        assert business.customer_base_ratio == {}
        assert business.input_commodity_available_ratio == 1.0
        assert business.reason_for_drop == {}
        assert business.business_functionality_level == 1.0
        assert business.revenue == {}
        assert business.pre_disaster_revenue_per_time_step == pytest.approx(1000 / 52)
        assert business.employee_homes == []
        assert business.parameters["CompanyName"] == "TestBusiness"
        assert business.parameters["NumEmployees"] == 2
        assert business.parameters["SalesVolume"] == 1000
        assert business.parameters["NAICS"] == 72251117
        assert business.parameters["AvgDailyVisits"] == 10
        assert business.parameters["VisitorHomeCBGs"] == {
            "060014272001": 0.4,
            "060014280001": 0.4,
            "Others": 0.2
        }
        assert business.parameters["NearestRetailLocations"] == [
            "374",
            "1845",
            "2472"
        ]
        assert business.parameters["EmployeeLocations"] == [
            "1",
            "2",
            "100000",
        ]

    def test_set_employee_homes(self, business):
        component1 = R2DBuilding()
        component1.aim_id = '1'
        component2 = R2DBuilding()
        component2.aim_id = '2'
        component3 = R2DBuilding()
        component3.aim_id = '3'
        component4 = R2DBuilding()
        component4.aim_id = '100000'
        components = [
            component1,
            component2,
            component3,
            component4,
        ]
        business.set_employee_homes(components)
        assert len(business.employee_homes) == 3
        assert business.employee_homes[0].aim_id == '1'
        assert business.employee_homes[1].aim_id == '2'
        assert business.employee_homes[2].aim_id == '100000'
        assert all(home.aim_id in ['1', '2', '100000'] for home in business.employee_homes)

    def test_get_employee_demand(self, business):
        business.business_functionality_level = 1.0
        assert business.get_employee_demand() == 2
        business.business_functionality_level = 0.5
        assert business.get_employee_demand() == 2
        business.business_functionality_level = 0.0
        assert business.get_employee_demand() == 0

    def test_get_employee_supply(self, business):
        business.employees_available = {'1': 0.5, '2': 1}
        assert business.get_employee_supply() == 2
        business.employees_available = {'1': 0.5}
        assert business.get_employee_supply() == 1
        business.employees_available = {'1': 0.5, '2': 0}
        assert business.get_employee_supply() == 0

    def test_get_employee_consumption(self, business):
        business.employees_available = {'1': 0.5, '2': 1}
        business.business_functionality_level = 1.0
        assert business.get_employee_consumption() == 2
        business.business_functionality_level = 0.5
        assert business.get_employee_consumption() == 2     # check this with Nikola: should it be 1?
        business.employees_available = {'1': 0.5, '2': 0}
        business.business_functionality_level = 1.0
        assert business.get_employee_consumption() == 0

    def test_update(self, business, home_component):
        # update_reason_for_drop now records every contributing reason - including ones
        # at Level 1.0 - so a fully-functional update still leaves a Home Component
        # Functionality row in reason_for_drop[t]. business_functionality_level is the
        # min over those rows.
        home_component.functionality_level = 1.0
        business.update(time_step=1)
        assert business.business_functionality_level == 1.0
        assert business.reason_for_drop == {1: [{'Name': 'Home Component Functionality', 'Level': 1.0}]}
        assert business.revenue[1] == 1000/52
        home_component.functionality_level = 0.5
        business.update(time_step=2)
        assert business.business_functionality_level == 0.5
        assert business.reason_for_drop == {
            1: [{'Name': 'Home Component Functionality', 'Level': 1.0}],
            2: [{'Name': 'Home Component Functionality', 'Level': 0.5}],
        }
        assert business.revenue[2] == 500/52
        home_component.functionality_level = 0.8
        business.update(time_step=3)
        assert business.business_functionality_level == 0.8
        assert business.reason_for_drop == {
            1: [{'Name': 'Home Component Functionality', 'Level': 1.0}],
            2: [{'Name': 'Home Component Functionality', 'Level': 0.5}],
            3: [{'Name': 'Home Component Functionality', 'Level': 0.8}],
        }
        assert business.revenue[3] == 800/52

    def test_check_employees(self, business, transfer_service_distribution_model):
        transfer_service_distribution_model.building_to_traffic_node_dict['2'] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]

        business_aim_id = '1'
        employee_aim_id = '2'
        business.home_component.aim_id = business_aim_id
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict[business_aim_id]
        employee_node = transfer_service_distribution_model.building_to_traffic_node_dict[employee_aim_id]

        employee_home = R2DBuilding()
        employee_home.aim_id = employee_aim_id
        employee_home.functionality_level = 1.0
        business.employee_homes = [employee_home]
        business.parameters['NumEmployees'] = 1

        # employees available: accessible travel times
        business.update(time_step=1)
        make_travel_setup(transfer_service_distribution_model, [(business_node, employee_node, 1000.0, 1.0)])
        business.check_employees(time_step=1, transfer_service_models=[transfer_service_distribution_model])
        assert business.employees_available[1] == 1.0
        assert business.business_functionality_level == 1.0

        # employees not available: travel time and change factor exceed cutoffs
        business.update(time_step=2)
        make_travel_setup(transfer_service_distribution_model, [(business_node, employee_node, 20000.0, 5.0)])
        business.check_employees(time_step=2, transfer_service_models=[transfer_service_distribution_model])
        assert business.employees_available[2] == 0.0
        assert business.business_functionality_level == 0.0

        # employees not available: home not functional
        business.update(time_step=3)
        employee_home.functionality_level = 0.5
        make_travel_setup(transfer_service_distribution_model, [(business_node, employee_node, 1000.0, 1.0)])
        business.check_employees(time_step=3, transfer_service_models=[transfer_service_distribution_model])
        assert business.employees_available[3] == 0.0
        assert business.business_functionality_level == 0.0

    def test_traffic_model_is_building_accessible(self, transfer_service_distribution_model):
        # is_building_accessible moved from Business onto the transfer-service models;
        # this exercises the ResidualDemandTrafficDistributionModel implementation that
        # Business now delegates to via the module-level dispatch function.
        transfer_service_distribution_model.building_to_traffic_node_dict['2'] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        other_node = transfer_service_distribution_model.building_to_traffic_node_dict['2']

        # accessible: travel time and change factor within cutoffs
        make_travel_setup(transfer_service_distribution_model, [(business_node, other_node, 1000.0, 1.0)])
        assert transfer_service_distribution_model.is_building_accessible(0, '1', '2') == True

        # inaccessible: both travel time and change factor exceed cutoffs
        make_travel_setup(transfer_service_distribution_model, [(business_node, other_node, 20000.0, 5.0)])
        assert transfer_service_distribution_model.is_building_accessible(0, '1', '2') == False

        # same building: always accessible regardless of travel times
        assert transfer_service_distribution_model.is_building_accessible(0, '1', '1') == True

        # unknown building not in node dict: not accessible
        assert transfer_service_distribution_model.is_building_accessible(0, '1', 'unknown') == False

    def test_check_trips_in_od_matrix(self, business, transfer_service_distribution_model, tmp_path):
        import shutil
        original_od_file = transfer_service_distribution_model.od_trip_checker.od_matrix_filename
        temp_od_file = str(tmp_path / 'OD_Matrix_test.csv')
        shutil.copy(original_od_file, temp_od_file)
        transfer_service_distribution_model.od_trip_checker.od_matrix_filename = temp_od_file
        transfer_service_distribution_model.building_to_traffic_node_dict['2'] = 3

        business.home_component.aim_id = '1'
        component_id = '2'

        od_size_before = len(transfer_service_distribution_model.od_trip_checker.od_matrix)
        business.check_trips_in_od_matrix(transfer_service_distribution_model, [component_id])
        od_size_after = len(transfer_service_distribution_model.od_trip_checker.od_matrix)

        assert od_size_after >= od_size_before

        # calling again should not add the trip a second time
        business.check_trips_in_od_matrix(transfer_service_distribution_model, [component_id])
        assert len(transfer_service_distribution_model.od_trip_checker.od_matrix) == od_size_after

        # unknown component id: should not crash and should not modify OD matrix
        business.check_trips_in_od_matrix(transfer_service_distribution_model, ['nonexistent_id'])
        assert len(transfer_service_distribution_model.od_trip_checker.od_matrix) == od_size_after

    def test_check_supplier_trips_in_od_matrix(self, business, transfer_service_distribution_model, tmp_path):
        import shutil
        original_od_file = transfer_service_distribution_model.od_trip_checker.od_matrix_filename
        temp_od_file = str(tmp_path / 'OD_Matrix_test.csv')
        shutil.copy(original_od_file, temp_od_file)
        transfer_service_distribution_model.od_trip_checker.od_matrix_filename = temp_od_file
        transfer_service_distribution_model.building_to_traffic_node_dict['2'] = 3

        business.home_component.aim_id = '1'
        business.parameters['NearestRetailLocations'] = ['2']

        od_size_before = len(transfer_service_distribution_model.od_trip_checker.od_matrix)
        business.check_supplier_trips_in_od_matrix(transfer_service_distribution_model)
        od_size_after = len(transfer_service_distribution_model.od_trip_checker.od_matrix)

        assert od_size_after >= od_size_before

        # calling again should not add the trip a second time
        business.check_supplier_trips_in_od_matrix(transfer_service_distribution_model)
        assert len(transfer_service_distribution_model.od_trip_checker.od_matrix) == od_size_after

    def test_check_employee_trips_in_od_matrix(self, business, transfer_service_distribution_model, tmp_path):
        import shutil
        original_od_file = transfer_service_distribution_model.od_trip_checker.od_matrix_filename
        temp_od_file = str(tmp_path / 'OD_Matrix_test.csv')
        shutil.copy(original_od_file, temp_od_file)
        transfer_service_distribution_model.od_trip_checker.od_matrix_filename = temp_od_file
        transfer_service_distribution_model.building_to_traffic_node_dict['2'] = 3

        business.home_component.aim_id = '1'
        business.parameters['EmployeeLocations'] = ['2']

        od_size_before = len(transfer_service_distribution_model.od_trip_checker.od_matrix)
        business.check_employee_trips_in_od_matrix(transfer_service_distribution_model)
        od_size_after = len(transfer_service_distribution_model.od_trip_checker.od_matrix)

        assert od_size_after >= od_size_before

        # calling again should not add the trip a second time
        business.check_employee_trips_in_od_matrix(transfer_service_distribution_model)
        assert len(transfer_service_distribution_model.od_trip_checker.od_matrix) == od_size_after

    def test_update_access_to_suppliers(self, business, transfer_service_distribution_model):
        transfer_service_distribution_model.building_to_traffic_node_dict['2'] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]

        business.home_component.aim_id = '1'
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        supplier_node = transfer_service_distribution_model.building_to_traffic_node_dict['2']
        business.parameters['NearestRetailLocations'] = ['2']

        # supplier accessible
        business.update(time_step=1)
        make_travel_setup(transfer_service_distribution_model, [(business_node, supplier_node, 1000.0, 1.0)])
        business.update_access_to_suppliers(1, [transfer_service_distribution_model])
        assert business.business_functionality_level == 1.0

        # supplier inaccessible
        business.update(time_step=2)
        make_travel_setup(transfer_service_distribution_model, [(business_node, supplier_node, 20000.0, 5.0)])
        business.update_access_to_suppliers(2, [transfer_service_distribution_model])
        assert business.business_functionality_level == 0.0
        assert {'Name': 'LocalSuppliers', 'Level': 0} in business.reason_for_drop[2]

    def test_traffic_model_check_accessibility(self, transfer_service_distribution_model):
        # check_accessibility moved from Business onto the transfer-service models.
        tsm = transfer_service_distribution_model
        travel_times = pd.DataFrame([
            {'agent_id': 1.0, 'origin_nid': 10, 'destin_nid': 20, 'travel_time_used': 1000.0},
            {'agent_id': 2.0, 'origin_nid': 30, 'destin_nid': 40, 'travel_time_used': 20000.0},
        ])
        trip_index = {(10, 20): 0, (30, 40): 1}
        change_index_ok = {1.0: 1.0, 2.0: 1.0}
        change_index_high = {1.0: 5.0, 2.0: 5.0}

        # accessible: both within cutoffs
        assert tsm.check_accessibility(10, 20, travel_times, trip_index, change_index_ok) == True
        # inaccessible: travel time exceeds cutoff
        assert tsm.check_accessibility(30, 40, travel_times, trip_index, change_index_ok) == False
        # inaccessible: change factor exceeds cutoff
        assert tsm.check_accessibility(10, 20, travel_times, trip_index, change_index_high) == False
        # inaccessible: both exceed cutoffs
        assert tsm.check_accessibility(30, 40, travel_times, trip_index, change_index_high) == False
        # same node: always accessible
        assert tsm.check_accessibility(99, 99, travel_times, trip_index, change_index_ok) == True
        # inaccessible: trip not found
        assert tsm.check_accessibility(99, 100, travel_times, trip_index, change_index_ok) == False

    def test_traffic_model_check_accessibility_uses_agent_id_not_row_index(self, transfer_service_distribution_model):
        # Regression test: travel_time_change must be looked up by agent_id, not row index.
        tsm = transfer_service_distribution_model
        travel_times = pd.DataFrame([
            {'agent_id': 1.0, 'origin_nid': 10, 'destin_nid': 20, 'travel_time_used': 500.0},  # trip A at row 0
            {'agent_id': 2.0, 'origin_nid': 30, 'destin_nid': 40, 'travel_time_used': 500.0},  # trip B at row 1
        ])
        trip_index = {(10, 20): 0, (30, 40): 1}
        # change index has trip B's high factor for agent 2, trip A's ok factor for agent 1
        change_index_misaligned = {2.0: 5.0, 1.0: 1.0}

        # trip A: correct factor is 1.0 (agent_id=1) -> accessible
        assert tsm.check_accessibility(10, 20, travel_times, trip_index, change_index_misaligned) == True
        # trip B: correct factor is 5.0 (agent_id=2) -> inaccessible
        assert tsm.check_accessibility(30, 40, travel_times, trip_index, change_index_misaligned) == False

    def test_update_current_business_functionality(self, business):
        business.update(time_step=1)
        business.update_current_business_functionality(time_step=1, updated_level=0.4, reason_for_drop='TestReason')
        assert business.business_functionality_level == 0.4
        assert {'Name': 'TestReason', 'Level': 0.4} in business.reason_for_drop[1]
        assert business.revenue[1] == pytest.approx(400/52)
        # adding a higher-level reason records the row but does not raise functionality
        # (business_functionality_level is the min across all reasons).
        business.update_current_business_functionality(time_step=1, updated_level=0.9, reason_for_drop='AnotherReason')
        assert business.business_functionality_level == 0.4
        assert {'Name': 'AnotherReason', 'Level': 0.9} in business.reason_for_drop[1]
        # a Level=1.0 reason is recorded too (every contributing reason gets a row);
        # it just doesn't lower the min, so functionality stays at 0.4.
        business.update_current_business_functionality(time_step=1, updated_level=1.0, reason_for_drop='NoDropReason')
        assert {'Name': 'NoDropReason', 'Level': 1.0} in business.reason_for_drop[1]
        assert business.business_functionality_level == 0.4

    def test_update_functionality_based_on_unmet_demand(self, business):
        business.update(time_step=1)
        business.update_functionality_based_on_unmet_demand(time_step=1, percent_of_met_demand=0.6)
        assert business.business_functionality_level == 0.6
        assert {'Name': 'Infrastructure', 'Level': 0.6} in business.reason_for_drop[1]
        # a higher value should not increase functionality
        business.update_functionality_based_on_unmet_demand(time_step=1, percent_of_met_demand=0.8)
        assert business.business_functionality_level == 0.6

    def test_update_revenue(self, business):
        business.update(time_step=1)
        assert business.revenue[1] == 1000/52
        business.business_functionality_level = 0.5
        business.update_revenue(time_step=2)
        assert business.revenue[2] == 500/52
        # update_revenue now overwrites with pre_disaster_revenue_per_time_step * current
        # business_functionality_level (no min-ratcheting), so calling it again at the
        # same time step with a higher functionality reflects the higher value.
        business.business_functionality_level = 1.0
        business.update_revenue(time_step=2)
        assert business.revenue[2] == 1000/52

    def test_recover(self, business):
        business.recover(time_step=1)
        assert business.business_functionality_level == 1.0
        assert business.revenue == {}

    def test_update_customer_base(self, business):
        customer_base_population_ratios = {
            "060014272001": 0.5,
            "060014280001": 0.3,
        }
        # no OutsideIslandCustomerBuildings and no traffic model: Others always counted
        business.update(time_step=1)
        business.update_customer_base(time_step=1, customer_base_population_ratios=customer_base_population_ratios)
        assert business.business_functionality_level == pytest.approx(0.52)  # 0.4*0.5 + 0.4*0.3 + 0.2
        # business.update first records the Home Component Functionality reason at the
        # building's default 1.0, then update_customer_base appends the Customer Base row.
        assert business.reason_for_drop == {1: [
            {'Name': 'Home Component Functionality', 'Level': 1.0},
            {'Name': 'Customer Base', 'Level': pytest.approx(0.52)},
        ]}
        assert business.revenue[1] == pytest.approx(520 / 52)

    # Customer accessibility is decided per visitor CBG: on-island CBGs (those in a locality) can
    # always reach the business, so they are never gated. Every other CBG - the externally
    # simulated ones plus the pooled 'Others' block - is off-island and gated on a functional
    # crossing from any mainland connector to the business, which the island model answers via the
    # off-island proxy origin. These tests stub that model.
    ON_ISLAND_CBGS = {"060014272001", "060014280001"}

    def test_update_customer_base_island_reachable_counts_others(self, business):
        customer_base_population_ratios = {"060014272001": 0.5, "060014280001": 0.3}
        business.update(time_step=1)
        business.update_customer_base(time_step=1,
                                      customer_base_population_ratios=customer_base_population_ratios,
                                      transfer_service_models=[_IslandStub(reachable=True)],
                                      on_island_cbgs=self.ON_ISLAND_CBGS,
                                      off_island_origin_id=OFF_ISLAND_ORIGIN)
        assert business.business_functionality_level == pytest.approx(0.52)  # 0.4*0.5 + 0.4*0.3 + 0.2

    def test_update_customer_base_island_unreachable_excludes_others(self, business):
        customer_base_population_ratios = {"060014272001": 0.5, "060014280001": 0.3}
        business.update(time_step=1)
        business.update_customer_base(time_step=1,
                                      customer_base_population_ratios=customer_base_population_ratios,
                                      transfer_service_models=[_IslandStub(reachable=False)],
                                      on_island_cbgs=self.ON_ISLAND_CBGS,
                                      off_island_origin_id=OFF_ISLAND_ORIGIN)
        assert business.business_functionality_level == pytest.approx(0.32)  # Others (off-island) excluded
        assert any(r['Name'] == 'Customer Base' for r in business.reason_for_drop[1])

    def test_update_customer_base_no_island_model_counts_others(self, business):
        # No accessibility model and no off-island proxy -> nothing is gated, everything counted.
        customer_base_population_ratios = {"060014272001": 0.5, "060014280001": 0.3}
        business.update(time_step=1)
        business.update_customer_base(time_step=1,
                                      customer_base_population_ratios=customer_base_population_ratios,
                                      transfer_service_models=None)
        assert business.business_functionality_level == pytest.approx(0.52)

    def test_update_customer_base_off_island_cbg_gated_when_unreachable(self, business):
        # A named CBG that is NOT on-island is off-island and is zeroed when the island is cut off,
        # on top of Others. On-island CBGs are always counted.
        customer_base_population_ratios = {"060014272001": 0.5, "060014280001": 0.3}
        business.update(time_step=1)
        business.update_customer_base(time_step=1,
                                      customer_base_population_ratios=customer_base_population_ratios,
                                      transfer_service_models=[_IslandStub(reachable=False)],
                                      on_island_cbgs={"060014272001"},  # 280001 is off-island
                                      off_island_origin_id=OFF_ISLAND_ORIGIN)
        # 0.4*0.5 (on-island CBG) + 0 (off-island CBG cut off) + 0 (Others cut off)
        assert business.business_functionality_level == pytest.approx(0.20)

    def test_update_customer_base_off_island_cbg_counted_when_reachable(self, business):
        customer_base_population_ratios = {"060014272001": 0.5, "060014280001": 0.3}
        business.update(time_step=1)
        business.update_customer_base(time_step=1,
                                      customer_base_population_ratios=customer_base_population_ratios,
                                      transfer_service_models=[_IslandStub(reachable=True)],
                                      on_island_cbgs={"060014272001"},  # 280001 is off-island
                                      off_island_origin_id=OFF_ISLAND_ORIGIN)
        assert business.business_functionality_level == pytest.approx(0.52)


class _StubResource:
    """Minimal resource stub exposing just the `current_amount` attribute used by the
    Business <-> home_component employee supply/demand accumulators."""
    def __init__(self, current_amount: float = 0.0):
        self.current_amount = float(current_amount)


class _AlwaysAccessible:
    """Transfer-service stub whose buildings are always reachable, isolating the
    residual-supply logic in check_employees from accessibility concerns."""
    def is_building_accessible(self, time_step, origin_building_id, destination_building_id):
        return True


class TestBusinessEmployeeRedistribution:
    """
    Unit tests for the methods added on Business to expose employees as a regular
    resource that can flow through ResidualEmployeeDistributionModel:
        is_blocked_from_operating, is_short_on_labor_but_can_operate,
        get_assigned_employees, check_employees (residual supply on homes),
        update_employee_demand, apply_received_employees.
    """

    @pytest.fixture
    def home_component(self):
        component = R2DBuildingWithBusiness()
        component.aim_id = '5'
        # Inject the Employee supply/demand resource slots that the component library
        # normally creates for a R2DBuildingWithBusiness.
        component.supply['Supply']['Employee'] = _StubResource()
        component.demand['OperationDemand']['Employee'] = _StubResource()
        return component

    @pytest.fixture
    def business(self, home_component):
        return Business(BUSINESS_ID, BUSINESS_PARAMETERS, home_component)

    # ---- is_blocked_from_operating -----------------------------------------

    def test_is_blocked_from_operating_true_for_each_blocker(self, business):
        # Each of the three blockers below 1.0 individually triggers True.
        for blocker_name in ('Home Component Functionality', 'Infrastructure', 'LocalSuppliers'):
            business.reason_for_drop = {1: [{'Name': blocker_name, 'Level': 0.0}]}
            assert business.is_blocked_from_operating(1), f'{blocker_name} should block operation'

    def test_is_blocked_from_operating_false_when_only_labor_drop(self, business):
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.4}]}
        assert business.is_blocked_from_operating(1) is False

    def test_is_blocked_from_operating_false_when_only_customer_base_drop(self, business):
        # Customer Base is intentionally excluded from the blocker set: low customer
        # base still requires employees to serve remaining customers.
        business.reason_for_drop = {1: [{'Name': 'Customer Base', 'Level': 0.2}]}
        assert business.is_blocked_from_operating(1) is False

    def test_is_blocked_from_operating_false_when_blocker_at_full_level(self, business):
        # A blocker present in reason_for_drop with Level == 1.0 is no real drop.
        business.reason_for_drop = {1: [{'Name': 'Infrastructure', 'Level': 1.0}]}
        assert business.is_blocked_from_operating(1) is False

    def test_is_blocked_from_operating_false_when_missing_time_step(self, business):
        # Pre-disaster step has no reasons yet; method must not raise.
        business.reason_for_drop = {}
        assert business.is_blocked_from_operating(-1) is False

    # ---- is_short_on_labor_but_can_operate ---------------------------------

    def test_short_on_labor_but_can_operate_true(self, business):
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5}]}
        assert business.is_short_on_labor_but_can_operate(1) is True

    def test_short_on_labor_but_can_operate_true_with_reduced_customer_base(self, business):
        # Reduced customer base does NOT disqualify a recipient: the business can still
        # operate and still needs its full workforce to serve remaining customers.
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5},
                                        {'Name': 'Customer Base', 'Level': 0.3}]}
        assert business.is_short_on_labor_but_can_operate(1) is True

    def test_short_on_labor_but_can_operate_false_when_blocked(self, business):
        # A hard blocker (here Infrastructure) means extra employees cannot help.
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5},
                                        {'Name': 'Infrastructure', 'Level': 0.6}]}
        assert business.is_short_on_labor_but_can_operate(1) is False

    def test_short_on_labor_but_can_operate_false_when_not_short_on_labor(self, business):
        business.reason_for_drop = {1: [{'Name': 'Customer Base', 'Level': 0.5}]}
        assert business.is_short_on_labor_but_can_operate(1) is False

    def test_short_on_labor_but_can_operate_false_when_no_drops(self, business):
        business.reason_for_drop = {1: []}
        assert business.is_short_on_labor_but_can_operate(1) is False

    # ---- get_assigned_employees --------------------------------------------

    def test_get_assigned_employees_floors_to_int(self, business):
        # NumEmployees=2 from BUSINESS_PARAMETERS; 0.4 * 2 = 0.8 -> 0 (int floor).
        business.employees_available = {1: 0.4}
        assert business.get_assigned_employees(1) == 0

    def test_get_assigned_employees_full(self, business):
        business.employees_available = {1: 1.0}
        assert business.get_assigned_employees(1) == business.parameters['NumEmployees']

    def test_get_assigned_employees_missing_step_defaults_full(self, business):
        # Pre-disaster: no entry -> treat as fully staffed (the conservative default).
        business.employees_available = {}
        assert business.get_assigned_employees(99) == business.parameters['NumEmployees']

    # ---- residual supply on employee homes (check_employees) ---------------
    # Supply originates at the employee HOME buildings, never at the business
    # building. A business that cannot operate frees its still-reachable employees,
    # which are registered as Employee supply on their homes (one per functional,
    # accessible home) so they can be reassigned to other businesses.

    def _make_home(self, aim_id, functionality_level=1.0):
        home = R2DBuilding()
        home.aim_id = aim_id
        home.functionality_level = functionality_level
        home.supply['Supply']['Employee'] = _StubResource()
        return home

    def test_check_employees_credits_homes_when_blocked(self, business):
        # Blocked at t-1 (=1) via Infrastructure -> each functional+accessible home
        # supplies one residual employee at t (=2). Business building is untouched.
        home1, home2 = self._make_home('h1'), self._make_home('h2')
        business.employee_homes = [home1, home2]
        business.parameters['NumEmployees'] = 2
        business.reason_for_drop = {1: [{'Name': 'Infrastructure', 'Level': 0.0}], 2: []}
        business.check_employees(time_step=2, transfer_service_models=[_AlwaysAccessible()])
        assert home1.supply['Supply']['Employee'].current_amount == 1
        assert home2.supply['Supply']['Employee'].current_amount == 1
        # Business building never supplies employees.
        assert business.home_component.supply['Supply']['Employee'].current_amount == 0

    def test_check_employees_no_home_supply_when_only_short_on_labor(self, business):
        # Not blocked (only Labor at t-1): the business keeps its workers, so its
        # homes contribute no residual supply.
        home1 = self._make_home('h1')
        business.employee_homes = [home1]
        business.parameters['NumEmployees'] = 1
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5}], 2: []}
        business.check_employees(time_step=2, transfer_service_models=[_AlwaysAccessible()])
        assert home1.supply['Supply']['Employee'].current_amount == 0

    def test_check_employees_only_functional_homes_supply(self, business):
        # A damaged home neither counts toward availability nor supplies a residual
        # employee, even when the business is blocked.
        home_ok, home_down = self._make_home('ok', 1.0), self._make_home('down', 0.5)
        business.employee_homes = [home_ok, home_down]
        business.parameters['NumEmployees'] = 2
        business.reason_for_drop = {1: [{'Name': 'Home Component Functionality', 'Level': 0.0}], 2: []}
        business.check_employees(time_step=2, transfer_service_models=[_AlwaysAccessible()])
        assert home_ok.supply['Supply']['Employee'].current_amount == 1
        assert home_down.supply['Supply']['Employee'].current_amount == 0

    # ---- update_employee_demand --------------------------------------------

    def test_update_employee_demand_when_labor_only(self, business, home_component):
        # Labor-only at t-1; NumEmployees=2; assigned=1 -> demand = 2 - 1 = 1.
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5}]}
        business.employees_available = {1: 0.5}
        business.update_employee_demand(time_step=2)
        assert home_component.demand['OperationDemand']['Employee'].current_amount == 1

    def test_update_employee_demand_with_reduced_customer_base(self, business, home_component):
        # Labor + Customer Base (no hard blocker): the business can still operate, so
        # it still demands its labor shortfall. NumEmployees=2; assigned=1 -> demand 1.
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5},
                                        {'Name': 'Customer Base', 'Level': 0.3}]}
        business.employees_available = {1: 0.5}
        business.update_employee_demand(time_step=2)
        assert home_component.demand['OperationDemand']['Employee'].current_amount == 1

    def test_update_employee_demand_zero_when_blocked(self, business, home_component):
        # Labor + a hard blocker (Infrastructure) -> no demand: the business cannot
        # operate, so extra employees would not help.
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5},
                                        {'Name': 'Infrastructure', 'Level': 0.5}]}
        business.employees_available = {1: 0.5}
        business.update_employee_demand(time_step=2)
        assert home_component.demand['OperationDemand']['Employee'].current_amount == 0

    def test_update_employee_demand_zero_when_fully_staffed(self, business, home_component):
        # No labor drop and no other drop -> demand 0.
        business.reason_for_drop = {1: []}
        business.employees_available = {1: 1.0}
        business.update_employee_demand(time_step=2)
        assert home_component.demand['OperationDemand']['Employee'].current_amount == 0

    # ---- apply_received_employees ------------------------------------------

    def test_apply_received_employees_bumps_labor(self, business):
        # NumEmployees=2; pre-redistribute employees_available=0.5 -> assigned=1.
        # Add 1 employee -> assigned becomes 2 -> employees_available[t]=1.0.
        business.employees_available = {2: 0.5}
        business.update(time_step=2)  # populate reason_for_drop[2]
        business.apply_received_employees(time_step=2, n_extra=1)
        assert business.employees_available[2] == 1.0

    def test_apply_received_employees_capped_at_num_employees(self, business):
        # Receiving more employees than NumEmployees must cap the ratio at 1.0.
        business.employees_available = {2: 0.5}
        business.update(time_step=2)
        business.apply_received_employees(time_step=2, n_extra=100)
        assert business.employees_available[2] == 1.0

    def test_apply_received_employees_noop_when_zero(self, business):
        # n_extra <= 0 must not mutate state.
        business.employees_available = {2: 0.5}
        original_reasons = {2: []}
        business.reason_for_drop = {2: list(original_reasons[2])}
        business.apply_received_employees(time_step=2, n_extra=0)
        assert business.employees_available[2] == 0.5
        assert business.reason_for_drop == {2: []}

    def test_apply_received_employees_updates_labor_reason_only_below_one(self, business):
        # Fractional bump to 0.75 -> reason_for_drop should include Labor at 0.75.
        business.employees_available = {2: 0.5}  # NumEmployees=2 -> assigned=1
        business.update(time_step=2)
        # Manually add a Labor reason at 0.5 as check_employees would have done.
        business.update_current_business_functionality(2, 0.5, 'Labor')
        business.apply_received_employees(time_step=2, n_extra=0.5)  # 1 + 0.5 = 1.5 -> ratio 0.75
        assert business.employees_available[2] == 0.75
        # Latest Labor entry recorded by apply_received_employees should be 0.75.
        labor_levels = [r['Level'] for r in business.reason_for_drop[2] if r['Name'] == 'Labor']
        assert 0.75 in labor_levels

    # ---- update() integration: demand updater wired in ---------------------

    def test_update_wires_demand_not_building_supply(self, business, home_component):
        # At step 2, business.update reads reason_for_drop[1] and writes only the
        # Employee DEMAND on the business building. Supply never lives on the business
        # building - it is registered on the employee homes in check_employees.
        # Labor-only at t-1 (=1): NumEmployees=2, assigned=1 -> demand = 1.
        business.reason_for_drop = {1: [{'Name': 'Labor', 'Level': 0.5}]}
        business.employees_available = {1: 0.5}
        home_component.functionality_level = 1.0
        business.update(time_step=2)
        assert home_component.demand['OperationDemand']['Employee'].current_amount == 1
        # The business building supplies no employees.
        assert home_component.supply['Supply']['Employee'].current_amount == 0
