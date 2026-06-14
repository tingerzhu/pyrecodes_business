from pyrecodes.resource_distribution_model.utility_distribution_model import UtilityDistributionModel
from pyrecodes.resource_distribution_model.residual_employee_distribution_model_constructor import ResidualEmployeeDistributionModelConstructor
from pyrecodes.resource_distribution_model.resource_distribution_model import ResourceDistributionModel
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness


class ResidualEmployeeDistributionModel(UtilityDistributionModel):
    """
    Reassigns RESIDUAL employees - it does not assign employees to businesses from
    scratch. The baseline employee-to-business assignment is done per business by
    check_employees; this model only redistributes the spare employees left over when
    some businesses cannot operate.

    Two passes:
      1) Per-business check_employees (homes functional + accessible) sets each
         business's employees_available[t] and Labor reason for drop. While doing so,
         a business that cannot operate registers its still-reachable employees as
         residual Employee SUPPLY on their HOME buildings (residential R2D buildings).
      2) Utility-style redistribution of that residual Employee supply using the
         system matrix and the configured priority. SUPPLY comes from the employee
         homes; DEMAND comes from the business buildings (the labor shortfall set by
         Business.update_employee_demand). Business buildings never supply employees.

    After redistribution, the fraction of demand met per recipient building is read
    back from the system matrix and the received employees are routed to the
    constituent businesses, where they bump employees_available[t] and Labor.
    """

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        self.constructor = ResidualEmployeeDistributionModelConstructor()
        self.constructor.construct(resource_name, resource_parameters, components, self)
        # Multiple accessibility checkers (traffic, island connectivity) used by check_employees.
        self.transfer_service_distribution_models: list[ResourceDistributionModel] = []
        # Singular slot expected by UtilityDistributionModel's locality path-functionality logic.
        # Left as None: employee redistribution is gated by the per-business check_employees pass
        # rather than a locality-path constraint.
        self.transfer_service_distribution_model = None

    def set_transfer_service_distribution_model(self, transfer_service_distribution_model: ResourceDistributionModel) -> None:
        """
        Accept multiple transfer service models (one or more accessibility checkers
        such as ResidualDemandTrafficDistributionModel and IslandConnectivity), the
        same convention as the original EmployeeDistributionModel.
        """
        self.transfer_service_distribution_models.append(transfer_service_distribution_model)
        if hasattr(transfer_service_distribution_model, 'od_trip_checker'):
            for component in self.components:
                if isinstance(component, R2DBuildingWithBusiness):
                    for business in component.businesses:
                        business.check_employee_trips_in_od_matrix(transfer_service_distribution_model)

    def distribute(self, time_step: int) -> None:
        if not self.distribute_at_this_time_step(time_step):
            return
        self._run_check_employees(time_step)
        self._two_pass_distribute()
        self._route_received_employees(time_step)

    def _two_pass_distribute(self) -> None:
        """
        Two-pass replacement for UtilityDistributionModel.distribute's single-pass loop.
        For Employee redistribution, suppliers (home rows) and recipients (business
        rows) are different rows. Under random priority, a recipient row may be visited
        before any supplier row has been added to the supplier pool, leaving its demand
        unmet despite available supply. Fix: collect every supplier FIRST, then meet
        recipient demand in priority order.
        """
        self.fill_system_matrix()
        priority_rows, priority_types = self.get_component_priorities()

        suppliers = []
        for row_id, _ in zip(priority_rows, priority_types):
            suppliers, _ = self.add_supplier(row_id, suppliers)

        for row_id, demand_type in zip(priority_rows, priority_types):
            suppliers = self.meet_component_demand(suppliers, row_id, demand_type)

        self.update_suppliers_based_on_consumption(suppliers)

    def _run_check_employees(self, time_step: int) -> None:
        for component in self.components:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    business.check_employees(time_step, self.transfer_service_distribution_models)

    def reduce_component_supply(self, component_row_id: int, percent_of_met_demand: float) -> None:
        """
        Override: when a recipient's Employee demand is only partially met, do NOT
        invoke the demander's update_supply_based_on_unmet_demand (which is meant for
        utilities whose supply scales with consumed inputs). The received employee
        count is applied in _route_received_employees.
        """
        return

    def _route_received_employees(self, time_step: int) -> None:
        matrix = self.system_matrix.matrix
        for row_id, component in enumerate(self.components):
            if not isinstance(component, R2DBuildingWithBusiness):
                continue
            demand = matrix[row_id, self.system_matrix.DEMAND_COL_ID]
            met_fraction = matrix[row_id, self.system_matrix.DEMAND_MET_COL_ID]
            n_extra = demand * met_fraction
            if n_extra > 0:
                component.distribute_received_employees(time_step, n_extra)

    def get_total_supply(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_supply = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    total_supply += business.get_employee_supply()
        return total_supply

    def get_total_demand(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_demand = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    total_demand += business.get_employee_demand()
        return total_demand

    def get_total_consumption(self, scope='All') -> float:
        components_to_include = self.get_scope(scope)
        total_consumption = 0
        for component in components_to_include:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    total_consumption += business.get_employee_consumption()
        return total_consumption
