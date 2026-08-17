import { evidenceUrl } from '../lib/api';
import { TYPE_LABELS, TYPE_BADGE, resolveType } from '../lib/violationTypes';

export default function ViolationsTable({ rows, onShowEvidence, emptyText }) {
  if (!rows || !rows.length) {
    return <div className="text-center text-base-content/40 py-10 text-sm">{emptyText || 'Belum ada data.'}</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            <th>Tanggal</th>
            <th>Waktu</th>
            <th>Lokasi</th>
            <th>Jenis</th>
            <th>Bukti</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((l) => {
            const t = resolveType(l.jenis);
            const hasFile = l.file_exists !== false;
            return (
              <tr key={l.id} className="hover">
                <td>{l.Tanggal}</td>
                <td className="font-mono-app text-xs">{l.Waktu}</td>
                <td>{l.Lokasi}</td>
                <td>
                  <span className={`badge badge-sm ${TYPE_BADGE[t] || 'badge-ghost'}`}>{TYPE_LABELS[t] || t}</span>
                </td>
                <td>
                  {hasFile ? (
                    <button type="button" className="flex items-center gap-2.5 text-left" onClick={() => onShowEvidence(l.Bukti)}>
                      <img
                        src={evidenceUrl(l.Bukti)}
                        alt="bukti"
                        loading="lazy"
                        className="w-[48px] h-[34px] object-cover rounded border border-base-300 bg-base-200 flex-shrink-0"
                      />
                      <span className="link link-primary text-xs">{l.Bukti}</span>
                    </button>
                  ) : (
                    <span className="text-base-content/40 text-xs" title="File sudah terhapus">
                      📷 {l.Bukti}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
