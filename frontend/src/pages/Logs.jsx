import { useEffect, useState } from 'react';
import * as api from '../lib/api';
import ViolationsTable from '../components/ViolationsTable';
import EvidenceModal from '../components/EvidenceModal';

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function firstOfMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
}

export default function Logs() {
  const [start, setStart] = useState(firstOfMonth());
  const [end, setEnd] = useState(today());
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState(false);
  const [evidence, setEvidence] = useState(null);

  async function load() {
    try {
      const data = await api.getLogs({ start, end });
      setLogs(data);
      setError(false);
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <label className="text-xs text-base-content/60">From</label>
        <input type="date" className="input input-bordered input-sm" value={start} onChange={(e) => setStart(e.target.value)} />
        <label className="text-xs text-base-content/60">To</label>
        <input type="date" className="input input-bordered input-sm" value={end} onChange={(e) => setEnd(e.target.value)} />
        <button type="button" className="btn btn-ghost btn-sm" onClick={load}>
          Filter
        </button>
      </div>
      <div className="card bg-base-100 border border-base-300 shadow-sm max-h-[calc(100vh-220px)] overflow-y-auto">
        {error ? (
          <div className="p-10 text-center text-error text-sm">Gagal memuat log.</div>
        ) : logs === null ? (
          <div className="p-10 flex justify-center">
            <span className="loading loading-spinner loading-md text-primary"></span>
          </div>
        ) : (
          <ViolationsTable rows={logs} onShowEvidence={setEvidence} emptyText="Tidak ada pelanggaran pada periode ini." />
        )}
      </div>
      <EvidenceModal filename={evidence} onClose={() => setEvidence(null)} />
    </div>
  );
}
