import pytest
from pyrecodes.business.business import Business
from tests.test_business.test_business_inputs import BUSINESS_ID, BUSINESS_PARAMETERS
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness, R2DBuilding

class TestBusiness:

    @pytest.fixture
    def home_component(self):
        component = R2DBuildingWithBusiness()
        component.aim_id = '5'
        return component
    
    @pytest.fixture
    def business(self, home_component):
        return Business(BUSINESS_ID, BUSINESS_PARAMETERS, home_component)

    def test_init(self, business):
        assert business.employees_available == {}
        assert business.customer_base_ratio == []
        assert business.input_commodity_available_ratio == 1.0
        assert business.reason_for_drop == {}
        assert business.business_functionality_level == 1.0
        assert business.revenue == {0: 1000/365}
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

    def test_update_customer_base(self, business):
        customer_base_population_ratios = {
            "060014272001": 0.5,
            "060014280001": 0.3,
        }
        business.update(time_step=1)
        business.update_customer_base(time_step=1, customer_base_population_ratios=customer_base_population_ratios)
        assert business.business_functionality_level == 0.52  # 0.4*0.5 + 0.4*0.3 + 0.2 = 0.2 + 0.12 + 0.2 = 0.52
        assert business.reason_for_drop == {1:[{'Name': 'Customer Base', 'Level': 0.52}]}
        assert business.revenue[1] == 520/365


