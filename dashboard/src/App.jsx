import { useEffect, useMemo, useState } from 'react';
import Sidebar from './components/Sidebar.jsx';
import HeatMap, { MapLegend } from './components/HeatMap.jsx';
import InsightsPanel from './components/InsightsPanel.jsx';
import StrategyChart from './components/StrategyChart.jsx';
import MaterialTable from './components/MaterialTable.jsx';
import PriorityTable from './components/PriorityTable.jsx';
import ValidationPanel from './components/ValidationPanel.jsx';

async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}`);
  }
  return response.json();
}

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [showScenario, setShowScenario] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    async function loadAll() {
      try {
        const [
          metadata,
          zones,
          heatmap,
          insights,
          scenarios,
          materials,
          priority,
          scenarioAfter,
          validation,
        ] = await Promise.all([
          loadJson('/data/metadata.json'),
          loadJson('/data/zones.geojson'),
          loadJson('/data/heatmap.geojson'),
          loadJson('/data/insights.json'),
          loadJson('/data/scenarios.json'),
          loadJson('/data/materials.json'),
          loadJson('/data/priority_table.json'),
          loadJson('/data/scenario_after.json'),
          loadJson('/data/validation.json').catch(() => null),
        ]);

        setData({
          metadata,
          zones,
          heatmap,
          insights,
          scenarios,
          materials,
          priority,
          scenarioAfter,
          validation,
        });
      } catch (err) {
        setError(err.message);
      }
    }

    loadAll();
  }, []);

  const zoneLabels = useMemo(() => {
    if (!data?.zones?.features) return [];
    return [...data.zones.features]
      .sort((a, b) => b.properties.lst_mean - a.properties.lst_mean)
      .slice(0, 6);
  }, [data]);

  if (error) {
    return (
      <div className="placeholder-view">
        <div>
          <h2>Data not found</h2>
          <p>{error}</p>
          <p>Run the Python pipeline first, then refresh.</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return <div className="placeholder-view">Loading Delhi heat dashboard...</div>;
  }

  const renderOverview = () => (
    <>
      <div className="dashboard-grid">
        <div className="card map-card">
          <h3>Urban Heat Map (Surface Temperature)</h3>
          <HeatMap
            heatmap={data.heatmap}
            zones={data.zones}
            scenarioAfter={data.scenarioAfter}
            showScenario={showScenario}
          />
          <MapLegend />
          <div className="scenario-toggle">
            <button
              className={!showScenario ? 'active' : ''}
              onClick={() => setShowScenario(false)}
            >
              Baseline LST
            </button>
            <button
              className={showScenario ? 'active' : ''}
              onClick={() => setShowScenario(true)}
            >
              After Cool Roofs
            </button>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '12px' }}>
            {zoneLabels.map((feature) => (
              <span
                key={feature.properties.id}
                style={{
                  background: 'rgba(255,255,255,0.05)',
                  borderRadius: '999px',
                  padding: '6px 10px',
                  fontSize: '0.78rem',
                  color: '#c7d5ea',
                }}
              >
                {feature.properties.name}: {feature.properties.lst_mean} °C
              </span>
            ))}
          </div>
        </div>
        <div className="right-stack">
          <InsightsPanel insights={data.insights} />
          <StrategyChart scenarios={data.scenarios} />
        </div>
      </div>
      <div className="bottom-grid">
        <MaterialTable materials={data.materials} />
        <PriorityTable priority={data.priority} />
      </div>
      {data.validation && <ValidationPanel validation={data.validation} />}
    </>
  );

  const renderSimple = (title, body) => (
    <div className="card placeholder-view" style={{ minHeight: 520 }}>
      <div>
        <h3>{title}</h3>
        <p>{body}</p>
      </div>
    </div>
  );

  let content = renderOverview();
  if (activeTab === 'heatmaps') {
    content = renderOverview();
  } else if (activeTab === 'materials') {
    content = <MaterialTable materials={data.materials} />;
  } else if (activeTab === 'analysis') {
    content = data.validation ? (
      <ValidationPanel validation={data.validation} />
    ) : (
      renderSimple('Analysis', 'Driver attribution and SHAP outputs are generated in data/processed/drivers.json.')
    );
  } else if (activeTab === 'predictions') {
    content = renderSimple('Predictions', 'Spatial LST predictions come from the trained XGBoost model in data/processed/lst_model.joblib.');
  } else if (activeTab === 'optimization') {
    content = <PriorityTable priority={data.priority} />;
  } else if (activeTab !== 'overview') {
    content = renderSimple(activeTab[0].toUpperCase() + activeTab.slice(1), 'This section is reserved for future expansion in the hackathon build.');
  }

  return (
    <div className="app-shell">
      <Sidebar active={activeTab} onChange={setActiveTab} />
      <main className="main-panel">
        <div className="page-header">
          <div>
            <h2>Urban Heat Mitigation Dashboard</h2>
            <span>{data.metadata.city} | Study date: {data.metadata.study_date}</span>
          </div>
          <span>{data.metadata.data_source}</span>
        </div>
        {content}
      </main>
    </div>
  );
}
