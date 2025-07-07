from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuilding
import pandas as pd
from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model import ResidualDemandTrafficDistributionModel

TRAVEL_TIME_CUTOFF = 14400  # four hours in seconds, used to determine if a business has access to suppliers
TRAVEL_TIME_CHANGE_CUTOFF = 4  # if the difference between pre and post disaster travel times is greater than this, the business has no access to suppliers

class Business():

    def __init__(self, business_id: str, business_parameters: dict, home_component: Component) -> None:
        """
        Initialize the business with an ID and parameters.
        """
        self.business_id = int(business_id)
        self.home_component = home_component
        self.set_parameters(business_parameters)
        self.employees_available = {}
        self.customer_base_ratio = []
        self.input_commodity_available_ratio = 1.0
        self.reason_for_drop = {}
        self.business_functionality_level = 1.0
        self.revenue = {0: business_parameters['SalesVolume'] / 365}  # Daily revenue, assuming SalesVolume is annual

    def set_parameters(self, parameters: dict) -> None:
        """
        Set the parameters of the business.
        """
        self.parameters = parameters
        self.employee_homes = []

    def set_employee_homes(self, components: list[Component]) -> None:
        for component in components:
            if isinstance(component, R2DBuilding):
                if component.aim_id in self.parameters['EmployeeLocations']:
                    self.employee_homes.append(component)

    def check_employees(self, time_step: int, traffic_flow_model: ResidualDemandTrafficDistributionModel) -> None:
        employee_available = 0
        for employee_home in self.employee_homes:
            if employee_home.functionality_level == 1.0 and self.business_accessible(time_step, traffic_flow_model, employee_home):
                employee_available += 1

        self.employees_available[time_step] = employee_available / self.parameters['NumEmployees']
        self.update_current_business_functionality(time_step, self.employees_available[time_step], 'Labor')

    def business_accessible(self, time_step: int, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel, employee_home: R2DBuilding) -> bool:
        employee_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict[employee_home.aim_id]
        business_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict[self.home_component.aim_id]
        latest_travel_times, latest_travel_time_change = self.get_latest_travel_times(transfer_service_distribution_model, time_step)       

        accessible = self.check_accessibility(business_closest_node, employee_closest_node, latest_travel_times, latest_travel_time_change)
        return accessible
    
    def get_latest_travel_times(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel, time_step: int) -> pd.DataFrame:
        last_distribution_time_step = transfer_service_distribution_model.find_nearest_distribution_time_step(time_step)
        latest_travel_times = transfer_service_distribution_model.travel_times[last_distribution_time_step]
        latest_travel_time_change = transfer_service_distribution_model.travel_time_change_factors[last_distribution_time_step]
        return latest_travel_times, latest_travel_time_change
        
    def get_employee_demand(self) -> float:
        if self.business_needs_employees():
            return self.parameters['NumEmployees']
        else:
            return 0
        
    def business_needs_employees(self) -> bool:
        if self.business_functionality_level > 0:
            return True
        else:
            return False
        
    def get_employee_supply(self) -> float:
        last_time_step = max(list(self.employees_available.keys()))
        return int(self.employees_available[last_time_step] * self.parameters['NumEmployees'])
    
    def get_employee_consumption(self) -> float:
        return min(self.get_employee_demand(), self.get_employee_supply())
    
    def update(self, time_step:int) -> None:
        """
        Update the business.
        """
        self.business_functionality_level = 1.0
        self.reason_for_drop[time_step] = []
        self.update_current_business_functionality(time_step, self.home_component.functionality_level, 'Home Component Functionality')
        
    def update_functionality_based_on_unmet_demand(self, time_step, percent_of_met_demand: float) -> None:
        """
        Update the functionality of the business based on the unmet demand.
        NOTE: Linear relation assumed between the unmet demand and the functionality of the business.
        """
        self.update_current_business_functionality(time_step, percent_of_met_demand, 'Infrastructure')

    def recover(self, time_step: int) -> None:
        pass

    def update_revenue(self, time_step: int) -> None:
        if time_step not in self.revenue:
            self.revenue[time_step] = self.revenue[0] * self.business_functionality_level
        else:
            self.revenue[time_step] = min(self.revenue[0] * self.business_functionality_level, self.revenue[time_step])

    def update_customer_base(self, time_step: int, customer_base_population_ratios: dict) -> None:
        total_customer_base_ratio = 0
        for block in self.parameters['VisitorHomeCBGs'].keys():
            if block == 'Others':
                total_customer_base_ratio += self.parameters['VisitorHomeCBGs'][block]
            else:
                block_customer_ratio = customer_base_population_ratios.get(block, 0)
                if block_customer_ratio == 10:
                    print(f"Warning: Block {block} not found in current block population.")
                    block_customer_ratio = 0
                total_customer_base_ratio += self.parameters['VisitorHomeCBGs'][block] * block_customer_ratio
        self.customer_base_ratio.append(round(total_customer_base_ratio, 5))
        self.update_current_business_functionality(time_step, total_customer_base_ratio, 'Customer Base')

    def update_current_business_functionality(self, time_step: int, updated_level: float, reason_for_drop: str) -> None:
        if self.business_functionality_level > updated_level:
            self.business_functionality_level = updated_level
        if updated_level < 1.0:
            self.reason_for_drop[time_step].append({'Name': reason_for_drop,
                                             'Level': updated_level})
        self.update_revenue(time_step)

    def check_trips_in_od_matrix(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel, component_ids: list[str]) -> list[dict]:
        business_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict[self.home_component.aim_id]
        for component_id in component_ids:
            component_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict.get(component_id, None)
            if component_closest_node is None:
                print(f"Component {component_id} not found in building_to_traffic_node_dict")
            else:
                if not (transfer_service_distribution_model.od_trip_checker.check_trip_in_od_matrix(component_closest_node, business_closest_node) or 
                        transfer_service_distribution_model.od_trip_checker.check_trip_in_od_matrix(business_closest_node, component_closest_node)):
                    transfer_service_distribution_model.od_trip_checker.add_to_od_matrix(component_closest_node, business_closest_node)

    def check_supplier_trips_in_od_matrix(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel) -> list[dict]:
        return self.check_trips_in_od_matrix(transfer_service_distribution_model, self.parameters['NearestRetailLocations'])

    def check_employee_trips_in_od_matrix(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel) -> list[dict]:
        return self.check_trips_in_od_matrix(transfer_service_distribution_model, self.parameters['EmployeeLocations'])

    def update_access_to_suppliers(self, time_step, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel) -> None:
        latest_travel_times, latest_travel_time_change = self.get_latest_travel_times(transfer_service_distribution_model, time_step)

        home_component_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict[self.home_component.aim_id]
        
        for supplier in self.parameters['NearestRetailLocations']:
            supplier_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict.get(supplier, None)
            if supplier_closest_node is None:
                print(f"Supplier {supplier} not found in building_to_traffic_node_dict")
            else:
                accessible = self.check_accessibility(home_component_closest_node, supplier_closest_node, latest_travel_times, latest_travel_time_change)
        if not(accessible):
            self.update_current_business_functionality(time_step, 0, 'LocalSuppliers')

    def find_trip_id(self, origin_node: str, stop_node: str, travel_times: dict, bidirectional: bool = True) -> int:
        """
        Find the trip ID for a given origin-destination pair.
        
        Args:
            origin_node: Origin node ID (as string)
            stop_node: Destination node ID (as string)
            travel_times: List of travel time dictionaries
            
        Returns:
            int: Index of the trip in travel_times, or -1 if not found
        """
        # Convert to integers for comparison if needed
        try:
            origin_node_int = int(origin_node)
            stop_node_int = int(stop_node)
        except ValueError:
            print(f"Warning: Could not convert node IDs to integers: {origin_node}, {stop_node}")
            return -1
            
        for i, travel_time in enumerate(travel_times):
            # Check for exact match (directional)         
            if (travel_time['origin_nid'] == origin_node_int and 
                travel_time['destin_nid'] == stop_node_int):
                return i
            
            if bidirectional and (travel_time['origin_nid'] == stop_node_int and 
                travel_time['destin_nid'] == origin_node_int):
                return i
                
        print(f"Trip not found for {origin_node} to {stop_node}")
        return -1

    def check_accessibility(self, home_component_closest_node: str, supplier_closest_node: str, latest_travel_times: pd.DataFrame, travel_time_change: list[dict]) -> bool:
        accessible = False
        latest_travel_times_dict = latest_travel_times.to_dict(orient='records')
        agent_row = self.find_trip_id(home_component_closest_node, supplier_closest_node, latest_travel_times_dict)
        
        # If no trip found, assume not accessible
        if agent_row == -1:
            return False
            
        travel_time = self.get_travel_time(agent_row, latest_travel_times_dict)
        travel_time_change_factor = self.get_travel_time_change_factor(agent_row, travel_time_change)
        if not(travel_time_change_factor > TRAVEL_TIME_CHANGE_CUTOFF and travel_time > TRAVEL_TIME_CUTOFF):
            accessible = True
            
        return accessible
       
    def get_travel_time(self, agent_row: int, travel_times: dict) -> float:
        return travel_times[agent_row]['travel_time_used']

    def get_travel_time_change_factor(self, agent_row: int, travel_time_change: list[dict]) -> float:
        return travel_time_change[agent_row]['travel_time_change']                             

    