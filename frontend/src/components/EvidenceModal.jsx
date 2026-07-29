import { evidenceUrl } from '../lib/api';

export default function EvidenceModal({ filename, onClose }) {
  if (!filename) return null;
  return (
    <div className="modal modal-open" onClick={onClose}>
      <div className="modal-box max-w-3xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold text-base mb-4">Evidence</h3>
        <div className="text-center">
          <img
            src={evidenceUrl(filename)}
            alt="bukti"
            className="max-w-full max-h-[70vh] mx-auto rounded-lg"
            onError={(e) => {
              e.target.style.display = 'none';
              e.target.nextElementSibling.style.display = 'block';
            }}
          />
          <div className="hidden text-base-content/60 py-10">
            <div className="text-5xl mb-3">📷</div>
            Foto tidak ditemukan.
            <br />
            File mungkin sudah dihapus dari server.
          </div>
        </div>
        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
