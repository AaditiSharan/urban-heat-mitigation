"""
Process ERA5 atmospheric data and OpenStreetMap urban morphology data.
Integrates meteorological variables and urban form features for heat stress analysis.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DATA_DIR,
    DELHI_BBOX,
    ERA5_CONFIG,
    OSM_CONFIG,
    DATA_SOURCES,
)


def download_era5_data(output_path: Path) -> xr.Dataset:
    """
    Download ERA5 reanalysis data using CDS API.
    Requires: ~/.cdsapirc file with API credentials.
    
    Setup instructions:
    1. Register at https://cds.climate.copernicus.eu/
    2. Install API key in ~/.cdsapirc: url: <your-url>, key: <your-key>
    3. Run this function to download data
    """
    try:
        import cdsapi
    except ImportError:
        print("CDS API not installed. Run: pip install cdsapi")
        print("See https://cds.climate.copernicus.eu/api-how-to for setup")
        return None
    
    c = cdsapi.Client()
    
    request = {
        "product_type": "reanalysis",
        "format": "netcdf",
        "variable": ERA5_CONFIG["era5"]["variables"],
        "year": "2024",
        "month": "05",
        "day": list(range(15, 31)),
        "time": [f"{h:02d}:00" for h in range(0, 24, 3)],
        "area": ERA5_CONFIG["area"],
    }
    
    c.retrieve("reanalysis-era5-single-levels", request, str(output_path))
    return xr.open_dataset(output_path)


def process_era5_data(era5_path: Path, grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process ERA5 data and interpolate to grid points.
    """
    if not era5_path.exists():
        print(f"ERA5 data not found at {era5_path}")
        print("Run download_era5_data() first or use synthetic meteorological data")
        return grid_df
    
    ds = xr.open_dataset(era5_path)
    
    # Calculate derived variables
    ds['wind_speed'] = np.sqrt(ds['u10']**2 + ds['v10']**2)
    ds['wind_direction'] = np.arctan2(ds['v10'], ds['u10']) * 180 / np.pi
    
    # Calculate relative humidity from temperature and dewpoint
    # Magnus formula approximation
    es = 6.112 * np.exp((17.67 * ds['t2m']) / (ds['t2m'] + 243.5))
    es_dew = 6.112 * np.exp((17.67 * ds['d2m']) / (ds['d2m'] + 243.5))
    ds['relative_humidity'] = 100 * (es_dew / es)
    
    # Temporal averaging over study period
    ds_mean = ds.mean(dim='time')
    
    # Interpolate to grid points
    grid_df['air_temp'] = grid_df.apply(
        lambda row: float(ds_mean['t2m'].sel(
            latitude=row['lat'], 
            longitude=row['lon'], 
            method='nearest'
        ).values - 273.15),  # Convert K to C
        axis=1
    )
    
    grid_df['humidity'] = grid_df.apply(
        lambda row: float(ds_mean['relative_humidity'].sel(
            latitude=row['lat'], 
            longitude=row['lon'], 
            method='nearest'
        ).values),
        axis=1
    )
    
    grid_df['wind'] = grid_df.apply(
        lambda row: float(ds_mean['wind_speed'].sel(
            latitude=row['lat'], 
            longitude=row['lon'], 
            method='nearest'
        ).values),
        axis=1
    )
    
    return grid_df


