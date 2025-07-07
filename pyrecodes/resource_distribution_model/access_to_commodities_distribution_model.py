from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model import ResidualDemandTrafficDistributionModel
from pyrecodes.resource_distribution_model.abstract_resource_distribution_model import AbstractResourceDistributionModel
from pyrecodes.component.component import Component
from pyrecodes.component.r2d_component import R2DBuildingWithBusiness

class AccessToCommoditiesDistributionModel(AbstractResourceDistributionModel):
    """
    AccessToCommoditiesDistributionModel checks whether a business has access to comodities provided by suppliers.
    Each business has a list of local suppliers and can also have suppliers outside the local area.
    The model is connected to the ResidualDemandTrafficDistributionModel.
    It uses the traffic flow simulator to check whether the business has access to suppliers.
    """
   
    def set_transfer_service_distribution_model(self, transfer_service_distribution_model: ResidualDemandTrafficDistributionModel) -> None:
        self.transfer_service_distribution_model = transfer_service_distribution_model
        self.check_supplier_trips_in_od_matrix()

    def check_supplier_trips_in_od_matrix(self) -> None:
        for component in self.components:
            if isinstance(component, R2DBuildingWithBusiness):
                for business in component.businesses:
                    business.check_supplier_trips_in_od_matrix(self.transfer_service_distribution_model)

    def distribute(self, time_step: int) -> None:
        self.update_access_to_suppliers(time_step,
                                        self.transfer_service_distribution_model)      

    def update_access_to_suppliers(self, time_step, transfer_service_distribution_model) -> None:
        for component in self.components:
            if isinstance(component, R2DBuildingWithBusiness):
                component.update_access_of_businesses_to_suppliers(time_step, transfer_service_distribution_model)

    def get_total_supply(self, scope: str) -> float:
        # TODO: implement this
        return 0

    def get_total_demand(self, scope: str) -> float:
        # TODO: implement this
        return 0

    def get_total_consumption(self, scope: str) -> float:
        # TODO: implement this
        return 0
      