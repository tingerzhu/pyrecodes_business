import pytest
from pyrecodes import main
from pyrecodes.utilities import read_json_file
from pyrecodes.resource_distribution_model.employee_distribution_model import EmployeeDistributionModel

MAIN_FILE = './tests/test_inputs/test_inputs_Alameda_Main.json'
RESOURCE_NAME = 'Employee'
RESOURCE_PARAMETERS = {}

class TestEmployeeDistributionModel:

    @pytest.fixture
    def system(self):
        input_dict = read_json_file(MAIN_FILE)
        return main.create_system(input_dict)
    
    @pytest.fixture
    def employee_distribution_model(self, system):
        return EmployeeDistributionModel(RESOURCE_NAME, RESOURCE_PARAMETERS, system.components)
    
    def test_init(self, employee_distribution_model, system):
        assert employee_distribution_model.resource_name == RESOURCE_NAME
        assert employee_distribution_model.distribution_time_steps == []
        assert len(employee_distribution_model.components) == len(system.components)