from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.customer_distribution_model_constructor import CustomerDistributionModelConstructor
from pyrecodes.resource_distribution_model.resource_distribution_model import ResourceDistributionModel
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness

class CustomerDistributionModel(AbstractResourceDistributionModel):

    components: list[Component]
    resource_name: str
    transfer_service_distribution_model: ResourceDistributionModel

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = CustomerDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        self.transfer_service_distribution_model = None

    def distribute(self, time_step: int) -> None:
        if self.distribute_at_this_time_step(time_step):
            current_block_population_ratios = self.update_customer_base_block_population()
            self.update_business_customer_base(time_step, current_block_population_ratios)
    
    def update_customer_base_block_population(self):
        current_block_population_ratios = {}
        for block in self.components_in_blocks.keys():
            current_block_population = 0
            for component in self.components_in_blocks[block]:
                current_block_population += component.supply['Supply']['Shelter'].current_amount
            current_block_population_ratios[block] = current_block_population / self.initial_block_population[block]
        return current_block_population_ratios

    def update_business_customer_base(self, time_step: int, current_block_population_ratios: dict) -> None:
        for component in self.components:
            if isinstance(component, R2DBuildingWithBusiness):
                component.update_business_customer_base(time_step, current_block_population_ratios)                             
    
    def get_total_supply(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_supply = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    # TODO: Implement logic to calculate total supply for customers
                    pass
        return total_supply

    def get_total_demand(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_demand = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    # TODO: Implement logic to calculate total demand for customers
                    pass
        return total_demand

    def get_total_consumption(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_consumption = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    # TODO: Implement logic to calculate total consumption for customers
                    pass
        return total_consumption


