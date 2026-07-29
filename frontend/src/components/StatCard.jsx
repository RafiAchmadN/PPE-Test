export default function StatCard({ icon, colorClass, label, value, sub }) {
  return (
    <div className="card bg-base-100 shadow-sm border border-base-300">
      <div className="card-body flex-row items-start gap-3.5 p-5">
        <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 text-white ${colorClass}`}>
          <span className="w-[22px] h-[22px]">{icon}</span>
        </div>
        <div className="min-w-0">
          <div className="text-xs text-base-content/60 mb-1">{label}</div>
          <div className="text-2xl font-bold font-mono-app leading-tight">{value}</div>
          {sub && <div className="text-[11px] text-base-content/40 mt-0.5">{sub}</div>}
        </div>
      </div>
    </div>
  );
}
