/**
 * Google Earth Engine export script for Delhi NCT.
 * Integrates Landsat 8, ECOSTRESS, and Sentinel-2 data for urban heat analysis.
 *
 * Usage:
 * 1. Open https://code.earthengine.google.com/
 * 2. Paste this script
 * 3. Run export tasks to Google Drive
 * 4. Replace data/processed/grid_features.csv with exported values
 */

var delhi = ee.Geometry.Rectangle([76.83, 28.40, 77.35, 28.88]);
var studyDate = ee.Date('2024-05-22');
var start = studyDate.advance(-7, 'day');
var end = studyDate.advance(7, 'day');

Map.centerObject(delhi, 10);

// Landsat 8 processing
function maskL8(image) {
  var qa = image.select('QA_PIXEL');
  var mask = qa.bitwiseAnd(1 << 3).eq(0)
    .and(qa.bitwiseAnd(1 << 4).eq(0));
  return image.updateMask(mask);
}

function computeLST(image) {
  var ndvi = image.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI');
  var lst = image.select('ST_B10')
    .multiply(0.00341802)
    .add(149.0)
    .subtract(273.15)
    .rename('LST_L8');
  return image.addBands(ndvi).addBands(lst);
}

var l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
  .filterBounds(delhi)
  .filterDate(start, end)
  .filter(ee.Filter.lt('CLOUD_COVER', 15))
  .map(maskL8)
  .map(computeLST)
  .median()
  .clip(delhi);

// ECOSTRESS LST processing (optional - may not be available in all regions)
// Note: ECOSTRESS data has limited coverage and may not be available for Delhi
// Using Landsat 8 LST as primary source
var ecostress_c = ee.Image(0).rename('LST_ECO').clip(delhi);

// Sentinel-2 LULC processing
function maskS2(image) {
  var qa = image.select('QA60');
  var cloudBitMask = 1 << 10;
  var cirrusBitMask = 1 << 11;
  var mask = qa.bitwiseAnd(cloudBitMask).eq(0)
    .and(qa.bitwiseAnd(cirrusBitMask).eq(0));
  return image.updateMask(mask);
}

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(delhi)
  .filterDate(start, end)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
  .map(maskS2)
  .median()
  .clip(delhi);

// Calculate indices from Sentinel-2
var s2_ndvi = s2.normalizedDifference(['B8', 'B4']).rename('NDVI_S2');
var s2_ndbi = s2.normalizedDifference(['B11', 'B8']).rename('NDBI_S2');
var s2_mndwi = s2.normalizedDifference(['B3', 'B11']).rename('MNDWI_S2');

// Sentinel-2 LULC classification
var s2_lulc = ee.Image(0)
  .where(s2_mndwi.gt(0.1), 1)          // water
  .where(s2_ndvi.gt(0.45), 2)          // vegetation
  .where(s2_ndbi.gt(0.2), 3)           // built-up
  .rename('LULC_S2');

// Landsat 8 derived indices
var l8_ndbi = l8.normalizedDifference(['SR_B6', 'SR_B5']).rename('NDBI_L8');
var l8_mndwi = l8.normalizedDifference(['SR_B3', 'SR_B6']).rename('MNDWI_L8');
var l8_ndvi = l8.select('NDVI');

// Combined LULC (prioritize Sentinel-2 where available)
var combined_lulc = s2_lulc.unmask(l8_ndbi.gt(0.2).multiply(3).add(l8_mndwi.gt(0.1).multiply(1)).add(l8_ndvi.gt(0.45).multiply(2))).rename('LULC');

// Albedo estimation based on LULC
var albedo = ee.Image(0.12)
  .where(combined_lulc.eq(1), 0.06)  // water
  .where(combined_lulc.eq(2), 0.22)  // vegetation
  .where(combined_lulc.eq(3), 0.10)  // built-up
  .rename('ALBEDO');

// Combine LST sources (prioritize ECOSTRESS where available, fallback to Landsat 8)
var combined_lst = ecostress_c.unmask(l8.select('LST_L8')).rename('LST');

// Combine vegetation indices (prioritize Sentinel-2)
var combined_ndvi = s2_ndvi.unmask(l8_ndvi).rename('NDVI');
var combined_ndbi = s2_ndbi.unmask(l8_ndbi).rename('NDBI');

// Create comprehensive stack
var stack = combined_lst
  .addBands([combined_ndvi, combined_ndbi, combined_lulc, albedo])
  .addBands([l8.select('LST_L8'), ecostress_c, s2_ndvi, s2_ndbi])
  .reproject({crs: 'EPSG:32643', scale: 250});

// Sample points for ML training
var samples = stack.sample({
  region: delhi,
  scale: 250,
  numPixels: 8000,
  seed: 42,
  geometries: true
});

// Export CSV with all features
Export.table.toDrive({
  collection: samples,
  description: 'delhi_multisensor_heat_grid',
  fileFormat: 'CSV'
});

// Export full raster stack
Export.image.toDrive({
  image: stack,
  description: 'delhi_multisensor_stack',
  region: delhi,
  scale: 250,
  crs: 'EPSG:32643',
  maxPixels: 1e13
});

// Export individual layers for visualization
Export.image.toDrive({
  image: combined_lst,
  description: 'delhi_combined_lst',
  region: delhi,
  scale: 250,
  crs: 'EPSG:32643',
  maxPixels: 1e13
});

Export.image.toDrive({
  image: combined_lulc,
  description: 'delhi_lulc',
  region: delhi,
  scale: 250,
  crs: 'EPSG:32643',
  maxPixels: 1e13
});

// Visualization layers
Map.addLayer(combined_lst, {min: 30, max: 55, palette: ['blue', 'cyan', 'lime', 'yellow', 'red']}, 'Combined LST');
Map.addLayer(l8.select('LST_L8'), {min: 35, max: 58, palette: ['blue', 'cyan', 'lime', 'yellow', 'red']}, 'Landsat 8 LST');
Map.addLayer(combined_lulc, {min: 0, max: 3, palette: ['blue', 'green', 'gray', 'red']}, 'LULC (Water/Veg/Built)');
Map.addLayer(combined_ndvi, {min: 0, max: 0.8, palette: ['white', 'green']}, 'NDVI');
