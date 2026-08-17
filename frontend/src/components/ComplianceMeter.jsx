// "Meter" (radial progress) untuk rasio kepatuhan APD — bukan pie 2-slice, sesuai
// panduan dataviz: rasio tunggal terhadap batas dipetakan ke Meter, warna fill
// mengikuti status (baik/perlu perhatian/kritis). Track ring adalah lapisan
// radial-progress kedua di --value:100 pada opacity rendah dari warna yang sama,
// supaya seluruh lingkaran (bukan cuma busur terisi) ikut membaca status.
const THRESH_GOOD = 90;
const THRESH_WARN = 75;
const SIZE = '11.5rem';
const THICKNESS = '14px';

export default function ComplianceMeter({ pct, compliant, violation }) {
  let colorClass = 'text-base-300';
  let label = 'Belum ada data';
  let badgeClass = 'badge-ghost';
  if (pct != null) {
    if (pct >= THRESH_GOOD) {
      colorClass = 'text-success';
      label = 'Baik';
      badgeClass = 'badge-success badge-soft';
    } else if (pct >= THRESH_WARN) {
      colorClass = 'text-warning';
      label = 'Perlu Perhatian';
      badgeClass = 'badge-warning badge-soft';
    } else {
      colorClass = 'text-error';
      label = 'Kritis';
      badgeClass = 'badge-error badge-soft';
    }
  }

  const markerPos = pct != null ? Math.min(Math.max(pct, 0), 100) : null;

  return (
    <div className="flex flex-col items-center justify-center p-5 flex-1 gap-6">
      <div className="relative" style={{ width: SIZE, height: SIZE }}>
        <div
          className={`radial-progress absolute inset-0 ${colorClass} opacity-15`}
          style={{ '--value': 100, '--size': SIZE, '--thickness': THICKNESS }}
        />
        <div
          className={`radial-progress absolute inset-0 ${colorClass}`}
          style={{ '--value': pct ?? 0, '--size': SIZE, '--thickness': THICKNESS }}
          role="progressbar"
          aria-valuenow={pct ?? 0}
        >
          <div className="flex flex-col items-center text-base-content">
            <span className="text-3xl font-bold font-mono-app">{pct != null ? `${pct}%` : '—'}</span>
            <span className={`badge badge-sm mt-1 ${badgeClass}`}>{label}</span>
          </div>
        </div>
      </div>

      <div className="w-full max-w-[280px]">
        <div className="flex gap-2">
          <div className="flex-1 rounded-lg bg-base-200/60 px-3 py-2">
            <div className="flex items-center gap-1.5 text-[11px] text-base-content/50">
              <span className="w-2 h-2 rounded-full bg-success flex-shrink-0"></span>Kepatuhan
            </div>
            <div className="font-mono-app font-bold text-base-content text-sm mt-0.5">
              {(compliant ?? 0).toLocaleString('id-ID')}
            </div>
          </div>
          <div className="flex-1 rounded-lg bg-base-200/60 px-3 py-2">
            <div className="flex items-center gap-1.5 text-[11px] text-base-content/50">
              <span className="w-2 h-2 rounded-full bg-error flex-shrink-0"></span>Pelanggaran
            </div>
            <div className="font-mono-app font-bold text-base-content text-sm mt-0.5">
              {(violation ?? 0).toLocaleString('id-ID')}
            </div>
          </div>
        </div>

        <div className="relative mt-5">
          <div className="h-2 rounded-full overflow-hidden flex bg-base-200">
            <div className="h-full bg-error/50" style={{ width: `${THRESH_WARN}%` }} />
            <div className="h-full bg-warning/50" style={{ width: `${THRESH_GOOD - THRESH_WARN}%` }} />
            <div className="h-full bg-success/50" style={{ width: `${100 - THRESH_GOOD}%` }} />
          </div>
          {markerPos != null && (
            <div
              className="absolute -top-1 w-1 h-4 rounded-full bg-base-content"
              style={{ left: `calc(${markerPos}% - 2px)` }}
              title={`${pct}%`}
            />
          )}
          <div className="flex justify-between text-[10px] text-base-content/40 mt-1 font-mono-app">
            <span>0</span>
            <span>{THRESH_WARN}</span>
            <span>{THRESH_GOOD}</span>
            <span>100</span>
          </div>
        </div>
      </div>
    </div>
  );
}
