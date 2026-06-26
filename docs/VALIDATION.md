# LST Validation Report

**Study area:** Delhi NCT  
**Study date:** 2024-05-22  
**Primary LST source:** Landsat 8 Collection 2 Level-2 (`ST_B10`)  
**Vegetation / built-up indices:** Sentinel-2 (NDVI, NDBI) with Landsat 8 fallback  

---

## 1. Why validation matters

The model is trained to predict **observed satellite LST**, not synthetic physics targets. This section compares:

1. **LST vs ground air temperature** at CPCB reference stations (via Open-Meteo ERA5-Land)
2. **Urban heat island (UHI) anomaly** between Central Delhi and a rural fringe reference
3. **Spatial hotspot pattern** across Delhi neighborhoods

---

## 2. CPCB station comparison

Air temperature is fetched from [Open-Meteo Archive API](https://open-meteo.com/) at ~05:00 UTC (Landsat morning overpass window). LST is sampled from the nearest 250 m grid cell.

| Station | Role | Expected LST − Air |
|---------|------|--------------------|
| ITO (Central Delhi) | Urban core | 10–18 °C |
| Anand Vihar / RK Puram | Urban | 8–16 °C |
| Narela | Rural fringe reference | 5–12 °C |

**Interpretation:** LST exceeds 2 m air temperature during clear-sky daytime overpass. A mean offset of **8–18 °C** is physically plausible for May pre-monsoon conditions.

See live results in `data/processed/validation.json` or the dashboard **Analysis** tab.

---

## 3. UHI anomaly (published benchmark)

Delhi UHI literature reports **5–8 °C** higher surface temperatures in dense built-up cores compared to rural fringe areas during summer.

We compute:

```
UHI anomaly = LST(ITO) − LST(Narela)
```

**Pass criteria:** anomaly within **5–12 °C** (5–8 °C benchmark + tolerance for single-date snapshot).

---

## 4. Model validation methodology

### Spatial hold-out (primary reported metric)

- **Train:** grid cells south of latitude median  
- **Test:** grid cells north of latitude median  
- **Model:** 35% physics energy-balance + 65% XGBoost  
- **Target:** observed Landsat 8 LST  

This avoids random train/test splits that leak spatial autocorrelation.

### 5-fold spatial block cross-validation

Delhi is split into **5 latitude bands**. Each fold holds out one band, trains on the rest, and reports hybrid / ML-only / physics-only R² and RMSE.

Metrics are saved in `data/processed/model_metrics.json`.

---

## 5. How to regenerate

```powershell
python scripts/fetch_real_satellite_data.py
python scripts/validate_lst.py
python scripts/train_and_simulate.py
```

### Data source priority

1. **Google Earth Engine** — run `earthengine authenticate` first (mirrors `gee/export_delhi.js`)
2. **Microsoft Planetary Computer** — automatic fallback (no GEE account required)

---

## 6. References

- CPCB Continuous Ambient Air Quality Monitoring (CAAQM), Delhi NCR
- Landsat 8 Collection 2 Level-2 Surface Temperature Product Guide
- Sentinel-2 MSI L2A user handbook (Copernicus)
- Delhi urban heat island studies (5–8 °C core vs fringe anomaly, pre-monsoon season)
