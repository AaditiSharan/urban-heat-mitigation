"""
InVEST (Integrated Valuation of Ecosystem Services and Tradeoffs) integration.
InVEST models ecosystem services including urban cooling, carbon sequestration, and biodiversity.

Note: Full InVEST requires external software. This module provides simplified
implementations and interfaces for key InVEST-like calculations relevant to urban heat mitigation.
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
    INVEST_CONFIG,
    PHYSICS_CONFIG,
)


def calculate_urban_cooling_capacity(
    ndvi: float,
    tree_cover: float,
    water_bodies: float,
    distance_to_green: float,
) -> float:
    """
    Calculate urban cooling capacity using InVEST Urban Cooling Model approach.
    
    Cooling capacity represents the ability of vegetation and water to reduce local temperatures.
    
    Args:
        ndvi: Normalized Difference Vegetation Index (0-1)
        tree_cover: Tree canopy cover fraction (0-1)
        water_bodies: Proximity to water bodies (0-1)
        distance_to_green: Distance to green spaces (meters)
    
    Returns:
        Cooling capacity index (0-1, higher = more cooling)
    """
    # Vegetation cooling effect
    veg_cooling = 0.6 * ndvi + 0.4 * tree_cover
    
    # Water cooling effect (stronger than vegetation)
    water_cooling = 0.8 * water_bodies
    
    # Distance decay for green space influence
    distance_decay = np.exp(-distance_to_green / 500)  # 500m influence radius
    
    # Combined cooling capacity
    cooling_capacity = veg_cooling + water_cooling * distance_decay
    
    return float(np.clip(cooling_capacity, 0, 1))


def calculate_carbon_sequestration(
    ndvi: float,
    tree_cover: float,
    building_density: float,
) -> float:
    """
    Calculate carbon sequestration potential using InVEST Carbon Model approach.
    
    Args:
        ndvi: Normalized Difference Vegetation Index (0-1)
        tree_cover: Tree canopy cover fraction (0-1)
        building_density: Building density (0-1)
    
    Returns:
        Carbon sequestration rate (tons CO2/ha/year)
    """
    # Base sequestration for vegetation
    base_sequestration = 10 * ndvi  # tons CO2/ha/year baseline
    
    # Tree cover enhancement
    tree_enhancement = 15 * tree_cover
    
    # Building density reduction (impervious surfaces don't sequester)
    impervious_reduction = 20 * building_density
    
    # Net sequestration
    net_sequestration = base_sequestration + tree_enhancement - impervious_reduction
    
    return float(max(0, net_sequestration))


def calculate_biodiversity_index(
    ndvi: float,
    habitat_connectivity: float,
    distance_to_parks: float,
    impervious: float,
) -> float:
    """
    Calculate biodiversity habitat quality using InVEST Habitat Quality approach.
    
    Args:
        ndvi: Normalized Difference Vegetation Index (0-1)
        habitat_connectivity: Connectivity of habitat patches (0-1)
        distance_to_parks: Distance to protected areas (meters)
        impervious: Impervious surface fraction (0-1)
    
    Returns:
        Biodiversity index (0-1, higher = better habitat quality)
    """
    # Habitat suitability based on vegetation
    habitat_suitability = 0.7 * ndvi + 0.3 * habitat_connectivity
    
    # Distance to protected areas
    park_proximity = np.exp(-distance_to_parks / 1000)  # 1km influence
    
    # Threat from impervious surfaces
    threat_level = 0.8 * impervious
    
    # Habitat quality
    biodiversity = habitat_suitability * park_proximity * (1 - threat_level)
    
    return float(np.clip(biodiversity, 0, 1))


def calculate_stormwater_retention(
    ndvi: float,
    impervious: float,
    soil_permeability: float = 0.5,
) -> float:
    """
    Calculate stormwater retention capacity using InVEST approach.
    
    Args:
        ndvi: Normalized Difference Vegetation Index (0-1)
        impervious: Impervious surface fraction (0-1)
        soil_permeability: Soil permeability (0-1)
    
    Returns:
        Stormwater retention fraction (0-1)
    """
    # Vegetation retention
    veg_retention = 0.6 * ndvi
    
    # Impervious surface reduction
    impervious_loss = 0.9 * impervious
    
    # Soil contribution
    soil_retention = 0.3 * soil_permeability
    
    # Total retention
    total_retention = veg_retention + soil_retention - impervious_loss
    
    return float(np.clip(total_retention, 0, 1))


def calculate_air_quality_benefit(
    ndvi: float,
    tree_cover: float,
    building_density: float,
    population_density: float,
) -> float:
    """
    Calculate air quality improvement from vegetation using InVEST approach.
    
    Args:
        ndvi: Normalized Difference Vegetation Index (0-1)
        tree_cover: Tree canopy cover fraction (0-1)
        building_density: Building density (0-1)
        population_density: Population density (persons/ha)
    
    Returns:
        Air quality benefit index (0-1, higher = better air quality)
    """
    # Vegetation pollution removal
    pollution_removal = 0.5 * ndvi + 0.5 * tree_cover
    
    # Pollution source from buildings
    pollution_source = 0.7 * building_density
    
    # Population exposure factor
    exposure_factor = min(population_density / 300, 1)  # Normalize
    
    # Net air quality benefit
    air_quality = pollution_removal - pollution_source * 0.5
    
    return float(np.clip(air_quality, 0, 1))


def apply_invest_to_grid(grid_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply InVEST-like ecosystem service calculations to entire grid.
    
    Args:
        grid_df: DataFrame with grid cell features
    
    Returns:
        DataFrame with added ecosystem service features
    """
    print("Applying InVEST-like ecosystem service calculations...")
    
    for idx, row in grid_df.iterrows():
        # Extract existing features
        ndvi = row.get('ndvi', 0.3)
        building_density = row.get('building_density', 0.5)
        impervious = row.get('impervious', 0.6)
        dist_water = row.get('dist_water_m', 1000)
        
        # Estimate derived features
        tree_cover = min(ndvi * 1.5, 0.8)  # Tree cover from NDVI
        water_bodies = np.exp(-dist_water / 500)  # Water proximity
        distance_to_green = dist_water * 0.5  # Approximate green space distance
        habitat_connectivity = 1 - building_density * 0.7  # Connectivity inverse to density
        distance_to_parks = dist_water * 0.8  # Approximate park distance
        population_density = row.get('population_density', 150)
        
        # Calculate ecosystem services
        cooling_capacity = calculate_urban_cooling_capacity(
            ndvi, tree_cover, water_bodies, distance_to_green
        )
        
        carbon_seq = calculate_carbon_sequestration(
            ndvi, tree_cover, building_density
        )
        
        biodiversity = calculate_biodiversity_index(
            ndvi, habitat_connectivity, distance_to_parks, impervious
        )
        
        stormwater = calculate_stormwater_retention(ndvi, impervious)
        
        air_quality = calculate_air_quality_benefit(
            ndvi, tree_cover, building_density, population_density
        )
        
        # Add to dataframe
        grid_df.at[idx, 'cooling_capacity'] = cooling_capacity
        grid_df.at[idx, 'carbon_sequestration_tons_ha_yr'] = carbon_seq
        grid_df.at[idx, 'biodiversity_index'] = biodiversity
        grid_df.at[idx, 'stormwater_retention'] = stormwater
        grid_df.at[idx, 'air_quality_benefit'] = air_quality
        
        # Calculate综合 ecosystem service index
        ecosystem_index = (
            0.3 * cooling_capacity +
            0.25 * biodiversity +
            0.2 * stormwater +
            0.15 * air_quality +
            0.1 * (carbon_seq / 20)  # Normalize carbon
        )
        grid_df.at[idx, 'ecosystem_service_index'] = ecosystem_index
    
    print("InVEST-like calculations complete")
    return grid_df


