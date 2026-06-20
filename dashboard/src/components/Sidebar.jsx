const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: '⌂' },
  { id: 'heatmaps', label: 'Heat Maps', icon: '◫' },
  { id: 'materials', label: 'Materials', icon: '▦' },
  { id: 'analysis', label: 'Analysis', icon: '◔' },
  { id: 'predictions', label: 'Predictions', icon: '◉' },
  { id: 'optimization', label: 'Optimization', icon: '⚙' },
  { id: 'alerts', label: 'Alerts', icon: '⚠' },
  { id: 'reports', label: 'Reports', icon: '▤' },
  { id: 'settings', label: 'Settings', icon: '⚲' },
];

export default function Sidebar({ active, onChange }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>Delhi Heat AI</h1>
        <p>Urban heat stress mitigation</p>
      </div>
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          className={`nav-item ${active === item.id ? 'active' : ''}`}
          onClick={() => onChange(item.id)}
        >
          <span>{item.icon}</span>
          <span>{item.label}</span>
        </button>
      ))}
    </aside>
  );
}
