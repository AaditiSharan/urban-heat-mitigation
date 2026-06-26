"""
Fetch real Landsat 8 LST + Sentinel-2 NDVI/NDBI for Delhi (2024-05-22).

Primary: Google Earth Engine (mirrors gee/export_delhi.js).
Fallback: Microsoft Planetary Computer STAC when GEE is not authenticated.

Usage:
    python scripts/fetch_real_satellite_data.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA_DIR, DASHBOARD_DATA, DELHI_BBOX, GRID_RES_DEG, ZONES
from generate_delhi_data import assign_zone, heatmap_geojson, zone_geojson, yamuna_distance_m

STUDY_DATE = "2024-05-22"
WINDOW_DAYS = 7


def _asset_href(item, *names: str) -> str | None:
    for name in names:
        if name in item.assets:
            return item.assets[name].href
        lower = {k.lower(): k for k in item.assets}
        if name.lower() in lower:
            return item.assets[lower[name.lower()]].href
    return None


def _build_coordinate_grid() -> pd.DataFrame:
    lats = np.arange(DELHI_BBOX["min_lat"], DELHI_BBOX["max_lat"], GRID_RES_DEG)
    lons = np.arange(DELHI_BBOX["min_lon"], DELHI_BBOX["max_lon"], GRID_RES_DEG)
    rows = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            rows.append({"cell_id": f"{i}_{j}", "lat": round(float(lat), 6), "lon": round(float(lon), 6)})
    return pd.DataFrame(rows)


def _add_derived_and_auxiliary(df: pd.DataFrame, rng_seed: int = 42) -> pd.DataFrame:
    """Add derived surface features and morphology proxies from satellite indices."""
    rng = np.random.default_rng(rng_seed)
    cp_lat, cp_lon = 28.6315, 77.2167
    study_air_temp = 38.5
    study_wind = 2.8
    study_humidity = 35.0

    out = df.copy()
    out["ndvi"] = out["ndvi"].clip(0.02, 0.90)
    out["ndbi"] = out["ndbi"].clip(0.0, 0.85)

    if "impervious" not in out.columns:
        if "lulc" in out.columns:
            out["impervious"] = np.select(
                [out["lulc"] == 3, out["lulc"] == 1, out["lulc"] == 2],
                [0.80, 0.10, 0.20],
                default=0.40 + out["ndbi"] * 0.4,
            )
        else:
            out["impervious"] = (0.25 + out["ndbi"] * 0.55 - out["ndvi"] * 0.25).clip(0.05, 0.95)

    if "albedo" not in out.columns or out["albedo"].isna().any():
        out["albedo"] = np.select(
            [out["ndvi"] > 0.45, out["ndbi"] > 0.25],
            [0.22, 0.10],
            default=0.15,
        )

    out["building_density"] = (0.15 + out["ndbi"] * 0.70).clip(0.0, 1.0)
    out["dist_water_m"] = out.apply(lambda r: yamuna_distance_m(r["lat"], r["lon"]), axis=1)

    dist_cp = out.apply(
        lambda r: math.sqrt((r["lat"] - cp_lat) ** 2 + (r["lon"] - cp_lon) ** 2) * 111000,
        axis=1,
    )
    urban_core = np.exp(-dist_cp / 3500)

    out["building_height_m"] = (10 + out["building_density"] * 25).clip(5, 50)
    out["sky_view_factor"] = np.exp(-0.15 * out["building_density"] * (out["building_height_m"] / 10)).clip(0.15, 0.95)
    out["street_width_m"] = (8 + (1 - out["building_density"]) * 20).clip(5, 35)
    out["ghsl_built_up"] = (0.85 * np.exp(-dist_cp / 4000) + 0.1).clip(0.1, 0.95)
    out["population_density"] = (out["ghsl_built_up"] * 250).clip(10, 500)
    out["thermal_anisotropy"] = (0.1 + (1 - out["sky_view_factor"]) * 0.3).clip(0.1, 0.8)

    out["air_temp"] = study_air_temp + 3.0 * np.exp(-dist_cp / 6000) + rng.normal(0, 0.4, len(out))
    out["humidity"] = study_humidity - 2.0 * urban_core + rng.normal(0, 2.5, len(out))
    out["wind"] = study_wind * (1 - 0.25 * urban_core) + rng.normal(0, 0.2, len(out))

    out["zone_id"] = out.apply(lambda r: assign_zone(r["lat"], r["lon"]) or "unassigned", axis=1)
    out["pop"] = (120 + urban_core * 700).astype(int)

    return out


def fetch_with_earth_engine(num_pixels: int = 12000) -> pd.DataFrame | None:
    try:
        import ee
    except ImportError:
        print("earthengine-api not installed.")
        return None

    try:
        ee.Initialize()
    except Exception as exc:
        print(f"Earth Engine not authenticated: {exc}")
        print("Run: earthengine authenticate")
        return None

    delhi = ee.Geometry.Rectangle(
        [DELHI_BBOX["min_lon"], DELHI_BBOX["min_lat"], DELHI_BBOX["max_lon"], DELHI_BBOX["max_lat"]]
    )
    study = ee.Date(STUDY_DATE)
    start = study.advance(-WINDOW_DAYS, "day")
    end = study.advance(WINDOW_DAYS, "day")

    def mask_l8(image):
        qa = image.select("QA_PIXEL")
        mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        return image.updateMask(mask)

    def compute_l8(image):
        ndvi = image.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
        lst = (
            image.select("ST_B10")
            .multiply(0.00341802)
            .add(149.0)
            .subtract(273.15)
            .rename("LST_L8")
        )
        return image.addBands([ndvi, lst])

    l8 = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(delhi)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUD_COVER", 15))
        .map(mask_l8)
        .map(compute_l8)
        .median()
        .clip(delhi)
    )

    def mask_s2(image):
        qa = image.select("QA60")
        cloud = 1 << 10
        cirrus = 1 << 11
        mask = qa.bitwiseAnd(cloud).eq(0).And(qa.bitwiseAnd(cirrus).eq(0))
        return image.updateMask(mask)

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(delhi)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .map(mask_s2)
        .median()
        .clip(delhi)
    )

    s2_ndvi = s2.normalizedDifference(["B8", "B4"]).rename("NDVI_S2")
    s2_ndbi = s2.normalizedDifference(["B11", "B8"]).rename("NDBI_S2")
    s2_mndwi = s2.normalizedDifference(["B3", "B11"]).rename("MNDWI_S2")
    s2_lulc = (
        ee.Image(0)
        .where(s2_mndwi.gt(0.1), 1)
        .where(s2_ndvi.gt(0.45), 2)
        .where(s2_ndbi.gt(0.2), 3)
        .rename("LULC_S2")
    )

    l8_ndbi = l8.normalizedDifference(["SR_B6", "SR_B5"]).rename("NDBI_L8")
    l8_ndvi = l8.select("NDVI")

    combined_lulc = s2_lulc.rename("LULC")
    combined_lst = l8.select("LST_L8").rename("LST")
    combined_ndvi = s2_ndvi.unmask(l8_ndvi).rename("NDVI")
    combined_ndbi = s2_ndbi.unmask(l8_ndbi).rename("NDBI")
    albedo = (
        ee.Image(0.12)
        .where(combined_lulc.eq(1), 0.06)
        .where(combined_lulc.eq(2), 0.22)
        .where(combined_lulc.eq(3), 0.10)
        .rename("ALBEDO")
    )

    stack = (
        combined_lst.addBands([combined_ndvi, combined_ndbi, combined_lulc, albedo])
        .reproject(crs="EPSG:32643", scale=250)
    )

    samples = stack.sample(
        region=delhi,
        scale=250,
        numPixels=num_pixels,
        seed=42,
        geometries=True,
    )

    rows = samples.getInfo()["features"]
    records = []
    for feat in rows:
        props = feat["properties"]
        geom = feat["geometry"]["coordinates"]
        lst = props.get("LST")
        if lst is None or lst < 20 or lst > 70:
            continue
        records.append(
            {
                "lon": round(geom[0], 6),
                "lat": round(geom[1], 6),
                "lst": round(float(lst), 2),
                "ndvi": round(float(props.get("NDVI", 0.2)), 4),
                "ndbi": round(float(props.get("NDBI", 0.2)), 4),
                "lulc": int(props.get("LULC", 0)),
                "albedo": round(float(props.get("ALBEDO", 0.12)), 4),
            }
        )

    if not records:
        print("Earth Engine returned no valid LST samples.")
        return None

    df = pd.DataFrame(records)
    df["cell_id"] = [f"gee_{i}" for i in range(len(df))]
    print(f"Earth Engine: fetched {len(df)} valid cells (LST {df['lst'].min():.1f}-{df['lst'].max():.1f} C)")
    return df


def fetch_with_planetary_computer() -> pd.DataFrame | None:
    """Fallback using Microsoft Planetary Computer STAC + rasterio (no GEE account required)."""
    try:
        import planetary_computer
        import pystac_client
        import pyproj
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds
    except ImportError:
        print("Planetary Computer fallback requires: pystac-client planetary-computer pyproj rasterio")
        return None

    bbox_wgs84 = (
        DELHI_BBOX["min_lon"],
        DELHI_BBOX["min_lat"],
        DELHI_BBOX["max_lon"],
        DELHI_BBOX["max_lat"],
    )

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign,
    )

    print("Planetary Computer: searching Landsat 8 L2 scenes...")
    l8_items = list(
        catalog.search(
            collections=["landsat-c2-l2"],
            bbox=list(bbox_wgs84),
            datetime="2024-05-15/2024-05-30",
            query={"eo:cloud_cover": {"lt": 25}},
            max_items=12,
        ).items()
    )
    if not l8_items:
        print("No Landsat scenes found for the study window.")
        return None

    l8_items.sort(key=lambda item: item.properties.get("eo:cloud_cover", 100))
    lst_stack = []
    ndvi_stack = []
    ndbi_stack = []

    for item in l8_items[:4]:
        signed = planetary_computer.sign(item)
        st_href = _asset_href(signed, "ST_B10", "lwir11")
        b4_href = _asset_href(signed, "SR_B4", "red")
        b5_href = _asset_href(signed, "SR_B5", "nir08")
        b6_href = _asset_href(signed, "SR_B6", "swir16")
        qa_href = _asset_href(signed, "QA_PIXEL", "qa_pixel")
        if not all([st_href, b4_href, b5_href, b6_href, qa_href]):
            print(f"Skipping {signed.id}: missing required Landsat assets")
            continue

        try:
            with rasterio.open(st_href) as st_src:
                dst_bounds = transform_bounds("EPSG:4326", st_src.crs, *bbox_wgs84)
                window = from_bounds(*dst_bounds, transform=st_src.transform)
                st = st_src.read(1, window=window, boundless=True, fill_value=0).astype("float32")
                transform = rasterio.windows.transform(window, st_src.transform)
                raster_crs = st_src.crs

            with rasterio.open(qa_href) as qa_src:
                qa = qa_src.read(1, window=window, boundless=True, fill_value=65535).astype("uint16")
            cloud_mask = ((qa & (1 << 3)) == 0) & ((qa & (1 << 4)) == 0)

            with rasterio.open(b4_href) as b4_src:
                b4 = b4_src.read(1, window=window, boundless=True, fill_value=0).astype("float32")
            with rasterio.open(b5_href) as b5_src:
                b5 = b5_src.read(1, window=window, boundless=True, fill_value=0).astype("float32")
            with rasterio.open(b6_href) as b6_src:
                b6 = b6_src.read(1, window=window, boundless=True, fill_value=0).astype("float32")

            lst_c = st * 0.00341802 + 149.0 - 273.15
            lst_c = np.where(cloud_mask, lst_c, np.nan)
            ndvi = np.where(cloud_mask, (b5 - b4) / (b5 + b4 + 1e-6), np.nan)
            ndbi = np.where(cloud_mask, (b6 - b5) / (b6 + b5 + 1e-6), np.nan)

            lst_stack.append(lst_c)
            ndvi_stack.append(ndvi)
            ndbi_stack.append(ndbi)
            raster_transform = transform
        except Exception as exc:
            print(f"Failed reading {signed.id}: {exc}")
            continue

    if not lst_stack:
        print("Could not read Landsat LST rasters from Planetary Computer.")
        return None

    lst_median = np.nanmedian(np.stack(lst_stack), axis=0)
    ndvi_median = np.nanmedian(np.stack(ndvi_stack), axis=0)
    ndbi_median = np.nanmedian(np.stack(ndbi_stack), axis=0)

    print("Planetary Computer: searching Sentinel-2 scenes...")
    s2_items = list(
        catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=list(bbox_wgs84),
            datetime="2024-05-15/2024-05-30",
            query={"eo:cloud_cover": {"lt": 30}},
            max_items=6,
        ).items()
    )
    if s2_items:
        s2_items.sort(key=lambda item: item.properties.get("eo:cloud_cover", 100))
        s2_ndvi_stack = []
        s2_ndbi_stack = []
        for item in s2_items[:3]:
            signed = planetary_computer.sign(item)
            b04_href = _asset_href(signed, "B04")
            b08_href = _asset_href(signed, "B08")
            b11_href = _asset_href(signed, "B11")
            if not all([b04_href, b08_href, b11_href]):
                continue
            try:
                with rasterio.open(b08_href) as b8_src:
                    dst_bounds = transform_bounds("EPSG:4326", b8_src.crs, *bbox_wgs84)
                    window = from_bounds(*dst_bounds, transform=b8_src.transform)
                    b8 = b8_src.read(1, window=window, boundless=True, fill_value=0).astype("float32")
                with rasterio.open(b04_href) as b4_src:
                    b4 = b4_src.read(1, window=window, boundless=True, fill_value=0).astype("float32")
                with rasterio.open(b11_href) as b11_src:
                    b11 = b11_src.read(1, window=window, boundless=True, fill_value=0).astype("float32")
                s2_ndvi_stack.append((b8 - b4) / (b8 + b4 + 1e-6))
                s2_ndbi_stack.append((b11 - b8) / (b11 + b8 + 1e-6))
            except Exception as exc:
                print(f"Failed reading S2 {signed.id}: {exc}")
                continue

        if s2_ndvi_stack:
            s2_ndvi_median = np.nanmedian(np.stack(s2_ndvi_stack), axis=0)
            s2_ndbi_median = np.nanmedian(np.stack(s2_ndbi_stack), axis=0)
            # Resample S2 (10m) to Landsat grid shape via nearest indices
            if s2_ndvi_median.shape != ndvi_median.shape:
                y_idx = np.linspace(0, s2_ndvi_median.shape[0] - 1, ndvi_median.shape[0]).astype(int)
                x_idx = np.linspace(0, s2_ndvi_median.shape[1] - 1, ndvi_median.shape[1]).astype(int)
                s2_ndvi_median = s2_ndvi_median[np.ix_(y_idx, x_idx)]
                s2_ndbi_median = s2_ndbi_median[np.ix_(y_idx, x_idx)]
            valid_s2 = np.isfinite(s2_ndvi_median)
            ndvi_median = np.where(valid_s2, s2_ndvi_median, ndvi_median)
            ndbi_median = np.where(valid_s2, s2_ndbi_median, ndbi_median)

    grid = _build_coordinate_grid()
    transformer = pyproj.Transformer.from_crs("EPSG:4326", raster_crs, always_xy=True)
    xs, ys = transformer.transform(grid["lon"].values, grid["lat"].values)

    height, width = lst_median.shape
    col_idx = np.floor((xs - raster_transform.c) / raster_transform.a).astype(int)
    row_idx = np.floor((ys - raster_transform.f) / raster_transform.e).astype(int)
    in_bounds = (row_idx >= 0) & (row_idx < height) & (col_idx >= 0) & (col_idx < width)

    grid["lst"] = np.nan
    grid["ndvi"] = np.nan
    grid["ndbi"] = np.nan
    grid.loc[in_bounds, "lst"] = lst_median[row_idx[in_bounds], col_idx[in_bounds]]
    grid.loc[in_bounds, "ndvi"] = ndvi_median[row_idx[in_bounds], col_idx[in_bounds]]
    grid.loc[in_bounds, "ndbi"] = ndbi_median[row_idx[in_bounds], col_idx[in_bounds]]

    valid = (
        np.isfinite(grid["lst"])
        & (grid["lst"] > 25)
        & (grid["lst"] < 65)
        & np.isfinite(grid["ndvi"])
        & np.isfinite(grid["ndbi"])
    )
    df = grid.loc[valid].copy()
    if df.empty:
        print("Planetary Computer sampling produced no valid cells.")
        return None

    df["lulc"] = np.select(
        [df["ndvi"] > 0.45, df["ndbi"] > 0.2],
        [2, 3],
        default=0,
    )
    df["albedo"] = np.select(
        [df["lulc"] == 2, df["lulc"] == 3],
        [0.22, 0.10],
        default=0.15,
    )

    print(
        f"Planetary Computer: sampled {len(df)} grid cells "
        f"(LST {df['lst'].min():.1f}-{df['lst'].max():.1f} C)"
    )
    return df


def write_real_outputs(df: pd.DataFrame, source_label: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)

    cols = [
        "cell_id", "lat", "lon", "lst", "ndvi", "ndbi", "impervious",
        "albedo", "building_density", "dist_water_m", "wind", "air_temp",
        "humidity", "sky_view_factor", "building_height_m", "street_width_m",
        "ghsl_built_up", "population_density", "thermal_anisotropy", "pop", "zone_id",
    ]
    df = df[cols]
    df.to_csv(DATA_DIR / "grid_features.csv", index=False)

    zones = zone_geojson(df)
    heatmap = heatmap_geojson(df)
    meta = {
        "city": "Delhi NCT",
        "study_date": STUDY_DATE,
        "data_source": source_label,
        "bbox": DELHI_BBOX,
        "grid_resolution_m": 250,
        "cell_count": len(df),
        "satellite_layers": {
            "lst": "Landsat 8 Collection 2 L2 (ST_B10)",
            "ndvi": "Sentinel-2 (B8/B4) with Landsat 8 fallback",
            "ndbi": "Sentinel-2 (B11/B8) with Landsat 8 fallback",
        },
        "study_window_days": WINDOW_DAYS,
    }

    for target in (DATA_DIR, DASHBOARD_DATA):
        (target / "zones.geojson").write_text(json.dumps(zones, indent=2), encoding="utf-8")
        (target / "heatmap.geojson").write_text(json.dumps(heatmap, indent=2), encoding="utf-8")
        (target / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Saved {len(df)} cells to {DATA_DIR / 'grid_features.csv'}")


def main() -> None:
    print(f"Fetching real satellite data for Delhi | study date {STUDY_DATE}")

    raw = fetch_with_earth_engine()
    source = "Landsat 8 + Sentinel-2 via Google Earth Engine (2024-05-22 window)"

    if raw is None:
        print("\nTrying Planetary Computer fallback...")
        raw = fetch_with_planetary_computer()
        source = "Landsat 8 + Sentinel-2 via Microsoft Planetary Computer (2024-05-15 to 2024-05-30)"

    if raw is None:
        raise RuntimeError(
            "Could not fetch real satellite data. "
            "Authenticate GEE (`earthengine authenticate`) or install Planetary Computer deps."
        )

    df = _add_derived_and_auxiliary(raw)
    write_real_outputs(df, source)
    print("Real satellite grid ready. Next: python scripts/validate_lst.py && python scripts/train_and_simulate.py")


if __name__ == "__main__":
    main()
