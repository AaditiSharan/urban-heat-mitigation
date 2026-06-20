"""
Generate a Delhi-like 250 m grid for local development and demo.

Replace output with real GEE exports using gee/export_delhi.js when ready.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DATA_DIR,
    DASHBOARD_DATA,
    DELHI_BBOX,
    GRID_RES_DEG,
    ZONES,
)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def assign_zone(lat: float, lon: float) -> str | None:
    best = None
    best_dist = float("inf")
    for zone in ZONES:
        zlat, zlon = zone["center"]
        dist = haversine_m(lat, lon, zlat, zlon)
        if dist < zone["radius_deg"] * 111000 and dist < best_dist:
            best = zone["id"]
            best_dist = dist
    return best


def yamuna_distance_m(lat: float, lon: float) -> float:
    # Yamuna runs roughly north-south near 77.27E in Delhi
    return haversine_m(lat, lon, lat, 77.27)


def build_grid() -> pd.DataFrame:
    lats = np.arange(DELHI_BBOX["min_lat"], DELHI_BBOX["max_lat"], GRID_RES_DEG)
    lons = np.arange(DELHI_BBOX["min_lon"], DELHI_BBOX["max_lon"], GRID_RES_DEG)

    rows = []
    rng = np.random.default_rng(42)
    study_air_temp = 38.5
    study_wind = 2.8

    cp_lat, cp_lon = 28.6315, 77.2167

    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            dist_cp = haversine_m(lat, lon, cp_lat, cp_lon)
            dist_water = yamuna_distance_m(lat, lon)

            # Urban morphology proxies
            urban_core = np.exp(-dist_cp / 3500)
            water_cooling = np.exp(-dist_water / 1200)
            ridge_green = np.exp(-haversine_m(lat, lon, 28.62, 77.16) / 1800) * 0.35

            ndvi = np.clip(0.08 + ridge_green + water_cooling * 0.25 - urban_core * 0.18 + rng.normal(0, 0.02), 0.02, 0.72)
            ndbi = np.clip(0.05 + urban_core * 0.55 - ndvi * 0.35 + rng.normal(0, 0.03), 0.0, 0.85)
            impervious = np.clip(0.25 + urban_core * 0.55 - ndvi * 0.45 - water_cooling * 0.15, 0.05, 0.95)
            building_density = np.clip(0.1 + ndbi * 0.75 + urban_core * 0.2, 0.0, 1.0)

            if impervious > 0.65:
                albedo = 0.10 + rng.normal(0, 0.015)
            elif ndvi > 0.35:
                albedo = 0.20 + rng.normal(0, 0.02)
            elif dist_water < 900:
                albedo = 0.07 + rng.normal(0, 0.01)
            else:
                albedo = 0.13 + rng.normal(0, 0.02)
            albedo = float(np.clip(albedo, 0.05, 0.30))

            # Physics-inspired LST with UHI hotspot
            lst = (
                study_air_temp
                + 22 * (1 - albedo)
                - 16 * ndvi
                + 9 * impervious
                + 6 * building_density
                - 4 * water_cooling
                - 0.7 * study_wind
                + rng.normal(0, 0.8)
            )
            lst = float(np.clip(lst, 34, 64))

            zone_id = assign_zone(lat, lon)
            pop = int(max(50, (800 if zone_id else 120) * (0.4 + urban_core * 2.2) * rng.uniform(0.7, 1.3)))

            rows.append(
                {
                    "cell_id": f"{i}_{j}",
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "lst": round(lst, 2),
                    "ndvi": round(ndvi, 4),
                    "ndbi": round(ndbi, 4),
                    "impervious": round(impervious, 4),
                    "albedo": round(albedo, 4),
                    "building_density": round(building_density, 4),
                    "dist_water_m": round(dist_water, 1),
                    "wind": study_wind,
                    "air_temp": study_air_temp,
                    "pop": pop,
                    "zone_id": zone_id or "unassigned",
                }
            )

    return pd.DataFrame(rows)


def zone_geojson(df: pd.DataFrame) -> dict:
    features = []
    for zone in ZONES:
        zlat, zlon = zone["center"]
        r = zone["radius_deg"]
        ring = []
        for angle in np.linspace(0, 360, 37):
            rad = math.radians(angle)
            ring.append([zlon + r * math.cos(rad), zlat + r * 0.85 * math.sin(rad)])
        ring.append(ring[0])

        zdf = df[df["zone_id"] == zone["id"]]
        if zdf.empty:
            lst_mean = 45.0
            hri = 5.0
        else:
            lst_mean = float(zdf["lst"].mean())
            hri = float(np.clip((lst_mean - 38) / 2.4, 1, 10))

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": zone["id"],
                    "name": zone["name"],
                    "lst_mean": round(lst_mean, 1),
                    "heat_risk_index": round(hri, 1),
                    "population_exposed": zone["population"],
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )

    return {"type": "FeatureCollection", "features": features}


def heatmap_geojson(df: pd.DataFrame, sample_step: int = 3) -> dict:
    features = []
    for _, row in df.iloc[::sample_step].iterrows():
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "cell_id": row["cell_id"],
                    "lst": row["lst"],
                    "zone_id": row["zone_id"],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["lon"], row["lat"]],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def write_outputs(df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)

    df.to_csv(DATA_DIR / "grid_features.csv", index=False)

    zones = zone_geojson(df)
    heatmap = heatmap_geojson(df)

    for target in (DATA_DIR, DASHBOARD_DATA):
        (target / "zones.geojson").write_text(json.dumps(zones, indent=2), encoding="utf-8")
        (target / "heatmap.geojson").write_text(json.dumps(heatmap, indent=2), encoding="utf-8")

    meta = {
        "city": "Delhi NCT",
        "study_date": "2024-05-22",
        "data_source": "Synthetic demo grid (replace with Landsat 8 / Sentinel-2 GEE export)",
        "bbox": DELHI_BBOX,
        "grid_resolution_m": 250,
        "cell_count": len(df),
    }
    meta_json = json.dumps(meta, indent=2)
    (DATA_DIR / "metadata.json").write_text(meta_json, encoding="utf-8")
    (DASHBOARD_DATA / "metadata.json").write_text(meta_json, encoding="utf-8")

    print(f"Generated {len(df)} grid cells")
    print(f"Saved to {DATA_DIR} and {DASHBOARD_DATA}")


def main() -> None:
    df = build_grid()
    write_outputs(df)


if __name__ == "__main__":
    main()
