# Delhi Urban Heat Mitigation System

Geospatial AI/ML system for identifying urban heat stress hotspots, quantifying drivers of urban heating, and generating optimized cooling interventions for Delhi NCT.

Built for the IIRS/ISRO urban heat hackathon framework:

1. Identify heat hotspots
2. Analyze drivers
3. Model with physics-informed AI/ML
4. Simulate cooling scenarios
5. Optimize and recommend

## Project structure

```
delhi-heat-mitigation/
├── gee/export_delhi.js          # Real Landsat export (Google Earth Engine)
├── scripts/
│   ├── config.py
│   ├── generate_delhi_data.py   # Demo grid generator
│   └── train_and_simulate.py    # ML + scenarios + optimizer
├── data/processed/              # Generated CSV/JSON/model
└── dashboard/                   # React dashboard
```

## Quick start

### 1. Python pipeline

```powershell
cd C:\Users\LENOVO\delhi-heat-mitigation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/generate_delhi_data.py
python scripts/train_and_simulate.py
```

### 2. Dashboard (no Node.js required)

```powershell
cd C:\Users\LENOVO\delhi-heat-mitigation\dashboard\public
python -m http.server 8080
```

Open http://localhost:8080

This standalone dashboard uses the JSON in `public/data/` and does not need `npm install`.

### 3. Dashboard (React version, optional)

Install Node.js 18+, then:

```powershell
cd C:\Users\LENOVO\delhi-heat-mitigation\dashboard
npm install
npm run dev
```

Open http://localhost:5173

## Replace demo data with real satellite data

1. Run `gee/export_delhi.js` in Google Earth Engine
2. Download exported CSV from Google Drive
3. Map columns to `grid_features.csv` format:
   - `LST_C` -> `lst`
   - `NDVI` -> `ndvi`
   - `NDBI` -> `ndbi`
   - derive `impervious`, `albedo`, `building_density`
4. Re-run `python scripts/train_and_simulate.py`

## Outputs

| File | Purpose |
|------|---------|
| `grid_features.csv` | 250 m grid features + LST |
| `zones.geojson` | Neighborhood zones for map |
| `scenarios.json` | Cooling potential by strategy |
| `priority_table.json` | Neighborhood prioritization |
| `insights.json` | AIML insight panel content |
| `materials.json` | Material comparison table |

## Hackathon demo script

1. Show Delhi heat map with Central Delhi hotspot
2. Open AIML insights (drivers + recommendation)
3. Show cooling potential bar chart
4. Show neighborhood priority table
5. Toggle scenario view (baseline vs cool roofs)

## Notes

- Current bundled data is a **physics-realistic synthetic Delhi grid** so the full app runs offline immediately.
- Swap in Landsat 8 / Sentinel-2 / ERA5 exports without changing the dashboard.
