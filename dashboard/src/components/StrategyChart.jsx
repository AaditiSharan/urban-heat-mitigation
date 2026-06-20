import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export default function StrategyChart({ scenarios }) {
  if (!scenarios?.length) return null;

  return (
    <div className="card">
      <h3>Cooling Potential by Strategy</h3>
      <div style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer>
          <BarChart data={scenarios} layout="vertical" margin={{ left: 20, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
            <XAxis type="number" stroke="#8ea0bb" unit="°C" />
            <YAxis type="category" dataKey="strategy" width={120} stroke="#8ea0bb" />
            <Tooltip
              contentStyle={{ background: '#101827', border: '1px solid rgba(255,255,255,0.08)' }}
            />
            <Bar dataKey="delta_t" fill="#38bdf8" radius={[0, 8, 8, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
