// "Meter" (radial progress) untuk rasio kepatuhan APD — bukan pie 2-slice, sesuai
// panduan dataviz: rasio tunggal terhadap batas dipetakan ke Meter, warna fill
// mengikuti status (baik/perlu perhatian/kritis).
export default function ComplianceMeter({ pct, compliant, violation }) {
  let colorClass = 'text-base-300';
  let label = 'Belum ada data';
  let badgeClass = 'badge-ghost';
  if (pct != null) {
    if (pct >= 90) {
      colorClass = 'text-success';
      label = 'Baik';
      badgeClass = 'badge-success badge-soft';
    } else if (pct >= 75) {
      colorClass = 'text-warning';
      label = 'Perlu Perhatian';
      badgeClass = 'badge-warning badge-soft';
    } else {
      colorClass = 'text-error';
      label = 'Kritis';
      badgeClass = 'badge-error badge-soft';
    }
  }

  return (
    <div className="flex flex-col items-center justify-center p-5 flex-1">
      <div
        className={`radial-progress ${colorClass}`}
        style={{ '--value': pct ?? 0, '--size': '9.5rem', '--thickness': '12px' }}
        role="progressbar"
        aria-valuenow={pct ?? 0}
      >
        <div className="flex flex-col items-center text-base-content">
          <span className="text-2xl font-bold font-mono-app">{pct != null ? `${pct}%` : '—'}</span>
          <span className={`badge badge-sm mt-1 ${badgeClass}`}>{label}</span>
        </div>
      </div>
      <div className="flex gap-5 mt-4 text-xs text-base-content/60">
        <span>
          <span className="inline-block w-2 h-2 rounded-full bg-success mr-1.5"></span>
          Kepatuhan <b className="text-base-content font-mono-app">{compliant ?? 0}</b>
        </span>
        <span>
          <span className="inline-block w-2 h-2 rounded-full bg-error mr-1.5"></span>
          Pelanggaran <b className="text-base-content font-mono-app">{violation ?? 0}</b>
        </span>
      </div>
    </div>
  );
}
