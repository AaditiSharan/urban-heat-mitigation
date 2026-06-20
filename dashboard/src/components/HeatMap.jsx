import { CircleMarker, MapContainer, Popup, TileLayer, GeoJSON } from 'react-leaflet';

function lstColor(value) {
  const min = 38;
  const max = 58;
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const stops = [
    [37, 99, 235],
    [6, 182, 212],
    [132, 204, 22],
    [250, 204, 21],
    [239, 68, 68],
  ];
  const idx = t * (stops.length - 1);
  const i = Math.floor(idx);
  const f = idx - i;
  const c1 = stops[Math.min(i, stops.length - 1)];
  const c2 = stops[Math.min(i + 1, stops.length - 1)];
  const mix = (a, b) => Math.round(a + (b - a) * f);
  return `rgb(${mix(c1[0], c2[0])}, ${mix(c1[1], c2[1])}, ${mix(c1[2], c2[2])})`;
}

export default function HeatMap({ heatmap, zones, scenarioAfter, showScenario }) {
  const zoneStyle = {
    color: '#7dd3fc',
    weight: 1.5,
    fillOpacity: 0.08,
  };

  const onEachZone = (feature, layer) => {
    const props = feature.properties;
    const scenario = scenarioAfter?.[props.id];
    const temp = showScenario && scenario ? scenario.after_lst : props.lst_mean;
    layer.bindPopup(
      `<strong>${props.name}</strong><br/>Surface temp: ${temp} °C<br/>Heat risk: ${props.heat_risk_index}`,
    );
  };

  return (
    <div className="map-wrapper">
      <MapContainer center={[28.63, 77.21]} zoom={11} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; OpenStreetMap, &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {zones && (
          <GeoJSON data={zones} style={zoneStyle} onEachFeature={onEachZone} />
        )}
        {heatmap?.features?.map((feature) => {
          const [lon, lat] = feature.geometry.coordinates;
          const lst = feature.properties.lst;
          return (
            <CircleMarker
              key={feature.properties.cell_id}
              center={[lat, lon]}
              radius={3}
              pathOptions={{
                color: lstColor(lst),
                fillColor: lstColor(lst),
                fillOpacity: 0.85,
                weight: 0,
              }}
            >
              <Popup>
                LST: {lst} °C
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}

export function MapLegend() {
  return (
    <div className="legend">
      <span>20°C</span>
      <div className="legend-bar" />
      <span>60°C</span>
    </div>
  );
}
