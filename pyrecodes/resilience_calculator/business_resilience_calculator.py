from pyrecodes.resilience_calculator.resilience_calculator import ResilienceCalculator
from pyrecodes.system.system import System
from pyrecodes.component.r2d_component import R2DBuilding
import numpy as np

class BusinessResilienceCalculator(ResilienceCalculator):
    """
    Class to calculate the resilience of a business.
    """

    def __init__(self, parameters: dict) -> None:
        self.businesses = []
        self.business_revenue = {}
        self.components_in_CBG = {}
        self.initial_CBG_population = {}
        self.current_CBG_population = {}
        self.customer_base = {}
        self.business_functionality = {}

    def __str__(self):
        return 'Business Resilience Calculator \n'
    
    def get_business_information(self, system: System):
        if len(self.businesses) == 0:
            for component in system.components:
                if hasattr(component, 'businesses'):
                    for business in component.businesses:
                        self.businesses.append(business)
                        self.business_functionality[business] = []
                        self.business_revenue[business] = []

    def calculate_resilience(self):
        self.calculate_business_revenue()
        self.calculate_total_lost_revenue()

    def calculate_total_lost_revenue(self):
        self.total_revenue = np.zeros(len(self.business_revenue[self.businesses[0]]))
        for business in self.businesses:
            self.total_revenue += np.array(self.business_revenue[business])

    def update(self, system: System):
        self.get_business_information(system)
        # self.update_customer_base(system)
        self.record_business_functionality()
    
    def calculate_business_revenue(self):
        for business in self.businesses:
            for business_functionality in self.business_functionality[business]:                
                base_revenue = business.parameters['SalesVolume'] / 365     # convert to daily revenue
                self.business_revenue[business].append(base_revenue * business_functionality)
    
    def update_customer_base(self, system: System):
        if len(self.components_in_CBG) == 0:
            self.get_components_in_CBG(system)
            self.set_initial_CBG_population(system)
        self.update_CBG_population()
        self.update_business_customer_base()

    def get_components_in_CBG(self, system: System):
        for component in system.components:
            if isinstance(component, R2DBuilding):
                component_CBG = component.general_information['CensusBlockGroup']
                if component_CBG not in self.components_in_CBG:
                    self.components_in_CBG[component_CBG] = [component]
                else:
                    self.components_in_CBG[component_CBG].append(component)

    def set_initial_CBG_population(self, system: System):
        for CBG in self.components_in_CBG.keys():
            initial_CBG_population = 0
            for component in self.components_in_CBG[CBG]:
                initial_CBG_population += component.supply['Supply']['Shelter'].initial_amount
            self.initial_CBG_population[CBG] = initial_CBG_population

    def update_CBG_population(self):
        for CBG in self.components_in_CBG.keys():
            current_CBG_population = 0
            for component in self.components_in_CBG[CBG]:
                current_CBG_population += component.supply['Supply']['Shelter'].current_amount
            self.current_CBG_population[CBG] = current_CBG_population
           
    def update_business_customer_base(self):
        for business in self.businesses:
            business_customer_base_availability = 0
            for CBG in business.parameters['VisitorHomeCBGs'].keys():
                if CBG == 'Others':
                    business_customer_base_availability += business.parameters['VisitorHomeCBGs'][CBG]
                else:
                    CBG_availability = self.current_CBG_population.get(CBG, 10) / self.initial_CBG_population.get(CBG, 1)
                    if CBG_availability == 10:
                        print(f"Warning: CBG {CBG} not found in current CBG population.")
                        CBG_availability = 0
                    business_customer_base_availability += business.parameters['VisitorHomeCBGs'][CBG] * CBG_availability
            self.customer_base[business] = round(business_customer_base_availability, 5)
            business.update_current_business_functionality(self.customer_base[business], 'Customer Base')
               
    def record_business_functionality(self):
        for business in self.businesses:
            self.business_functionality[business].append(business.business_functionality_level)
