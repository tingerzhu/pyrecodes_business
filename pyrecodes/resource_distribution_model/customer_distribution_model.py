from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.customer_distribution_model_constructor import CustomerDistributionModelConstructor
from pyrecodes.resource_distribution_model.resource_distribution_model import ResourceDistributionModel
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness

# Synthetic trip origin shared by all off-island customer CBGs. It is registered as an
# outside-island building id on the transfer-service models so the traffic model abstains
# and the island-connectivity model answers whether those customers can cross to a business.
OFF_ISLAND_ORIGIN_ID = '__off_island_customers__'


class CustomerDistributionModel(AbstractResourceDistributionModel):

    components: list[Component]
    resource_name: str
    transfer_service_distribution_models: list[ResourceDistributionModel]

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = CustomerDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        self.transfer_service_distribution_models = []

    def set_transfer_service_distribution_model(self, transfer_service_distribution_model: ResourceDistributionModel) -> None:
        super().set_transfer_service_distribution_model(transfer_service_distribution_model)
        # Flag the shared off-island origin so the traffic model treats it as outside the
        # island (and abstains) while the island-connectivity model claims it. On-island customers
        # are always considered accessible, so no on-island customer trips are registered here.
        outside_island_building_ids = getattr(transfer_service_distribution_model, 'outside_island_building_ids', None)
        if outside_island_building_ids is not None:
            outside_island_building_ids.add(OFF_ISLAND_ORIGIN_ID)

    def distribute(self, time_step: int) -> None:
        if self.distribute_at_this_time_step(time_step):
            current_block_population_ratios = self.update_customer_base_block_population(time_step)
            self.update_business_customer_base(time_step, current_block_population_ratios)

    def update_customer_base_block_population(self, time_step: int):
        current_block_population_ratios = {}
        for block in self.components_in_blocks.keys():
            current_block_population = 0
            for component in self.components_in_blocks[block]:
                current_block_population += component.supply['Supply']['Shelter'].current_amount
            if self.initial_block_population[block] == 0:
                current_block_population_ratios[block] = 0
            else:
                current_block_population_ratios[block] = current_block_population / self.initial_block_population[block]
        self.add_external_customer_base_recovery(time_step, current_block_population_ratios)
        return current_block_population_ratios

    def add_external_customer_base_recovery(self, time_step: int, current_block_population_ratios: dict) -> None:
        """
        Add the recovery ratio for blocks (CBGs) whose customer-base recovery is simulated
        externally and that have no building components in this model. The ratio is read at
        this time_step, held at the last available value once time_step exceeds the series.
        """
        for block, series in self.external_customer_base_recovery.items():
            capped_time_step = min(time_step, max(series.keys()))
            current_block_population_ratios[block] = series[capped_time_step]

    def update_business_customer_base(self, time_step: int, current_block_population_ratios: dict) -> None:
        # On-island CBGs (those with building components, i.e. in a locality) can always reach the
        # business; every other CBG (externally simulated, plus the pooled 'Others') is off-island
        # and gated on a functional island crossing.
        on_island_cbgs = set(self.components_in_blocks.keys())
        for component in self.components:
            if isinstance(component, R2DBuildingWithBusiness):
                component.update_business_customer_base(time_step, current_block_population_ratios,
                                                        self.transfer_service_distribution_models,
                                                        on_island_cbgs, OFF_ISLAND_ORIGIN_ID)
    
    def get_total_supply(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_supply = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    # TODO: Implement logic to calculate total supply of customers
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


