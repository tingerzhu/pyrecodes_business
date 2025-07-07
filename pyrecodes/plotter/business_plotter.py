import matplotlib.pyplot as plt
from pyrecodes.constants import GANTT_BAR_DISTANCE, GANTT_BAR_WIDTH, GANTT_Y_LABELS
from pyrecodes.business.business import Business

class BusinessPlotter():

    def plot_business_revenue(self, business_revenue: list, business, save_fig: bool = True, show_fig: bool = False) -> None:
        """
        Plot the business revenue over time.
        """
        plt.figure()
        plt.plot(business_revenue)
        # add a shading area to show how much is the total lost revenue
        self.fill_unmet_revenue(business_revenue, plt.gca())
        plt.title(f'{business.parameters["CompanyName"]} | Revenue')
        plt.xlabel('Days after the earthquake')
        plt.ylabel('Revenue [$/day]')
        plt.grid(True)
        if save_fig:
            plt.savefig(f'business_{business.parameters["CompanyName"]}_revenue.png', dpi=300)
        if show_fig:
            plt.show()

    def plot_total_revenue(self, total_revenue: list, save_fig: bool = True) -> None:
        plt.plot(total_revenue)
        self.fill_unmet_revenue(total_revenue, plt.gca())
        plt.title(f'Total Business Revenue')
        plt.xlabel('Days after the earthquake')
        plt.ylabel('Revenue [$/day]')
        plt.grid(True)
        plt.show()
        if save_fig:
            plt.savefig(f'total_revenue.png', transparent=True, dpi=300)
        
    def fill_unmet_revenue(self, business_revenue: list, axis: plt.axis, alpha=0.2) -> None:
        """
        Fill the unmet revenue area in the plot.
        """
        time_steps = range(len(business_revenue))
        constant_revenue = [business_revenue[0] for _ in time_steps]
        axis.fill_between(time_steps, business_revenue, constant_revenue,
                            label='Unmet Revenue', alpha=alpha)
        lost_revenue = sum([max(0, abs(business_revenue[i] - constant_revenue[i])) for i in time_steps])
        axis.text(0.95, 0.05, 'Lost revenue: '+ f"{lost_revenue:,.0f}" + '$',
            transform=axis.transAxes,  # Relative to axes
            fontsize=10,
            va='bottom', ha='right',  # Align bottom-right
            bbox=dict(boxstyle='round', facecolor='lightyellow', edgecolor='gray', alpha=0.8))

    def plot_business_gantt_chart(self, business: object, x_axis_label='Days after the earthquake', save_fig: bool = True, show_fig: bool = False) -> None:
        """
        Plot the Gantt chart for the business.
        """
        reasons_for_drop = self.get_reasons_for_drop(business)
        plt.figure()
        axis_object = plt.gca()
        plt.xlabel(x_axis_label)
        for i, reason in enumerate(reasons_for_drop.values()):
            y_center = i * GANTT_BAR_DISTANCE
            for reason_time_step in reason:
                bar_height = GANTT_BAR_WIDTH * (1 - reason_time_step['Level'])  # adjust width
                Y_position = y_center - bar_height / 2 
                axis_object.broken_barh([(reason_time_step['Start'], 
                                            reason_time_step['Duration'])], 
                                            (Y_position, GANTT_BAR_WIDTH*(1-reason_time_step['Level'])),
                    edgecolor="none") 
            
        axis_object.set_yticks([(i) * GANTT_BAR_DISTANCE for i in range(len(list(reasons_for_drop.keys())))])
        y_tick_labels = [GANTT_Y_LABELS.get(reason, reason) for reason in reasons_for_drop.keys()]
        axis_object.set_yticklabels(y_tick_labels)
        plt.grid(True)
        if save_fig:
            plt.savefig(f'business_{business.parameters["CompanyName"]}_gantt_chart.png', dpi=300)
        if show_fig:
            plt.show()

    def get_reasons_for_drop(self, business: object) -> list:
        """
        Get the reasons for drop in business functionality.
        """
        reasons_for_drop = {}
        for time_step, reason_list in business.reason_for_drop.items():
            for reason in reason_list:
                if reason['Name'] not in reasons_for_drop:
                    duration = self.get_reason_for_drop_duration(reason, time_step, reasons_for_drop)
                    reasons_for_drop[reason['Name']] = [{'Start': time_step, 'Duration': duration, 'Level': reason['Level']}]
                else:
                    reasons_for_drop[reason['Name']].append({'Start': time_step, 'Duration': duration, 'Level': reason['Level']})
        return reasons_for_drop
    
    def get_reason_for_drop_duration(self, reason: dict, time_step: int, reason_for_drop: dict) -> int:
        if reason['Name'] == 'Infrastructure':
            for dummy_time_step in range(time_step + 1, len(reason_for_drop)):
                if reason['Name'] == 'Infrastructure':
                    return dummy_time_step - time_step
        else:
            return 1
    
      
    