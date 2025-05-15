from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.concrete_resource_distribution_model_constructor import ConcreteResourceDistributionModelConstructor
from pyrecodes.resource_distribution_model.resource_distribution_model import ResourceDistributionModel
from pyrecodes.resource_distribution_model.single_resource_system_matrix_creator import SingleResourceSystemMatrixCreator
from pyrecodes.component.component import Component
from pyrecodes.component.standard_irecodes_component import StandardiReCoDeSComponent
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness
from pyrecodes.component.component import SupplyOrDemand
import json
import math
import numpy as np
import itertools

class EmployeeDistributionModel(AbstractResourceDistributionModel):
    """
    | Class to distribute resources in the system. This is the simplest distribution model, which distributes resources based on the priority of the components.
    | Resource distribution is done using the system matrix, containing the supply and demand of each component.
    | No physical laws (e.g., power flow or water flow physics) are considered in the distribution of resources.
    """
    components: list[Component]
    resource_name: str
    transfer_service_distribution_model: ResourceDistributionModel

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = ConcreteResourceDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        self.transfer_service_distribution_model = None

    def distribute(self, time_step: int) -> None:
        if self.distribute_at_this_time_step(time_step):
            for component in self.components:
                if isinstance(component, R2DBuildingWithBusiness):
                    for business in component.businesses:
                        business.set_employee_homes(self.components)
                        business.check_employees(time_step)
                                    
    
    def get_total_supply(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_supply = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    total_supply += business.get_employee_supply()
        return total_supply

    def get_total_demand(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_demand = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    total_demand += business.get_employee_demand()
        return total_demand

    def get_total_consumption(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_consumption = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    total_consumption += business.get_employee_consumption()
        return total_consumption


