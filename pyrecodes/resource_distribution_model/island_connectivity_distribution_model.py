from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.island_connectivity_distribution_model_constructor import IslandConnectivityDistributionModelConstructor
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness
import pandas as pd


class IslandConnectivityDistributionModel(AbstractResourceDistributionModel):
    """
    Distribution model that tracks whether an island is connected to the mainland.

    A trip to/from an off-island location is accessible only if at least one mainland
    connector (bridge or tunnel) is functional AND the residual-demand traffic model finds a
    functional on-island path between that connector's nearest traffic node and the business.
    The model is therefore a thin wrapper around the ResidualDemand traffic model: it adds the
    island-crossing leg, then delegates the on-island leg to the traffic model.
    Components flagged with OutsideIsland in GeneralInformation are considered off-island.
    """

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = IslandConnectivityDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        self.traffic_model = None
        self.connector_nodes = {}

    def set_transfer_service_distribution_model(self, traffic_model) -> None:
        """
        Receive the residual-demand traffic model this model wraps. Map each mainland connector
        to its nearest traffic node and register connector->business trips in the OD matrix so
        the traffic model scores them. This must happen before the first simulation - the same
        lifecycle as the other transfer-service trip registrations.
        """
        self.traffic_model = traffic_model
        self.connector_nodes = self.find_connector_nodes(traffic_model)
        self.register_connector_trips(traffic_model)

    def find_connector_nodes(self, traffic_model) -> dict:
        """Map each mainland connector to its nearest traffic node, reusing the same
        nearest-node routine used for buildings so the node ids live in the same space as
        traffic_model.building_to_traffic_node_dict."""
        flow_simulator = traffic_model.flow_simulator
        nodes_df = flow_simulator.nodes_df.copy()
        nodes_df['lon'] = nodes_df['x']
        nodes_df['lat'] = nodes_df['y']
        nodes_df = nodes_df.set_index('node_id')
        connector_locations = pd.DataFrame([
            {'Latitude': connector.general_information['location']['latitude'],
             'Longitude': connector.general_information['location']['longitude']}
            for connector in self.mainland_connectors
        ])
        connector_locations = flow_simulator.closest_neighbour(connector_locations, nodes_df)
        return {connector: int(node) for connector, node in
                zip(self.mainland_connectors, connector_locations['closest_node'])}

    def register_connector_trips(self, traffic_model) -> None:
        """Inject connector_node->business_node trips into the OD matrix for every business that
        has an off-island relationship, so the traffic model computes their travel times."""
        if not hasattr(traffic_model, 'od_trip_checker'):
            return
        checker = traffic_model.od_trip_checker
        for business_node in self.business_nodes_with_off_island_links(traffic_model):
            for connector_node in self.connector_nodes.values():
                if not (checker.check_trip_in_od_matrix(connector_node, business_node) or
                        checker.check_trip_in_od_matrix(business_node, connector_node)):
                    checker.add_to_od_matrix(connector_node, business_node)

    def business_nodes_with_off_island_links(self, traffic_model) -> set:
        """Traffic nodes of businesses that have at least one off-island relationship, so only
        those businesses get connector trips registered (a purely on-island business never needs
        to be reached from the mainland)."""
        business_nodes = set()
        for component in self.components:
            if isinstance(component, R2DBuildingWithBusiness):
                business_node = traffic_model.building_to_traffic_node_dict.get(component.aim_id)
                if business_node is None:
                    continue
                if any(self.business_has_off_island_link(business) for business in component.businesses):
                    business_nodes.add(business_node)
        return business_nodes

    def business_has_off_island_link(self, business) -> bool:
        """
        True if the business depends on anything off-island: an employee home or supplier flagged
        outside the island, an explicit outside-island customer building, or the pooled off-island
        'Others' visitor CBG. Only such businesses need a mainland-crossing leg scored for them.
        """
        parameters = business.parameters
        if any(location in self.outside_island_building_ids
               for location in parameters.get('EmployeeLocations', [])):
            return True
        if any(location in self.outside_island_building_ids
               for location in parameters.get('NearestRetailLocations', [])):
            return True
        if parameters.get('OutsideIslandCustomerBuildings'):
            return True
        if 'Others' in parameters.get('VisitorHomeCBGs', {}):
            return True
        return False

    def is_outside_island(self, building_id) -> bool:
        return building_id in self.outside_island_building_ids

    def is_connected(self) -> bool:
        return any(connector.functionality_level > 0 for connector in self.mainland_connectors)

    def is_reachable_from_mainland(self, time_step: int, business_id: str) -> bool:
        """
        True if at least one functional mainland connector has a working on-island path to the
        business. Falls back to is_connected() if the wrapped traffic model is unavailable or the
        business is not on the road graph.
        """
        if self.traffic_model is None:
            return self.is_connected()
        business_node = self.traffic_model.building_to_traffic_node_dict.get(business_id)
        if business_node is None:
            return self.is_connected()
        return any(
            connector.functionality_level > 0
            and self.traffic_model.path_accessible(time_step, connector_node, business_node)
            for connector, connector_node in self.connector_nodes.items()
        )

    def is_building_accessible(self, time_step: int, origin_building_id: str, destination_building_id: str):
        origin_off = self.is_outside_island(origin_building_id)
        destination_off = self.is_outside_island(destination_building_id)
        if not origin_off and not destination_off:
            return None  # neither endpoint is off-island - abstain, let the traffic model answer
        if origin_off and destination_off:
            return self.is_connected()  # both off-island, no on-island business to route a path to
        business_id = destination_building_id if origin_off else origin_building_id
        return self.is_reachable_from_mainland(time_step, business_id)

    def distribute(self, time_step: int) -> None:
        pass

    def get_total_supply(self, scope='All') -> float:
        return 0

    def get_total_demand(self, scope='All') -> float:
        return 0

    def get_total_consumption(self, scope='All') -> float:
        return 0
