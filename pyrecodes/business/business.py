from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuilding

TRAVEL_TIME_CUTOFF = 2.0  # in hours, used to determine if a business has access to suppliers

class Business():

    def __init__(self, business_id: str, business_parameters: dict, home_component: Component) -> None:
        """
        Initialize the business with an ID and parameters.
        """
        self.business_id = int(business_id)
        self.home_component = home_component
        self.set_parameters(business_parameters)
        self.employees_available = {}
        self.input_commodity_available_ratio = 1.0
        self.reason_for_drop = []
        self.business_functionality_level = 1.0

    def set_parameters(self, parameters: dict) -> None:
        """
        Set the parameters of the business.
        """
        self.parameters = parameters
        self.employee_homes = []

    def set_employee_homes(self, components: list[Component]) -> None:
        for component in components:
            if isinstance(component, R2DBuilding):
                id = component.aim_id
                location_list = self.parameters['EmployeeLocations']
                if component.aim_id in self.parameters['EmployeeLocations']:
                    self.employee_homes.append(component)

    def check_employees(self, time_step: int) -> None:
        employee_sum = self.parameters['NumEmployees']
        for employee_home in self.employee_homes:
            if employee_home.get_functionality_level() < 1.0:
                employee_sum -= 1

        self.employees_available[time_step] = employee_sum / self.parameters['NumEmployees']
        
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
        self.reason_for_drop.append('')
        self.update_current_business_functionality(self.home_component.functionality_level, 'Home Component Functionality')
        # home_component_functionality = self.get_home_component_functionality_level_constrained_by_supply()
        # self.business_functionality_level = self.home_component.functionality_level
        # self.business_functionality_level = min(home_component_functionality, labor_functionality_level, self.input_commodity_available_ratio)
        
    def update_functionality_based_on_unmet_demand(self, percent_of_met_demand: float) -> None:
        """
        Update the functionality of the business based on the unmet demand.
        NOTE: Linear relation assumed between the unmet demand and the functionality of the business.
        """
        self.update_current_business_functionality(percent_of_met_demand, 'Infrastructure')

    def recover(self, time_step: int) -> None:
        labor_functionality_level = self.employees_available[time_step]
        self.update_current_business_functionality(labor_functionality_level, 'Labor')

    def update_current_business_functionality(self, updated_level: float, reason_for_drop: str) -> None:
        if self.business_functionality_level > updated_level:
            self.business_functionality_level = updated_level
            self.reason_for_drop[-1] = reason_for_drop
    
    def update_access_to_suppliers(self, travel_times):
        # change the inputs to match the inputs provided in R2DComponent module
        # find the closests nodes to the business and the suppliers in one of the inputs
        # check if the travel time change is less than the cutoff or if the absolute travel time is less than a threshold (you choose)
        # if none of the suppliers are accessible, set the input commodity available ratio to 0 (in a new attribute)
        # maybe also change business functionality or revenue
        # consider adding artifical components as the mainland suppliers in the exposure file        
        pass




                

    