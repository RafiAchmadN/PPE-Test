import { TYPE_LABELS, TYPE_BAR_COLOR } from '../lib/violationTypes';

// Horizontal bar list untuk distribusi jenis pelanggaran (categorical magnitude
// comparison) — data dari stats.by_type (/api/stats), diurutkan desc.
export default function ViolationTypeChart({ byType }) {
  const entries = Object.entries(byType || {})
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1]);

  if (!entries.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-center text-base-content/40 py-10 text-sm">
        Belum ada data pelanggaran.
      </div>
    );
  }

  const max = entries[0][1];

  return (
    <div className="flex flex-col justify-center gap-4 p-5 flex-1">
      {entries.map(([type, count]) => (
        <div key={type} className="flex items-center gap-3">
          <span className="w-24 flex-shrink-0 text-xs text-base-content/70 truncate" title={TYPE_LABELS[type] || type}>
            {TYPE_LABELS[type] || type}
          </span>
          <div className="flex-1 h-5 bg-base-200 rounded overflow-hidden">
            <div
              className={`h-full rounded-r ${TYPE_BAR_COLOR[type] || 'bg-neutral'}`}
              style={{ width: `${Math.max((count / max) * 100, 4)}%` }}
            />
          </div>
          <span className="w-8 flex-shrink-0 text-right text-xs font-mono-app text-base-content">
            {count.toLocaleString('id-ID')}
          </span>
        </div>
      ))}
    </div>
  );
}
