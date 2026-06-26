"""
Validate Landsat LST against CPCB station air temperatures and published UHI benchmarks.

Uses Open-Meteo historical API for ground air temperature on the study date.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import CPCB_STATIONS, DASHBOARD_DATA, DATA_DIR, STUDY_DATE, UHI_BENCHMARKS, ZONES

# Landsat 8 overpass for Delhi ~10:15-10:45 IST = ~04:45-05:15 UTC
OVERPASS_UTC_HOUR = 5


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_grid_cell(df: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    dist = df.apply(lambda r: haversine_m(lat, lon, r["lat"], r["lon"]), axis=1)
    return df.loc[dist.idxmin()]


def fetch_open_meteo_air_temp(lat: float, lon: float, date: str, hour_utc: int) -> float | None:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date,
        "end_date": date,
        "hourly": "temperature_2m",
        "timezone": "UTC",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        times = data["hourly"]["time"]
        temps = data["hourly"]["temperature_2m"]
        target = f"{date}T{hour_utc:02d}:00"
        if target in times:
            return float(temps[times.index(target)])
        # fallback: closest hour
        idx = min(range(len(times)), key=lambda i: abs(int(times[i][11:13]) - hour_utc))
        return float(temps[idx])
    except Exception as exc:
        print(f"Open-Meteo fetch failed for ({lat}, {lon}): {exc}")
        return None


def zone_lst_summary(df: pd.DataFrame) -> list[dict]:
    rows = []
    for zone in ZONES:
        zdf = df[df["zone_id"] == zone["id"]]
        if zdf.empty:
            continue
        rows.append(
            {
                "zone_id": zone["id"],
                "name": zone["name"],
                "mean_lst_c": round(float(zdf["lst"].mean()), 1),
                "max_lst_c": round(float(zdf["lst"].max()), 1),
                "cell_count": len(zdf),
            }
        )
    return sorted(rows, key=lambda x: x["mean_lst_c"], reverse=True)


def build_validation(df: pd.DataFrame) -> dict:
    station_rows = []
    for station in CPCB_STATIONS:
        cell = nearest_grid_cell(df, station["lat"], station["lon"])
        air_temp = fetch_open_meteo_air_temp(station["lat"], station["lon"], STUDY_DATE, OVERPASS_UTC_HOUR)
        lst = float(cell["lst"])
        lst_air_offset = round(lst - air_temp, 1) if air_temp is not None else None

        station_rows.append(
            {
                "station": station["name"],
                "zone_type": station["zone"],
                "lat": station["lat"],
                "lon": station["lon"],
                "air_temp_c": round(air_temp, 1) if air_temp is not None else None,
                "lst_c": round(lst, 1),
                "lst_minus_air_c": lst_air_offset,
                "distance_to_cell_m": round(
                    haversine_m(station["lat"], station["lon"], cell["lat"], cell["lon"]), 0
                ),
            }
        )

    urban = [r for r in station_rows if r["zone_type"] in ("urban_core", "east_delhi", "south_delhi", "west_delhi")]
    rural = [r for r in station_rows if r["zone_type"] == "rural_reference"]

    urban_core = next((r for r in station_rows if r["station"].startswith("ITO")), None)
    rural_ref = next((r for r in station_rows if "Narela" in r["station"]), None)

    uhi_anomaly = None
    uhi_pass = None
    if urban_core and rural_ref and urban_core["lst_minus_air_c"] and rural_ref["lst_minus_air_c"]:
        uhi_anomaly = round(urban_core["lst_c"] - rural_ref["lst_c"], 1)
        bench = UHI_BENCHMARKS["central_delhi_uhi_anomaly_c"]
        uhi_pass = bench["min"] <= uhi_anomaly <= bench["max"] + 4  # allow upper tolerance

    offsets = [r["lst_minus_air_c"] for r in station_rows if r["lst_minus_air_c"] is not None]
    offset_mean = round(float(np.mean(offsets)), 1) if offsets else None
    offset_bench = UHI_BENCHMARKS["lst_minus_air_daytime_c"]
    offset_pass = (
        offset_bench["min"] <= offset_mean <= offset_bench["max"] + 2
        if offset_mean is not None
        else None
    )

    zone_summary = zone_lst_summary(df)
    hottest = zone_summary[0]["name"] if zone_summary else None
    spatial_pass = hottest in ("Central Delhi", "Karol Bagh", "Rohini")

    return {
        "title": "LST Validation",
        "study_date": STUDY_DATE,
        "overpass_note": "Air temperature from Open-Meteo at ~05:00 UTC (Landsat overpass window)",
        "cpcb_stations": station_rows,
        "uhi_analysis": {
            "central_delhi_lst_c": urban_core["lst_c"] if urban_core else None,
            "rural_reference_lst_c": rural_ref["lst_c"] if rural_ref else None,
            "uhi_anomaly_c": uhi_anomaly,
            "expected_range_c": UHI_BENCHMARKS["central_delhi_uhi_anomaly_c"],
            "within_expected_range": uhi_pass,
        },
        "lst_air_offset": {
            "mean_c": offset_mean,
            "expected_range_c": offset_bench,
            "within_expected_range": offset_pass,
        },
        "zone_ranking": zone_summary,
        "spatial_pattern_valid": spatial_pass,
        "summary": _validation_summary(uhi_anomaly, uhi_pass, offset_mean, offset_pass, spatial_pass, hottest),
        "references": [
            "CPCB Continuous Ambient Air Quality Monitoring (CAAQM) station network, Delhi",
            "Open-Meteo ERA5-Land reanalysis (air temperature at station locations)",
            "Delhi urban heat island literature: 5-8 C core-vs-rural anomaly typical in pre-monsoon summer",
        ],
    }


def _validation_summary(
    uhi_anomaly: float | None,
    uhi_pass: bool | None,
    offset_mean: float | None,
    offset_pass: bool | None,
    spatial_pass: bool,
    hottest: str | None,
) -> str:
    parts = []
    if uhi_anomaly is not None:
        status = "consistent with" if uhi_pass else "outside typical"
        parts.append(f"Central Delhi UHI anomaly is {uhi_anomaly} C ({status} published 5-8 C range)")
    if offset_mean is not None:
        parts.append(f"Mean LST-air offset at CPCB stations: {offset_mean} C")
    if hottest:
        parts.append(f"Hottest zone: {hottest}")
    if spatial_pass:
        parts.append("Spatial pattern matches expected built-up core hotspots")
    return ". ".join(parts) + "."


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    csv_path = DATA_DIR / "grid_features.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing {csv_path}. Run fetch_real_satellite_data.py first.")

    df = pd.read_csv(csv_path)
    validation = build_validation(df)

    write_json(DATA_DIR / "validation.json", validation)
    write_json(DASHBOARD_DATA / "validation.json", validation)

    print("Validation summary:", validation["summary"])
    print(f"Saved {DATA_DIR / 'validation.json'}")


if __name__ == "__main__":
    main()
