# Data Quality Notes

## Known Issues with GEE Export Data

### UHI Anomaly Anomaly
The validation shows a **negative UHI anomaly of -6.1°C** for Central Delhi, meaning rural areas appear hotter than urban areas. This is opposite to the expected UHI effect and outside the typical published range of 5-8°C for Delhi.

**Possible Causes:**
1. **Study date conditions** (2024-05-22) may have had unusual weather patterns
2. **Cloud contamination** in Landsat 8 LST retrieval despite QA filtering
3. **Thermal anisotropy** effects from viewing geometry
4. **Urban canopy cooling** from vegetation or water bodies on that specific date

### Spatial Pattern Anomalies
- **Hottest area**: Southwest Delhi (lat ~28.53, lon ~76.88), mostly unassigned zones
- **Central Delhi**: 47.1°C mean (cooler than expected for urban core)
- **Unassigned areas**: 53.4°C mean (hottest overall)
- **Rohini**: 51.5°C (identified as hottest zone by model)

This spatial pattern suggests the GEE LST data may not accurately represent the typical UHI pattern for Delhi.

### Model Performance
- **R² = 0.318** (5-fold spatial CV, ML-only model)
- **RMSE = 3.31°C**
- Physics model disabled due to synthetic data tuning mismatch

The moderate R² indicates the model captures some spatial patterns but has significant unexplained variance, likely due to data quality issues.

### Recommendations for Hackathon Submission
1. **Be transparent** about data quality limitations
2. **Highlight the methodology** (real satellite data + spatial CV) despite data issues
3. **Focus on the pipeline robustness** (GEE + Planetary Computer fallback)
4. **Suggest future improvements** (multi-temporal averaging, better cloud filtering)
5. **Emphasize the physics-informed approach** even if currently disabled for real data

### Validation Against Literature
| Metric | Expected | Observed | Status |
|--------|----------|----------|--------|
| UHI Anomaly (Central Delhi) | 5-8°C | -6.1°C | ❌ Inverted |
| LST-Air Offset (Daytime) | 8-12°C | 11.6°C | ✓ Within range |
| Hottest Zone | Central Delhi | Southwest (unassigned) | ❌ Unexpected |

**Note:** The LST-air offset is within expected range, suggesting the absolute LST values are reasonable, but the spatial pattern is anomalous.