def calculate_intervention_benefits(
    intervention_type: str,
    baseline_ecosystem: float,
    intervention_area_m2: float,
) -> dict:
    """
    Calculate ecosystem service benefits from specific interventions.
    
    Args:
        intervention_type: Type of intervention (cool_roofs, green_roofs, urban_greening, etc.)
        baseline_ecosystem: Baseline ecosystem service index
        intervention_area_m2: Area of intervention (square meters)
    
    Returns:
        Dictionary with benefit estimates
    """
    # Intervention effectiveness factors
    effectiveness = {
        'cool_roofs': {
            'cooling': 0.3,
            'carbon': 0.05,
            'biodiversity': 0.1,
            'stormwater': 0.1,
            'air_quality': 0.15,
        },
        'green_roofs': {
            'cooling': 0.4,
            'carbon': 0.3,
            'biodiversity': 0.4,
            'stormwater': 0.6,
            'air_quality': 0.35,
        },
        'urban_greening': {
            'cooling': 0.5,
            'carbon': 0.6,
            'biodiversity': 0.7,
            'stormwater': 0.4,
            'air_quality': 0.6,
        },
        'cool_pavements': {
            'cooling': 0.25,
            'carbon': 0.05,
            'biodiversity': 0.05,
            'stormwater': 0.3,
            'air_quality': 0.1,
        },
    }
    
    if intervention_type not in effectiveness:
        intervention_type = 'cool_roofs'
    
    factors = effectiveness[intervention_type]
    
    # Calculate benefits
    benefits = {
        'cooling_benefit': baseline_ecosystem * factors['cooling'] * intervention_area_m2 / 10000,
        'carbon_benefit_tons': baseline_ecosystem * factors['carbon'] * intervention_area_m2 / 10000,
        'biodiversity_benefit': baseline_ecosystem * factors['biodiversity'],
        'stormwater_benefit_m3': baseline_ecosystem * factors['stormwater'] * intervention_area_m2 * 0.5,
        'air_quality_benefit': baseline_ecosystem * factors['air_quality'],
    }
    
    return benefits


