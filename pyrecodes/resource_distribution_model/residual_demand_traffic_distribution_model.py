from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model_constructor import ResidualDemandTrafficDistributionModelConstructor
from pyrecodes.resource_distribution_model.spatial_resource_aggregator import SpatialResourceAggregator
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuilding, R2DComponent
import math
import os
import pandas as pd

TRAVEL_TIME_CUTOFF = 14400  # four hours in seconds
TRAVEL_TIME_CHANGE_CUTOFF = 4  # max ratio of post/pre disaster travel time

class ResidualDemandTrafficDistributionModel(AbstractResourceDistributionModel):

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = ResidualDemandTrafficDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        self.transfer_service_distribution_model = None #consider moving this into the constructor or finding a better solution-the point is to have an initial value for this property
        self.spatial_resource_aggregator = SpatialResourceAggregator()
        self.travel_times = []
        self.travel_time_change_factors = []
        self.trip_index = []  # parallel to travel_times: (origin_nid, destin_nid) -> row index, rebuilt each distribution time step
        self.travel_time_change_index = []  # parallel to travel_time_change_factors: agent_id -> change factor, rebuilt each distribution time step
        self.connect_buildings_to_traffic_nodes()
        self.outside_island_building_ids = {
            component.aim_id for component in self.components
            if isinstance(component, R2DComponent) and component.general_information.get('OutsideIsland', False)
        }
        isolated_nodes = getattr(self.flow_simulator, 'isolated_nodes', set())
        self.od_trip_checker = ODTripChecker(resource_parameters['ODFilePre'], isolated_nodes)

    def connect_buildings_to_traffic_nodes(self) -> None:
        self.building_to_traffic_node_dict = {}
        building_aim_to_node = dict(zip(
            self.flow_simulator.building_df['AIM_id'],
            self.flow_simulator.building_df['closest_node']
        ))

        # Build the mapping only for R2DBuilding components that exist in the dict
        self.building_to_traffic_node_dict = {
            component.aim_id: int(building_aim_to_node[component.aim_id])
            for component in self.components
            if isinstance(component, R2DBuilding) and component.aim_id in building_aim_to_node
        }

    def distribute(self, time_step: int) -> None:
        """
        | Calculate travel times if the model is supposed to distribute traffic at this time step.
        | If not, append an empty list to the travel_times list to keep the length of the list consistent with the number of time steps.
        """
        self.add_to_time_step_list(time_step, [self.travel_times, self.travel_time_change_factors, self.travel_time_change_index, self.trip_index])
        if self.distribute_at_this_time_step(time_step):
            self.update_r2d_dict()
            self.distribute_traffic(time_step)

    def add_to_time_step_list(self, time_step: int, list_of_lists: list[list]) -> None:
        """
        | Add an empty list to the list_of_lists if the time_step is not already in the list.
        | This is done to keep the length of the list consistent with the number of time steps.
        """
        for list in list_of_lists:
            while len(list) <= time_step:
                list.append([])   

    def find_nearest_distribution_time_step(self, time_step: int) -> int:
        # Assuming self.distribution_time_steps is a sorted list of time steps
        return next((n for n in reversed(self.distribution_time_steps) if n <= time_step), None)

    def update_r2d_dict(self):
        """
        | Method to update the r2d_dict based on the current state of the components.
        | At the moment, the r2d_dict is created from scratch at each time step. Not efficient, optimize later.
        """
        self.r2d_dict = self.constructor.create_r2d_dict(self.components)

    def distribute_traffic(self, time_step: int) -> None:
        """
        | Run the traffic simulator to calculate travel times.
        | Supress output to the console from low-level libraries.
        """
        self.add_to_time_step_list(time_step, [self.travel_times, self.travel_time_change_factors, self.travel_time_change_index, self.trip_index])
        with open(os.devnull, 'w') as devnull:
            original_stdout_fd = os.dup(1) 
            try:
                os.dup2(devnull.fileno(), 1) 
                self.travel_times[time_step] = self.flow_simulator.simulate(
                    self.r2d_dict, od_matrix=self.od_trip_checker.od_matrix)
            finally:
                os.dup2(original_stdout_fd, 1)  
                os.close(original_stdout_fd) 
        self.get_travel_time_change(time_step)

    def is_building_accessible(self, time_step: int, origin_building_id: str, destination_building_id: str):
        if origin_building_id in self.outside_island_building_ids or destination_building_id in self.outside_island_building_ids:
            return None
        origin_node = self.building_to_traffic_node_dict.get(origin_building_id, None)
        destination_node = self.building_to_traffic_node_dict.get(destination_building_id, None)
        return self.path_accessible(time_step, origin_node, destination_node)

    def path_accessible(self, time_step: int, origin_node, destination_node) -> bool:
        """
        | Check whether a functional path exists between two traffic nodes at the given time step,
          reusing the precomputed travel times.
        | origin_node/destination_node are traffic node ids (as stored in building_to_traffic_node_dict).
        | Returns False if either node is missing or isolated. Exposed so other models (e.g. the
          island connectivity model) can score node-to-node paths without going through buildings.
        """
        if origin_node is None or destination_node is None:
            return False
        if origin_node in self.od_trip_checker.isolated_nodes or destination_node in self.od_trip_checker.isolated_nodes:
            return False
        last_distribution_time_step = self.find_nearest_distribution_time_step(time_step)
        travel_times = self.travel_times[last_distribution_time_step]
        change_index = self.travel_time_change_index[last_distribution_time_step]
        return self.check_accessibility(origin_node, destination_node, travel_times,
                                        self.trip_index[last_distribution_time_step], change_index)

    def check_accessibility(self, origin_node, destination_node, travel_times: pd.DataFrame, trip_index: dict, change_index: dict) -> bool:
        if origin_node == destination_node:
            return True
        row = trip_index.get((origin_node, destination_node))
        if row is None:
            row = trip_index.get((destination_node, origin_node))
        if row is None:
            return False
        record = travel_times.iloc[row]
        travel_time = record['travel_time_used']
        travel_time_change_factor = change_index.get(record['agent_id'], float('inf'))
        return travel_time_change_factor <= TRAVEL_TIME_CHANGE_CUTOFF and travel_time <= TRAVEL_TIME_CUTOFF

    def get_travel_time_change(self, time_step: int) -> None:
        # Pair pre-disaster and current travel times by agent_id, NOT by row position: unroutable
        # trips are appended at the end of the results, so the row order differs between steps and a
        # positional zip would divide one trip's current time by a different trip's pre-disaster time.
        current = self.travel_times[time_step]
        pre_disaster_time_by_agent = dict(zip(self.travel_times[0]['agent_id'],
                                              self.travel_times[0]['travel_time_used']))
        for now in current.itertuples():
            pre_disaster_time = pre_disaster_time_by_agent.get(now.agent_id, float('inf'))
            if not math.isfinite(pre_disaster_time) or pre_disaster_time == 0:
                # An unroutable pre-disaster trip implies the destination is always inaccessible.
                travel_time_change_factor = float('inf')
            else:
                travel_time_change_factor = now.travel_time_used / pre_disaster_time
            self.travel_time_change_factors[time_step].append({'agent_id': now.agent_id, 'origin_nid': now.origin_nid,
                                            'stop_nid': now.stop_nid, 'travel_time_change': travel_time_change_factor})
        records = current.to_dict(orient='records')
        self.trip_index[time_step] = {(r['origin_nid'], r['destin_nid']): i for i, r in enumerate(records)}
        self.travel_time_change_index[time_step] = {e['agent_id']: e['travel_time_change'] for e in self.travel_time_change_factors[time_step]}

    # def update_buildings_traffic_situation(self) -> None:
    #     """
    #     | Update supply of buildings based on their travel times.
    #     | At the moment, updates only R2DBuilding components
    #     """
    #     for component in self.components:      
    #         component.update_traffic_situation(self.building_to_traffic_node_dict, self.travel_times[-1], self.travel_time_change_factors[-1])  

    def get_od_matrix(self) -> dict:
        """
        Get the OD matrix from the flow simulator.
        Returns None if there is no flow simulator.
        """
        if hasattr(self, 'flow_simulator') and self.flow_simulator is not None:
            return self.flow_simulator.od_matrix
        return None

    def get_total_supply(self, scope: str) -> float:
        """
        Supply is calculated the same as consumption.
        """
        return self.get_total_consumption(scope)

    def get_total_demand(self, scope: str) -> float:
        """
        | Demand for the transportation service is the number of agents that need to travel from one location to another.
        | If traffic is not distributed at the current time step, demand is 0.
        """
        if scope == 'All':
            if len(self.travel_times[-1]) > 0:
                return len(self.travel_times[-1])
            else:
                return 0
        else:
            raise ValueError("Scope not implemented. Only 'All' is supported.")

    def get_total_consumption(self, scope: str) -> float:
        """
        | Consumption of the transportation service is the number of agents whose travel time is not extended beyond the pre-disaster time times the TRIP_CUTOFF_THRESHOLD.
        | If traffic is not distributed at the current time step, consumption is 0.
        """
        if scope == 'All':
            if len(self.travel_times[-1]) > 0:
                completed_trips = 0
                for travel_time_change in self.travel_time_change_factors[-1]:
                    if travel_time_change['travel_time_change'] <= self.TRIP_CUTOFF_THRESHOLD:
                        completed_trips += 1
                return completed_trips
            else:
                return 0
        else:
            raise ValueError("Scope not implemented. Only 'All' is supported.")

