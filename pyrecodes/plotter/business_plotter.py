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

# Revenue is stored per time step ($/time step, i.e. $/week when TIME_STEPS_IN_A_YEAR == 52),
# so the plots use it directly.

# Larger fonts across all business plots.
plt.rcParams.update({
    'font.size': 14,
    'axes.titlesize': 20,
    'axes.labelsize': 18,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 14,
})


class BusinessPlotter():

    # ------------------------------------------------------------------
    # Individual business plots
    # ------------------------------------------------------------------

    def plot_business_revenue(self, business_revenue: list, business, save_fig: bool = True, show_fig: bool = False) -> None:
        plt.figure(figsize=(14, 6))
        business_revenue = list(business_revenue)
        # Mirror the reasons-for-drop correction: the customer base can erroneously suppress
        # revenue at time step 0. Shift the whole curve up so it starts at the pre-disaster
        # revenue, matching the reasons-for-drop plot. The lost-revenue area is unchanged.
        delta_revenue = business.pre_disaster_revenue_per_time_step - business_revenue[0]
        business_revenue = [r + delta_revenue for r in business_revenue]
        plt.plot(business_revenue)
        constant_revenue = [business_revenue[0]] * len(business_revenue)
        self.fill_unmet_revenue(business_revenue, constant_revenue, plt.gca())
        plt.title(f'{business.parameters["CompanyName"]} | Revenue')
        plt.xlabel('Weeks after earthquake')
        plt.ylabel('Revenue [$/week]')
        plt.grid(True)
        if save_fig:
            plt.savefig(f'business_{business.parameters["CompanyName"]}_revenue.png', dpi=300)
        if show_fig:
            plt.show()

    def plot_business_revenue_reasons_for_drop_lines(self, business, reasons_as_lines: dict,
                                                     reasons_to_plot: list = REASON_NAMES,
                                                     show_fig: bool = True, save_fig: bool = False, linestyle: str = '--') -> None:
        plt.figure(figsize=(14, 6))
        axis_object = plt.gca()
        plt.xlabel('Weeks after earthquake')
        plt.ylabel('Revenue [$/week]')
        plt.ylim(bottom=0, top=max(max(data['Revenue']) for data in reasons_as_lines.values()) * 1.1)
        for reason_name, reason_data in reasons_as_lines.items():
            if reason_name in reasons_to_plot:
                axis_object.plot(reason_data['TimeStep'], reason_data['Revenue'],
                                 label=REASON_LABELS[reason_name], linestyle=linestyle, color=REASON_COLOR[reason_name])
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

    def plot_business_gantt_chart(self, business, x_axis_label: str = 'Weeks after earthquake',
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
        total_revenue = list(total_revenue)
        plt.plot(total_revenue)
        upper_revenue_bound = [max(total_revenue)] * len(total_revenue)
        self.fill_unmet_revenue(total_revenue, upper_revenue_bound, plt.gca())
        plt.title('Total Business Revenue')
        plt.xlabel('Weeks after earthquake')
        plt.ylabel('Revenue [$/week]')
        plt.grid(True)
        if save_fig:
            plt.savefig('total_revenue.png', transparent=True, dpi=300)
        if show_fig:
            plt.show()

    def plot_total_revenue_BI_CBI(self, total_revenue: list, total_BI: list, total_CBI: list,
                                   save_fig: bool = True, show_fig: bool = True,
                                   BI_label: str = 'BI - lost revenue from building damage: ',
                                   CBI_label: str = 'CBI - lost revenue from other causes: ') -> None:
        """
        Stack the per-time-step BI and CBI lost-revenue series (from BusinessResilienceCalculator)
        on top of the realised revenue. The BI band (building damage) sits directly above realised
        revenue; the CBI band (every other reason) stacks on top up to pre-disaster revenue.
        BI_t + CBI_t = pre-disaster revenue - realised revenue at each step.
        """
        plt.figure(figsize=(14, 6))
        total_revenue = np.asarray(total_revenue, dtype=float)
        total_BI = np.asarray(total_BI, dtype=float)
        total_CBI = np.asarray(total_CBI, dtype=float)
        plt.plot(total_revenue, color='black', linewidth=1.5, label='Realised revenue')
        bi_upper = total_revenue + total_BI
        cbi_upper = bi_upper + total_CBI  # = pre-disaster (potential) revenue
        self.fill_unmet_revenue(total_revenue, bi_upper, plt.gca(),
                                label='BI (building damage)', lost_revenue_label=BI_label,
                                text_position=(0.95, 0.05))
        self.fill_unmet_revenue(bi_upper, cbi_upper, plt.gca(),
                                label='CBI (other causes)', lost_revenue_label=CBI_label,
                                text_position=(0.95, 0.15))
        plt.plot(cbi_upper, color='gray', linestyle='--', linewidth=1, label='Pre-disaster revenue')
        plt.title('Total Business Revenue | BI vs CBI')
        plt.xlabel('Weeks after earthquake')
        plt.ylabel('Revenue [$/week]')
        # Keep the legend in the upper-right so it does not overlap the BI/CBI total-loss text boxes,
        # which are anchored in the lower-right corner (see fill_unmet_revenue text_position).
        plt.legend(loc='upper right')
        plt.grid(True)
        if save_fig:
            plt.savefig('total_revenue_BI_CBI.png', transparent=True, dpi=300)
        if show_fig:
            plt.show()

    def plot_total_reasons_for_drop_gantt(self, total_reasons_for_drop: dict,
                                          x_axis_label: str = 'Weeks after earthquake',
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
                                                    save_fig: bool = True, show_fig: bool = True,
                                                    linestyle: str = '--') -> None:
        plt.figure(figsize=(14, 6))
        axis_object = plt.gca()
        plt.xlabel('Weeks after earthquake')
        plt.ylabel('Revenue [$/week]')
        for reason_name, reason_data in total_reasons_as_lines.items():
            if reason_name in reasons_to_plot:
                axis_object.plot(reason_data['TimeStep'], reason_data['Revenue'],
                                 label=REASON_LABELS[reason_name], linestyle=linestyle, color=REASON_COLOR[reason_name])
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
                    'Revenue': business.pre_disaster_revenue_per_time_step * reason['Level'],
                }
                reasons_for_drop[reason['Name']].append(reason_dict)
            for reason_name in reasons_for_drop_names:
                if reason_name not in [r['Name'] for r in reason_list]:
                    reasons_for_drop[reason_name].append({
                        'Start': time_step, 'Duration': 1, 'Level': 1.0, 'Revenue': business.pre_disaster_revenue_per_time_step,
                    })
        # The customer base can erroneously suppress revenue at time step 0, when no disaster
        # impact should yet be felt. Shift the entire customer base curve up by the time-step-0
        # deficit so it starts at the pre-disaster revenue, matching every other reason line.
        if reasons_for_drop.get('Customer Base'):
            delta_revenue = business.pre_disaster_revenue_per_time_step - reasons_for_drop['Customer Base'][0]['Revenue']
            for reason_dict in reasons_for_drop['Customer Base']:
                reason_dict['Revenue'] += delta_revenue
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
        # Bounds are already passed in per-week ($/week), so summing them gives the weekly loss directly.
        lost_revenue = sum(max(0, abs(upper_bound[i] - lower_bound[i])) for i in time_steps)
        axis.text(
            text_position[0], text_position[1],
            lost_revenue_label + f'{lost_revenue:,.0f}$',
            transform=axis.transAxes,
            fontsize=14,
            va='bottom', ha='right',
            bbox=dict(boxstyle='round', facecolor='lightyellow', edgecolor='gray', alpha=0.8),
        )
