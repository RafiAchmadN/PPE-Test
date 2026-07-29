import { useEffect, useState, useCallback } from 'react';
import * as api from '../lib/api';
import StatCard from '../components/StatCard';
import ComplianceMeter from '../components/ComplianceMeter';
import ViolationsTable from '../components/ViolationsTable';
import EvidenceModal from '../components/EvidenceModal';
import { useVisibleCameras } from '../hooks/useVisibleCameras';

function NoSignal({ text }) {
  return (
    <div className="flex flex-col items-center gap-2 text-base-content/40 text-sm">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-9 h-9 opacity-60">
        <circle cx="12" cy="12" r="10" />
        <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
      </svg>
      {text}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [logs, setLogs] = useState(null);
  const [preview, setPreview] = useState(null);
  const [evidence, setEvidence] = useState(null);

  const load = useCallback(async () => {
    const [s, camList, logsData] = await Promise.all([
      api.getStats().catch(() => null),
      api.getCameras().catch(() => null),
      api.getLogs({ limit: 20 }).catch(() => null),
    ]);
    if (s) setStats(s);
    if (logsData) setLogs(logsData);
    const enabled = (camList || []).filter((c) => c.enabled);
    setPreview(enabled.find((c) => c.online) || enabled[0] || null);
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  useVisibleCameras(preview ? [preview.id] : []);

  const totalFrames = (stats?.compliant_frames || 0) + (stats?.violation_frames || 0);

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
        <StatCard
          colorClass="bg-primary"
          label="Kamera Aktif"
          value={stats?.active_cameras ?? '—'}
          sub={`${stats?.online_cameras ?? 0} online`}
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 7l-7 5 7 5V7z" />
              <rect x="1" y="5" width="15" height="14" rx="2" />
            </svg>
          }
        />
        <StatCard
          colorClass="bg-success"
          label="Kepatuhan APD"
          value={stats?.compliance_pct != null ? `${stats.compliance_pct}%` : '—'}
          sub={totalFrames ? `${totalFrames.toLocaleString('id-ID')} frame terpantau` : 'Belum ada data hari ini'}
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2l8 4v6c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6l8-4z" />
              <path d="M9 12l2 2 4-4" />
            </svg>
          }
        />
        <StatCard
          colorClass="bg-warning"
          label="Pelanggaran Hari Ini"
          value={stats?.today_violations ?? '—'}
          sub="Sejak 00:00"
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          }
        />
        <StatCard
          colorClass="bg-secondary"
          label="Total Pelanggaran"
          value={stats?.total_violations ?? '—'}
          sub="30 hari terakhir"
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
              <rect x="9" y="3" width="6" height="4" rx="1" />
            </svg>
          }
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-4 mb-5 items-stretch">
        <div className="card bg-base-100 shadow-sm border border-base-300 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-base-300">
            <h3 className="font-semibold text-sm">{preview ? `Live Monitoring — ${preview.name}` : 'Live Monitoring'}</h3>
            {preview?.online && (
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-error">
                <span className="w-1.5 h-1.5 rounded-full bg-error animate-pulse"></span>LIVE
              </span>
            )}
          </div>
          <div className="aspect-video bg-black flex items-center justify-center overflow-hidden">
            {preview ? (
              preview.online ? (
                <img src={api.streamUrl(preview.id)} alt={preview.name} className="w-full h-full object-contain" />
              ) : (
                <NoSignal text={preview.error || 'No Signal'} />
              )
            ) : (
              <NoSignal text="Belum ada kamera" />
            )}
          </div>
          <div className="flex items-center justify-between px-5 py-3 text-xs text-base-content/60">
            <span>
              <span className="inline-block w-2 h-2 rounded-full bg-success mr-1.5"></span>APD Lengkap
            </span>
            <span>
              <span className="inline-block w-2 h-2 rounded-full bg-error mr-1.5"></span>APD Tidak Lengkap
            </span>
          </div>
        </div>

        <div className="card bg-base-100 shadow-sm border border-base-300 overflow-hidden">
          <div className="px-5 py-4 border-b border-base-300">
            <h3 className="font-semibold text-sm">Statistik Kepatuhan</h3>
          </div>
          <ComplianceMeter pct={stats?.compliance_pct ?? null} compliant={stats?.compliant_frames} violation={stats?.violation_frames} />
        </div>
      </div>

      <h2 className="text-sm text-base-content/60 mb-4">Riwayat Pelanggaran Terbaru</h2>
      <div className="card bg-base-100 shadow-sm border border-base-300 max-h-[420px] overflow-y-auto">
        <ViolationsTable rows={logs} onShowEvidence={setEvidence} emptyText="Belum ada pelanggaran hari ini." />
      </div>

      <EvidenceModal filename={evidence} onClose={() => setEvidence(null)} />
    </div>
  );
}
