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
    return updated_nodes_df

def update_od(initial_od, nodes_df, initial_r2d_dict, new_r2d_dict):
    return initial_od
    