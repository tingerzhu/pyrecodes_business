from pyrecodes.resource_distribution_model.utility_distribution_model_constructor import UtilityDistributionModelConstructor
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness
from pyrecodes.resource_distribution_model.resource_distribution_model import ResourceDistributionModel
from pyrecodes.component.component import Component


class ResidualEmployeeDistributionModelConstructor(UtilityDistributionModelConstructor):
    """
    Constructor for ResidualEmployeeDistributionModel. Reuses the standard utility
    distribution constructor and additionally seeds every business with the list of
    its employee-home components, so the per-business check_employees pass can run.
    """

    def construct(self, resource_name, resource_parameters, components, distribution_model):
        super().construct(resource_name, resource_parameters, components, distribution_model)
        self.set_employee_homes(components)

    def set_components(self, components: list[Component], distribution_model: ResourceDistributionModel) -> None:
        # Override the standard set_components to only include components relevant for the employee distribution model, which are those that can be employee homes (residential buildings) or workplaces (businesses).
        relevant_components = []
        for component in components:
            if component.has_resource_supply('Employee') or isinstance(component, R2DBuildingWithBusiness):
                relevant_components.append(component)
        distribution_model.components = relevant_components

    def set_employee_homes(self, components):
        for component in components:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    business.set_employee_homes(components)
