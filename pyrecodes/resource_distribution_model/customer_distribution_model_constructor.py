from pyrecodes.resource_distribution_model.concrete_resource_distribution_model_constructor import ConcreteResourceDistributionModelConstructor
from pyrecodes.component.r2d_component import R2DBuilding

class CustomerDistributionModelConstructor(ConcreteResourceDistributionModelConstructor):

    def construct(self, resource_name: str, resource_parameters: dict, components: list, distribution_model):
        super().construct(resource_name, resource_parameters, components, distribution_model)
        components_in_blocks = self.map_buildings_to_blocks(components)
        distribution_model.initial_block_population = self.get_initial_block_population(components_in_blocks)
        distribution_model.components_in_blocks = components_in_blocks

    def map_buildings_to_blocks(self, components: list) -> None:
        components_in_blocks = {}
        for component in components:
            if isinstance(component, R2DBuilding):
                component_block = component.general_information['CensusBlockGroup']
                if component_block not in components_in_blocks:
                    components_in_blocks[component_block] = [component]
                else:
                    components_in_blocks[component_block].append(component)   
        return components_in_blocks

    def get_initial_block_population(self, components_in_blocks: dict) -> None:
        initial_block_population = {}
        for block in components_in_blocks.keys():
            population = 0
            for component in components_in_blocks[block]:
                population += component.supply['Supply']['Shelter'].initial_amount
            initial_block_population[block] = population
        return initial_block_population