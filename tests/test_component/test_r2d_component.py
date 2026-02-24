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
        assert business.reason_for_drop == {1: [{'Name': 'Infrastructure', 'Level': 0.75}]}
