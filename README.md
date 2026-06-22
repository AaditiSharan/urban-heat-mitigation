# Delhi Urban Heat Mitigation System

Geospatial AI/ML system for identifying urban heat stress hotspots, quantifying drivers of urban heating, and generating optimized cooling interventions for Delhi NCT.

Built for the IIRS/ISRO urban heat hackathon framework:

1. Identify heat hotspots
2. Analyze drivers
3. Model with physics-informed AI/ML
4. Simulate cooling scenarios
5. Optimize and recommend

## Data Sources

### Remote Sensing Data
- **Landsat 8**: Land Surface Temperature (LST), NDVI, NDBI at 30m resolution (primary LST source)
- **ECOSTRESS**: High-resolution LST (70m) from ISS for thermal anisotropy analysis (limited coverage - may not be available for Delhi in GEE)
- **Sentinel-2**: Land Use/Land Cover (LULC) at 10m resolution with improved accuracy

### Meteorological Data
- **ERA5**: Atmospheric reanalysis data (air temperature, humidity, wind speed) at 0.25° resolution
- **CPCB**: Central Pollution Control Board ground station measurements (optional alternative)

### Urban Form & Infrastructure
- **OpenStreetMap**: Building footprints, road networks, urban morphology features
- **GHSL**: Global Human Settlement Layer for built-up density and population
- **UT-GLOBUS**: Urban morphology data (optional, if available)

### Optional Modeling Tools
- **SOLWEIG**: Solar LongWave Environmental Irradiance Geometry for thermal comfort modeling
- **InVEST**: Integrated Valuation of Ecosystem Services for cooling capacity and carbon sequestration

## Project structure

```
delhi-heat-mitigation/
├── gee/export_delhi.js              # Multi-sensor GEE export (Landsat 8, ECOSTRESS, Sentinel-2)
├── scripts/
│   ├── config.py                    # Configuration with data source parameters
│   ├── generate_delhi_data.py       # Demo grid generator with enhanced features
│   ├── process_meteorological_urban.py  # ERA5, OSM, GHSL, CPCB data processing
│   ├── train_and_simulate.py        # ML + scenarios + optimizer (enhanced)
│   ├── integrate_solweig.py         # SOLWEIG thermal comfort integration
│   └── integrate_invest.py          # InVEST ecosystem services integration
├── data/processed/                  # Generated CSV/JSON/model
└── dashboard/                       # React dashboard
```

## Quick start

### 1. Python pipeline

```powershell
cd C:\Users\LENOVO\urban-heat-mitigation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/generate_delhi_data.py
python scripts/process_meteorological_urban.py  # Process ERA5/OSM/GHSL data
python scripts/train_and_simulate.py
```

### 2. Dashboard (no Node.js required)

```powershell
cd C:\Users\LENOVO\urban-heat-mitigation\dashboard\public
python -m http.server 8080
```

Open http://localhost:8080

This standalone dashboard uses the JSON in `public/data/` and does not need `npm install`.

### 3. Dashboard (React version, optional)

Install Node.js 18+, then:

```powershell
cd C:\Users\LENOVO\urban-heat-mitigation\dashboard
npm install
npm run dev
```

Open http://localhost:5173

## Data Integration Workflow

### Option 1: Use Synthetic Data (Quick Start)
The system includes physics-realistic synthetic data for immediate use:
- Enhanced with urban morphology features (sky view factor, building height)
- Meteorological variables (humidity, wind patterns)
- Thermal anisotropy from ECOSTRESS-like patterns
- GHSL built-up and population density

### Option 2: Integrate Real Data

#### Step 1: Remote Sensing Data (Google Earth Engine)
1. Open https://code.earthengine.google.com/
2. Run `gee/export_delhi.js` to export multi-sensor data:
   - Landsat 8 LST, NDVI, NDBI
   - ECOSTRESS LST (thermal anisotropy)
   - Sentinel-2 LULC
3. Download exported CSV from Google Drive
4. Map columns to `grid_features.csv` format

