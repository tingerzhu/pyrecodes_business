from pyrecodes.resilience_calculator.resilience_calculator import ResilienceCalculator
from pyrecodes.system.system import System
from pyrecodes.component.r2d_component import R2DBuilding


class BusinessResilienceCalculator(ResilienceCalculator):
    """
    Class to calculate the resilience of a business.
    """

    def __init__(self, parameters: dict) -> None:
        self.businesses = []
        self.business_revenue = {}
        self.customer_base = {}
        self.business_functionality = {}

    def __str__(self):
        return 'Business Resilience Calculator \n'
    
    def get_business_information(self, system: System):
        for component in system.components:
            if hasattr(component, 'businesses'):
                for business in component.businesses:
                    self.businesses.append(business)

    def calculate_resilience(self):
        self.calculate_business_revenue()

    def update(self, system: System):
        self.update_customer_base(system)
        self.record_business_functionality()
    
    def calculate_business_revenue(self):
        for business in self.businesses:
            base_revenue = business.parameters['SalesVolume'] / 365     # convert to daily revenue
            self.business_revenue[business] = base_revenue * self.business_functionality[business]
    
    def update_customer_base(self, system: System):
        CBG_population_recovery_level = self.get_CBG_population_recovery_level(system)
        for business in self.businesses:
            business_customer_base = 0
            for CBG in business.parameters['VisitorHomeCBGs'].keys():
                if CBG == 'Others':
                    business_customer_base += business.parameters['VisitorHomeCBGs'][CBG]
                else:
                    business_customer_base += business.parameters['VisitorHomeCBGs'][CBG] * CBG_population_recovery_level[CBG]
            self.customer_base[business] = business_customer_base

    def get_CBG_population_recovery_level(self, system: System):
        CBG_population_before = {}
        CBG_population_current = {}
        CBG_population_recovery_level = {}
        for component in system.components:
            if isinstance(component, R2DBuilding):
                CBG = component.general_information['CenterBlockGroup']
                if CBG not in CBG_population_before:
                    CBG_population_before[CBG] = component.supply['Supply']['Shelter'].initial_amount
                    CBG_population_current[CBG] = component.supply['Supply']['Shelter'].current_amount
                else:
                    CBG_population_before[CBG] += component.supply['Supply']['Shelter'].initial_amount
                    CBG_population_current[CBG] += component.supply['Supply']['Shelter'].current_amount
        for CBG in CBG_population_before.keys():
            if CBG_population_before[CBG] > 0:
                CBG_population_recovery_level[CBG] = CBG_population_current[CBG] / CBG_population_before[CBG]
            else:
                CBG_population_recovery_level[CBG] = 1
        return CBG_population_recovery_level
    
    def record_business_functionality(self):
        for business in self.businesses:
            if business.business_functionality_level > self.customer_base[business]:
                self.business_functionality[business] = business.self.customer_base[business]
            else:
                self.business_functionality[business] = business.business_functionality_level
