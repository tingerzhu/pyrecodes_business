import pandas as pd
import geopandas as gpd
import warnings
import numpy as np

# Extract the building information from the det file and convert it to a pandas dataframe
def extract_building_from_det(det):
            # Extract the required information and convert it to a pandas dataframe
            extracted_data = []

            for aim_id, info in det['Buildings']['Building'].items():
                general_info = info.get('GeneralInformation', {})
                extracted_data.append({
                    'AIM_id': aim_id,
                    'Latitude': general_info.get('Latitude'),
                    'Longitude': general_info.get('Longitude'),
                    'Population': general_info.get('Population'),
                    'PopulationRatio': general_info.get('PopulationRatio')
                })
            extracted_df = pd.DataFrame(extracted_data)
            return gpd.GeoDataFrame(extracted_df, geometry=gpd.points_from_xy(extracted_df.Longitude, extracted_df.Latitude), crs='epsg:4326')
# Aggregate the population in buildings to the closest road network node
def closest_neighbour(building_df, nodes_df):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # merged_df = building_df.sjoin_nearest(nodes_df, how = 'left')
        # Use the population of the nearest building to the road network node as the reference population
        # of the road network node. This is not the true population at each node. This is only used to calculate the percentage change of the population at each node. 
        # The percentage change of trips generated at each node is euqal to the percentage change of the
        # population of the nearest building to the node.
        merged_df = nodes_df.sjoin_nearest(building_df, how = 'left').drop_duplicates(subset = ['node_id'], keep = 'first')
    merged_df = merged_df.drop(columns=['AIM_id', 'Latitude', 'Longitude', 'index_right'])
    merged_df = merged_df.rename(columns={'Population': 'PopulationOfNearestBuilding'})
    merged_df = merged_df.fillna(0)
    merged_df['PopulationOfNearestBuilding'] = merged_df['PopulationOfNearestBuilding'] * merged_df['PopulationRatio']

    # Aggregate the population of the neareast buildings to the road network node
    # return merged_df.groupby('node_id').agg({'x': 'first', 'y': 'first', 'geometry': 'first', 'Population': 'sum'}).reset_index()
    return merged_df
# Function to add the population information to the nodes file
def find_population(nodes, det):
    # Extract the building information from the det file and convert it to a pandas dataframe
    building_df = extract_building_from_det(det)
    # Aggregate the population in buildings to the closest road network node
    updated_nodes_df = closest_neighbour(building_df, nodes)

    return updated_nodes_df  # noqa: RET504

def update_od(initial_od, nodes_df, initial_r2d_dict, new_r2d_dict, constant_tour_type: list[str] = ['CONSTANT']):
    # First, identify all trips with constant tour types that should always be preserved
    constant_trips_mask = initial_od['tour_category'].isin(constant_tour_type)
    constant_trips_indices = initial_od[constant_trips_mask].index.tolist()
    
    trips_starting_at_nodes = initial_od.reset_index()[['origin_nid', 'index']].groupby(
        'origin_nid').agg(list).to_dict()['index']
    trips_ending_at_nodes = initial_od.reset_index()[['destin_nid', 'index']].groupby(
        'destin_nid').agg(list).to_dict()['index']
    # old population at each node
    old_population = find_population(nodes_df, initial_r2d_dict)
    # new population at each node
    new_population = find_population(nodes_df, new_r2d_dict)
    population_change = new_population['PopulationOfNearestBuilding'] - old_population['PopulationOfNearestBuilding']
    # population change percentage at each node
    trips_index_set = set()
    for i in old_population.index:
        node_id = old_population.loc[i, 'node_id']
        # The population did not change, the OD starting and ending at this node does not change
        if population_change[i] == 0:
            trips_index_set = trips_index_set.union(set(trips_starting_at_nodes.get(node_id, [])))
            trips_index_set = trips_index_set.union(set(trips_ending_at_nodes.get(node_id, [])))
        # If the population changed and if the original OD starting and ending at this node is zero,
        # Generate new OD starting and ending at this node. This is considered impossible in this
        # implementation as new population can only be generated at nodes with non-zero pre-event population
        elif old_population.loc[i, 'PopulationOfNearestBuilding'] == 0:
            print(f'Warning: New population generated at node {node_id}, which had zero pre-event population')
        # If the population changed and if the original OD starting and ending at this node is not zero,
        # Modify the trips starting and ending at this node according to the population change percentage
        else:
            change_percentage = population_change[i] / old_population.loc[i, 'PopulationOfNearestBuilding']
            origin_trips = trips_starting_at_nodes.get(node_id, [])
            origin_trips = np.random.choice(origin_trips, int(len(origin_trips) * (1+change_percentage)), replace=False)
            destin_trips = trips_ending_at_nodes.get(node_id, [])
            destin_trips = np.random.choice(destin_trips, int(len(destin_trips) * (1+change_percentage)), replace=False)
            trips_index_set = trips_index_set.union(set(origin_trips)).union(set(destin_trips))
    
    # Combine the dynamically selected trips with the constant trips
    trips_index_set = trips_index_set.union(set(constant_trips_indices))
    trips_index_set = sorted(trips_index_set)
    return initial_od.loc[trips_index_set, :]