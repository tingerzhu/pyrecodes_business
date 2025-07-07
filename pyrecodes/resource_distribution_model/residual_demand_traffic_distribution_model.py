from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model_constructor import ResidualDemandTrafficDistributionModelConstructor
from pyrecodes.resource_distribution_model.spatial_resource_aggregator import SpatialResourceAggregator
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness, R2DBuilding
import math
import os
import pandas as pd

class ResidualDemandTrafficDistributionModel(AbstractResourceDistributionModel):

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = ResidualDemandTrafficDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        self.transfer_service_distribution_model = None #consider moving this into the constructor or finding a better solution-the point is to have an initial value for this property
        self.spatial_resource_aggregator = SpatialResourceAggregator()
        self.travel_times = []
        self.travel_time_change_factors = []
        self.connect_buildings_to_traffic_nodes()
        self.od_trip_checker = ODTripChecker(resource_parameters['ODFilePre'])

    def connect_buildings_to_traffic_nodes(self) -> None:
        self.building_to_traffic_node_dict = {}
        building_aim_to_node = dict(zip(
            self.flow_simulator.building_df['AIM_id'],
            self.flow_simulator.building_df['closest_node']
        ))

        # Build the mapping only for R2DBuilding components that exist in the dict
        self.building_to_traffic_node_dict = {
            component.aim_id: building_aim_to_node[component.aim_id]
            for component in self.components
            if isinstance(component, R2DBuilding) and component.aim_id in building_aim_to_node
        }

    def distribute(self, time_step: int) -> None:
        """
        | Calculate travel times if the model is supposed to distribute traffic at this time step.
        | If not, append an empty list to the travel_times list to keep the length of the list consistent with the number of time steps.
        """
        self.add_to_time_step_list(time_step, [self.travel_times, self.travel_time_change_factors])
        if self.distribute_at_this_time_step(time_step):
            self.update_r2d_dict()
            self.distribute_traffic(time_step)

    def add_to_time_step_list(self, time_step: int, list_of_lists: list[list]) -> None:
        """
        | Add an empty list to the list_of_lists if the time_step is not already in the list.
        | This is done to keep the length of the list consistent with the number of time steps.
        """
        for list in list_of_lists:
            if len(list) <= time_step:
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
        with open(os.devnull, 'w') as devnull:
            original_stdout_fd = os.dup(1) 
            try:
                os.dup2(devnull.fileno(), 1) 
                self.travel_times[time_step] = self.flow_simulator.simulate(self.r2d_dict)
            finally:
                os.dup2(original_stdout_fd, 1)  
                os.close(original_stdout_fd) 
        self.get_travel_time_change(time_step)

    def get_travel_time_change(self, time_step: int) -> None:
        for agent_pre_disaster, agent_now in zip(self.travel_times[0].iterrows(), self.travel_times[-1].iterrows()):
            travel_time_change_factor = agent_now[1]['travel_time_used'] / agent_pre_disaster[1]['travel_time_used']
            self.travel_time_change_factors[time_step].append({'agent_id': agent_pre_disaster[1]['agent_id'], 'origin_nid': agent_pre_disaster[1]['origin_nid'], 
                                            'stop_nid': agent_pre_disaster[1]['stop_nid'], 'travel_time_change': travel_time_change_factor})

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

    def __init__(self, od_matrix_filename: str):
        self.od_matrix_filename = od_matrix_filename
        self.od_matrix = pd.read_csv(od_matrix_filename)
        # Ensure node IDs are integers to avoid dtype mismatch errors
        self.od_matrix['origin_nid'] = self.od_matrix['origin_nid'].astype('int64')
        self.od_matrix['destin_nid'] = self.od_matrix['destin_nid'].astype('int64')
    
    def add_to_od_matrix(self, origin_node: str, stop_node: str, tour_category: str = 'CONSTANT') -> None:
        agent_id = len(self.od_matrix) + self.BIG_NUMBER # add a large number to avoid duplicates
        new_row = pd.DataFrame({'agent_id': [int(agent_id)], 'origin_nid': [int(origin_node)], 'destin_nid': [int(stop_node)], 'hour': [7], 'quarter': [0], 'tour_category': [tour_category], 'person_id': [int(agent_id)]})
        self.od_matrix = pd.concat([self.od_matrix, new_row], ignore_index=True)
        # self.od_matrix['origin_nid'] = self.od_matrix['origin_nid'].astype('int64')
        # self.od_matrix['destin_nid'] = self.od_matrix['destin_nid'].astype('int64')
        self.od_matrix.to_csv(self.od_matrix_filename, index=False)

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
        
