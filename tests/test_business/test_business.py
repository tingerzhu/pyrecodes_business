import pytest
import pandas as pd
from pyrecodes import main
from pyrecodes.utilities import read_json_file
from pyrecodes.business.business import Business
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
    tsm.trip_index = trip_index
    tsm.travel_time_change_index = [change_index]
    tsm.travel_time_change_factors = [change_factors]
    tsm.od_trip_checker.isolated_nodes = set()


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

    def test_get_latest_travel_times(self, business, transfer_service_distribution_model):
        mock_tt_0 = pd.DataFrame([{'agent_id': 1.0, 'origin_nid': 1, 'destin_nid': 2, 'travel_time_used': 500.0}])
        mock_tt_2 = pd.DataFrame([{'agent_id': 1.0, 'origin_nid': 1, 'destin_nid': 2, 'travel_time_used': 900.0}])
        mock_ttci_0 = {1.0: 1.0}
        mock_ttci_2 = {1.0: 2.0}
        transfer_service_distribution_model.distribution_time_steps = [0, 2]
        transfer_service_distribution_model.travel_times = [mock_tt_0, [], mock_tt_2]
        transfer_service_distribution_model.travel_time_change_index = [mock_ttci_0, {}, mock_ttci_2]
        transfer_service_distribution_model.trip_index = {(1, 2): 0}

        travel_times, trip_index, change_index = business.get_latest_travel_times(transfer_service_distribution_model, time_step=3)
        assert travel_times.equals(mock_tt_2)
        assert trip_index == {(1, 2): 0}
        assert change_index == mock_ttci_2

    def test_init(self, business):
        assert business.employees_available == {}
        assert business.customer_base_ratio == {}
        assert business.input_commodity_available_ratio == 1.0
        assert business.reason_for_drop == {}
        assert business.business_functionality_level == 1.0
        assert business.revenue == {}
        assert business.pre_disaster_daily_revenue == pytest.approx(1000 / 365)
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
        home_component.functionality_level = 1.0
        business.update(time_step=1)
        assert business.business_functionality_level == 1.0
        assert business.reason_for_drop == {1:[]}
        assert business.revenue[1] == 1000/365
        home_component.functionality_level = 0.5
        business.update(time_step=2)
        assert business.business_functionality_level == 0.5
        assert business.reason_for_drop == {1:[], 2:[{'Name': 'Home Component Functionality', 'Level': 0.5}]}
        assert business.revenue[2] == 500/365
        home_component.functionality_level = 0.8
        business.update(time_step=3)
        assert business.business_functionality_level == 0.8
        assert business.reason_for_drop == {1:[], 2:[{'Name': 'Home Component Functionality', 'Level': 0.5}], 3:[{'Name': 'Home Component Functionality', 'Level': 0.8}]}
        assert business.revenue[3] == 800/365

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
        business.check_employees(time_step=1, traffic_flow_model=transfer_service_distribution_model)
        assert business.employees_available[1] == 1.0
        assert business.business_functionality_level == 1.0

        # employees not available: travel time and change factor exceed cutoffs
        business.update(time_step=2)
        make_travel_setup(transfer_service_distribution_model, [(business_node, employee_node, 20000.0, 5.0)])
        business.check_employees(time_step=2, traffic_flow_model=transfer_service_distribution_model)
        assert business.employees_available[2] == 0.0
        assert business.business_functionality_level == 0.0

        # employees not available: home not functional
        business.update(time_step=3)
        employee_home.functionality_level = 0.5
        make_travel_setup(transfer_service_distribution_model, [(business_node, employee_node, 1000.0, 1.0)])
        business.check_employees(time_step=3, traffic_flow_model=transfer_service_distribution_model)
        assert business.employees_available[3] == 0.0
        assert business.business_functionality_level == 0.0

    def test_is_building_accessible(self, business, transfer_service_distribution_model):
        transfer_service_distribution_model.building_to_traffic_node_dict['2'] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]

        business.home_component.aim_id = '1'
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        other_node = transfer_service_distribution_model.building_to_traffic_node_dict['2']

        # accessible: travel time and change factor within cutoffs
        make_travel_setup(transfer_service_distribution_model, [(business_node, other_node, 1000.0, 1.0)])
        assert business.is_building_accessible(0, transfer_service_distribution_model, '1', '2') == True

        # inaccessible: both travel time and change factor exceed cutoffs
        make_travel_setup(transfer_service_distribution_model, [(business_node, other_node, 20000.0, 5.0)])
        assert business.is_building_accessible(0, transfer_service_distribution_model, '1', '2') == False

        # same building: always accessible regardless of travel times
        assert business.is_building_accessible(0, transfer_service_distribution_model, '1', '1') == True

        # unknown building not in node dict: not accessible
        assert business.is_building_accessible(0, transfer_service_distribution_model, '1', 'unknown') == False

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
        business.update_access_to_suppliers(1, transfer_service_distribution_model)
        assert business.business_functionality_level == 1.0

        # supplier inaccessible
        business.update(time_step=2)
        make_travel_setup(transfer_service_distribution_model, [(business_node, supplier_node, 20000.0, 5.0)])
        business.update_access_to_suppliers(2, transfer_service_distribution_model)
        assert business.business_functionality_level == 0.0
        assert {'Name': 'LocalSuppliers', 'Level': 0} in business.reason_for_drop[2]

    def test_check_accessibility(self, business):
        travel_times = pd.DataFrame([
            {'agent_id': 1.0, 'origin_nid': 10, 'destin_nid': 20, 'travel_time_used': 1000.0},
            {'agent_id': 2.0, 'origin_nid': 30, 'destin_nid': 40, 'travel_time_used': 20000.0},
        ])
        trip_index = {(10, 20): 0, (30, 40): 1}
        change_index_ok = {1.0: 1.0, 2.0: 1.0}
        change_index_high = {1.0: 5.0, 2.0: 5.0}

        # accessible: both within cutoffs
        assert business.check_accessibility(10, 20, travel_times, trip_index, change_index_ok) == True
        # inaccessible: travel time exceeds cutoff
        assert business.check_accessibility(30, 40, travel_times, trip_index, change_index_ok) == False
        # inaccessible: change factor exceeds cutoff
        assert business.check_accessibility(10, 20, travel_times, trip_index, change_index_high) == False
        # inaccessible: both exceed cutoffs
        assert business.check_accessibility(30, 40, travel_times, trip_index, change_index_high) == False
        # same node: always accessible
        assert business.check_accessibility(99, 99, travel_times, trip_index, change_index_ok) == True
        # inaccessible: trip not found
        assert business.check_accessibility(99, 100, travel_times, trip_index, change_index_ok) == False

    def test_check_accessibility_uses_agent_id_not_row_index(self, business):
        # Regression test: travel_time_change must be looked up by agent_id, not row index.
        travel_times = pd.DataFrame([
            {'agent_id': 1.0, 'origin_nid': 10, 'destin_nid': 20, 'travel_time_used': 500.0},  # trip A at row 0
            {'agent_id': 2.0, 'origin_nid': 30, 'destin_nid': 40, 'travel_time_used': 500.0},  # trip B at row 1
        ])
        trip_index = {(10, 20): 0, (30, 40): 1}
        # change index has trip B's high factor for agent 2, trip A's ok factor for agent 1
        change_index_misaligned = {2.0: 5.0, 1.0: 1.0}

        # trip A: correct factor is 1.0 (agent_id=1) -> accessible
        assert business.check_accessibility(10, 20, travel_times, trip_index, change_index_misaligned) == True
        # trip B: correct factor is 5.0 (agent_id=2) -> inaccessible
        assert business.check_accessibility(30, 40, travel_times, trip_index, change_index_misaligned) == False

    def test_update_current_business_functionality(self, business):
        business.update(time_step=1)
        business.update_current_business_functionality(time_step=1, updated_level=0.4, reason_for_drop='TestReason')
        assert business.business_functionality_level == 0.4
        assert {'Name': 'TestReason', 'Level': 0.4} in business.reason_for_drop[1]
        assert business.revenue[1] == pytest.approx(400/365)
        # higher level does not raise functionality
        business.update_current_business_functionality(time_step=1, updated_level=0.9, reason_for_drop='AnotherReason')
        assert business.business_functionality_level == 0.4
        # level of 1.0 does not add to reason_for_drop
        business.update_current_business_functionality(time_step=1, updated_level=1.0, reason_for_drop='NoDropReason')
        assert not any(r['Name'] == 'NoDropReason' for r in business.reason_for_drop[1])

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
        assert business.revenue[1] == 1000/365
        business.business_functionality_level = 0.5
        business.update_revenue(time_step=2)
        assert business.revenue[2] == 500/365
        # calling again at same time step with higher functionality should keep the minimum
        business.business_functionality_level = 1.0
        business.update_revenue(time_step=2)
        assert business.revenue[2] == 500/365

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
        assert business.reason_for_drop == {1: [{'Name': 'Customer Base', 'Level': pytest.approx(0.52)}]}
        assert business.revenue[1] == pytest.approx(520 / 365)

    def test_update_customer_base_outside_island_accessible(self, business, transfer_service_distribution_model):
        outside_id = '99001'
        business.parameters['OutsideIslandCustomerBuildings'] = [outside_id]
        transfer_service_distribution_model.building_to_traffic_node_dict[outside_id] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]
        business.home_component.aim_id = '1'
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        outside_node = transfer_service_distribution_model.building_to_traffic_node_dict[outside_id]
        make_travel_setup(transfer_service_distribution_model, [(business_node, outside_node, 1000.0, 1.0)])

        customer_base_population_ratios = {"060014272001": 0.5, "060014280001": 0.3}
        business.update(time_step=1)
        business.update_customer_base(time_step=1,
                                      customer_base_population_ratios=customer_base_population_ratios,
                                      transfer_service_distribution_model=transfer_service_distribution_model)
        assert business.business_functionality_level == pytest.approx(0.52)  # 0.4*0.5 + 0.4*0.3 + 0.2

    def test_update_customer_base_outside_island_inaccessible(self, business, transfer_service_distribution_model):
        outside_id = '99001'
        business.parameters['OutsideIslandCustomerBuildings'] = [outside_id]
        transfer_service_distribution_model.building_to_traffic_node_dict[outside_id] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]
        business.home_component.aim_id = '1'
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        outside_node = transfer_service_distribution_model.building_to_traffic_node_dict[outside_id]
        make_travel_setup(transfer_service_distribution_model, [(business_node, outside_node, 20000.0, 5.0)])

        customer_base_population_ratios = {"060014272001": 0.5, "060014280001": 0.3}
        business.update(time_step=1)
        business.update_customer_base(time_step=1,
                                      customer_base_population_ratios=customer_base_population_ratios,
                                      transfer_service_distribution_model=transfer_service_distribution_model)
        assert business.business_functionality_level == pytest.approx(0.32)  # 0.4*0.5 + 0.4*0.3, Others excluded
        assert any(r['Name'] == 'Customer Base' for r in business.reason_for_drop[1])

    def test_update_customer_base_outside_island_buildings_no_traffic_model(self, business):
        business.parameters['OutsideIslandCustomerBuildings'] = ['99001']
        customer_base_population_ratios = {"060014272001": 0.5, "060014280001": 0.3}
        business.update(time_step=1)
        business.update_customer_base(time_step=1,
                                      customer_base_population_ratios=customer_base_population_ratios,
                                      transfer_service_distribution_model=None)
        assert business.business_functionality_level == pytest.approx(0.52)

    def test_check_outside_island_customer_accessibility_no_buildings_configured(self, business,
                                                                                  transfer_service_distribution_model):
        business.parameters.pop('OutsideIslandCustomerBuildings', None)
        assert business.check_outside_island_customer_accessibility(0, transfer_service_distribution_model) is True

    def test_check_outside_island_customer_accessibility_empty_list(self, business,
                                                                      transfer_service_distribution_model):
        business.parameters['OutsideIslandCustomerBuildings'] = []
        assert business.check_outside_island_customer_accessibility(0, transfer_service_distribution_model) is True

    def test_check_outside_island_customer_accessibility_no_traffic_model(self, business):
        business.parameters['OutsideIslandCustomerBuildings'] = ['99001']
        assert business.check_outside_island_customer_accessibility(0, None) is True

    def test_check_outside_island_customer_accessibility_accessible(self, business,
                                                                      transfer_service_distribution_model):
        outside_id = '99001'
        business.parameters['OutsideIslandCustomerBuildings'] = [outside_id]
        transfer_service_distribution_model.building_to_traffic_node_dict[outside_id] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]
        business.home_component.aim_id = '1'
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        outside_node = transfer_service_distribution_model.building_to_traffic_node_dict[outside_id]
        make_travel_setup(transfer_service_distribution_model, [(business_node, outside_node, 1000.0, 1.0)])
        assert business.check_outside_island_customer_accessibility(0, transfer_service_distribution_model) is True

    def test_check_outside_island_customer_accessibility_inaccessible_travel_time(
            self, business, transfer_service_distribution_model):
        outside_id = '99001'
        business.parameters['OutsideIslandCustomerBuildings'] = [outside_id]
        transfer_service_distribution_model.building_to_traffic_node_dict[outside_id] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]
        business.home_component.aim_id = '1'
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        outside_node = transfer_service_distribution_model.building_to_traffic_node_dict[outside_id]
        make_travel_setup(transfer_service_distribution_model, [(business_node, outside_node, 20000.0, 1.0)])
        assert business.check_outside_island_customer_accessibility(0, transfer_service_distribution_model) is False

    def test_check_outside_island_customer_accessibility_inaccessible_change_factor(
            self, business, transfer_service_distribution_model):
        outside_id = '99001'
        business.parameters['OutsideIslandCustomerBuildings'] = [outside_id]
        transfer_service_distribution_model.building_to_traffic_node_dict[outside_id] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]
        business.home_component.aim_id = '1'
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        outside_node = transfer_service_distribution_model.building_to_traffic_node_dict[outside_id]
        make_travel_setup(transfer_service_distribution_model, [(business_node, outside_node, 1000.0, 5.0)])
        assert business.check_outside_island_customer_accessibility(0, transfer_service_distribution_model) is False

    def test_check_outside_island_customer_accessibility_building_not_in_node_dict(
            self, business, transfer_service_distribution_model):
        business.parameters['OutsideIslandCustomerBuildings'] = ['unknown_id']
        business.home_component.aim_id = '1'
        transfer_service_distribution_model.distribution_time_steps = [0]
        make_travel_setup(transfer_service_distribution_model, [(1, 2, 1000.0, 1.0)])
        assert business.check_outside_island_customer_accessibility(0, transfer_service_distribution_model) is False

    def test_check_outside_island_customer_accessibility_multiple_buildings_one_accessible(
            self, business, transfer_service_distribution_model):
        outside_id_1 = 'unknown_id'
        outside_id_2 = '99001'
        business.parameters['OutsideIslandCustomerBuildings'] = [outside_id_1, outside_id_2]
        transfer_service_distribution_model.building_to_traffic_node_dict[outside_id_2] = 3
        transfer_service_distribution_model.distribution_time_steps = [0]
        business.home_component.aim_id = '1'
        business_node = transfer_service_distribution_model.building_to_traffic_node_dict['1']
        outside_node = transfer_service_distribution_model.building_to_traffic_node_dict[outside_id_2]
        make_travel_setup(transfer_service_distribution_model, [(business_node, outside_node, 1000.0, 1.0)])
        assert business.check_outside_island_customer_accessibility(0, transfer_service_distribution_model) is True

    def test_check_customer_base_outside_island_trips_in_od_matrix(self, business,
                                                                     transfer_service_distribution_model, tmp_path):
        import shutil
        original_od_file = transfer_service_distribution_model.od_trip_checker.od_matrix_filename
        temp_od_file = str(tmp_path / 'OD_Matrix_test.csv')
        shutil.copy(original_od_file, temp_od_file)
        transfer_service_distribution_model.od_trip_checker.od_matrix_filename = temp_od_file

        outside_id = '99001'
        business.parameters['OutsideIslandCustomerBuildings'] = [outside_id]
        transfer_service_distribution_model.building_to_traffic_node_dict[outside_id] = 3
        business.home_component.aim_id = '1'

        od_size_before = len(transfer_service_distribution_model.od_trip_checker.od_matrix)
        business.check_customer_base_outside_island_trips_in_od_matrix(transfer_service_distribution_model)
        od_size_after = len(transfer_service_distribution_model.od_trip_checker.od_matrix)
        assert od_size_after >= od_size_before

        # calling again should not add the trip a second time
        business.check_customer_base_outside_island_trips_in_od_matrix(transfer_service_distribution_model)
        assert len(transfer_service_distribution_model.od_trip_checker.od_matrix) == od_size_after

    def test_check_customer_base_outside_island_trips_in_od_matrix_no_buildings(
            self, business, transfer_service_distribution_model, tmp_path):
        import shutil
        original_od_file = transfer_service_distribution_model.od_trip_checker.od_matrix_filename
        temp_od_file = str(tmp_path / 'OD_Matrix_test.csv')
        shutil.copy(original_od_file, temp_od_file)
        transfer_service_distribution_model.od_trip_checker.od_matrix_filename = temp_od_file
        business.home_component.aim_id = '1'

        od_size_before = len(transfer_service_distribution_model.od_trip_checker.od_matrix)
        business.check_customer_base_outside_island_trips_in_od_matrix(transfer_service_distribution_model)
        assert len(transfer_service_distribution_model.od_trip_checker.od_matrix) == od_size_before

    def test_check_customer_base_outside_island_trips_in_od_matrix_unknown_building(
            self, business, transfer_service_distribution_model, tmp_path):
        import shutil
        original_od_file = transfer_service_distribution_model.od_trip_checker.od_matrix_filename
        temp_od_file = str(tmp_path / 'OD_Matrix_test.csv')
        shutil.copy(original_od_file, temp_od_file)
        transfer_service_distribution_model.od_trip_checker.od_matrix_filename = temp_od_file
        business.parameters['OutsideIslandCustomerBuildings'] = ['nonexistent_id']
        business.home_component.aim_id = '1'

        od_size_before = len(transfer_service_distribution_model.od_trip_checker.od_matrix)
        business.check_customer_base_outside_island_trips_in_od_matrix(transfer_service_distribution_model)
        assert len(transfer_service_distribution_model.od_trip_checker.od_matrix) == od_size_before
