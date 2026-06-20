/**
 * Google Earth Engine export script for Delhi NCT.
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

function maskL8(image) {
  var qa = image.select('QA_PIXEL');
  var mask = qa.bitwiseAnd(1 << 3).eq(0)
    .and(qa.bitwiseAnd(1 << 4).eq(0));
  return image.updateMask(mask);
}

function computeLST(image) {
  var ndvi = image.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI');
  var emissivity = ndvi.expression(
    'b(NDVI) < 0.2 ? 0.97 : (b(NDVI) < 0.5 ? 0.99 : 0.995)',
    {NDVI: ndvi}
  );
  var lst = image.select('ST_B10')
    .multiply(0.00341802)
    .add(149.0)
    .subtract(273.15)
    .rename('LST_C');
  return image.addBands([ndvi, lst]);
}

var l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
  .filterBounds(delhi)
  .filterDate(start, end)
  .filter(ee.Filter.lt('CLOUD_COVER', 15))
  .map(maskL8)
  .map(computeLST)
  .median()
  .clip(delhi);

var ndbi = l8.normalizedDifference(['SR_B6', 'SR_B5']).rename('NDBI');
var mndwi = l8.normalizedDifference(['SR_B3', 'SR_B6']).rename('MNDWI');
var ndvi = l8.select('NDVI');

var lulc = ee.Image(0)
  .where(mndwi.gt(0.1), 1)          // water
  .where(ndvi.gt(0.45), 2)          // vegetation
  .where(ndbi.gt(0.2), 3)           // built-up
  .rename('LULC');

var albedo = ee.Image(0.12)
  .where(lulc.eq(1), 0.06)
  .where(lulc.eq(2), 0.22)
  .where(lulc.eq(3), 0.10)
  .rename('ALBEDO');

var stack = l8.select(['LST_C', 'NDVI'])
  .addBands([ndbi, lulc, albedo])
  .reproject({crs: 'EPSG:32643', scale: 250});

var samples = stack.sample({
  region: delhi,
  scale: 250,
  numPixels: 5000,
  seed: 42,
  geometries: true
});

Export.table.toDrive({
  collection: samples,
  description: 'delhi_lst_grid',
  fileFormat: 'CSV'
});

Export.image.toDrive({
  image: stack,
  description: 'delhi_lst_stack',
  region: delhi,
  scale: 250,
  crs: 'EPSG:32643',
  maxPixels: 1e13
});

Map.addLayer(l8.select('LST_C'), {min: 35, max: 58, palette: ['blue', 'cyan', 'lime', 'yellow', 'red']}, 'LST');
