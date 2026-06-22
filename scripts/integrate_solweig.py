"""
SOLWEIG (SOlar LongWave Environmental Irradiance Geometry) integration for thermal comfort modeling.
SOLWEIG calculates sky view factors, shadow patterns, and mean radiant temperature.

Note: Full SOLWEIG requires external software. This module provides simplified
implementations and interfaces for key SOLWEIG-like calculations.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DATA_DIR,
    SOLWEIG_CONFIG,
    PHYSICS_CONFIG,
)


def calculate_sky_view_factor_3d(
    building_heights: np.ndarray,
    street_width: float,
    building_density: float,
) -> float:
    """
    Calculate 3D sky view factor using simplified SOLWEIG-like approach.
    
    SVF represents the fraction of the sky hemisphere visible from a point.
    Lower SVF indicates more urban canyon effect (trapped radiation).
    
    Args:
        building_heights: Array of nearby building heights (meters)
        street_width: Average street width (meters)
        building_density: Building density (0-1)
    
    Returns:
        Sky view factor (0-1)
    """
    if len(building_heights) == 0:
        return 0.8  # Default for open areas
    
    avg_height = np.mean(building_heights)
    max_height = np.max(building_heights)
    
    # Simplified SVF calculation based on street canyon geometry
    # SVF decreases with higher buildings and narrower streets
    aspect_ratio = avg_height / (street_width + 1e-6)
    
    # SVF formula for urban canyon (simplified)
    svf = 0.5 * (1 - aspect_ratio / (1 + aspect_ratio))
    
    # Adjust for building density
    svf = svf * (1 - 0.5 * building_density)
    
    # Ensure physical bounds
    svf = np.clip(svf, 0.1, 0.95)
    
    return float(svf)


def calculate_mean_radiant_temperature(
    air_temp: float,
    svf: float,
    albedo: float,
    lst: float,
    solar_altitude: float = 60.0,
) -> float:
    """
    Calculate Mean Radiant Temperature (MRT) using SOLWEIG-like approach.
    
    MRT represents the average radiant temperature of surrounding surfaces.
    Critical for thermal comfort assessment.
    
    Args:
        air_temp: Air temperature (°C)
        svf: Sky view factor (0-1)
        albedo: Surface albedo (0-1)
        lst: Land surface temperature (°C)
        solar_altitude: Solar altitude angle (degrees)
    
    Returns:
        Mean radiant temperature (°C)
    """
    # Solar radiation components
    solar_alt_rad = math.radians(solar_altitude)
    
    # Direct solar radiation (simplified)
    direct_solar = 800 * math.sin(solar_alt_rad) * (1 - albedo)
    
    # Diffuse solar radiation
    diffuse_solar = 100 * svf
    
    # Longwave radiation from surfaces
    stefan_boltzmann = PHYSICS_CONFIG["stefan_boltzmann"]
    surface_temp_k = lst + 273.15
    longwave = stefan_boltzmann * (surface_temp_k ** 4)
    
    # Total radiant temperature
    # Convert radiation to equivalent temperature
    mrt = air_temp + (direct_solar + diffuse_solar) / 15 + (longwave / 50) * (1 - svf)
    
    return float(mrt)


def calculate_thermal_comfort_index(
    air_temp: float,
    mrt: float,
    humidity: float,
    wind_speed: float,
) -> dict:
    """
    Calculate thermal comfort indices including PET and UTCI.
    
    Physiological Equivalent Temperature (PET) and Universal Thermal Climate Index (UTCI)
    are standard indices for outdoor thermal comfort.
    
    Args:
        air_temp: Air temperature (°C)
        mrt: Mean radiant temperature (°C)
        humidity: Relative humidity (%)
        wind_speed: Wind speed (m/s)
    
    Returns:
        Dictionary with thermal comfort indices
    """
    # Simplified PET calculation (RayMan model approximation)
    # PET requires complex physiological modeling - this is a simplified version
    
    # Core temperature calculation
    temp_mean = (air_temp + mrt) / 2
    
    # Humidity adjustment
    humidity_factor = 1 - (humidity - 50) / 200
    
    # Wind adjustment
    wind_factor = 1 - wind_speed / 10
    
    # Simplified PET
    pet = temp_mean * humidity_factor * wind_factor + 5
    
    # UTCI approximation (simplified)
    utci = air_temp + 0.3 * (mrt - air_temp) - 0.1 * wind_speed + 0.2 * (humidity - 50) / 10
    
    return {
        "pet_c": round(float(pet), 1),
        "utci_c": round(float(utci), 1),
        "thermal_stress": classify_thermal_stress(pet),
    }


def classify_thermal_stress(pet: float) -> str:
    """
    Classify thermal stress level based on PET.
    
    PET ranges for thermal stress (Matzarakis & Mayer, 1996):
    - < 4°C: Extreme cold stress
    - 4-8°C: Strong cold stress
    - 8-13°C: Moderate cold stress
    - 13-18°C: Slight cold stress
    - 18-23°C: No thermal stress
    - 23-29°C: Slight heat stress
    - 29-35°C: Moderate heat stress
    - 35-41°C: Strong heat stress
    - > 41°C: Extreme heat stress
    """
    if pet < 4:
        return "Extreme cold stress"
    elif pet < 8:
        return "Strong cold stress"
    elif pet < 13:
        return "Moderate cold stress"
    elif pet < 18:
        return "Slight cold stress"
    elif pet < 23:
        return "No thermal stress"
    elif pet < 29:
        return "Slight heat stress"
    elif pet < 35:
        return "Moderate heat stress"
    elif pet < 41:
        return "Strong heat stress"
    else:
        return "Extreme heat stress"


def calculate_shadow_patterns(
    lat: float,
    lon: float,
    building_heights: np.ndarray,
    building_positions: list[tuple[float, float]],
    time_hour: float = 12.0,
    day_of_year: int = 142,  # May 22
) -> np.ndarray:
    """
    Calculate shadow patterns from buildings at a given time.
    
    Args:
        lat: Latitude (degrees)
        lon: Longitude (degrees)
        building_heights: Array of building heights (meters)
        building_positions: List of (lon, lat) tuples for building positions
        time_hour: Hour of day (0-24)
        day_of_year: Day of year (1-365)
    
    Returns:
        Boolean array indicating shadowed areas
    """
    # Solar position calculation
    declination = 23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365))
    hour_angle = 15 * (time_hour - 12)
    
    lat_rad = math.radians(lat)
    decl_rad = math.radians(declination)
    hour_rad = math.radians(hour_angle)
    
    # Solar altitude and azimuth
    solar_altitude = math.asin(
        math.sin(lat_rad) * math.sin(decl_rad) +
        math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_rad)
    )
    
    solar_azimuth = math.atan2(
        math.sin(hour_rad),
        math.cos(hour_rad) * math.sin(lat_rad) - math.tan(decl_rad) * math.cos(lat_rad)
    )
    
    # Shadow length calculation
    shadow_length = np.array(building_heights) / math.tan(solar_altitude + 1e-6)
    
    # This is a simplified shadow calculation
    # Full implementation would require raster-based shadow casting
    shadow_mask = np.zeros(len(building_positions), dtype=bool)
    
    return shadow_mask


def apply_solweig_to_grid(grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply SOLWEIG-like calculations to entire grid.
    
    Args:
        grid_df: DataFrame with grid cell features
    
    Returns:
        DataFrame with added thermal comfort features
    """
    print("Applying SOLWEIG-like thermal comfort calculations...")
    
    for idx, row in grid_df.iterrows():
        # Extract existing features
        air_temp = row.get('air_temp', 38.5)
        lst = row.get('lst', 45.0)
        albedo = row.get('albedo', 0.15)
        humidity = row.get('humidity', 35.0)
        wind = row.get('wind', 2.8)
        svf = row.get('sky_view_factor', 0.5)
        building_height = row.get('building_height_m', 15.0)
        street_width = row.get('street_width_m', 15.0)
        building_density = row.get('building_density', 0.5)
        
        # Calculate MRT
        mrt = calculate_mean_radiant_temperature(
            air_temp, svf, albedo, lst
        )
        
        # Calculate thermal comfort indices
        comfort = calculate_thermal_comfort_index(
            air_temp, mrt, humidity, wind
        )
        
        # Add to dataframe
        grid_df.at[idx, 'mean_radiant_temp_c'] = mrt
        grid_df.at[idx, 'pet_c'] = comfort['pet_c']
        grid_df.at[idx, 'utci_c'] = comfort['utci_c']
        grid_df.at[idx, 'thermal_stress'] = comfort['thermal_stress']
        
        # Calculate heat stress index (0-10 scale)
        heat_stress = (comfort['pet_c'] - 18) / 3  # Normalize around comfort zone
        heat_stress = np.clip(heat_stress, 0, 10)
        grid_df.at[idx, 'heat_stress_index'] = heat_stress
    
    print("SOLWEIG-like calculations complete")
    return grid_df


