"""Shared configuration for Delhi urban heat mitigation pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
DASHBOARD_DATA = ROOT / "dashboard" / "public" / "data"

# Delhi NCT bounding box
DELHI_BBOX = {
    "min_lon": 76.83,
    "min_lat": 28.40,
    "max_lon": 77.35,
    "max_lat": 28.88,
}

GRID_RES_DEG = 0.00225  # ~250 m

FEATURE_COLUMNS = [
    "ndvi",
    "ndbi",
    "impervious",
    "albedo",
    "building_density",
    "dist_water_m",
    "wind",
    "air_temp",
]

ZONES = [
    {
        "id": "central_delhi",
        "name": "Central Delhi",
        "center": (28.6315, 77.2167),
        "radius_deg": 0.018,
        "population": 31245,
    },
    {
        "id": "karol_bagh",
        "name": "Karol Bagh",
        "center": (28.6512, 77.1910),
        "radius_deg": 0.015,
        "population": 28400,
    },
    {
        "id": "rohini",
        "name": "Rohini",
        "center": (28.7434, 77.0676),
        "radius_deg": 0.020,
        "population": 35600,
    },
    {
        "id": "dwarka",
        "name": "Dwarka",
        "center": (28.5921, 77.0460),
        "radius_deg": 0.018,
        "population": 29800,
    },
    {
        "id": "mayur_vihar",
        "name": "Mayur Vihar",
        "center": (28.6090, 77.2950),
        "radius_deg": 0.016,
        "population": 26500,
    },
    {
        "id": "saket",
        "name": "Saket",
        "center": (28.5244, 77.2066),
        "radius_deg": 0.015,
        "population": 22100,
    },
    {
        "id": "najafgarh",
        "name": "Najafgarh",
        "center": (28.6092, 77.0360),
        "radius_deg": 0.018,
        "population": 18700,
    },
    {
        "id": "yamuna_fringe",
        "name": "Yamuna Fringe",
        "center": (28.6500, 77.2800),
        "radius_deg": 0.014,
        "population": 9200,
    },
]

MATERIALS = [
    {
        "material": "Conventional Asphalt",
        "albedo": 0.08,
        "surface_temp": 62.3,
        "cost_inr_m2": 450,
        "durability": "7-10 years",
    },
    {
        "material": "Cool Pavement Coating",
        "albedo": 0.35,
        "surface_temp": 48.1,
        "cost_inr_m2": 680,
        "durability": "5-8 years",
    },
    {
        "material": "High-Albedo Roof Paint",
        "albedo": 0.70,
        "surface_temp": 42.4,
        "cost_inr_m2": 320,
        "durability": "3-5 years",
    },
    {
        "material": "Cool Roof Membrane",
        "albedo": 0.65,
        "surface_temp": 44.0,
        "cost_inr_m2": 550,
        "durability": "10-15 years",
    },
    {
        "material": "Permeable Green Pavers",
        "albedo": 0.28,
        "surface_temp": 51.2,
        "cost_inr_m2": 820,
        "durability": "8-12 years",
    },
]

INTERVENTIONS = {
    "cool_roofs": {"label": "Cool Roofs", "albedo": 0.25, "ndvi": 0.0, "impervious": 0.0},
    "cool_pavements": {"label": "Cool Pavements", "albedo": 0.20, "ndvi": 0.0, "impervious": -0.05},
    "urban_greening": {"label": "Urban Greening", "albedo": 0.02, "ndvi": 0.15, "impervious": -0.08},
    "green_roofs": {"label": "Green Roofs", "albedo": 0.10, "ndvi": 0.10, "impervious": -0.03},
    "high_albedo_paint": {"label": "High Albedo Paint", "albedo": 0.35, "ndvi": 0.0, "impervious": 0.0},
}

COST_PER_M2 = {
    "cool_roofs": 550,
    "cool_pavements": 680,
    "urban_greening": 420,
    "green_roofs": 900,
    "high_albedo_paint": 320,
}

DEFAULT_BUDGET_INR = 50_000_000  # 5 crore demo budget (50M INR)
