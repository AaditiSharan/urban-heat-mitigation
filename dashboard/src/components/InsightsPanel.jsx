export default function InsightsPanel({ insights }) {
  if (!insights) return null;

  return (
    <div className="card insights-card">
      <div className="insights-header">
        <div className="brain-icon">🧠</div>
        <div>
          <h3>{insights.title || 'AIML Insights'}</h3>
          <span style={{ color: '#8ea0bb', fontSize: '0.82rem' }}>
            Physics-informed ML analysis
          </span>
        </div>
      </div>
      <ul>
        <li><strong>Drivers:</strong> {insights.drivers}</li>
        <li>
          <strong>Priority zones:</strong> {insights.priority_zones?.join(', ')}
        </li>
        <li>
          <strong>Impact estimates:</strong> Cool pavements {insights.impact_estimates?.cool_pavements}; reflective roofs {insights.impact_estimates?.cool_roofs}.
        </li>
        <li><strong>Recommendation:</strong> {insights.recommendation}</li>
      </ul>
      {insights.model_metrics && (
        <p style={{ color: '#8ea0bb', fontSize: '0.82rem', marginBottom: 0 }}>
          Hybrid model R² {insights.model_metrics.r2} | RMSE {insights.model_metrics.rmse_c}°C
          {insights.model_metrics.spatial_cross_validation && (
            <> | 5-fold spatial CV R² {insights.model_metrics.spatial_cross_validation.hybrid_physics_ml?.r2}</>
          )}
        </p>
      )}
    </div>
  );
}
