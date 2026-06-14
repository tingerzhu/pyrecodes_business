INCH_TO_MILE = 63360
FEET_TO_MILE = 5280
METER_TO_MILE = 1609.34
SECONDS_IN_TIME_STEP = 3600

# --- Business revenue time resolution ----------------------------------------------------
# A business' SalesVolume is an annual figure. The revenue earned per simulation time step is
# SalesVolume / TIME_STEPS_IN_A_YEAR. Single knob for the revenue time resolution:
# 52 -> weekly time steps; 365 -> daily time steps.
TIME_STEPS_IN_A_YEAR = 52

GANTT_BAR_DISTANCE = 10
GANTT_BAR_WIDTH = 5
LOR_ALPHA = 0.2
DAMAGE_LEVEL_TOLERANCE = 1e-5
ALL_RECOVERY_ACTIVITIES_COLORS = {'RapidInspection': 'lightblue',
                                    'Financing': 'orange',
                                    'ContractorMobilization': 'springgreen',
                                    'SitePreparation': 'purple',
                                    'CleanUp': 'yellow',
                                    'DetailedInspection': 'tomato',
                                    'ArchAndEngDesign': 'pink',
                                    'Permitting': 'darkblue',
                                    'Demolition': 'gray',
                                    'Repair': 'red',
                                    'Functional': 'green'}
RECOVERY_FINANCING_ACTIVITY_NAME = 'Financing'
MONEY_RESOURCE_NAME = 'Money'

GANTT_Y_LABELS = {'Home Component Functionality': 'Building damage',
                  'Infrastructure': 'Infrastructure outage',
                  'Labor': 'Employee availability',
                  'LocalSuppliers': 'Access to local suppliers',
                  'Customer Base': 'Customer base'}