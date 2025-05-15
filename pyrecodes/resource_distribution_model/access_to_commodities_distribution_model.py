from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model import ResidualDemandTrafficDistributionModel
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness

class AccessToCommoditiesDistributionModel(ResidualDemandTrafficDistributionModel):
    """
    AccessToCommoditiesDistributionModel checks whether a business has access to comodities provided by suppliers.
    Each business has a list of local suppliers and can also have suppliers outside the local area.
    The model builds on the ResidualDemandTrafficDistributionModel, but it is not a traffic model.
    It uses the traffic flow simulator to check whether the business has access to suppliers.
    """

    def __init__(self, resource_name: str, resource_parameters: dict, components: list[Component]):
        super().__init__(resource_name, resource_parameters, components)
        
    def distribute(self, time_step: int) -> None:
        super().distribute(time_step)
        self.update_access_to_suppliers()

    def update_access_to_suppliers(self) -> None:        
        for component in self.components:
            # TODO: @Tinger please check this condition
            if isinstance(component, R2DBuildingWithBusiness):
                component.update_access_of_businesses_to_suppliers(self.building_to_traffic_node_dict, self.travel_times[-1], self.travel_time_change)  
                # TODO: @Tinger please add this method to the R2DBuildingWithBusiness class
                # check out the update_buildings_traffic_situation method in the ResidualDemandTrafficDistributionModel
                # once you have the travel time change factor for traveling from the business to all the supplier
                # see if any one of those is below the cutoff threshold and that will give you the access to suppliers
                # we might need to modify the od matrix to include the suppliers as well
                # component.update_access_of_businesses_to_suppliers(self.travel_times[-1])

    
      