#### Step 2: Meteorological Data (ERA5)
1. Register at https://cds.climate.copernicus.eu/
2. Install API key in `~/.cdsapirc`
3. Run `python scripts/process_meteorological_urban.py` to download ERA5 data
4. Alternative: Download CPCB data manually and place in `data/processed/cpcb_meteorological.csv`

#### Step 3: Urban Morphology Data (OSM)
1. The system automatically downloads OSM data using OSMnx
2. Extracts building footprints, road networks, and urban morphology features
3. Calculates sky view factor, building height, street width

#### Step 4: GHSL Data
1. Download GHSL built-up data from https://ghsl.jrc.ec.europa.eu/
2. Save as `data/processed/ghsl_built_up.tif`
3. System processes and integrates with grid data

#### Step 5: Optional Tools
- **SOLWEIG**: Enable in `config.py` by setting `SOLWEIG_CONFIG['enabled'] = True`
- **InVEST**: Enable in `config.py` by setting `INVEST_CONFIG['enabled'] = True`

### Step 6: Train Model
```powershell
python scripts/train_and_simulate.py
```

## Enhanced Features

### Physics-Informed Modeling
- **Urban Canyon Effect**: Sky view factor captures trapped radiation
- **Thermal Mass**: Building height influences heat storage
- **Humidity Effects**: Moist air reduces diurnal temperature range
- **Thermal Anisotropy**: Directional temperature variation from ECOSTRESS

### Urban Morphology Features
- **Sky View Factor**: 3D geometry of urban canyons
- **Building Height**: Thermal mass and shading effects
- **Street Width**: Ventilation and cooling potential
- **GHSL Built-up**: Satellite-derived urban density
- **Population Density**: Exposure and vulnerability

### Thermal Comfort (SOLWEIG)
- **Mean Radiant Temperature (MRT)**: Average radiant temperature of surroundings
- **Physiological Equivalent Temperature (PET)**: Human thermal comfort index
- **Universal Thermal Climate Index (UTCI)**: Standard outdoor comfort assessment

### Ecosystem Services (InVEST)
- **Urban Cooling Capacity**: Vegetation and water cooling potential
- **Carbon Sequestration**: CO2 uptake by vegetation
- **Biodiversity Index**: Habitat quality assessment
- **Stormwater Retention**: Flood mitigation capacity
- **Air Quality Benefit**: Pollution removal by vegetation

## Outputs

| File | Purpose |
|------|---------|
| `grid_features.csv` | 250 m grid with enhanced features (15+ variables) |
| `zones.geojson` | Neighborhood zones for map |
| `scenarios.json` | Cooling potential by strategy |
| `priority_table.json` | Neighborhood prioritization |
| `insights.json` | AIML insight panel content |
| `materials.json` | Material comparison table |
| `metadata.json` | Data sources and feature documentation |

## Feature Columns

The system uses 15+ features for physics-informed ML modeling:
- **Remote Sensing**: `ndvi`, `ndbi`, `impervious`, `albedo`, `thermal_anisotropy`
- **Meteorological**: `air_temp`, `humidity`, `wind`
- **Urban Morphology**: `building_density`, `sky_view_factor`, `building_height_m`, `street_width_m`
- **Human Settlement**: `ghsl_built_up`, `population_density`
- **Geographic**: `dist_water_m`

## Hackathon demo script

1. Show Delhi heat map with Central Delhi hotspot
2. Open AIML insights (enhanced drivers with urban morphology)
3. Show cooling potential bar chart (physics-informed scenarios)
4. Show neighborhood priority table (multi-criteria optimization)
5. Toggle scenario view (baseline vs cool roofs with thermal comfort)
6. Display ecosystem services (if InVEST enabled)

## Notes

- Current bundled data is a **physics-realistic synthetic Delhi grid** with enhanced features for immediate offline use.
- The system integrates multiple data sources with fallback to synthetic data when real data is unavailable.
- All data processing scripts handle missing data gracefully with synthetic alternatives.
- SOLWEIG and InVEST integrations are optional and can be enabled in `config.py`.