def main() -> None:
    """
    Main function to run InVEST integration.
    """
    if not INVEST_CONFIG.get("enabled", False):
        print("InVEST integration is disabled in config.py")
        print("Set INVEST_CONFIG['enabled'] = True to enable")
        return
    
    # Load grid data
    grid_path = DATA_DIR / "grid_features.csv"
    if not grid_path.exists():
        raise FileNotFoundError(f"Missing {grid_path}. Run generate_delhi_data.py first.")
    
    grid_df = pd.read_csv(grid_path)
    print(f"Loaded {len(grid_df)} grid cells")
    
    # Apply InVEST calculations
    grid_df = apply_invest_to_grid(grid_df)
    
    # Save updated data
    grid_df.to_csv(grid_path, index=False)
    print(f"Saved updated grid data with ecosystem services to {grid_path}")
    
    # Summary statistics
    print("\nEcosystem Services Summary:")
    print(f"Mean Cooling Capacity: {grid_df['cooling_capacity'].mean():.2f}")
    print(f"Mean Carbon Sequestration: {grid_df['carbon_sequestration_tons_ha_yr'].mean():.2f} tons/ha/yr")
    print(f"Mean Biodiversity Index: {grid_df['biodiversity_index'].mean():.2f}")
    print(f"Mean Stormwater Retention: {grid_df['stormwater_retention'].mean():.2f}")
    print(f"Mean Air Quality Benefit: {grid_df['air_quality_benefit'].mean():.2f}")
    print(f"Mean Ecosystem Service Index: {grid_df['ecosystem_service_index'].mean():.2f}")
    
    # Calculate intervention benefits example
    print("\nExample Intervention Benefits (per hectare):")
    for intervention in ['cool_roofs', 'green_roofs', 'urban_greening']:
        benefits = calculate_intervention_benefits(intervention, 0.5, 10000)
        print(f"\n{intervention}:")
        print(f"  Cooling benefit: {benefits['cooling_benefit']:.2f}")
        print(f"  Carbon benefit: {benefits['carbon_benefit_tons']:.2f} tons")
        print(f"  Stormwater benefit: {benefits['stormwater_benefit_m3']:.2f} m³")


if __name__ == "__main__":
    main()
