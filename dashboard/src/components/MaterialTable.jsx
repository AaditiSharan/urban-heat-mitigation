export default function MaterialTable({ materials }) {
  if (!materials?.length) return null;

  return (
    <div className="card">
      <h3>Material Performance Comparison</h3>
      <table>
        <thead>
          <tr>
            <th>Material</th>
            <th>Albedo</th>
            <th>Surface Temp</th>
            <th>Cost</th>
            <th>Durability</th>
          </tr>
        </thead>
        <tbody>
          {materials.map((row) => (
            <tr key={row.material}>
              <td>{row.material}</td>
              <td>{row.albedo.toFixed(2)}</td>
              <td>{row.surface_temp.toFixed(1)} °C</td>
              <td>₹{row.cost_inr_m2}/m²</td>
              <td>{row.durability}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
