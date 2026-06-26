export default function ValidationPanel({ validation }) {
  if (!validation) return null;

  const uhi = validation.uhi_analysis;
  const offset = validation.lst_air_offset;

  return (
    <div className="card validation-card">
      <h3>{validation.title || 'LST Validation'}</h3>
      <p className="muted" style={{ fontSize: '0.82rem', color: '#8ea0bb' }}>
        {validation.summary}
      </p>

      <div className="validation-grid">
        <div className="validation-stat">
          <span className="label">UHI anomaly (Central vs rural)</span>
          <strong>{uhi?.uhi_anomaly_c ?? '—'} °C</strong>
          <span className="tag">{uhi?.within_expected_range ? 'Within 5–8 °C range' : 'Check range'}</span>
        </div>
        <div className="validation-stat">
          <span className="label">Mean LST − air (CPCB stations)</span>
          <strong>{offset?.mean_c ?? '—'} °C</strong>
          <span className="tag">{offset?.within_expected_range ? 'Plausible daytime offset' : 'Review offset'}</span>
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Station</th>
            <th>Air °C</th>
            <th>LST °C</th>
            <th>LST − Air</th>
          </tr>
        </thead>
        <tbody>
          {validation.cpcb_stations?.map((row) => (
            <tr key={row.station}>
              <td>{row.station}</td>
              <td>{row.air_temp_c ?? '—'}</td>
              <td>{row.lst_c}</td>
              <td>{row.lst_minus_air_c ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
