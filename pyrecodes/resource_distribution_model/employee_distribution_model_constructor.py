from pyrecodes.resource_distribution_model.concrete_resource_distribution_model_constructor import ConcreteResourceDistributionModelConstructor
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness

class EmployeeDistributionModelConstructor(ConcreteResourceDistributionModelConstructor):

    def construct(self, resource_name: str, resource_parameters: dict, components: list, distribution_model):
        super().construct(resource_name, resource_parameters, components, distribution_model)
        self.set_employee_homes(components)

    def set_employee_homes(self, components):
        for component in components:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    business.set_employee_homes(components)