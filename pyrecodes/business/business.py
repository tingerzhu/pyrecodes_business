from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuilding
from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model import ResidualDemandTrafficDistributionModel


def is_building_accessible(transfer_service_models: list, time_step: int,
                           origin_building_id: str, destination_building_id: str) -> bool:
    for model in transfer_service_models:
        result = model.is_building_accessible(time_step, origin_building_id, destination_building_id)
        if result is not None:
            return result
    return False


class Business():

    def __init__(self, business_id: str, business_parameters: dict, home_component: Component) -> None:
        """
        Initialize the business with an ID and parameters.
        """
        self.business_id = int(business_id)
        self.home_component = home_component
        self.parameters = business_parameters
        self.employee_homes = []
        self.employees_available = {}
        self.customer_base_ratio = {}
        self.input_commodity_available_ratio = 1.0
        self.reason_for_drop = {}
        self.business_functionality_level = 1.0
        self.pre_disaster_daily_revenue = business_parameters['SalesVolume'] / 365
        self.revenue = {}  # time_step -> revenue [$/day]; populated during simulation

    def filter_locations_to_buildings(self, components: list[Component]) -> None:
        building_aim_ids = {c.aim_id for c in components if isinstance(c, R2DBuilding)}
        self.parameters['EmployeeLocations'] = [
            aim_id for aim_id in self.parameters['EmployeeLocations'] if aim_id in building_aim_ids
        ]
        self.parameters['NearestRetailLocations'] = [
            aim_id for aim_id in self.parameters.get('NearestRetailLocations', []) if aim_id in building_aim_ids
        ]

    def set_employee_homes(self, components: list[Component]) -> None:
        self.filter_locations_to_buildings(components)
        for component in components:
            if isinstance(component, R2DBuilding):
                if component.aim_id in self.parameters['EmployeeLocations']:
                    self.employee_homes.append(component)

    def check_employees(self, time_step: int, transfer_service_models: list) -> None:
        employee_available = 0
        for employee_home in self.employee_homes:
            if employee_home.functionality_level == 1.0 and is_building_accessible(transfer_service_models, time_step, employee_home.aim_id, self.home_component.aim_id):
                employee_available += 1

        self.employees_available[time_step] = employee_available / self.parameters['NumEmployees']
        self.update_current_business_functionality(time_step, self.employees_available[time_step], 'Labor')

    def get_employee_demand(self) -> float:
        return self.parameters['NumEmployees'] if self.business_functionality_level > 0 else 0

    def get_employee_supply(self) -> float:
        if not self.employees_available:
            return 0
        last_time_step = max(self.employees_available)
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
        current = self.pre_disaster_daily_revenue * self.business_functionality_level
        self.revenue[time_step] = min(current, self.revenue[time_step]) if time_step in self.revenue else current

    def update_customer_base(self, time_step: int, customer_base_population_ratios: dict,
                             transfer_service_models: list = None) -> None:
        total_customer_base_ratio = 0
        outside_island_accessible = self.check_outside_island_customer_accessibility(
            time_step, transfer_service_models)
        for block in self.parameters['VisitorHomeCBGs'].keys():
            if block == 'Others':
                if outside_island_accessible:
                    total_customer_base_ratio += self.parameters['VisitorHomeCBGs'][block]
            else:
                block_customer_ratio = customer_base_population_ratios.get(block, 0)
                total_customer_base_ratio += self.parameters['VisitorHomeCBGs'][block] * block_customer_ratio
        self.customer_base_ratio[time_step] = round(total_customer_base_ratio, 5)
        self.update_current_business_functionality(time_step, total_customer_base_ratio, 'Customer Base')

    def check_outside_island_customer_accessibility(self, time_step: int,
                                                    transfer_service_models: list = None) -> bool:
        outside_island_buildings = self.parameters.get('OutsideIslandCustomerBuildings', [])
        if not outside_island_buildings or not transfer_service_models:
            return True
        for building_id in outside_island_buildings:
            if is_building_accessible(transfer_service_models, time_step, self.home_component.aim_id, building_id):
                return True
        return False

    def update_current_business_functionality(self, time_step: int, updated_level: float, reason_for_drop: str) -> None:
        if self.business_functionality_level > updated_level:
            self.business_functionality_level = updated_level
        if updated_level < 1.0:
            self.reason_for_drop[time_step].append({'Name': reason_for_drop,
                                             'Level': updated_level})
        self.update_revenue(time_step)

    def check_trips_in_od_matrix(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel, component_ids: list[str]) -> None:
        business_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict[self.home_component.aim_id]
        for component_id in component_ids:
            component_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict.get(component_id, None)
            if component_closest_node is None:
                print(f"Component {component_id} not found in building_to_traffic_node_dict")
            else:
                if not (transfer_service_distribution_model.od_trip_checker.check_trip_in_od_matrix(component_closest_node, business_closest_node) or
                        transfer_service_distribution_model.od_trip_checker.check_trip_in_od_matrix(business_closest_node, component_closest_node)):
                    transfer_service_distribution_model.od_trip_checker.add_to_od_matrix(component_closest_node, business_closest_node)

    def check_supplier_trips_in_od_matrix(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel) -> None:
        self.check_trips_in_od_matrix(transfer_service_distribution_model, self.parameters['NearestRetailLocations'])

    def check_employee_trips_in_od_matrix(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel) -> None:
        self.check_trips_in_od_matrix(transfer_service_distribution_model, self.parameters['EmployeeLocations'])

    def update_access_to_suppliers(self, time_step, transfer_service_models: list) -> None:
        any_accessible = any(
            is_building_accessible(transfer_service_models, time_step, self.home_component.aim_id, supplier)
            for supplier in self.parameters['NearestRetailLocations']
        )
        if not any_accessible:
            self.update_current_business_functionality(time_step, 0, 'LocalSuppliers')