class ODTripChecker:

    BIG_NUMBER = 10e6

    def __init__(self, od_matrix_filename: str, isolated_nodes: set = None):
        self.od_matrix_filename = od_matrix_filename
        self.isolated_nodes = isolated_nodes or set()
        self.od_matrix = pd.read_csv(od_matrix_filename)
        # Drop rows with NaN node IDs, then cast to int64
        self.od_matrix = self.od_matrix.dropna(subset=['origin_nid', 'destin_nid'])
        # Ensure node IDs are integers to avoid dtype mismatch errors
        self.od_matrix['origin_nid'] = self.od_matrix['origin_nid'].astype('int64')
        self.od_matrix['destin_nid'] = self.od_matrix['destin_nid'].astype('int64')
        # Remove any pre-existing trips that start or end at isolated/dangling nodes
        if self.isolated_nodes:
            self.od_matrix = self.od_matrix[
                ~self.od_matrix['origin_nid'].isin(self.isolated_nodes) &
                ~self.od_matrix['destin_nid'].isin(self.isolated_nodes)
            ]
    
    def add_to_od_matrix(self, origin_node: str, stop_node: str, tour_category: str = 'CONSTANT') -> None:
        if origin_node == stop_node:
            return
        if origin_node in self.isolated_nodes or stop_node in self.isolated_nodes:
            return
        # Unique id robust to re-registration: continue past the current max agent_id, but stay in
        # the BIG_NUMBER range so registered trips remain distinguishable from real demand.
        # (len(od_matrix) + BIG_NUMBER was not unique once the OD matrix is re-registered, which
        # produced colliding agent_ids and corrupted the per-agent travel-time-change lookup.)
        max_existing = int(self.od_matrix['agent_id'].max()) if len(self.od_matrix) else 0
        agent_id = max(max_existing + 1, int(self.BIG_NUMBER))
        new_row = pd.DataFrame({'agent_id': [int(agent_id)], 'origin_nid': [int(origin_node)], 'destin_nid': [int(stop_node)], 'hour': [7], 'quarter': [0], 'tour_category': [tour_category], 'person_id': [int(agent_id)]})
        self.od_matrix = pd.concat([self.od_matrix, new_row], ignore_index=True)
        # Registered trips are kept in memory and passed to the flow simulator at simulate() time;
        # the input OD file is intentionally NOT mutated.

    def check_trip_in_od_matrix(self, origin_node_id: int, destin_node_id: int) -> bool:
        """
        Check whether a trip with the given origin and destination node IDs exists in the OD matrix.
        
        Args:
            origin_node_id: The origin node ID
            destin_node_id: The destination node ID
            
        Returns:
            bool: True if the trip exists, False otherwise
        """
        trip_exists = ((self.od_matrix['origin_nid'] == int(origin_node_id)) & 
                      (self.od_matrix['destin_nid'] == int(destin_node_id))).any()
        
        return trip_exists
        
