from pyrecodes.component.r2d_component import R2DComponent
from pyrecodes.resource_distribution_model.concrete_resource_distribution_model_constructor import ConcreteResourceDistributionModelConstructor


class IslandConnectivityDistributionModelConstructor(ConcreteResourceDistributionModelConstructor):

    def construct(self, resource_name: str, resource_parameters: dict, components: list, distribution_model):
        super().construct(resource_name, resource_parameters, components, distribution_model)
        distribution_model.mainland_connectors = self.find_mainland_connectors(components)
        distribution_model.outside_island_building_ids = self.find_outside_island_building_ids(components)

    def find_mainland_connectors(self, components: list) -> list:
        return [
            c for c in components
            if isinstance(c, R2DComponent) and c.general_information.get('MainlandConnector', False)
        ]

    def find_outside_island_building_ids(self, components: list) -> set:
        return {
            c.aim_id for c in components
            if isinstance(c, R2DComponent) and c.general_information.get('OutsideIsland', False)
        }
