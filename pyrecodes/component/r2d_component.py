from pyrecodes.component.standard_irecodes_component import StandardiReCoDeSComponent
from pyrecodes.component.component import Component

class R2DComponent(StandardiReCoDeSComponent):
    """
    Class used to simulate components created using R2D outputs.

    Note that SimCenter's infrastructure simulators (REWET, residual demand) only work with R2DComponent objects.
    """
    def update(self, time_step: int) -> None:
        """
        Extend the parent method to update the R2D dictionary used to interface pyrecodes with SimCenter's infrastructure simulators.
        """
        super().update(time_step)
        self.update_r2d_dict()

    def update_r2d_dict(self, demand_types=[StandardiReCoDeSComponent.DemandTypes.OPERATION_DEMAND.value, StandardiReCoDeSComponent.DemandTypes.RECOVERY_DEMAND.value]) -> None:
        """
        Update the R2D dictionary with the current resource demand of the component. SimCenter's infrastructure simulators get component's demand from this dictionary.
        """
        for demand_type in demand_types:
            for resource in self.demand[demand_type].values():
                self.general_information[demand_type][resource.name] = resource.current_amount

class R2DTransportationComponent(R2DComponent):
    """
    Subclass used to identify transportation components in a system. For now that's the only purpose.

    """

    def update_r2d_dict(self) -> None:
        """
        Update the resource-to-damage dictionary based on the current damage level of the pipe.
        """
        self.general_information['FunctionalityLevel'] = self.functionality_level

class R2DBridge(R2DTransportationComponent):
    """
    Subclass used to identify R2D Bridges in a system. For now that's the only purpose.

    **TODO**: Add specific bridge methods and attributes. Future work.
    """
    pass

class R2DRoadway(R2DTransportationComponent):
    """
    Subclass used to identify R2D Roadways in a system. For now that's the only purpose.

    **TODO**: Add specific roadway methods and attributes. Future work.
    """
    pass

class R2DTunnel(R2DTransportationComponent):
    """
    Subclass used to identify R2D Tunnels in a system. For now that's the only purpose.

    **TODO**: Add specific tunnel methods and attributes. Future work.
    """
    pass

class R2DPipe(R2DComponent):
    """
    Subclass representing pipes in a water distribution system defined using the R2D files as inputs.
    """

    def __init__(self) -> None:
        super().__init__()
        self.damage_information = {'Location': [], 'Type': []}
        self.general_information = {'Status': 'OPEN'}

    def update_r2d_dict(self) -> None:
        """
        Extend the parent method to update the functionality parameter of an R2DPipe in the R2D dictionary based on its functionality level.
        """
        super().update_r2d_dict()
        if self.functionality_level < 1.0:
            self.general_information['Status'] = 'CLOSED'
        elif self.functionality_level == 1.0:
            self.general_information['Status'] = 'OPEN'
            self.damage_information  = {'Location': [], 'Type': []}

class R2DBuilding(R2DComponent):
    """
    Class used to represent buildings in a system when using the R2D files as inputs.
    """

    def __init__(self) -> None:
        super().__init__()
        self.general_information = {'PopulationRatio': 1.0}

    def update_r2d_dict(self):
        """
        Extend the parent method to update the ratio of the population in the building at a time step in the R2D dictionary based on the functionality level.
        The population ratio is used by SimCenter infrastructure simulators (residual demand) to calculate the demand for resources.
        """
        super().update_r2d_dict()
        self.general_information['PopulationRatio'] = self.functionality_level

class R2DBuildingWithBusiness(R2DBuilding):
    """
    Class used to represent buildings with businesses in a system when using the R2D files as inputs.
    """

    def update(self, time_step: int) -> None:
        """
        Extend the parent method to update the R2D dictionary used to interface pyrecodes with SimCenter's infrastructure simulators.
        """
        super().update(time_step)
        self.update_businesses(time_step)

    def update_businesses(self, time_step: int) -> None:
        for business in self.businesses:
            business.update(time_step)

    def update_supply_based_on_unmet_demand(self, percent_of_met_demand, time_step):
        super().update_supply_based_on_unmet_demand(percent_of_met_demand)
        self.update_businesses_based_on_unmet_demand(time_step, percent_of_met_demand)

    def update_businesses_based_on_unmet_demand(self, time_step, percent_of_met_demand):
        """
        Update the businesses based on the unmet demand of the building.
        """
        for business in self.businesses:
            business.update_functionality_based_on_unmet_demand(time_step, percent_of_met_demand)

    def map_building_to_businesses(self, components: list[Component]) -> None:
        """
        Map a building to a business.
        """
        for business in self.businesses:
            business.set_employee_homes(components)

    def recover(self, time_step):
        super().recover(time_step)
        for business in self.businesses:
            business.recover(time_step)

    def update_access_of_businesses_to_suppliers(self, time_step, transfer_service_distribution_model) -> None:
        # there is no need to have transfer_service_distribution_model as input here, change the code to reference the model in the business class as attribute. TODO: Implement later.
        for business in self.businesses:
            business.update_access_to_suppliers(time_step, transfer_service_distribution_model)

    def update_business_customer_base(self, time_step: int, current_block_population_ratios: dict) -> None:
        for business in self.businesses:
            business.update_customer_base(time_step, current_block_population_ratios) 