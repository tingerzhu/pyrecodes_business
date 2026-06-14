from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.concrete_resource_distribution_model_constructor import ConcreteResourceDistributionModelConstructor
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBridge, R2DTunnel, R2DRoadway


class BridgeTunnelDistributionModel(AbstractResourceDistributionModel):
    """
    Captures the effect of bridge/tunnel functionality on the road links that sit on them.

    A road link that sits on a bridge or tunnel requires CarrierService to operate, which is
    supplied by the bridge/tunnel carrying it. In distribute(), each such link demands one unit
    of CarrierService and the structure supplies its functionality level; the link's
    functionality is gated by what is met, so a non-functional bridge/tunnel makes its carrier
    road links non-functional too (and the traffic model, distributed next, drops them).

    Carrier road links are the R2DRoadway components flagged RequiresCarrierService in the
    exposure; each bridge/tunnel's RoadID lists the carrier links it carries. This resource is
    placed in the BridgeService group so it is distributed before the transfer services.
    """

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]) -> None:
        self.constructor = ConcreteResourceDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        self.map_carrier_links_to_structures()

    def map_carrier_links_to_structures(self) -> None:
        """Map each bridge/tunnel to the carrier road links it carries, via its RoadID."""
        roads_by_id = {str(c.aim_id): c for c in self.components if isinstance(c, R2DRoadway)}
        self.structure_carrier_links = []  # list of (structure, [carrier road links])
        for component in self.components:
            if isinstance(component, (R2DBridge, R2DTunnel)):
                road_ids = str(component.general_information.get('RoadID', '')).split(',')
                links = [roads_by_id[rid.strip()] for rid in road_ids
                         if rid.strip() in roads_by_id
                         and roads_by_id[rid.strip()].general_information.get('RequiresCarrierService', False)]
                if links:
                    self.structure_carrier_links.append((component, links))

    def distribute(self, time_step: int) -> None:
        if self.distribute_at_this_time_step(time_step):
            for structure, links in self.structure_carrier_links:
                carrier_supply = structure.functionality_level   # CarrierService supplied by the structure
                for link in links:
                    # each link demands one unit of CarrierService; met fraction = carrier_supply
                    link.functionality_level = min(link.functionality_level, carrier_supply)
                    link.update_r2d_dict()

    def get_total_supply(self, scope='All') -> float:
        return float(sum(structure.functionality_level for structure, _ in self.structure_carrier_links))

    def get_total_demand(self, scope='All') -> float:
        return float(sum(len(links) for _, links in self.structure_carrier_links))

    def get_total_consumption(self, scope='All') -> float:
        return float(sum(len(links) for structure, links in self.structure_carrier_links
                         if structure.functionality_level > 0))
