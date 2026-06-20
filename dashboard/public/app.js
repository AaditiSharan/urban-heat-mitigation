async function loadJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

function lstColor(value) {
  const min = 38;
  const max = 58;
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const stops = [[37,99,235],[6,182,212],[132,204,22],[250,204,21],[239,68,68]];
  const idx = t * (stops.length - 1);
  const i = Math.floor(idx);
  const f = idx - i;
  const c1 = stops[Math.min(i, stops.length - 1)];
  const c2 = stops[Math.min(i + 1, stops.length - 1)];
  const mix = (a, b) => Math.round(a + (b - a) * f);
  return `rgb(${mix(c1[0], c2[0])}, ${mix(c1[1], c2[1])}, ${mix(c1[2], c2[2])})`;
}

function renderChart(scenarios) {
  const max = Math.max(...scenarios.map((s) => s.delta_t), 1);
  document.getElementById('chart').innerHTML = scenarios
    .map(
      (item) => `
      <div class="bar-row">
        <span>${item.strategy}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(item.delta_t / max) * 100}%"></div></div>
        <span>${item.delta_t}°C</span>
      </div>`,
    )
    .join('');
}

function renderMaterials(materials) {
  document.getElementById('materialsTable').innerHTML = `
    <thead><tr><th>Material</th><th>Albedo</th><th>Surface Temp</th><th>Cost</th><th>Durability</th></tr></thead>
    <tbody>
      ${materials
        .map(
          (row) => `<tr>
            <td>${row.material}</td>
            <td>${row.albedo.toFixed(2)}</td>
            <td>${row.surface_temp.toFixed(1)} °C</td>
            <td>₹${row.cost_inr_m2}/m²</td>
            <td>${row.durability}</td>
          </tr>`,
        )
        .join('')}
    </tbody>`;
}

function renderPriority(priority) {
  document.getElementById('priorityTable').innerHTML = `
    <thead><tr><th>Neighborhood</th><th>Heat Risk</th><th>Population</th><th>Priority</th><th>Strategy</th></tr></thead>
    <tbody>
      ${priority
        .map(
          (row) => `<tr>
            <td>${row.neighborhood}</td>
            <td>${row.heat_risk_index}<div class="risk-bar"><span style="width:${Math.min(row.heat_risk_index * 10, 100)}%"></span></div></td>
            <td>${row.population_exposed.toLocaleString()}</td>
            <td>${row.priority_score}</td>
            <td>${row.recommended_strategy}</td>
          </tr>`,
        )
        .join('')}
    </tbody>`;
}

function renderInsights(insights) {
  document.getElementById('insightsList').innerHTML = `
    <li><strong>Drivers:</strong> ${insights.drivers}</li>
    <li><strong>Priority zones:</strong> ${insights.priority_zones.join(', ')}</li>
    <li><strong>Impact estimates:</strong> Cool pavements ${insights.impact_estimates.cool_pavements}; reflective roofs ${insights.impact_estimates.cool_roofs}.</li>
    <li><strong>Recommendation:</strong> ${insights.recommendation}</li>`;
  document.getElementById('modelMetrics').textContent =
    `Model R² ${insights.model_metrics.r2} | RMSE ${insights.model_metrics.rmse_c}°C`;
}

function renderZoneLabels(zones, scenarioAfter, showScenario) {
  const labels = [...zones.features]
    .sort((a, b) => b.properties.lst_mean - a.properties.lst_mean)
    .slice(0, 6);
  document.getElementById('zoneLabels').innerHTML = labels
    .map((feature) => {
      const props = feature.properties;
      const temp =
        showScenario && scenarioAfter[props.id]
          ? scenarioAfter[props.id].after_lst
          : props.lst_mean;
      return `<span class="chip">${props.name}: ${temp} °C</span>`;
    })
    .join('');
}

async function main() {
  const [metadata, zones, heatmap, insights, scenarios, materials, priority, scenarioAfter] =
    await Promise.all([
      loadJson('./data/metadata.json'),
      loadJson('./data/zones.geojson'),
      loadJson('./data/heatmap.geojson'),
      loadJson('./data/insights.json'),
      loadJson('./data/scenarios.json'),
      loadJson('./data/materials.json'),
      loadJson('./data/priority_table.json'),
      loadJson('./data/scenario_after.json'),
    ]);

  document.getElementById('subtitle').textContent =
    `${metadata.city} | Study date: ${metadata.study_date}`;

  renderInsights(insights);
  renderChart(scenarios);
  renderMaterials(materials);
  renderPriority(priority);

  const map = L.map('map').setView([28.63, 77.21], 11);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap, &copy; CARTO',
  }).addTo(map);

  const zoneLayer = L.geoJSON(zones, {
    style: { color: '#7dd3fc', weight: 1.5, fillOpacity: 0.08 },
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(`<strong>${p.name}</strong><br/>Surface temp: ${p.lst_mean} °C`);
    },
  }).addTo(map);

  heatmap.features.forEach((feature) => {
    const [lon, lat] = feature.geometry.coordinates;
    const lst = feature.properties.lst;
    L.circleMarker([lat, lon], {
      radius: 3,
      color: lstColor(lst),
      fillColor: lstColor(lst),
      fillOpacity: 0.85,
      weight: 0,
    })
      .bindPopup(`LST: ${lst} °C`)
      .addTo(map);
  });

  let showScenario = false;
  const updateLabels = () => renderZoneLabels(zones, scenarioAfter, showScenario);

  document.getElementById('baselineBtn').addEventListener('click', () => {
    showScenario = false;
    document.getElementById('baselineBtn').classList.add('active');
    document.getElementById('scenarioBtn').classList.remove('active');
    zoneLayer.eachLayer((layer) => {
      const p = layer.feature.properties;
      layer.setPopupContent(`<strong>${p.name}</strong><br/>Surface temp: ${p.lst_mean} °C`);
    });
    updateLabels();
  });

  document.getElementById('scenarioBtn').addEventListener('click', () => {
    showScenario = true;
    document.getElementById('scenarioBtn').classList.add('active');
    document.getElementById('baselineBtn').classList.remove('active');
    zoneLayer.eachLayer((layer) => {
      const p = layer.feature.properties;
      const after = scenarioAfter[p.id]?.after_lst ?? p.lst_mean;
      layer.setPopupContent(`<strong>${p.name}</strong><br/>After cool roofs: ${after} °C`);
    });
    updateLabels();
  });

  updateLabels();
}

main().catch((err) => {
  document.body.innerHTML = `<div style="padding:40px;color:white"><h2>Failed to load dashboard</h2><p>${err.message}</p><p>Run the Python pipeline first.</p></div>`;
});
