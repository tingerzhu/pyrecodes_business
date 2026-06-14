import numpy as np
from pyrecodes.resilience_calculator.resilience_calculator import ResilienceCalculator

class ReCoDeSCalculator(ResilienceCalculator):
    """
    Resilience calculator class that assesses the resilience of a system based on the ReCoDeS framework.    
    """

    def __init__(self, parameters: dict) -> None:   
        self.system_supply = {}
        self.system_demand = {}
        self.system_consumption = {}
        self.resource_names = parameters["Resources"]
        self.scope = parameters["Scope"]
        for resource_name in self.resource_names:
            self.system_supply[resource_name] = []
            self.system_demand[resource_name] = []
            self.system_consumption[resource_name] = []
    
    def __str__(self):
        lack_of_resilience = self.calculate_resilience()
        output = 'Re-CoDeS Resilience Calculator \n'
        output += 'Scope: ' + self.scope + '\n'
        output += '----------------------------- \n'
        output += 'Total unmet demand: \n'
        for resource_name, value in lack_of_resilience.items():
            output += ' ' + resource_name + ': ' + str(value) + '\n'
        return output

    def calculate_resilience(self) -> dict:
        self.lack_of_resilience = dict()
        for resource_name in self.resource_names:
            self.lack_of_resilience[resource_name] = np.sum(
                np.asarray(self.system_demand[resource_name]) - np.asarray(self.system_consumption[resource_name]))
        return self.lack_of_resilience

    def update(self, system):
        resources = system.resources
        for resource_name, resource_parameters in resources.items():
            if resource_name in self.resource_names:
                model = resource_parameters['DistributionModel']
                # Resources with sparse DistributionTimeStepping (e.g. water distributed every few
                # steps) only have a meaningful supply/demand/consumption on the steps they are
                # actually distributed; the getters report the not-distributed state in between.
                # Hold the last distributed value on those steps so the recorded series reflects the
                # state since the last distribution instead of zig-zagging to/from zero.
                distributed = getattr(model, 'distribute_at_this_time_step',
                                      lambda time_step: True)(system.time_step)
                self.append_or_hold(self.system_supply[resource_name], model.get_total_supply, distributed)
                self.append_or_hold(self.system_demand[resource_name], model.get_total_demand, distributed)
                self.append_or_hold(self.system_consumption[resource_name], model.get_total_consumption, distributed)

    def append_or_hold(self, series: list, getter, distributed: bool) -> None:
        """Append the freshly queried value when the resource is distributed this step (or when there
        is no prior value); otherwise carry forward the value from the last distribution."""
        if distributed or not series:
            series.append(getter(scope=self.scope))
        else:
            series.append(series[-1])