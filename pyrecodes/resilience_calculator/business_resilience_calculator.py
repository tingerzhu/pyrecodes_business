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
        self.calculate_BI_CBI()
        self.calculate_lost_revenue_to_repair_cost_ratios()

    def calculate_BI_CBI(self):
        """
        Decompose lost revenue, per business and PER TIME STEP, into:
          BI  (Business Interruption)            - lost revenue due to building damage alone
          CBI (Contingent Business Interruption) - additional lost revenue due to every other reason

        Every reason's level changes from step to step, so the split is recomputed at each time
        step. At time step t, reading both quantities from the SAME reason_for_drop[t] entry so
        they always refer to the same step:
            f_building = the 'Home Component Functionality' reason level (1.0 if undamaged)
            f_total    = min over ALL reasons at t (= business_functionality_level, what revenue
                         reflects, so f_total <= f_building)
            BI_t  = pre_disaster_rev * (1 - f_building)
            CBI_t = pre_disaster_rev * (f_building - f_total)
        so BI_t + CBI_t = pre_disaster_rev * (1 - f_total) = total lost revenue that step. When
        building damage is the binding constraint CBI_t = 0 (all loss is BI); when the building is
        undamaged BI_t = 0 (all loss is CBI); otherwise the loss is split. Results are summed
        across businesses into per-time-step series (lost revenue, $/time step).
        """
        time_steps = sorted(self.businesses[0].reason_for_drop.keys())
        n = len(time_steps)
        self.total_BI = np.zeros(n)
        self.total_CBI = np.zeros(n)
        self.potential_revenue = sum(b.pre_disaster_revenue_per_time_step for b in self.businesses)
        for business in self.businesses:
            pre = business.pre_disaster_revenue_per_time_step
            for i, t in enumerate(time_steps):
                reasons = business.reason_for_drop.get(t, [])
                f_building = next((r['Level'] for r in reasons
                                   if r['Name'] == 'Home Component Functionality'), 1.0)
                f_total = min((r['Level'] for r in reasons), default=1.0)
                total_loss = pre * (1.0 - f_total)
                # Building's standalone loss, capped at total loss (guards against f_building <
                # f_total, keeping BI, CBI >= 0 and BI + CBI = total loss at every step).
                bi = min(pre * (1.0 - f_building), total_loss)
                self.total_BI[i] += bi
                self.total_CBI[i] += total_loss - bi

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
                self.business_revenue[business].append(business.pre_disaster_revenue_per_time_step * business_functionality)
    
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
                    CBG_availability = self.current_CBG_population.get(CBG, 0) / self.initial_CBG_population.get(CBG, 1)
                    business_customer_base_availability += business.parameters['VisitorHomeCBGs'][CBG] * CBG_availability
            self.customer_base[business] = round(business_customer_base_availability, 5)
            business.update_current_business_functionality(self.customer_base[business], 'Customer Base')
               
    def record_business_functionality(self):
        for business in self.businesses:
            self.business_functionality[business].append(business.business_functionality_level)

    def get_repair_cost(self, business) -> float:
        home = business.home_component
        loss_ratio = getattr(home, 'loss_ratio', 0.0)
        replacement_cost = home.general_information.get('ReplacementCost', 0.0)
        return loss_ratio * replacement_cost
 
    def calculate_business_lost_revenue(self, business) -> float:
        pre_disaster = business.pre_disaster_revenue_per_time_step
        revenue_series = self.business_revenue.get(business, [])
        return sum(max(0, pre_disaster - rev) for rev in revenue_series)
 
    def calculate_lost_revenue_to_repair_cost_ratios(self) -> None:
        self.lost_revenue = {}
        self.repair_cost = {}
        self.lost_revenue_to_repair_cost_ratio = {}
 
        for business in self.businesses:
            lost = self.calculate_business_lost_revenue(business)
            cost = self.get_repair_cost(business)
            self.lost_revenue[business] = lost
            self.repair_cost[business] = cost
            if cost > 0:
                self.lost_revenue_to_repair_cost_ratio[business] = lost / cost
