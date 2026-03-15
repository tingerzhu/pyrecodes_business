import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as mcm
import numpy as np
from pyrecodes.constants import GANTT_BAR_DISTANCE, GANTT_BAR_WIDTH

REASON_LABELS = {
    'Home Component Functionality': 'Building damage',
    'Infrastructure': 'Infrastructure outage',
    'Labor': 'Employee availability',
    'LocalSuppliers': 'Access to local suppliers',
    'Customer Base': 'Customer base',
}

REASON_COLOR = {
    'Home Component Functionality': 'blue',
    'Infrastructure': 'orange',
    'Labor': 'green',
    'LocalSuppliers': 'red',
    'Customer Base': 'purple',
}

REASON_NAMES = ['Home Component Functionality', 'LocalSuppliers', 'Infrastructure', 'Labor', 'Customer Base']


class BusinessPlotter():

    # ------------------------------------------------------------------
    # Individual business plots
    # ------------------------------------------------------------------

    def plot_business_revenue(self, business_revenue: list, business, save_fig: bool = True, show_fig: bool = False) -> None:
        plt.figure(figsize=(14, 6))
        plt.plot(business_revenue)
        constant_revenue = [business_revenue[0]] * len(business_revenue)
        self.fill_unmet_revenue(business_revenue, constant_revenue, plt.gca())
        plt.title(f'{business.parameters["CompanyName"]} | Revenue')
        plt.xlabel('Days after the earthquake')
        plt.ylabel('Revenue [$/day]')
        plt.grid(True)
        if save_fig:
            plt.savefig(f'business_{business.parameters["CompanyName"]}_revenue.png', dpi=300)
        if show_fig:
            plt.show()

    def plot_business_revenue_reasons_for_drop_lines(self, business, reasons_as_lines: dict,
                                                     reasons_to_plot: list = REASON_NAMES,
                                                     show_fig: bool = True, save_fig: bool = False) -> None:
        plt.figure(figsize=(14, 6))
        axis_object = plt.gca()
        plt.xlabel('Days after the earthquake')
        plt.ylabel('Revenue [$/day]')
        plt.ylim(bottom=0, top=max(max(data['Revenue']) for data in reasons_as_lines.values()) * 1.1)
        for reason_name, reason_data in reasons_as_lines.items():
            if reason_name in reasons_to_plot:
                axis_object.plot(reason_data['TimeStep'], reason_data['Revenue'],
                                 label=REASON_LABELS[reason_name], linestyle='--', color=REASON_COLOR[reason_name])
        plt.title(f'{business.parameters["CompanyName"]} | Reasons for Revenue Drop')
        plt.legend(loc='lower right')
        plt.grid(True)
        if save_fig:
            plt.savefig(f'business_{business.parameters["CompanyName"]}_revenue_reasons.png', dpi=300)
        if show_fig:
            plt.show()

    def plot_reasons_for_revenue_drop_as_lines(self, axis_object: plt.axes, business) -> None:
        reasons_for_drop = self.get_reasons_for_drop(business)
        reasons_as_lines = self.get_reasons_for_drop_as_lines(reasons_for_drop)
        for reason_name, reason_data in reasons_as_lines.items():
            axis_object.plot(reason_data['TimeStep'], reason_data['Revenue'],
                             label=reason_name, linestyle='--', color=REASON_COLOR[reason_name])

    def plot_business_gantt_chart(self, business, x_axis_label: str = 'Days after the earthquake',
                                  save_fig: bool = True, show_fig: bool = False) -> None:
        reasons_for_drop = self.get_reasons_for_drop(business)
        plt.figure()
        axis_object = plt.gca()
        plt.xlabel(x_axis_label)
        for i, reason in enumerate(reasons_for_drop.values()):
            y_center = i * GANTT_BAR_DISTANCE
            for reason_time_step in reason:
                bar_height = GANTT_BAR_WIDTH * (1 - reason_time_step['Level'])
                Y_position = y_center - bar_height / 2
                axis_object.broken_barh(
                    [(reason_time_step['Start'], reason_time_step['Duration'])],
                    (Y_position, GANTT_BAR_WIDTH * (1 - reason_time_step['Level'])),
                    edgecolor='none',
                )
        axis_object.set_yticks([i * GANTT_BAR_DISTANCE for i in range(len(reasons_for_drop))])
        axis_object.set_yticklabels([REASON_LABELS.get(r, r) for r in reasons_for_drop.keys()])
        plt.grid(True)
        if save_fig:
            plt.savefig(f'business_{business.parameters["CompanyName"]}_gantt_chart.png', dpi=300)
        if show_fig:
            plt.show()

    # ------------------------------------------------------------------
    # Total / aggregate plots
    # ------------------------------------------------------------------

    def plot_total_revenue(self, total_revenue: list, save_fig: bool = True, show_fig: bool = True) -> None:
        plt.figure(figsize=(14, 6))
        plt.plot(total_revenue)
        upper_revenue_bound = [max(total_revenue)] * len(total_revenue)
        self.fill_unmet_revenue(total_revenue, upper_revenue_bound, plt.gca())
        plt.title('Total Business Revenue')
        plt.xlabel('Days after the earthquake')
        plt.ylabel('Revenue [$/day]')
        plt.grid(True)
        if save_fig:
            plt.savefig('total_revenue.png', transparent=True, dpi=300)
        if show_fig:
            plt.show()

    def plot_total_revenue_BI_CBI(self, total_revenue: list, total_revenue_no_building_damage: list,
                                   save_fig: bool = True, show_fig: bool = True) -> None:
        plt.figure(figsize=(14, 6))
        plt.plot(total_revenue)
        upper_CBI_bound = [max(total_revenue)] * len(total_revenue)
        lower_CBI_bound = [
            total_revenue_no_building_damage[i] + (upper_CBI_bound[i] - max(total_revenue_no_building_damage))
            for i in range(len(total_revenue))
        ]
        self.fill_unmet_revenue(lower_CBI_bound, upper_CBI_bound, plt.gca(),
                                lost_revenue_label='Lost revenue with no building damage (CBI): ')
        self.fill_unmet_revenue(total_revenue, lower_CBI_bound, plt.gca(),
                                lost_revenue_label='Lost revenue with building damage (BI): ',
                                text_position=(0.95, 0.15))
        plt.title('Total Business Revenue | BI vs CBI')
        plt.xlabel('Days after the earthquake')
        plt.ylabel('Revenue [$/day]')
        plt.grid(True)
        if save_fig:
            plt.savefig('total_revenue_BI_CBI.png', transparent=True, dpi=300)
        if show_fig:
            plt.show()

    def plot_total_reasons_for_drop_gantt(self, total_reasons_for_drop: dict,
                                          x_axis_label: str = 'Days after the earthquake',
                                          save_fig: bool = True, show_fig: bool = False) -> None:
        plt.figure(figsize=(14, 6))
        axis_object = plt.gca()
        plt.xlabel(x_axis_label)
        for i, reason in enumerate(total_reasons_for_drop.values()):
            y_center = i * GANTT_BAR_DISTANCE
            for reason_time_step in reason:
                bar_height = GANTT_BAR_WIDTH * reason_time_step['Drop']
                Y_position = y_center - bar_height / 2
                axis_object.broken_barh(
                    [(reason_time_step['Start'], reason_time_step['Duration'])],
                    (Y_position, GANTT_BAR_WIDTH * reason_time_step['Drop']),
                    edgecolor='none',
                )
        axis_object.set_yticks([i * GANTT_BAR_DISTANCE for i in range(len(total_reasons_for_drop))])
        axis_object.set_yticklabels([REASON_LABELS.get(r, r) for r in total_reasons_for_drop.keys()])
        plt.grid(True)
        if save_fig:
            plt.savefig('total_gantt_chart.png', transparent=True, dpi=300)
        if show_fig:
            plt.show()
    
    def plot_total_revenue_reasons_for_drop_lines(self, total_reasons_as_lines: dict,
                                                  reasons_to_plot: list = REASON_NAMES,
                                                    save_fig: bool = True, show_fig: bool = True) -> None:
        plt.figure(figsize=(14, 6))
        axis_object = plt.gca()
        plt.xlabel('Days after the earthquake')
        plt.ylabel('Revenue [$/day]')
        for reason_name, reason_data in total_reasons_as_lines.items():
            if reason_name in reasons_to_plot:
                axis_object.plot(reason_data['TimeStep'], reason_data['Revenue'],
                                 label=REASON_LABELS[reason_name], linestyle='--', color=REASON_COLOR[reason_name])
        plt.legend(loc='lower right')
        plt.grid(True)
        if save_fig:
            plt.savefig('total_revenue_reasons.png', transparent=True, dpi=300)
        if show_fig:
            plt.show()

    def plot_lost_revenue_to_repair_cost_histogram(self, ratios: dict,
                                                    bins: int = 20,
                                                    save_fig: bool = True,
                                                    show_fig: bool = True) -> None:
        ratio_values = list(ratios.values())
        plt.figure(figsize=(14, 6))
        plt.hist(ratio_values, bins=bins, edgecolor='black', alpha=0.75)
        plt.axvline(np.median(ratio_values), color='red', linestyle='--',
                    label=f'Median: {np.median(ratio_values):.2f}')
        plt.axvline(np.mean(ratio_values), color='orange', linestyle='--',
                    label=f'Mean: {np.mean(ratio_values):.2f}')
        plt.axvline(0.1, color='blue', linestyle='--', label='Insurance baseline: 0.1')
        plt.xlabel('Ratio of lost revenue to repair cost')
        plt.ylabel('Number of businesses')
        plt.legend()
        plt.grid(True, alpha=0.3)
        if save_fig:
            plt.savefig('lost_revenue_to_repair_cost_histogram.png', dpi=300, transparent=True)
        if show_fig:
            plt.show()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def get_reasons_for_drop(self, business, reasons_for_drop_names: list = REASON_NAMES) -> dict:
        reasons_for_drop = {key: [] for key in reasons_for_drop_names}
        all_time_steps = list(business.revenue.keys())
        for time_step, reason_list in zip(all_time_steps, business.reason_for_drop.values()):
            for reason in reason_list:
                reason_dict = {
                    'Start': time_step, 'Duration': 1,
                    'Level': reason['Level'],
                    'Revenue': business.pre_disaster_daily_revenue * reason['Level'],
                }
                reasons_for_drop[reason['Name']].append(reason_dict)
            for reason_name in reasons_for_drop_names:
                if reason_name not in [r['Name'] for r in reason_list] and reason_name != 'Infrastructure':
                    reasons_for_drop[reason_name].append({
                        'Start': time_step, 'Duration': 1, 'Level': 1.0, 'Revenue': business.pre_disaster_daily_revenue,
                    })
        # Reconstruct Infrastructure from contiguous outage windows (handles sparse time steps)
        outage_start = None
        outage_end = 1
        reasons_for_drop['Infrastructure'] = []
        for time_step, reason_list in zip(all_time_steps, business.reason_for_drop.values()):
            reasons_for_drop['Infrastructure'].append({
                'Start': time_step, 'Duration': 1, 'Level': 1.0, 'Revenue': business.pre_disaster_daily_revenue,
            })
            if 'Infrastructure' in [r['Name'] for r in reason_list]:
                outage_end = time_step
                if outage_start is None:
                    outage_start = time_step
        if outage_start is not None:
            for time_step in range(outage_start, outage_end + 1):
                reasons_for_drop['Infrastructure'][time_step] = {
                    'Start': time_step, 'Duration': 1, 'Level': 0.0, 'Revenue': 0.0,
                }
        return reasons_for_drop

    def get_reasons_for_drop_as_lines(self, reasons_for_drop: dict) -> dict:
        reasons_as_lines = {key: {'TimeStep': [], 'Level': [], 'Revenue': []} for key in reasons_for_drop}
        for reason_name, reason_list in reasons_for_drop.items():
            for reason in reason_list:
                reasons_as_lines[reason_name]['TimeStep'].append(reason['Start'])
                reasons_as_lines[reason_name]['Level'].append(reason['Level'])
                reasons_as_lines[reason_name]['Revenue'].append(reason['Revenue'])
        return reasons_as_lines

    def get_total_reasons_for_drop(self, all_businesses: list,
                                   reasons_for_drop_names: list = REASON_NAMES) -> dict:
        all_business_reasons = [self.get_reasons_for_drop(b, reasons_for_drop_names) for b in all_businesses]
        total_reasons_for_drop = {key: [] for key in reasons_for_drop_names}
        for time_step in range(len(all_businesses[0].revenue)):
            for reason_name in reasons_for_drop_names:
                entry = {'Start': time_step, 'Duration': 1, 'Level': 0, 'Revenue': 0}
                for business_reasons in all_business_reasons:
                    if reason_name in business_reasons:
                        entry['Revenue'] += business_reasons[reason_name][time_step]['Revenue']
                total_reasons_for_drop[reason_name].append(entry)
        return total_reasons_for_drop
    
    def get_total_reasons_for_drop_as_lines(self, total_reasons_for_drop: dict) -> dict:
        total_reasons_as_lines = {key: {'TimeStep': [], 'Level': [], 'Revenue': []} for key in total_reasons_for_drop}
        for reason_name, reason_list in total_reasons_for_drop.items():
            for reason in reason_list:
                total_reasons_as_lines[reason_name]['TimeStep'].append(reason['Start'])
                total_reasons_as_lines[reason_name]['Level'].append(reason['Level'])
                total_reasons_as_lines[reason_name]['Revenue'].append(reason['Revenue'])
        return total_reasons_as_lines

    def calculate_total_revenue(self, business_resilience_calculator) -> np.ndarray:
        total_revenue = np.zeros(len(business_resilience_calculator.business_revenue[
            business_resilience_calculator.businesses[0]]))
        for business in business_resilience_calculator.businesses:
            total_revenue += np.array(business_resilience_calculator.business_revenue[business])
        return total_revenue

    def calculate_total_revenue_no_building_damage(self, business_resilience_calculator) -> np.ndarray:
        total_revenue = np.zeros(len(business_resilience_calculator.business_revenue[
            business_resilience_calculator.businesses[0]]))
        for business in business_resilience_calculator.businesses:
            unaffected = all(
                r['Level'] >= 1.0
                for reasons in business.reason_for_drop.values()
                for r in reasons
                if r['Name'] == 'Home Component Functionality'
            )
            if unaffected:
                total_revenue += np.array(business_resilience_calculator.business_revenue[business])
        return total_revenue

    def fill_unmet_revenue(self, lower_bound: list, upper_bound: list, axis: plt.axes,
                           label: str = 'Unmet Revenue', alpha: float = 0.2,
                           lost_revenue_label: str = 'Lost revenue: ',
                           text_position: tuple = (0.95, 0.05)) -> None:
        time_steps = range(len(lower_bound))
        axis.fill_between(time_steps, lower_bound, upper_bound, label=label, alpha=alpha)
        lost_revenue = sum(max(0, abs(upper_bound[i] - lower_bound[i])) for i in time_steps)
        axis.text(
            text_position[0], text_position[1],
            lost_revenue_label + f'{lost_revenue:,.0f}$',
            transform=axis.transAxes,
            fontsize=10,
            va='bottom', ha='right',
            bbox=dict(boxstyle='round', facecolor='lightyellow', edgecolor='gray', alpha=0.8),
        )
