from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.island_connectivity_distribution_model_constructor import IslandConnectivityDistributionModelConstructor
from pyrecodes.component.component import Component


class IslandConnectivityDistributionModel(AbstractResourceDistributionModel):
    """
    Distribution model that tracks whether an island is connected to the mainland.
    Connected means at least one mainland connector (bridge or tunnel) is functional.
    Components flagged with OutsideIsland in GeneralInformation are considered off-island.
    """

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = IslandConnectivityDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)

    def is_outside_island(self, building_id) -> bool:
        return building_id in self.outside_island_building_ids

    def is_connected(self) -> bool:
        return any(connector.functionality_level > 0 for connector in self.mainland_connectors)

    def is_building_accessible(self, time_step: int, origin_building_id: str, destination_building_id: str):
        if self.is_outside_island(origin_building_id) or self.is_outside_island(destination_building_id):
            return self.is_connected()
        return None

    def distribute(self, time_step: int) -> None:
        pass

    def get_total_supply(self, scope='All') -> float:
        return 0

    def get_total_demand(self, scope='All') -> float:
        return 0

    def get_total_consumption(self, scope='All') -> float:
        return 0
