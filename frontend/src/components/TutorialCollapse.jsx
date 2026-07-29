import { useState } from 'react';

const STEPS = [
  {
    title: 'Klik "Add Camera"',
    desc: (
      <>
        Klik tombol biru <b>Add Camera</b> di pojok kanan atas, atau tombol <b>+</b> di sidebar kiri bawah.
      </>
    ),
  },
  {
    title: 'Isi Nama Kamera',
    desc: (
      <>
        Masukkan nama lokasi kamera, misal <b>Area Produksi</b> atau <b>Pintu Masuk Gudang</b>.
      </>
    ),
  },
  {
    title: 'Masukkan IP atau URL',
    desc: (
      <>
        Ketik IP kamera di kolom IP, lalu pilih brand (Hikvision/Dahua) agar URL RTSP terisi otomatis. Ganti{' '}
        <b>password</b> sesuai kamera.
      </>
    ),
  },
  {
    title: 'Simpan & Monitor',
    desc: (
      <>
        Klik <b>Save</b>. Kamera langsung mulai streaming dan deteksi APD berjalan otomatis.
      </>
    ),
  },
];

const URL_FORMATS = [
  {
    type: 'Hikvision (RTSP)',
    code: 'rtsp://admin:password@192.168.1.x:554/Streaming/Channels/101',
    note: 'Channel 101 = stream utama kamera 1. Ganti 201 untuk kamera 2.',
  },
  {
    type: 'Dahua (RTSP)',
    code: 'rtsp://admin:password@192.168.1.x:554/cam/realmonitor?channel=1&subtype=0',
    note: 'subtype=0 = main stream (HD), subtype=1 = sub stream (ringan).',
  },
  {
    type: 'Generic RTSP',
    code: 'rtsp://admin:password@192.168.1.x:554/stream',
    note: 'Untuk kamera IP generik. Path /stream bisa berbeda per merk.',
  },
  { type: 'HTTP MJPEG', code: 'http://192.168.1.x:8080/video', note: 'Untuk kamera IP yang menggunakan MJPEG over HTTP.' },
  {
    type: 'DVR Xiongmai',
    code: 'dvrip://admin:password@192.168.1.x:34567/0',
    note: 'Angka di akhir = nomor channel (0 = kamera 1, 1 = kamera 2).',
  },
  {
    type: 'File Video',
    code: '/path/ke/file/video.mp4',
    note: 'Untuk testing. Format: .mp4 .avi .mov .mkv. Video diulang terus.',
  },
  { type: 'Webcam Lokal', code: '0', note: 'Angka 0 = webcam pertama di server. 1 = webcam kedua, dst.' },
];

export default function TutorialCollapse() {
  const [open, setOpen] = useState(false);
  return (
    <div className="collapse collapse-arrow bg-base-100 border border-base-300 mb-4">
      <input type="checkbox" checked={open} onChange={() => setOpen((o) => !o)} />
      <div className="collapse-title font-semibold text-sm flex items-center gap-2.5">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        Cara Menambahkan Kamera
      </div>
      <div className="collapse-content">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-5">
          {STEPS.map((s, i) => (
            <div key={i} className="bg-base-200 border border-base-300 rounded-lg p-3.5 flex flex-col gap-2">
              <div className="w-[26px] h-[26px] rounded-full bg-primary text-primary-content text-xs font-bold flex items-center justify-center">
                {i + 1}
              </div>
              <div className="text-[13px] font-semibold">{s.title}</div>
              <div className="text-xs text-base-content/60 leading-relaxed">{s.desc}</div>
            </div>
          ))}
        </div>

        <div className="text-[13px] font-semibold mb-2.5 text-base-content/60">Format URL yang Didukung</div>
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Tipe Kamera</th>
                <th>Format URL</th>
                <th>Keterangan</th>
              </tr>
            </thead>
            <tbody>
              {URL_FORMATS.map((f) => (
                <tr key={f.type}>
                  <td className="font-semibold whitespace-nowrap">{f.type}</td>
                  <td>
                    <code className="font-mono-app bg-base-200 text-primary px-1.5 py-0.5 rounded text-[11px] break-all">
                      {f.code}
                    </code>
                  </td>
                  <td className="text-base-content/60">{f.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div role="alert" className="alert alert-warning alert-soft mt-3.5 text-xs items-start">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="flex-shrink-0 mt-0.5">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>
            <b>Tips:</b> Jika kamera berstatus <b>Offline</b> setelah ditambah, periksa: (1) IP kamera dapat di-ping
            dari server, (2) username &amp; password benar, (3) port 554 tidak diblokir firewall. Coba ganti path
            stream jika gagal (misal /stream1, /live, /h264).
          </span>
        </div>
      </div>
    </div>
  );
}
