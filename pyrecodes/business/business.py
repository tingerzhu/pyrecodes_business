from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuilding
from pyrecodes.constants import TIME_STEPS_IN_A_YEAR
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
        # Own-home contribution only (set by check_employee_availability, never bumped
        # by apply_received_employees). Used by update_employee_demand so the labor
        # shortfall asked from the residual pool reflects the structural gap rather
        # than last step's post-redistribution top-up - which would silently extinguish
        # this step's request and cause employees to oscillate between businesses.
        self.own_employees_available = {}
        self.customer_base_ratio = {}
        self.input_commodity_available_ratio = 1.0
        self.reason_for_drop = {}
        self.business_functionality_level = 1.0
        # Revenue earned over one time step ($/time step, e.g. $/week when TIME_STEPS_IN_A_YEAR == 52).
        self.pre_disaster_revenue_per_time_step = business_parameters['SalesVolume'] / TIME_STEPS_IN_A_YEAR
        self.revenue = {}  # time_step -> revenue earned that time step [$/time step]; populated during simulation

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
        self.check_employee_availability(time_step, transfer_service_models)
        self.register_residual_employee_supply(time_step, transfer_service_models)

    def get_reachable_employee_homes(self, time_step: int, transfer_service_models: list) -> list:
        """Employee homes that are functional and can reach the business at time_step."""
        return [
            home for home in self.employee_homes
            if home.functionality_level == 1.0
            and is_building_accessible(transfer_service_models, time_step, home.aim_id, self.home_component.aim_id)
        ]

    def check_employee_availability(self, time_step: int, transfer_service_models: list) -> None:
        """Count employees who can reach the business and update its Labor functionality."""
        reachable = self.get_reachable_employee_homes(time_step, transfer_service_models)
        ratio = len(reachable) / self.parameters['NumEmployees']
        self.employees_available[time_step] = ratio
        self.own_employees_available[time_step] = ratio
        self.update_current_business_functionality(time_step, ratio, 'Labor')

    def register_residual_employee_supply(self, time_step: int, transfer_service_models: list) -> None:
        """
        If this business could not operate at the previous step (its building, its
        utilities or its suppliers were down), the employees that can still reach it
        are free to work elsewhere. Register them as residual Employee supply on their
        HOME buildings so the ResidualEmployeeDistributionModel can reassign them to
        businesses that are short on labor. Supply originates at the homes, never at the
        business building (which only ever demands employees).
        """
        if not self.is_blocked_from_operating(time_step - 1):
            return
        for home in self.get_reachable_employee_homes(time_step, transfer_service_models):
            home.add_employee_supply(1)

    def get_employee_demand(self) -> float:
        return self.parameters['NumEmployees'] if self.business_functionality_level > 0 else 0

    def get_employee_supply(self) -> float:
        if not self.employees_available:
            return 0
        last_time_step = max(self.employees_available)
        return int(self.employees_available[last_time_step] * self.parameters['NumEmployees'])

    def get_employee_consumption(self) -> float:
        return min(self.get_employee_demand(), self.get_employee_supply())

    def get_assigned_employees(self, time_step: int) -> int:
        """Employees that physically showed up from registered homes at time_step."""
        ratio = self.employees_available.get(time_step, 1.0)
        return int(round(ratio * self.parameters['NumEmployees']))

    def get_own_assigned_employees(self, time_step: int) -> int:
        """
        Own-home employees only at time_step - the pre-redistribution count, set by
        check_employee_availability and never bumped by apply_received_employees.

        Use this (NOT get_assigned_employees) anywhere you need the STRUCTURAL labor
        gap (NumEmployees - own_count). If you use the post-receiving count instead,
        a business that was topped up by the pool at t-1 will look "fully assigned"
        at t-1 and the t-step logic that subtracts that count will compute a zero
        outstanding need - which causes the every-other-step delivery oscillation
        seen for businesses that depend on the residual pool every step.

        Falls back to employees_available[time_step] for tests that pre-stage state
        without populating own_employees_available; real runtime always sets the latter
        first via check_employee_availability.
        """
        ratio = self.own_employees_available.get(time_step,
                                                  self.employees_available.get(time_step, 1.0))
        return int(round(ratio * self.parameters['NumEmployees']))

    def is_blocked_from_operating(self, time_step: int) -> bool:
        """
        True if at time_step the business cannot operate at all, no matter how many
        employees it has. Triggered when one of these constraints is below 1.0:
          - Home Component Functionality  (the building itself is damaged)
          - Infrastructure                (utilities like water/power unavailable)
          - LocalSuppliers                (no access to input suppliers)

        Customer Base is intentionally excluded: low customer base means reduced
        activity but the business still serves the customers it has and still needs
        employees.
        """
        blockers = {'Home Component Functionality', 'Infrastructure', 'LocalSuppliers'}
        return any(r['Name'] in blockers and r['Level'] < 1.0
                   for r in self.reason_for_drop.get(time_step, []))

    def is_short_on_labor_but_can_operate(self, time_step: int) -> bool:
        """
        True if at time_step the business has a STRUCTURAL labor gap (own-home employees
        cannot fully staff it) and could otherwise operate. Used to decide eligibility
        as a recipient of the residual employee pool.

        Reads `own_employees_available` (the pre-redistribution own-home contribution)
        rather than the Labor row in `reason_for_drop`. Why: `apply_received_employees`
        calls `update_current_business_functionality(..., 'Labor', allow_increase=True)`,
        which `max()`-merges the Labor row up to 1.0 once the pool tops the business up.
        If we read that Labor row, a still-structurally-short business looks "fully
        staffed" at the next step, asks for 0, silently de-staffs, then asks again at
        the step after - the oscillation the user is seeing in Example 5.

        Customer Base is intentionally NOT a disqualifier: low customer base lowers
        activity but the business still serves the customers it has and still needs its
        full workforce.
        """
        if self.is_blocked_from_operating(time_step):
            return False
        own_ratio = self.own_employees_available.get(time_step)
        if own_ratio is not None:
            return own_ratio < 1.0
        # Back-compat fallback for tests that pre-stage reason_for_drop without setting
        # own_employees_available. Real runtime always populates the latter first via
        # check_employee_availability.
        reasons = self.reason_for_drop.get(time_step, [])
        return any(r['Name'] == 'Labor' and r['Level'] < 1.0 for r in reasons)

    def update_employee_demand(self, time_step: int) -> None:
        # Ask the residual pool for the STRUCTURAL labor gap (NumEmployees minus the
        # own-home contribution at prev). See Business.get_own_assigned_employees for
        # why this MUST NOT read the post-receiving employees_available[prev].
        prev = time_step - 1
        if self.is_short_on_labor_but_can_operate(prev):
            demand = self.parameters['NumEmployees'] - self.get_own_assigned_employees(prev)
        else:
            demand = 0
        self.home_component.add_employee_demand(demand)

    def apply_received_employees(self, time_step: int, n_extra: float) -> None:
        """
        Add n_extra employees received from the redistribution pool to this business at
        time_step, bump employees_available accordingly, and recompute Labor reason and
        business functionality.
        """
        if n_extra <= 0:
            return
        already_here = self.get_assigned_employees(time_step)
        new_count = min(self.parameters['NumEmployees'], already_here + n_extra)
        new_ratio = new_count / self.parameters['NumEmployees']
        self.employees_available[time_step] = new_ratio
        self.update_current_business_functionality(time_step, new_ratio, 'Labor', allow_increase=True)

    def update(self, time_step:int) -> None:
        """
        Update the business.
        """
        self.business_functionality_level = 1.0
        self.reason_for_drop[time_step] = []
        self.update_current_business_functionality(time_step, self.home_component.functionality_level, 'Home Component Functionality')
        self.update_employee_demand(time_step)

    def update_functionality_based_on_unmet_demand(self, time_step, percent_of_met_demand: float) -> None:
        """
        Update the functionality of the business based on the unmet demand.
        NOTE: Linear relation assumed between the unmet demand and the functionality of the business.
        """
        self.update_current_business_functionality(time_step, percent_of_met_demand, 'Infrastructure')

    def recover(self, time_step: int) -> None:
        pass

    def update_revenue(self, time_step: int) -> None:
        # Revenue at a time step is the current business functionality times the pre-disaster
        # revenue. It is overwritten (not min-ratcheted) so that a functionality recovery within
        # the same step - e.g. labor topped up from the residual employee pool - is reflected.
        self.revenue[time_step] = self.pre_disaster_revenue_per_time_step * self.business_functionality_level

    def update_customer_base(self, time_step: int, customer_base_population_ratios: dict,
                             transfer_service_models: list = None,
                             on_island_cbgs: set = None,
                             off_island_origin_id: str = None) -> None:
        transfer_service_models = transfer_service_models or []
        on_island_cbgs = on_island_cbgs or set()
        total_customer_base_ratio = 0
        for block, weight in self.parameters['VisitorHomeCBGs'].items():
            # 'Others' is a pooled off-island group with no externally supplied recovery series,
            # so it is assumed fully present and gated only on accessibility; every other CBG
            # carries the recovery ratio computed by the distribution model (0 if unknown).
            default_ratio = 1.0 if block == 'Others' else 0.0
            block_customer_ratio = customer_base_population_ratios.get(block, default_ratio)
            # On-island CBGs (in a locality) can always reach the business. Off-island CBGs
            # (externally simulated + the pooled 'Others') are gated on a functional crossing from
            # any mainland connector to the business, via the island connectivity model.
            if block not in on_island_cbgs and off_island_origin_id is not None and not is_building_accessible(
                    transfer_service_models, time_step, off_island_origin_id, self.home_component.aim_id):
                block_customer_ratio = 0
            total_customer_base_ratio += weight * block_customer_ratio
        self.customer_base_ratio[time_step] = round(total_customer_base_ratio, 5)
        self.update_current_business_functionality(time_step, total_customer_base_ratio, 'Customer Base')

    def update_current_business_functionality(self, time_step: int, updated_level: float, reason_for_drop: str, allow_increase=False) -> None:
        self.update_reason_for_drop(time_step, updated_level, reason_for_drop, allow_increase)
        self.update_business_functionality_level(time_step)
        self.update_revenue(time_step)

    def update_reason_for_drop(self, time_step: int, updated_level: float, reason_for_drop: str, allow_increase) -> None:
        for reason in self.reason_for_drop[time_step]:
            if reason['Name'] == reason_for_drop:
                if allow_increase:
                    # for reasons where functionality can improve over time (e.g. labor), take the max level; for reasons where functionality can only drop or stay the same (e.g. home component damage), take the min level.
                    reason['Level'] = max(reason['Level'], updated_level)
                else:
                    reason['Level'] = min(reason['Level'], updated_level)
                break
        else:
            self.reason_for_drop[time_step].append({'Name': reason_for_drop, 'Level': updated_level})
    
    def update_business_functionality_level(self, time_step: int) -> None:
       self.business_functionality_level = min(r['Level'] for r in self.reason_for_drop[time_step])       

    def check_trips_in_od_matrix(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel, component_ids: list[str]) -> None:
        business_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict[self.home_component.aim_id]
        for component_id in component_ids:
            component_closest_node = transfer_service_distribution_model.building_to_traffic_node_dict.get(component_id, None)
            if component_closest_node is None:
                # Off-island components have no on-island traffic node; their accessibility is
                # handled by the island connectivity model, not by a road OD trip. Skip them.
                continue
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
