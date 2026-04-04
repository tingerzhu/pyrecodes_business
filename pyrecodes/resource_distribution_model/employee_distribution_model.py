from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.employee_distribution_model_constructor import EmployeeDistributionModelConstructor
from pyrecodes.resource_distribution_model.resource_distribution_model import ResourceDistributionModel
from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model import ResidualDemandTrafficDistributionModel
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness


class EmployeeDistributionModel(AbstractResourceDistributionModel):
  
    components: list[Component]
    resource_name: str
    transfer_service_distribution_models: list[ResourceDistributionModel]

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = EmployeeDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        self.transfer_service_distribution_models = []

    def set_transfer_service_distribution_model(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel) -> None:
        super().set_transfer_service_distribution_model(transfer_service_distribution_model)
        if hasattr(transfer_service_distribution_model, 'od_trip_checker'):
            self.check_employee_trips_in_od_matrix(transfer_service_distribution_model)

    def check_employee_trips_in_od_matrix(self, traffic_model) -> None:
        for component in self.components:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    business.check_employee_trips_in_od_matrix(traffic_model)

    def distribute(self, time_step: int) -> None:
        if self.distribute_at_this_time_step(time_step):
            for component in self.components:
                if isinstance(component, R2DBuildingWithBusiness):
                    for business in component.businesses:
                        business.check_employees(time_step, self.transfer_service_distribution_models)
                                    
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