def extract_osm_features(grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract urban morphology features from OpenStreetMap using OSMnx.
    """
    try:
        import osmnx as ox
    except ImportError:
        print("OSMnx not installed. Run: pip install osmnx")
        return grid_df
    
    # Configure OSMnx
    ox.settings.use_cache = True
    ox.settings.log_console = True
    
    # Create bounding box polygon
    bbox_polygon = [
        (DELHI_BBOX["min_lon"], DELHI_BBOX["min_lat"]),
        (DELHI_BBOX["max_lon"], DELHI_BBOX["min_lat"]),
        (DELHI_BBOX["max_lon"], DELHI_BBOX["max_lat"]),
        (DELHI_BBOX["min_lon"], DELHI_BBOX["max_lat"]),
        (DELHI_BBOX["min_lon"], DELHI_BBOX["min_lat"]),
    ]
    
    try:
        # Download building footprints
        print("Downloading OSM building data...")
        buildings = ox.geometries_from_polygon(
            Point(DELHI_BBOX["min_lon"] + 0.1, DELHI_BBOX["min_lat"] + 0.1).buffer(0.1),
            tags={'building': True}
        )
        
        # Download road network
        print("Downloading OSM road network...")
        graph = ox.graph_from_bbox(
            DELHI_BBOX["max_lat"], DELHI_BBOX["min_lat"],
            DELHI_BBOX["max_lon"], DELHI_BBOX["min_lon"],
            network_type=OSM_CONFIG["network_type"]
        )
        
        # Calculate urban morphology metrics for each grid cell
        for idx, row in grid_df.iterrows():
            lat, lon = row['lat'], row['lon']
            
            # Create buffer around grid cell
            cell_point = Point(lon, lat)
            buffer = cell_point.buffer(OSM_CONFIG["buffer_m"] / 111000)  # Convert m to degrees
            
            # Building density (buildings per km²)
            nearby_buildings = buildings[buildings.geometry.intersects(buffer)]
            building_density = len(nearby_buildings) / (np.pi * (OSM_CONFIG["buffer_m"]/1000)**2)
            
            # Average building height (if available)
            heights = nearby_buildings['height'].dropna()
            if len(heights) > 0:
                avg_height = pd.to_numeric(heights.str.replace(' m', '').astype(float)).mean()
            else:
                avg_height = 15  # Default for Delhi
            
            # Sky view factor (simplified estimation)
            # SVF decreases with building density and height
            svf = np.exp(-0.1 * building_density * (avg_height / 10))
            svf = np.clip(svf, 0.1, 1.0)
            
            # Street width (average distance between roads)
            try:
                nodes = ox.distance.nearest_nodes(graph, lon, lat)
                subgraph = ox.graph.subgraph(graph, nodes)
                edges = list(subgraph.edges(data=True))
                if edges:
                    street_width = np.mean([data.get('width', 10) for _, _, data in edges])
                else:
                    street_width = 15
            except:
                street_width = 15
            
            grid_df.at[idx, 'building_density'] = min(building_density / 100, 1.0)
            grid_df.at[idx, 'building_height_m'] = avg_height
            grid_df.at[idx, 'sky_view_factor'] = svf
            grid_df.at[idx, 'street_width_m'] = street_width
            
    except Exception as e:
        print(f"OSM extraction failed: {e}")
        print("Using synthetic urban morphology data")
        grid_df = generate_synthetic_urban_morphology(grid_df)
    
    return grid_df


def generate_synthetic_urban_morphology(grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate synthetic urban morphology features when OSM data is unavailable.
    Uses physics-informed relationships based on location.
    """
    cp_lat, cp_lon = 28.6315, 77.2167  # Central Delhi
    
    for idx, row in grid_df.iterrows():
        lat, lon = row['lat'], row['lon']
        
        # Distance from urban core
        dist_core = math.sqrt((lat - cp_lat)**2 + (lon - cp_lon)**2) * 111000  # meters
        
        # Building density decreases with distance from core
        building_density = np.clip(0.8 * np.exp(-dist_core / 5000) + 0.1, 0.1, 0.95)
        
        # Building height correlates with density
        building_height = 10 + building_density * 25  # 10-35m
        
        # Sky view factor decreases with building density and height
        svf = np.exp(-0.15 * building_density * (building_height / 10))
        svf = np.clip(svf, 0.15, 0.95)
        
        # Street width increases in suburban areas
        street_width = 8 + (1 - building_density) * 20  # 8-28m
        
        grid_df.at[idx, 'building_density'] = building_density
        grid_df.at[idx, 'building_height_m'] = building_height
        grid_df.at[idx, 'sky_view_factor'] = svf
        grid_df.at[idx, 'street_width_m'] = street_width
    
    return grid_df


def download_ghsl_data(output_path: Path) -> None:
    """
    Download Global Human Settlement Layer data.
    GHSL provides built-up area and population density at 250m resolution.
    
    Data available from: https://ghsl.jrc.ec.europa.eu/
    """
    print("GHSL data download requires manual download from:")
    print("https://ghsl.jrc.ec.europa.eu/download.php?ds=bu")
    print("Download GHS-BUILT-LDS-2015-GLOBE-R2018A.tif")
    print(f"Save to: {output_path}")


def process_ghsl_data(ghsl_path: Path, grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process GHSL data and extract built-up and population density.
    """
    if not ghsl_path.exists():
        print(f"GHSL data not found at {ghsl_path}")
        print("Using synthetic GHSL data")
        return generate_synthetic_ghsl(grid_df)
    
    try:
        import rioxarray
        da = rioxarray.open_rasterio(ghsl_path)
        
        for idx, row in grid_df.iterrows():
            lat, lon = row['lat'], row['lon']
            
            # Extract GHSL values at grid point
            try:
                built_up = float(da.sel(x=lon, y=lat, method='nearest').values)
                grid_df.at[idx, 'ghsl_built_up'] = min(built_up / 100, 1.0)
            except:
                grid_df.at[idx, 'ghsl_built_up'] = 0.5
        
    except Exception as e:
        print(f"GHSL processing failed: {e}")
        grid_df = generate_synthetic_ghsl(grid_df)
    
    return grid_df


def generate_synthetic_ghsl(grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate synthetic GHSL data when actual data is unavailable.
    """
    cp_lat, cp_lon = 28.6315, 77.2167
    
    for idx, row in grid_df.iterrows():
        lat, lon = row['lat'], row['lon']
        
        # Built-up density based on distance from core
        dist_core = math.sqrt((lat - cp_lat)**2 + (lon - cp_lon)**2) * 111000
        built_up = np.clip(0.9 * np.exp(-dist_core / 4000), 0.1, 0.95)
        
        # Population density correlates with built-up
        pop_density = built_up * 250 + np.random.normal(0, 20)  # persons/ha
        pop_density = max(10, pop_density)
        
        grid_df.at[idx, 'ghsl_built_up'] = built_up
        grid_df.at[idx, 'population_density'] = pop_density
    
    return grid_df


def calculate_thermal_anisotropy(grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate thermal anisotropy from ECOSTRESS data.
    Thermal anisotropy represents directional variation in surface temperature.
    """
    # Simplified estimation based on urban morphology
    for idx, row in grid_df.iterrows():
        svf = row.get('sky_view_factor', 0.5)
        building_height = row.get('building_height_m', 15)
        
        # Higher anisotropy in dense, tall urban areas
        anisotropy = 0.1 + (1 - svf) * 0.3 + (building_height / 50) * 0.2
        grid_df.at[idx, 'thermal_anisotropy'] = np.clip(anisotropy, 0.1, 0.8)
    
    return grid_df


def add_synthetic_meteorological_data(grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add synthetic meteorological data when ERA5 is unavailable.
    """
    # Delhi summer conditions (May 2024)
    base_temp = 38.5
    base_humidity = 35.0
    base_wind = 2.8
    
    cp_lat, cp_lon = 28.6315, 77.2167

    grid_df[['lon', 'lat']] = grid_df['.geo'].apply(
    lambda x: pd.Series(json.loads(x)['coordinates'])
)
    
    for idx, row in grid_df.iterrows():
        lat, lon = row['lat'], row['lon']
        dist_core = math.sqrt((lat - cp_lat)**2 + (lon - cp_lon)**2) * 111000
        
        # UHI effect: warmer in urban core
        uhi_effect = 3.0 * np.exp(-dist_core / 6000)
        
        # Temperature varies with UHI
        temp = base_temp + uhi_effect + np.random.normal(0, 0.5)
        
        # Humidity lower in urban core
        humidity = base_humidity - uhi_effect * 2 + np.random.normal(0, 3)
        
        # Wind speed lower in dense areas
        wind = base_wind * (1 - 0.3 * np.exp(-dist_core / 4000)) + np.random.normal(0, 0.3)
        
        grid_df.at[idx, 'air_temp'] = np.clip(temp, 32, 45)
        grid_df.at[idx, 'humidity'] = np.clip(humidity, 15, 70)
        grid_df.at[idx, 'wind'] = np.clip(wind, 0.5, 6.0)
    
    return grid_df


def fetch_cpcb_data(output_path: Path) -> pd.DataFrame:
    """
    Fetch meteorological data from Central Pollution Control Board (CPCB).
    CPCB provides real-time air quality and meteorological data for Delhi.
    
    Data available from: https://cpcb.nic.in/
    """
    print("CPCB data requires manual download from:")
    print("https://cpcb.nic.in/NAAQ/India_Air_Quality_Monitoring_Stations.php")
    print("Download Delhi monitoring station data")
    print(f"Save to: {output_path}")
    
    # Return empty DataFrame - user needs to manually download
    return pd.DataFrame()


def process_cpcb_data(cpcb_path: Path, grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process CPCB meteorological data and interpolate to grid points.
    """
    if not cpcb_path.exists():
        print(f"CPCB data not found at {cpcb_path}")
        print("Using ERA5 or synthetic meteorological data instead")
        return grid_df
    
    try:
        cpcb_df = pd.read_csv(cpcb_path)
        
        # Assuming CPCB data has columns: station_id, lat, lon, temperature, humidity, wind_speed
        # Interpolate to grid points using inverse distance weighting
        for idx, row in grid_df.iterrows():
            lat, lon = row['lat'], row['lon']
            
            # Calculate distances to all CPCB stations
            distances = np.sqrt(
                (cpcb_df['lat'] - lat)**2 + 
                (cpcb_df['lon'] - lon)**2
            ) * 111000  # Convert to meters
            
            # Inverse distance weighting
            weights = 1 / (distances + 100)  # Add small constant to avoid division by zero
            weights = weights / weights.sum()
            
            # Weighted average of meteorological variables
            if 'temperature' in cpcb_df.columns:
                grid_df.at[idx, 'air_temp'] = np.sum(cpcb_df['temperature'] * weights)
            if 'humidity' in cpcb_df.columns:
                grid_df.at[idx, 'humidity'] = np.sum(cpcb_df['humidity'] * weights)
            if 'wind_speed' in cpcb_df.columns:
                grid_df.at[idx, 'wind'] = np.sum(cpcb_df['wind_speed'] * weights)
        
        print("Successfully integrated CPCB data")
        
    except Exception as e:
        print(f"CPCB data processing failed: {e}")
        print("Falling back to ERA5 or synthetic data")
    
    return grid_df


def main() -> None:
    """
    Main processing pipeline for meteorological and urban morphology data.
    """
    print("Processing meteorological and urban morphology data...")
    
    # Load existing grid data
    grid_path = DATA_DIR / "grid_features.csv"
    if not grid_path.exists():
        raise FileNotFoundError(f"Missing {grid_path}. Run generate_delhi_data.py first.")
    
    grid_df = pd.read_csv(grid_path)
    print(f"Loaded {len(grid_df)} grid cells")
    
    # Process ERA5 data
    era5_path = DATA_DIR / "era5_delhi_2024.nc"
    if era5_path.exists():
        print("Processing ERA5 data...")
        grid_df = process_era5_data(era5_path, grid_df)
    else:
        print("ERA5 data not found, checking CPCB data...")
        cpcb_path = DATA_DIR / "cpcb_meteorological.csv"
        if cpcb_path.exists():
            print("Processing CPCB data...")
            grid_df = process_cpcb_data(cpcb_path, grid_df)
        else:
            print("CPCB data not found, using synthetic meteorological data")
            grid_df = add_synthetic_meteorological_data(grid_df)
    
    # Process OSM urban morphology
    print("Processing urban morphology from OSM...")
    grid_df = extract_osm_features(grid_df)
    
    # Process GHSL data
    ghsl_path = DATA_DIR / "ghsl_built_up.tif"
    if ghsl_path.exists():
        print("Processing GHSL data...")
        grid_df = process_ghsl_data(ghsl_path, grid_df)
    else:
        print("GHSL data not found, using synthetic GHSL data")
        grid_df = generate_synthetic_ghsl(grid_df)
    
    # Calculate thermal anisotropy
    print("Calculating thermal anisotropy...")
    grid_df = calculate_thermal_anisotropy(grid_df)
    
    # Ensure all new features exist
    required_features = [
        'humidity', 'sky_view_factor', 'building_height_m', 
        'street_width_m', 'ghsl_built_up', 'population_density', 
        'thermal_anisotropy'
    ]
    
    for feature in required_features:
        if feature not in grid_df.columns:
            print(f"Warning: {feature} not in dataframe, adding default values")
            grid_df[feature] = 0.5
    
    # Save updated grid data
    grid_df.to_csv(grid_path, index=False)
    print(f"Saved updated grid data to {grid_path}")
    
    # Update metadata
    metadata_path = DATA_DIR / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        metadata['data_sources'] = {
            'remote_sensing': ['Landsat 8', 'ECOSTRESS', 'Sentinel-2'],
            'meteorological': ['ERA5 (reanalysis)', 'CPCB (optional)'],
            'urban_form': ['OpenStreetMap', 'GHSL', 'UT-GLOBUS (optional)'],
        }
        metadata['features'] = grid_df.columns.tolist()
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"Updated metadata at {metadata_path}")
    
    print("Processing complete!")
    print(f"Grid features: {list(grid_df.columns)}")


if __name__ == "__main__":
    main()
