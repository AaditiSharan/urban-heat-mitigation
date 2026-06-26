"""
Map GEE exported column names to expected format and add missing derived features.
"""

import pandas as pd
import numpy as np
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA_DIR, ZONES

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def assign_zone(lat: float, lon: float) -> str:
    best = None
    best_dist = float("inf")
    for zone in ZONES:
        zlat, zlon = zone["center"]
        dist = haversine_m(lat, lon, zlat, zlon)
        if dist < zone["radius_deg"] * 111000 and dist < best_dist:
            best = zone["id"]
            best_dist = dist
    return best if best else "unassigned"

def map_gee_columns(input_path: Path, output_path: Path) -> None:
    """
    Map GEE column names to expected format and add missing derived features.
    """
    # Load GEE exported data
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df)} rows from GEE export")
    print(f"Original columns: {list(df.columns)}")
    
    # Create column mapping
    column_mapping = {
        'LST': 'lst',
        'NDVI': 'ndvi',
        'NDBI': 'ndbi',
        'ALBEDO': 'albedo',
        'LULC': 'lulc',
        'LST_L8': 'lst_l8',
        'LST_ECO': 'lst_eco',
        'NDVI_S2': 'ndvi_s2',
        'NDBI_S2': 'ndbi_s2',
        '.geo': 'geo',
    }
    
    # Rename columns
    df = df.rename(columns=column_mapping)
    
    # Ensure required columns exist
    # Use NDVI from GEE (prefer Sentinel-2 if available, else Landsat 8)
    if 'ndvi_s2' in df.columns:
        df['ndvi'] = df['ndvi_s2'].fillna(df.get('ndvi', 0))
    elif 'ndvi' not in df.columns:
        df['ndvi'] = 0.3
    
    # Use NDBI from GEE (prefer Sentinel-2 if available, else Landsat 8)
    if 'ndbi_s2' in df.columns:
        df['ndbi'] = df['ndbi_s2'].fillna(df.get('ndbi', 0))
    elif 'ndbi' not in df.columns:
        df['ndbi'] = 0.2
    
    # Ensure albedo exists
    if 'albedo' not in df.columns:
        df['albedo'] = 0.15
    
    # Ensure lst exists
    if 'lst' not in df.columns:
        if 'lst_l8' in df.columns:
            df['lst'] = df['lst_l8']
        else:
            df['lst'] = 40.0
    
    # Add missing derived columns
    # Impervious surface from NDBI and LULC
    if 'impervious' not in df.columns:
        if 'lulc' in df.columns:
            df['impervious'] = np.where(df['lulc'] == 3, 0.8,  # built-up
                                     np.where(df['lulc'] == 1, 0.1,  # water
                                             np.where(df['lulc'] == 2, 0.2,  # vegetation
                                                     0.4 + df['ndbi'] * 0.4)))  # mixed
        else:
            df['impervious'] = 0.4 + df['ndbi'] * 0.4
        df['impervious'] = df['impervious'].clip(0.05, 0.95)
    
    # Building density from NDBI
    if 'building_density' not in df.columns:
        df['building_density'] = (0.3 + df['ndbi'] * 0.6).clip(0.0, 1.0)
    
    # Distance to water (use lat/lon to estimate distance to Yamuna)
    if 'dist_water_m' not in df.columns:
        if 'lat' in df.columns and 'lon' in df.columns:
            # Yamuna runs roughly north-south near 77.27E
            df['dist_water_m'] = abs(df['lon'] - 77.27) * 111000
        else:
            df['dist_water_m'] = 1000
    
    # Ensure meteorological columns exist
    if 'air_temp' not in df.columns:
        df['air_temp'] = 38.5
    if 'humidity' not in df.columns:
        df['humidity'] = 35.0
    if 'wind' not in df.columns:
        df['wind'] = 2.8
    
    # Ensure urban morphology columns exist
    if 'sky_view_factor' not in df.columns:
        df['sky_view_factor'] = 0.5
    if 'building_height_m' not in df.columns:
        df['building_height_m'] = 15.0
    if 'street_width_m' not in df.columns:
        df['street_width_m'] = 15.0
    if 'ghsl_built_up' not in df.columns:
        df['ghsl_built_up'] = 0.5
    if 'population_density' not in df.columns:
        df['population_density'] = 150.0
    if 'thermal_anisotropy' not in df.columns:
        df['thermal_anisotropy'] = 0.3
    
    # Create cell_id if missing
    if 'cell_id' not in df.columns:
        df['cell_id'] = [f"{i}" for i in range(len(df))]
    
    # Add zone_id if missing (assign based on coordinates)
    if 'lat' in df.columns and 'lon' in df.columns:
        print("Assigning zones based on coordinates...")
        df['zone_id'] = df.apply(lambda row: assign_zone(row['lat'], row['lon']), axis=1)
        print(f"Zone distribution: {df['zone_id'].value_counts().to_dict()}")
    else:
        df['zone_id'] = 'unassigned'
    
    # Add pop if missing
    if 'pop' not in df.columns:
        df['pop'] = 100
    
    # Select only required columns
    required_columns = [
        'cell_id', 'lat', 'lon', 'lst', 'ndvi', 'ndbi', 'impervious', 
        'albedo', 'building_density', 'dist_water_m', 'wind', 'air_temp',
        'humidity', 'sky_view_factor', 'building_height_m', 'street_width_m',
        'ghsl_built_up', 'population_density', 'thermal_anisotropy',
        'pop', 'zone_id'
    ]
    
    # Add any extra columns that exist
    existing_columns = [col for col in required_columns if col in df.columns]
    df = df[existing_columns]
    
    # Save mapped data
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} rows to {output_path}")
    print(f"Final columns: {list(df.columns)}")
    print(f"\nColumn statistics:")
    print(df[['lst', 'ndvi', 'ndbi', 'albedo', 'impervious']].describe())

if __name__ == "__main__":
    input_path = DATA_DIR / "grid_features.csv"
    output_path = DATA_DIR / "grid_features.csv"
    
    print("Mapping GEE columns to expected format...")
    map_gee_columns(input_path, output_path)
    print("\nColumn mapping complete!")
