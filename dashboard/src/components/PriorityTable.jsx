export default function PriorityTable({ priority }) {
  if (!priority?.length) return null;

  return (
    <div className="card">
      <h3>Neighborhood Prioritization</h3>
      <table>
        <thead>
          <tr>
            <th>Neighborhood</th>
            <th>Heat Risk</th>
            <th>Population</th>
            <th>Priority</th>
            <th>Strategy</th>
          </tr>
        </thead>
        <tbody>
          {priority.map((row) => (
            <tr key={row.zone_id}>
              <td>{row.neighborhood}</td>
              <td>
                <div>{row.heat_risk_index}</div>
                <div className="risk-bar">
                  <span style={{ width: `${Math.min(row.heat_risk_index * 10, 100)}%` }} />
                </div>
              </td>
              <td>{row.population_exposed.toLocaleString()}</td>
              <td>{row.priority_score}</td>
              <td>{row.recommended_strategy}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