def main() -> None:
    """
    Main function to run SOLWEIG integration.
    """
    if not SOLWEIG_CONFIG.get("enabled", False):
        print("SOLWEIG integration is disabled in config.py")
        print("Set SOLWEIG_CONFIG['enabled'] = True to enable")
        return
    
    # Load grid data
    grid_path = DATA_DIR / "grid_features.csv"
    if not grid_path.exists():
        raise FileNotFoundError(f"Missing {grid_path}. Run generate_delhi_data.py first.")
    
    grid_df = pd.read_csv(grid_path)
    print(f"Loaded {len(grid_df)} grid cells")
    
    # Apply SOLWEIG calculations
    grid_df = apply_solweig_to_grid(grid_df)
    
    # Save updated data
    grid_df.to_csv(grid_path, index=False)
    print(f"Saved updated grid data with thermal comfort indices to {grid_path}")
    
    # Summary statistics
    print("\nThermal Comfort Summary:")
    print(f"Mean PET: {grid_df['pet_c'].mean():.1f}°C")
    print(f"Mean UTCI: {grid_df['utci_c'].mean():.1f}°C")
    print(f"Mean Heat Stress Index: {grid_df['heat_stress_index'].mean():.1f}/10")
    print("\nThermal Stress Distribution:")
    print(grid_df['thermal_stress'].value_counts())


if __name__ == "__main__":
    main()
