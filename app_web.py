# =============================================================================
#  MAPPER — Monitoring Automated PPE Detection & Reporting
#  File   : app_web.py
#  Fungsi : Backend utama sistem — mengelola model YOLO, stream kamera CCTV,
#           deteksi APD real-time, logging pelanggaran ke SQLite, dan
#           menyajikan dashboard web berbasis Flask.
# =============================================================================

import os
import sys
import json
import time
import queue
import socket
import sqlite3
import secrets
import threading
import traceback
import zipfile
from datetime import datetime, date
from functools import wraps
from urllib.parse import urlparse
import cv2
import numpy as np
from flask import Flask, request, jsonify, Response, send_from_directory, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from dvrip import DVRIPCam
    _DVRIP_LIB_OK = True
except ImportError:
    _DVRIP_LIB_OK = False

try:
    import av  
    _AV_LIB_OK = True
except ImportError:
    _AV_LIB_OK = False

DVRIP_AVAILABLE = _DVRIP_LIB_OK and _AV_LIB_OK

# --- CONFIG ---
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'logging.db')
OUTPUT_FOLDER  = os.path.join(BASE_DIR, 'data', 'violations')
ARCHIVE_FOLDER = os.path.join(OUTPUT_FOLDER, 'archive')  # ZIP harian, lihat _archive_worker()
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'videos')
BACKUP_FOLDER = os.path.join(BASE_DIR, 'backups')
INFERENCE_SIZE       = (640, 480)
ALLOWED_VIDEO_EXTS   = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v'}
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)

# Mode demo/preview publik (lihat docs/SAAS_READINESS_AUDIT.md §8): auto-login
# semua pengunjung sebagai guest, nonaktifkan endpoint yang mengubah state
# (kamera/video/password/settings), dan batasi sumber kamera hanya ke file
# video lokal (cegah SSRF lewat URL RTSP/HTTP bebas dari publik anonim).
DEMO_MODE = os.environ.get('DEMO_MODE', '0') == '1'

# Batas upload — cegah disk penuh akibat upload berulang tanpa batas.
MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', '500'))

# Frontend React (Vite) berjalan sebagai service terpisah — lihat frontend/.
# Boleh diisi banyak origin dipisah koma lewat env var untuk deployment lain.
FRONTEND_ORIGINS = os.environ.get('FRONTEND_ORIGIN', 'http://localhost:5173').split(',')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ppe-monitor-default-change-me-2026')
# credentials (cookie sesi) harus ikut terkirim dari origin frontend yang berbeda port/domain
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024
CORS(app, supports_credentials=True, origins=FRONTEND_ORIGINS)

# Rate limiting — selalu aktif untuk login (cegah brute force), dan jauh lebih
# ketat secara global saat DEMO_MODE (pengunjung publik anonim, bukan staf
# terpercaya) supaya satu pengunjung tidak bisa menghabiskan resource GPU/
# bandwidth demo untuk semua calon pelanggan lain.
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
    default_limits=(["60 per minute"] if DEMO_MODE else []),
)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def demo_readonly(f):
    """Blokir endpoint yang mengubah state saat DEMO_MODE aktif — demo publik
    hanya boleh dilihat-lihat, tidak boleh diubah oleh pengunjung anonim."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if DEMO_MODE:
            return jsonify({'error': 'Dinonaktifkan di mode demo'}), 403
        return f(*args, **kwargs)
    return decorated

@app.before_request
def _demo_auto_login():
    if DEMO_MODE and not session.get('logged_in'):
        session['logged_in'] = True
        session['demo_guest'] = True

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

# Runtime settings (adjustable via UI)
settings = {
    'violation_delay': 20,      # seconds between captures per camera — JANGAN diset
                                 # terlalu kecil: dengan 1 detik, satu pelanggaran yang
                                 # diam di frame selama beberapa menit menghasilkan satu
                                 # JPEG baru TIAP DETIK (root cause 1,1 juta file / disk
                                 # penuh dalam 3 hari observasi lapangan).
    'confidence': 0.5,          # threshold untuk PPE class (helmet, rompi, dll)
    'person_confidence': 0.7,   # threshold khusus class Person (lebih tinggi = kurangi false detect)
    'inference_enabled': True,
    'stream_fps': 5,             # max fps for MJPEG stream
}

# ─── DATABASE ────────────────────────────────────────────────────────────────
_violation_queue = queue.Queue()   # camera threads push ke sini, bukan langsung ke DB

def get_db():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # izinkan baca & tulis bersamaan
    conn.execute("PRAGMA synchronous=NORMAL") # lebih cepat, masih aman
    return conn

def db_execute(query, params=(), fetch=False, fetchone=False):
    conn = get_db()
    try:
        cur = conn.execute(query, params)
        if fetch:
            return [dict(r) for r in cur.fetchall()]
        if fetchone:
            r = cur.fetchone()
            return dict(r) if r else None
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

RETENTION_DAYS = 30  # hapus data lebih lama dari N hari (0 = tidak hapus)
BACKUP_RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', '14'))

def _get_must_change_password():
    row = db_execute("SELECT value FROM app_settings WHERE key='must_change_password'", fetchone=True)
    return bool(row) and row['value'] == '1'

def _mask_url(url):
    """Sembunyikan kredensial (user:pass@) dari URL kamera untuk response list.
    Kredensial lengkap hanya dikirim lewat GET /api/cameras/<id> (dipakai form edit)."""
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            netloc = parsed.hostname or ''
            if parsed.port:
                netloc += f':{parsed.port}'
            return parsed._replace(netloc=f'***:***@{netloc}').geturl()
    except Exception:
        pass
    return url

def _archive_zip_path(tanggal):
    return os.path.join(ARCHIVE_FOLDER, f'violations_{tanggal}.zip')

def _evidence_in_archive(bukti, tanggal):
    """True kalau file bukti sudah diarsipkan ke ZIP harian (lihat _archive_worker)."""
    if not bukti or not tanggal:
        return False
    zpath = _archive_zip_path(tanggal)
    if not os.path.isfile(zpath):
        return False
    try:
        with zipfile.ZipFile(zpath) as zf:
            return bukti in zf.namelist()
    except Exception:
        return False

def _archive_worker():
    """Arsipkan foto bukti pelanggaran hari-hari sebelumnya jadi satu ZIP per
    tanggal (data/violations/archive/violations_YYYY-MM-DD.zip), lalu hapus
    JPEG lepasannya. Root cause penumpukan >1 juta file kecil sudah dipangkas
    lewat violation_delay di atas; ini lapisan kedua supaya foto yang sudah
    terlanjur ada tetap dirapikan per hari tanpa kehilangan akses — /foto/<f>
    fallback baca langsung dari ZIP kalau file lepasannya sudah tidak ada."""
    last_archive_date = None
    while True:
        try:
            today_str = date.today().isoformat()
            if last_archive_date != today_str:
                loose = {f for f in os.listdir(OUTPUT_FOLDER) if f.lower().endswith('.jpg')}
                if loose:
                    rows = db_execute(
                        "SELECT Bukti, Tanggal FROM data WHERE Tanggal < ? AND Bukti IS NOT NULL",
                        (today_str,), fetch=True
                    )
                    by_date = {}
                    for r in rows:
                        if r['Bukti'] in loose:
                            by_date.setdefault(r['Tanggal'], []).append(r['Bukti'])
                    for tanggal, files in by_date.items():
                        zpath = _archive_zip_path(tanggal)
                        try:
                            with zipfile.ZipFile(zpath, 'a', zipfile.ZIP_DEFLATED) as zf:
                                already = set(zf.namelist())
                                for fname in files:
                                    if fname in already:
                                        continue
                                    fpath = os.path.join(OUTPUT_FOLDER, fname)
                                    if os.path.isfile(fpath):
                                        zf.write(fpath, arcname=fname)
                            with zipfile.ZipFile(zpath) as zf:
                                zipped = set(zf.namelist())
                            removed = 0
                            for fname in files:
                                if fname in zipped:
                                    try:
                                        os.remove(os.path.join(OUTPUT_FOLDER, fname))
                                        removed += 1
                                    except OSError:
                                        pass
                            if removed:
                                print(f"[ARCHIVE] {tanggal}: {removed:,} foto diarsipkan -> {os.path.basename(zpath)}")
                        except Exception as e:
                            print(f"[ARCHIVE] Gagal arsipkan {tanggal}: {e}")
                last_archive_date = today_str
        except Exception as e:
            print(f"[ARCHIVE] Error: {e}")
        time.sleep(3600)  # cek tiap jam — arsip sungguhan hanya jalan 1x/hari (guard di atas)

def _backup_worker():
    """Backup harian logging.db lewat SQLite backup API (aman dijalankan
    bersamaan dengan WAL). Retensi backup terpisah dari retensi data live —
    lihat docs/SAAS_READINESS_AUDIT.md §3/§7. Snapshot media (data/violations)
    sebaiknya dibackup di level OS (rsync/robocopy) karena hanya kumpulan file
    statis, tidak butuh penanganan konsistensi khusus seperti database."""
    last_backup_date = None
    while True:
        try:
            today_str = date.today().isoformat()
            if last_backup_date != today_str:
                dest = os.path.join(BACKUP_FOLDER, f'logging_{today_str}.db')
                if not os.path.exists(dest):
                    src_conn = sqlite3.connect(DATABASE_PATH)
                    dst_conn = sqlite3.connect(dest)
                    with dst_conn:
                        src_conn.backup(dst_conn)
                    src_conn.close()
                    dst_conn.close()
                    print(f"[BACKUP] Snapshot dibuat: {dest}")
                last_backup_date = today_str

                if BACKUP_RETENTION_DAYS > 0:
                    cutoff = (datetime.now() - __import__('datetime').timedelta(days=BACKUP_RETENTION_DAYS)).date()
                    for fname in os.listdir(BACKUP_FOLDER):
                        if fname.startswith('logging_') and fname.endswith('.db'):
                            try:
                                fdate = date.fromisoformat(fname[len('logging_'):-len('.db')])
                                if fdate < cutoff:
                                    os.remove(os.path.join(BACKUP_FOLDER, fname))
                                    print(f"[BACKUP] Hapus backup lama: {fname}")
                            except ValueError:
                                pass
        except Exception as e:
            print(f"[BACKUP] Error: {e}")
        time.sleep(3600)  # cek tiap jam — backup sungguhan hanya jalan 1x/hari (guard di atas)

def _violation_writer():
    """Thread khusus menulis violations ke DB — camera thread tidak perlu tunggu DB.

    Retensi dijalankan berbasis WAKTU (maks. 1x/hari), bukan hitungan insert —
    supaya site dengan volume pelanggaran rendah tetap ter-cleanup. Setiap
    baris yang dihapus, file JPEG buktinya ikut dihapus (sebelumnya hanya
    baris DB yang terhapus, file menumpuk terus di disk).
    """
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    last_cleanup_date = None

    def run_retention_cleanup():
        cutoff = (datetime.now() - __import__('datetime').timedelta(days=RETENTION_DAYS)).strftime('%Y-%m-%d')
        rows = conn.execute("SELECT Bukti FROM data WHERE Tanggal < ?", (cutoff,)).fetchall()
        if not rows:
            return
        deleted = conn.execute("DELETE FROM data WHERE Tanggal < ?", (cutoff,)).rowcount
        conn.commit()
        for (bukti,) in rows:
            if not bukti:
                continue
            fpath = os.path.join(OUTPUT_FOLDER, bukti)
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
            except Exception as e:
                print(f"[CLEANUP] Gagal hapus file {bukti}: {e}")
        for fname in os.listdir(ARCHIVE_FOLDER):
            if fname.startswith('violations_') and fname.endswith('.zip'):
                fdate = fname[len('violations_'):-len('.zip')]
                if fdate < cutoff:
                    try:
                        os.remove(os.path.join(ARCHIVE_FOLDER, fname))
                        print(f"[CLEANUP] Hapus arsip ZIP lama: {fname}")
                    except OSError as e:
                        print(f"[CLEANUP] Gagal hapus arsip {fname}: {e}")
        print(f"[CLEANUP] Hapus {deleted:,} record + file bukti terkait, lebih lama dari {cutoff}")

    while True:
        try:
            item = _violation_queue.get(timeout=1)
            conn.execute(
                "INSERT INTO data (Tanggal, Waktu, Lokasi, Bukti, jenis) VALUES (?,?,?,?,?)",
                item
            )
            conn.commit()
            _violation_queue.task_done()
        except queue.Empty:
            pass
        except Exception as e:
            print(f"[DB WRITER] {e}")
            try: conn.close()
            except: pass
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            continue

        today_str = date.today().isoformat()
        if RETENTION_DAYS > 0 and last_cleanup_date != today_str:
            last_cleanup_date = today_str
            try:
                run_retention_cleanup()
            except Exception as e:
                print(f"[CLEANUP] Error: {e}")

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS cameras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, url TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Tanggal TEXT, Waktu TEXT, Lokasi TEXT, Bukti TEXT, jenis TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY, value TEXT
    )""")
    conn.commit()

    # ── Add 'jenis' column if missing (existing DB migration) ──
    cols = [row[1] for row in conn.execute("PRAGMA table_info(data)").fetchall()]
    if 'jenis' not in cols:
        print("[MIGRATE] Adding 'jenis' column to data table...")
        conn.execute("ALTER TABLE data ADD COLUMN jenis TEXT DEFAULT ''")
        conn.execute("UPDATE data SET jenis='no-helmet' WHERE Bukti LIKE '%tanpahelm%'")
        conn.execute("UPDATE data SET jenis='no-vest'   WHERE Bukti LIKE '%tanpavest%'")
        conn.commit()
        print("[MIGRATE] Done. Backfilled jenis from existing Bukti filenames.")

    # Persistent secret key (survives restart)
    row = conn.execute("SELECT value FROM app_settings WHERE key='secret_key'").fetchone()
    if not row:
        key = secrets.token_hex(32)
        conn.execute("INSERT INTO app_settings (key,value) VALUES ('secret_key',?)", (key,))
        conn.commit()
        app.secret_key = key
    else:
        app.secret_key = row[0]

    # Default admin password: admin123 — wajib diganti di login pertama (must_change_password)
    row = conn.execute("SELECT value FROM app_settings WHERE key='admin_pw_hash'").fetchone()
    if not row:
        conn.execute("INSERT INTO app_settings (key,value) VALUES ('admin_pw_hash',?)",
                     (generate_password_hash('admin123'),))
        conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('must_change_password','1')")
        conn.commit()
    else:
        # Migrasi instance lama: paksa ganti password kalau ternyata masih memakai
        # default admin123 (instance yang sudah diganti passwordnya tidak diganggu).
        mcp_row = conn.execute("SELECT value FROM app_settings WHERE key='must_change_password'").fetchone()
        if mcp_row is None:
            still_default = check_password_hash(row['value'], 'admin123')
            conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('must_change_password',?)",
                         ('1' if still_default else '0',))
            conn.commit()

    # Load saved settings
    for row in conn.execute("SELECT key, value FROM app_settings").fetchall():
        k = row[0]
        if k in settings:
            try:
                if isinstance(settings[k], bool):
                    settings[k] = row[1] == '1' or row[1].lower() == 'true'
                elif isinstance(settings[k], int):
                    settings[k] = int(float(row[1]))
                else:
                    settings[k] = float(row[1])
            except: pass
    conn.close()

# ─── YOLO MODEL ──────────────────────────────────────────────────────────────
_model = None
_model_lock = threading.Lock()
_model_type = None       # 'v5' or 'ultralytics'
_model_names = {}
_device = 'cpu'          # akan diupdate saat model load
# Queue bersama: camera thread push frame, inference worker ambil & proses batch
# maxsize=40 → jika worker kewalahan, frame lama di-drop (tidak menumpuk di RAM)
_infer_queue = queue.Queue(maxsize=40)

# Kamera yang sedang tertampil di grid Live Cameras pada frontend (4 kamera per
# halaman). Selama _visible_restricted=True, YOLO inference hanya dijalankan
# untuk kamera yang ada di _visible_cam_ids, supaya beban GPU/CPU tidak naik
# terus seiring jumlah total kamera. Saat user meninggalkan halaman Live Cameras,
# frontend melepas pembatasan (_visible_restricted=False) sehingga seluruh kamera
# kembali dideteksi terus-menerus seperti semula (monitoring 24/7 tetap jalan).
_visible_lock = threading.Lock()
_visible_cam_ids = set()
_visible_restricted = False

def _is_camera_visible(cam_id):
    with _visible_lock:
        if not _visible_restricted:
            return True
        return cam_id in _visible_cam_ids

# Statistik kepatuhan APD harian — dihitung dari frame yang benar-benar diproses
# YOLO (bukan estimasi/rekaan). Setiap frame yang mengandung minimal satu Person
# diklasifikasikan compliant (tidak ada pelanggaran) atau violation (ada
# pelanggaran), lalu diakumulasi per hari. Reset otomatis saat tanggal berganti.
# Ini metrik "seberapa sering pemantauan menemukan APD lengkap", bukan hitungan
# pekerja unik (sistem ini tidak melakukan person-tracking lintas frame).
_frame_stats_lock = threading.Lock()
_frame_stats = {'date': None, 'compliant': 0, 'violation': 0}

def _record_frame_compliance(has_person, has_violation):
    if not has_person:
        return
    with _frame_stats_lock:
        today_str = date.today().isoformat()
        if _frame_stats['date'] != today_str:
            _frame_stats['date'] = today_str
            _frame_stats['compliant'] = 0
            _frame_stats['violation'] = 0
        if has_violation:
            _frame_stats['violation'] += 1
        else:
            _frame_stats['compliant'] += 1

def get_compliance_stats():
    with _frame_stats_lock:
        if _frame_stats['date'] != date.today().isoformat():
            return {'compliant_frames': 0, 'violation_frames': 0, 'compliance_pct': None}
        compliant = _frame_stats['compliant']
        violation = _frame_stats['violation']
    total = compliant + violation
    pct = round(compliant / total * 100, 1) if total else None
    return {'compliant_frames': compliant, 'violation_frames': violation, 'compliance_pct': pct}

def load_model():
    global _model, _model_type, _model_names
    with _model_lock:
        if _model is not None:
            return _model, _model_type
        
        # Hanya gunakan yolo11m.pt
        model_path = os.path.join(BASE_DIR, 'best.pt')

        # 1. Cek secara eksplisit apakah file fisik ada di folder
        if not os.path.exists(model_path):
            print(f"[MODEL ERROR] File model TIDAK DITEMUKAN di: {model_path}")
            print("[MODEL ERROR] Pastikan file yolo11m.pt ada di folder yang sama dengan script ini.")
            return None, None

        # 2. Jika file ada, langsung muat menggunakan ultralytics
        try:
            import torch
            from ultralytics import YOLO
            global _device
            _device = 'cuda' if torch.cuda.is_available() else 'cpu'
            _model = YOLO(model_path)
            _model.to(_device)
            _model_names = _model.names
            _model_type = 'ultralytics'
            print(f"[MODEL] Berhasil memuat {model_path}")
            print(f"[MODEL] Device: {_device.upper()} {'(' + torch.cuda.get_device_name(0) + ')' if _device == 'cuda' else '(no GPU)'}")
            print(f"[MODEL] Classes: {_model_names}")
            return _model, _model_type
            
        except ImportError:
            print("[MODEL ERROR] Library 'ultralytics' belum diinstall. Ketik: pip install ultralytics")
            return None, None
        except Exception as e:
            print(f"[MODEL ERROR] Gagal memuat yolo11m.pt karena error: {e}")
            return None, None

VIOLATION_MAP = {
    'no_helmet': 'no-helmet',
    'no_rompi':  'no-vest',
}
 
def _classify(cls_id, cls_name):
    """Map class name ke violation type. Return None jika bukan violation."""
    name = (cls_name or '').lower().replace('-', '_').strip()
    # Cek exact match dulu
    if name in VIOLATION_MAP:
        return VIOLATION_MAP[name]
    # Fallback: partial match
    for key, vtype in VIOLATION_MAP.items():
        if key in name:
            return vtype
    return None
 
 
def run_inference(frame):
    """Returns (annotated_frame, violations_list)."""
    global _device
    model, mtype = load_model()
    if model is None:
        return frame, []

    violations = []
    try:
        if mtype == 'ultralytics':
            import torch
            min_conf = min(settings['confidence'], settings['person_confidence'])
            try:
                results = model.predict(
                    frame, conf=min_conf, imgsz=640, verbose=False, device=_device
                )
            except RuntimeError as cuda_err:
                if 'no kernel image' in str(cuda_err).lower() or 'cudaerror' in str(cuda_err).lower():
                    print(f"[MODEL] CUDA kernel error, fallback ke CPU: {cuda_err}")
                    _device = 'cpu'
                    model.to('cpu')
                    results = model.predict(frame, conf=min_conf, imgsz=640, verbose=False, device='cpu')
                else:
                    raise
            result = results[0]
            names = _model_names or {}
            person_conf_thr = settings['person_confidence']
            ppe_conf_thr    = settings['confidence']

            if len(result.boxes) > 0:
                keep = []
                for b in result.boxes:
                    cname = (names.get(int(b.cls[0]), '')).lower()
                    thr = person_conf_thr if cname == 'person' else ppe_conf_thr
                    keep.append(float(b.conf[0]) >= thr)
                mask = torch.tensor(keep, dtype=torch.bool)
                result.boxes = result.boxes[mask]

            annotated = result.plot()
            for b in result.boxes:
                cid   = int(b.cls[0])
                cnf   = float(b.conf[0])
                cname = names.get(cid, f'unknown_{cid}')
                vt    = _classify(cid, cname)
                if vt:
                    violations.append({'type': vt, 'conf': cnf})

        elif mtype == 'v5':
            model.conf = settings['confidence']
            results = model(frame)
            annotated = np.squeeze(results.render())
            coor = results.xyxy[0]
            names = model.names if hasattr(model, 'names') else {}
            for i in range(len(coor)):
                cid   = int(coor[i][5].item())
                cnf   = float(coor[i][4].item())
                cname = names.get(cid, '') if isinstance(names, dict) else (names[cid] if cid < len(names) else '')
                vt    = _classify(cid, cname)
                if vt:
                    violations.append({'type': vt, 'conf': cnf})
        else:
            annotated = frame

    except Exception as e:
        print(f"[INFERENCE] Error saat deteksi: {e}")
        annotated = frame

    return annotated, violations


def _inference_worker():
    """Dedicated thread: ambil frame dari _infer_queue, proses batch, kirim hasil balik.

    Satu worker mampu menangani 10–20 kamera karena GPU memproses satu batch
    (N frame) hampir secepat memproses 1 frame secara sendiri-sendiri.
    Tambah worker ke-2 (NUM_WORKERS=2) jika kamera > 20.
    """
    BATCH_SIZE = 8     # jumlah frame per batch — sesuaikan dengan VRAM GPU
    BATCH_WAIT  = 0.04  # tunggu max 40ms untuk kumpulkan frame sebelum proses

    while True:
        batch = []   # list of (CameraStream_instance, frame_ndarray)
        deadline = time.time() + BATCH_WAIT

        # Kumpulkan frame dari berbagai kamera sampai batch penuh atau timeout
        while len(batch) < BATCH_SIZE:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                item = _infer_queue.get(timeout=max(remaining, 0.001))
                batch.append(item)
            except queue.Empty:
                break

        if not batch:
            time.sleep(0.01)
            continue

        if not settings['inference_enabled']:
            # Inference dimatikan — kembalikan frame mentah ke masing-masing kamera
            for cs, frame in batch:
                with cs.lock:
                    cs.frame = frame
            continue

        model, mtype = load_model()
        if model is None or mtype != 'ultralytics':
            for cs, frame in batch:
                with cs.lock:
                    cs.frame = frame
            continue

        try:
            import torch
            frames     = [item[1] for item in batch]
            min_conf   = min(settings['confidence'], settings['person_confidence'])

            # Satu panggilan predict untuk semua frame dalam batch
            results = model.predict(frames, conf=min_conf, imgsz=640, verbose=False, device=_device)

            names           = _model_names or {}
            person_conf_thr = settings['person_confidence']
            ppe_conf_thr    = settings['confidence']

            for (cs, orig_frame), result in zip(batch, results):
                # Filter confidence per kelas
                if len(result.boxes) > 0:
                    keep = []
                    for b in result.boxes:
                        cname = names.get(int(b.cls[0]), '').lower()
                        thr   = person_conf_thr if cname == 'person' else ppe_conf_thr
                        keep.append(float(b.conf[0]) >= thr)
                    result.boxes = result.boxes[torch.tensor(keep, dtype=torch.bool)]

                annotated = result.plot()

                # Update frame kamera dengan overlay bounding box
                with cs.lock:
                    cs.frame = annotated

                # Cek dan log pelanggaran
                violations = []
                has_person = False
                for b in result.boxes:
                    cid  = int(b.cls[0])
                    cnf  = float(b.conf[0])
                    cname = names.get(cid, '')
                    if cname.lower() == 'person':
                        has_person = True
                    vt   = _classify(cid, cname)
                    if vt:
                        violations.append({'type': vt, 'conf': cnf})

                _record_frame_compliance(has_person, bool(violations))

                if violations:
                    delay = settings['violation_delay']
                    if time.time() - cs.last_violation_time >= delay:
                        v      = violations[0]
                        ts     = time.strftime("%m%d%H%M%S")
                        prefix = "tanpahelm" if v['type'] == 'no-helmet' else "tanpavest"
                        fname  = f'{prefix}_{cs.name.replace(" ", "")}_{ts}.jpg'
                        fpath  = os.path.join(OUTPUT_FOLDER, fname)
                        try:
                            cv2.imwrite(fpath, annotated)
                            _violation_queue.put((
                                time.strftime("%Y-%m-%d"),
                                datetime.now().strftime("%H:%M:%S"),
                                cs.name, fname, v['type']
                            ))
                            print(f"[VIOLATION] {cs.name}: {v['type']} conf={v['conf']:.2f}")
                        except Exception as e:
                            print(f"[VIOLATION] Save error: {e}")
                        cs.last_violation_time = time.time()

        except Exception as e:
            print(f"[INFER WORKER] Batch error: {e}")
            for cs, frame in batch:
                with cs.lock:
                    cs.frame = frame

            # "illegal memory access" / "unspecified launch failure" / device-side
            # assert dkk menandakan CUDA context proses ini sudah corrupt — SEMUA
            # panggilan CUDA berikutnya akan gagal identik selamanya (bukan error
            # per-frame yang bisa di-skip). Tidak ada cara pulih di dalam proses
            # yang sama, jadi keluar paksa dan biarkan `restart: unless-stopped`
            # (Docker Compose) / reconcile otomatis (K8s Deployment) menyalakan
            # proses baru dengan CUDA context bersih, daripada diam-diam macet
            # (inference "mati" tanpa restart manual, lihat riwayat chat).
            fatal_cuda = any(sig in str(e).lower() for sig in (
                'illegal memory access', 'unspecified launch failure',
                'device-side assert', 'cuda error',
            ))
            if fatal_cuda and _device == 'cuda':
                print("[INFER WORKER] CUDA context corrupt, tidak bisa dipulihkan "
                      "di proses ini — keluar supaya container di-restart otomatis.")
                os._exit(1)


# ─── CAMERA STREAMING ────────────────────────────────────────────────────────
class CameraStream:
    def __init__(self, cam_id, url, name):
        self.cam_id = cam_id
        self.url = url
        self.name = name
        self.frame = None
        self.lock = threading.Lock()
        self.active = False
        self.thread = None
        self.last_violation_time = 0
        self.fps = 0
        self.connected = False
        self.error_msg = ""

    def start(self):
        if self.active: return
        # Pertahanan berlapis: walau endpoint tambah/ubah kamera sudah diblokir
        # di DEMO_MODE (lihat demo_readonly), cek ulang di sini supaya kamera
        # manapun di DB yang bukan file video lokal tidak pernah benar-benar
        # dijalankan saat demo publik aktif — mencegah SSRF lewat RTSP/HTTP/
        # webcam bebas dari pengunjung anonim.
        if DEMO_MODE and not self._is_demo_safe_url(self.url):
            self.error_msg = "URL tidak diizinkan di mode demo (hanya video contoh yang tersedia)"
            print(f"[CAM {self.cam_id}] Diblokir mode demo: {self.url}")
            return
        self.active = True
        # Pilih loop sesuai protokol URL
        if self.url.lower().startswith("dvrip://"):
            target = self._loop_dvrip
        else:
            target = self._loop
        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()
        print(f"[CAM {self.cam_id}] Started: {self.name} -> {self.url}")

    def stop(self):
        self.active = False
        print(f"[CAM {self.cam_id}] Stopped: {self.name}")

    @staticmethod
    def _is_demo_safe_url(url):
        """Mode demo hanya boleh memutar file video lokal di data/videos —
        blokir RTSP/HTTP/RTMP/DVRIP/webcam index sepenuhnya."""
        if not isinstance(url, str):
            return False
        if url.lower().startswith(('rtsp://', 'http://', 'https://', 'rtmp://', 'mms://', 'dvrip://')):
            return False
        if url.isdigit():
            return False
        resolved, _ = CameraStream._resolve_url(url)
        if not isinstance(resolved, str) or not os.path.isfile(resolved):
            return False
        try:
            real_upload = os.path.realpath(UPLOAD_FOLDER)
            real_target = os.path.realpath(resolved)
            return os.path.commonpath([real_upload, real_target]) == real_upload
        except ValueError:
            return False

    @staticmethod
    def _resolve_url(url):
        """Resolve the actual stream URL (handles YouTube, numeric webcam, etc.)."""
        # Numeric webcam index
        if url.isdigit():
            return int(url), None

        # YouTube URL -> resolve via yt-dlp
        if 'youtube.com' in url or 'youtu.be' in url:
            try:
                import subprocess
                result = subprocess.run(
                    ['yt-dlp', '-f', 'best[height<=480]', '-g', url],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0 and result.stdout.strip():
                    resolved = result.stdout.strip().split('\n')[0]
                    print(f"[YT-DLP] Resolved: {url[:50]}... -> stream URL")
                    return resolved, None
                else:
                    return None, f"yt-dlp failed: {result.stderr.strip()[:80]}"
            except FileNotFoundError:
                return None, "YouTube requires yt-dlp (pip install yt-dlp)"
            except subprocess.TimeoutExpired:
                return None, "YouTube URL resolve timeout"
            except Exception as e:
                return None, f"YouTube error: {str(e)[:80]}"

        # Konversi path Windows (C:\...) ke path container Linux
        import re
        if re.match(r'^[A-Za-z]:[\\\/]', url):
            unix = url.replace('\\', '/')
            # Cari bagian relatif setelah marker folder yang dikenal
            for marker in ['data/videos/', 'data/violations/', 'data/']:
                idx = unix.lower().find(marker)
                if idx >= 0:
                    rel = unix[idx:]
                    candidate = os.path.join(BASE_DIR, rel)
                    if os.path.isfile(candidate):
                        print(f"[CAM] Windows path dikonversi -> {candidate}")
                        return candidate, None
            # Fallback: cari berdasarkan nama file saja di data/videos/
            fname = os.path.basename(unix)
            candidate = os.path.join(BASE_DIR, 'data', 'videos', fname)
            if os.path.isfile(candidate):
                print(f"[CAM] Windows path (filename only) -> {candidate}")
                return candidate, None
            return None, f"File tidak ditemukan di container. Gunakan path: /app/data/videos/{os.path.basename(unix)}"

        # Cek apakah path lokal (relatif maupun absolut)
        if not url.lower().startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://", "dvrip://")):
            # Coba path absolut dulu
            if os.path.isfile(url):
                return url, None
            # Coba relatif terhadap BASE_DIR
            candidate = os.path.join(BASE_DIR, url)
            if os.path.isfile(candidate):
                return candidate, None
            # Coba relatif terhadap BASE_DIR/data/
            candidate2 = os.path.join(BASE_DIR, 'data', url)
            if os.path.isfile(candidate2):
                return candidate2, None

        # Regular URL (RTSP, HTTP MJPEG, etc.)
        return url, None

    def _push_frame(self, frame):
        """Kirim frame ke inference worker (non-blocking).
        Jika queue penuh, frame di-drop — lebih baik lewati 1 frame
        daripada menunda seluruh pipeline."""
        try:
            _infer_queue.put_nowait((self, frame))
        except queue.Full:
            pass

    def _loop(self):
        cap = None
        retry_delay = 3
        fc = 0
        ft = time.time()
        infer_fc = 0   # counter untuk skip frame inference

        while self.active:
            # Connect / reconnect
            if cap is None or not cap.isOpened():
                self.connected = False
                self.error_msg = "Connecting..."

                # Resolve URL (YouTube, etc.)
                src, err = self._resolve_url(self.url)
                if err:
                    self.error_msg = err
                    print(f"[CAM {self.cam_id}] {err}")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
                    continue

                try:
                    # Deteksi: ini file video lokal?
                    is_videofile = (
                        isinstance(src, str)
                        and not src.lower().startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://"))
                        and os.path.isfile(src)
                    )
                    self._is_videofile = is_videofile

                    cap = cv2.VideoCapture(src)
                    # Timeout & buffer hanya untuk network stream — file lokal tidak perlu
                    if isinstance(src, str) and not is_videofile:
                        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)  # 10s open timeout
                        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000)  # 10s read timeout
                    if not is_videofile:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # minimize buffer lag (live streams only)

                    if not cap.isOpened():
                        err_detail = "Cannot open stream"
                        if isinstance(src, int):
                            err_detail = f"Webcam {src} not found"
                        elif 'rtsp://' in str(src):
                            err_detail = "RTSP unreachable (check network/credentials)"
                        elif 'http' in str(src):
                            err_detail = "HTTP stream unreachable"
                        elif isinstance(src, str):
                            # Bukan URL — kemungkinan file lokal
                            if not os.path.isfile(src):
                                err_detail = f"File tidak ditemukan: {src}"
                            else:
                                err_detail = f"Codec/format video tidak didukung OpenCV: {os.path.basename(src)}"
                        self.error_msg = err_detail
                        print(f"[CAM {self.cam_id}] {err_detail}")
                        if cap: cap.release(); cap = None
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, 60)
                        continue

                    self.connected = True
                    self.error_msg = ""
                    retry_delay = 3
                    src_kind = "video file" if is_videofile else "live stream"
                    print(f"[CAM {self.cam_id}] Connected: {self.name} ({src_kind})")

                except Exception as e:
                    self.error_msg = f"OpenCV error: {str(e)[:60]}"
                    print(f"[CAM {self.cam_id}] {self.error_msg}")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
                    continue

            ret, frame = cap.read()
            if not ret:
                # Untuk file video: EOF bukan error — rewind dan ulangi
                if getattr(self, '_is_videofile', False) and cap is not None:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                # Untuk live stream: betulan putus
                cap.release(); cap = None
                self.connected = False
                self.error_msg = "Stream lost, reconnecting..."
                time.sleep(retry_delay)
                continue

            # FPS counter (diukur dari frame capture, bukan inference)
            fc += 1
            el = time.time() - ft
            if el >= 2:
                self.fps = fc / el
                fc = 0; ft = time.time()

            # Simpan frame mentah untuk streaming — tidak tunggu inference.
            # PENTING: kalau kamera ini sedang aktif dideteksi (visible + inference
            # enabled), JANGAN timpa cs.frame di sini — biarkan _inference_worker
            # yang menulis frame beranotasi (lihat di bawah). Loop capture ini jalan
            # ~10x/detik sedangkan inference cuma update tiap beberapa ratus ms, jadi
            # kalau frame mentah selalu menimpa balik, bounding box akan kedip-kedip
            # (muncul sekejap lalu ketiban frame mentah tanpa kotak). Kalau kamera
            # tidak sedang dideteksi, stream tetap hidup dari sini (tanpa overlay).
            is_being_annotated = settings['inference_enabled'] and _is_camera_visible(self.cam_id)
            if not is_being_annotated:
                with self.lock:
                    self.frame = frame

            # Push setiap 3 frame ke inference worker (non-blocking) — hanya jika
            # kamera ini sedang tertampil di frontend (lihat _is_camera_visible)
            infer_fc += 1
            if infer_fc >= 3:
                infer_fc = 0
                if _is_camera_visible(self.cam_id):
                    self._push_frame(frame)

            time.sleep(1.0 / max(settings['stream_fps'] * 2, 1))

        if cap: cap.release()

    # ── DVR Xiongmai / Sofia (port 34567) ──────────────────────────────────
    def _loop_dvrip(self):
        """
        Handler khusus DVR Xiongmai/Sofia.
        Format URL: dvrip://username:password@host:port/channel
        Contoh   : dvrip://admin:[email protected]:34567/0
        Channel  : 0 = kamera 1, 1 = kamera 2, dst.
        Stream   : default 'Main' (HD). Tambahkan ?stream=Extra untuk substream ringan.
        """
        if not DVRIP_AVAILABLE:
            missing = []
            if not _DVRIP_LIB_OK: missing.append("python-dvr")
            if not _AV_LIB_OK:    missing.append("av (PyAV)")
            self.error_msg = f"Library belum terinstall: {', '.join(missing)}"
            print(f"[CAM {self.cam_id}] {self.error_msg}")
            print(f"[CAM {self.cam_id}] Install: pip install av && pip install git+https://github.com/NeiroNx/python-dvr.git")
            # Diam di state error tapi jangan crash
            while self.active:
                time.sleep(2)
            return

        # Parse URL
        try:
            p = urlparse(self.url)
            host = p.hostname
            port = p.port or 34567
            user = p.username or "admin"
            pwd  = p.password or ""
            try:
                channel = int(p.path.strip("/")) if p.path.strip("/") else 0
            except ValueError:
                channel = 0
            # ?stream=Main / ?stream=Extra
            stream_type = "Main"
            if p.query:
                for kv in p.query.split("&"):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        if k.lower() == "stream" and v.lower() in ("main", "extra"):
                            stream_type = v.capitalize()
            if not host:
                self.error_msg = "URL dvrip:// tidak valid (host kosong)"
                print(f"[CAM {self.cam_id}] {self.error_msg}")
                while self.active: time.sleep(2)
                return
        except Exception as e:
            self.error_msg = f"Parse URL error: {str(e)[:80]}"
            print(f"[CAM {self.cam_id}] {self.error_msg}")
            while self.active: time.sleep(2)
            return

        cam = None
        codec = None
        retry_delay = 3
        # Counter frame untuk hitung FPS, di-share dengan callback via list
        frame_counter = [0]
        ft = time.time()

        def on_h264_data(raw_data, _meta=None, _user=None):
            """Callback dari DVRIPCam — terima H264 NAL chunks, decode, lalu proses."""
            try:
                if codec is None or raw_data is None:
                    return
                packets = codec.parse(raw_data)
                for packet in packets:
                    for fr in codec.decode(packet):
                        img = fr.to_ndarray(format='bgr24')
                        # Sama seperti _loop: jangan timpa cs.frame dengan frame mentah
                        # kalau kamera ini sedang aktif dideteksi, supaya overlay bounding
                        # box dari _inference_worker tidak kedip ketiban frame mentah.
                        is_being_annotated = settings['inference_enabled'] and _is_camera_visible(self.cam_id)
                        if not is_being_annotated:
                            with self.lock:
                                self.frame = img
                        if _is_camera_visible(self.cam_id):
                            self._push_frame(img)
                        frame_counter[0] += 1
            except Exception:
                # Decode H264 kadang error di awal sampai dapat keyframe — diam saja
                pass

        while self.active:
            if cam is None:
                self.connected = False
                self.error_msg = "Connecting to Sofia DVR..."
                try:
                    codec = av.CodecContext.create('h264', 'r')
                    cam = DVRIPCam(host, user=user, password=pwd, port=port)

                    if not cam.login():
                        self.error_msg = "Login DVR gagal — cek username/password"
                        print(f"[CAM {self.cam_id}] {self.error_msg}")
                        try: cam.close()
                        except: pass
                        cam = None
                        codec = None
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, 60)
                        continue

                    # Mulai monitor — API NeiroNx/python-dvr
                    # Signature umum: start_monitor(callback, channel=0, stream='Main')
                    try:
                        cam.start_monitor(on_h264_data, channel=channel, stream=stream_type)
                    except TypeError:
                        # Beberapa versi punya signature lebih sederhana
                        cam.start_monitor(on_h264_data)

                    self.connected = True
                    self.error_msg = ""
                    retry_delay = 3
                    print(f"[CAM {self.cam_id}] DVRIP connected: {host}:{port} ch={channel} stream={stream_type}")

                except Exception as e:
                    self.error_msg = f"DVRIP error: {str(e)[:80]}"
                    print(f"[CAM {self.cam_id}] {self.error_msg}")
                    try:
                        if cam: cam.close()
                    except: pass
                    cam = None
                    codec = None
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
                    continue

            # Idle loop — semua kerjaan ada di callback. Kita cuma update FPS.
            time.sleep(0.1)
            el = time.time() - ft
            if el >= 2:
                self.fps = frame_counter[0] / el
                frame_counter[0] = 0
                ft = time.time()

        # Cleanup saat dihentikan
        if cam:
            try: cam.stop_monitor()
            except: pass
            try: cam.close()
            except: pass

    def get_jpeg(self):
        with self.lock:
            if self.frame is not None:
                frame = self.frame
                h, w = frame.shape[:2]
                if w > 640:
                    frame = cv2.resize(frame, (640, int(h * 640 / w)))
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                return buf.tobytes()
        return None

    def get_info(self):
        return {'connected': self.connected, 'fps': round(self.fps, 1), 'error': self.error_msg}


camera_streams = {}

def start_all_cameras():
    rows = db_execute("SELECT id, name, url FROM cameras WHERE enabled=1", fetch=True)
    for r in rows:
        if r['id'] not in camera_streams:
            cs = CameraStream(r['id'], r['url'], r['name'])
            camera_streams[r['id']] = cs
            cs.start()

def stop_camera(cid):
    if cid in camera_streams:
        camera_streams[cid].stop()
        del camera_streams[cid]

def restart_camera(cid):
    stop_camera(cid)
    r = db_execute("SELECT id, name, url, enabled FROM cameras WHERE id=?", (cid,), fetchone=True)
    if r and r['enabled']:
        cs = CameraStream(r['id'], r['url'], r['name'])
        camera_streams[r['id']] = cs
        cs.start()

# ─── FLASK ROUTES (JSON API murni — frontend React terpisah) ─────────────────

@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login_post():
    d = request.json or {}
    username = d.get('username', '').strip()
    password = d.get('password', '')
    if username != 'admin':
        return jsonify({'error': 'Username atau password salah'}), 401
    row = db_execute("SELECT value FROM app_settings WHERE key='admin_pw_hash'", fetchone=True)
    if not row or not check_password_hash(row['value'], password):
        return jsonify({'error': 'Username atau password salah'}), 401
    session['logged_in'] = True
    session.permanent = True
    return jsonify({'ok': True})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/status')
def auth_status():
    logged_in = bool(session.get('logged_in'))
    return jsonify({
        'logged_in': logged_in,
        'must_change_password': _get_must_change_password() if (logged_in and not DEMO_MODE) else False,
        'demo_mode': DEMO_MODE,
    })

@app.route('/foto/<path:filename>')
@login_required
def serve_foto(filename):
    if os.path.isfile(os.path.join(OUTPUT_FOLDER, filename)):
        return send_from_directory(OUTPUT_FOLDER, filename)
    # Sudah diarsipkan ke ZIP harian oleh _archive_worker — cari tanggalnya di DB.
    row = db_execute("SELECT Tanggal FROM data WHERE Bukti=?", (filename,), fetchone=True)
    if row:
        zpath = _archive_zip_path(row['Tanggal'])
        if os.path.isfile(zpath):
            try:
                with zipfile.ZipFile(zpath) as zf:
                    return Response(zf.read(filename), mimetype='image/jpeg')
            except KeyError:
                pass
    return jsonify({'error': 'File tidak ditemukan'}), 404

@app.route('/api/info')
@login_required
def api_info():
    ip = get_local_ip()
    return jsonify({'local_ip': ip, 'port': 5000, 'access_url': f'http://{ip}:5000'})

@app.route('/api/auth/change-password', methods=['POST'])
@login_required
@demo_readonly
def change_password():
    d = request.json or {}
    current = d.get('current', '')
    new_pw  = d.get('new', '')
    row = db_execute("SELECT value FROM app_settings WHERE key='admin_pw_hash'", fetchone=True)
    if not row or not check_password_hash(row['value'], current):
        return jsonify({'error': 'Password lama salah'}), 401
    if len(new_pw) < 6:
        return jsonify({'error': 'Password baru minimal 6 karakter'}), 400
    db_execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('admin_pw_hash',?)",
               (generate_password_hash(new_pw),))
    db_execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('must_change_password','0')")
    return jsonify({'ok': True})

# Camera CRUD
@app.route('/api/cameras', methods=['GET'])
@login_required
def api_cameras_list():
    """List kamera — URL disamarkan (kredensial disembunyikan). Untuk URL
    lengkap saat edit, frontend memanggil GET /api/cameras/<id>."""
    rows = db_execute("SELECT * FROM cameras ORDER BY id", fetch=True)
    for c in rows:
        c['url'] = _mask_url(c['url'])
        cs = camera_streams.get(c['id'])
        if cs:
            info = cs.get_info()
            c['online'] = info['connected']
            c['fps']    = info['fps']
            c['error']  = info['error']
        else:
            c['online'] = False; c['fps'] = 0; c['error'] = 'Not started'
    return jsonify(rows)

@app.route('/api/cameras/<int:cid>', methods=['GET'])
@login_required
def api_cameras_get(cid):
    """Detail 1 kamera dengan URL lengkap (termasuk kredensial) — dipakai
    form edit di frontend, berbeda dari GET /api/cameras (list) yang
    menyamarkan kredensial."""
    row = db_execute("SELECT * FROM cameras WHERE id=?", (cid,), fetchone=True)
    if not row:
        return jsonify({'error': 'Kamera tidak ditemukan'}), 404
    return jsonify(row)

@app.route('/api/cameras', methods=['POST'])
@login_required
@demo_readonly
def api_cameras_create():
    d = request.json
    name = d.get('name','').strip(); url = d.get('url','').strip()
    if not name or not url:
        return jsonify({'error': 'Name and URL required'}), 400
    cid = db_execute("INSERT INTO cameras (name, url) VALUES (?,?)", (name, url))
    cs = CameraStream(cid, url, name); camera_streams[cid] = cs; cs.start()
    return jsonify({'id': cid}), 201

@app.route('/api/cameras/<int:cid>', methods=['PUT'])
@login_required
@demo_readonly
def api_cameras_update(cid):
    d = request.json
    name = d.get('name','').strip(); url = d.get('url','').strip(); enabled = d.get('enabled', 1)
    if not name or not url:
        return jsonify({'error': 'Name and URL required'}), 400
    db_execute("UPDATE cameras SET name=?, url=?, enabled=? WHERE id=?", (name, url, enabled, cid))
    restart_camera(cid)
    return jsonify({'ok': True})

@app.route('/api/cameras/<int:cid>', methods=['DELETE'])
@login_required
@demo_readonly
def api_cameras_delete(cid):
    stop_camera(cid)
    db_execute("DELETE FROM cameras WHERE id=?", (cid,))
    return jsonify({'ok': True})

@app.route('/api/cameras/visible', methods=['POST'])
@login_required
def api_cameras_visible():
    """Frontend melaporkan kamera mana yang sedang tertampil di grid Live Cameras
    (4 kamera per halaman). Selama pembatasan aktif, YOLO inference hanya jalan
    untuk kamera-kamera ini. Kirim {"ids": null} untuk melepas pembatasan (dipakai
    saat user meninggalkan halaman Live Cameras) — semua kamera kembali dideteksi
    terus-menerus seperti semula."""
    global _visible_restricted
    d = request.json or {}
    ids = d.get('ids')
    with _visible_lock:
        if ids is None:
            _visible_restricted = False
            _visible_cam_ids.clear()
        else:
            _visible_restricted = True
            _visible_cam_ids.clear()
            _visible_cam_ids.update(int(i) for i in ids)
    return jsonify({'ok': True, 'restricted': _visible_restricted, 'visible': sorted(_visible_cam_ids)})

# ── Upload video lokal untuk testing PPE detection ─────────────────────
@app.route('/api/videos', methods=['GET'])
@login_required
def api_videos_list():
    """List file video yang sudah di-upload — pakai path-nya sebagai URL kamera."""
    files = []
    if os.path.isdir(UPLOAD_FOLDER):
        for f in sorted(os.listdir(UPLOAD_FOLDER)):
            if os.path.splitext(f)[1].lower() in ALLOWED_VIDEO_EXTS:
                full = os.path.join(UPLOAD_FOLDER, f)
                files.append({
                    'filename': f,
                    'path': full,
                    'size_mb': round(os.path.getsize(full) / 1_000_000, 2),
                })
    return jsonify(files)


@app.route('/api/videos/upload', methods=['POST'])
@login_required
@demo_readonly
def api_videos_upload():
    """Upload satu file video. Response berisi path absolute yang bisa dipakai sebagai URL kamera."""
    if 'file' not in request.files:
        return jsonify({'error': 'Field "file" tidak ada di request'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'Filename kosong'}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        return jsonify({
            'error': f'Ekstensi {ext} tidak didukung',
            'allowed': sorted(ALLOWED_VIDEO_EXTS),
        }), 400

    # Sanitasi nama: hanya alnum, dash, underscore — hindari path traversal
    base = os.path.splitext(f.filename)[0]
    safe_base = ''.join(c for c in base if c.isalnum() or c in ('-', '_'))[:64] or 'video'
    safe_name = f"{int(time.time())}_{safe_base}{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, safe_name)
    f.save(save_path)

    return jsonify({
        'filename': safe_name,
        'path': save_path,
        'size_mb': round(os.path.getsize(save_path) / 1_000_000, 2),
        'hint': f'Tambah kamera baru dengan URL: {save_path}',
    }), 201


@app.route('/api/videos/<path:filename>', methods=['DELETE'])
@login_required
@demo_readonly
def api_videos_delete(filename):
    """Hapus file video upload."""
    safe = os.path.basename(filename)  # cegah path traversal
    full = os.path.join(UPLOAD_FOLDER, safe)
    if not os.path.isfile(full):
        return jsonify({'error': 'File tidak ditemukan'}), 404
    os.remove(full)
    return jsonify({'ok': True})

# Stream
def gen_mjpeg(cid):
    while True:
        cs = camera_streams.get(cid)
        if cs:
            jpeg = cs.get_jpeg()
            if jpeg:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
        time.sleep(1.0 / max(settings['stream_fps'], 1))

@app.route('/api/stream/<int:cid>')
@login_required
def video_feed(cid):
    return Response(gen_mjpeg(cid), mimetype='multipart/x-mixed-replace; boundary=frame')

# Logs
@app.route('/api/logs', methods=['GET'])
@login_required
def api_logs():
    s     = request.args.get('start')
    e     = request.args.get('end')
    limit = min(int(request.args.get('limit', 200)), 1000)  # max 1000 per request
    if s and e:
        rows = db_execute(
            "SELECT * FROM data WHERE Tanggal BETWEEN ? AND ? ORDER BY id DESC LIMIT ?",
            (s, e, limit), fetch=True
        )
    else:
        rows = db_execute(
            "SELECT * FROM data ORDER BY id DESC LIMIT ?",
            (limit,), fetch=True
        )
    # Cek file existence hanya untuk record yang ditampilkan (bukan semua)
    for r in rows:
        bukti = r.get('Bukti', '')
        r['file_exists'] = (
            os.path.isfile(os.path.join(OUTPUT_FOLDER, bukti))
            or _evidence_in_archive(bukti, r.get('Tanggal', ''))
        )
    return jsonify(rows)

@app.route('/api/stats', methods=['GET'])
@login_required
def api_stats():
    stats = {
        'total_violations': db_execute("SELECT COUNT(*) as c FROM data", fetchone=True)['c'],
        'today_violations': db_execute("SELECT COUNT(*) as c FROM data WHERE Tanggal=?", (date.today().isoformat(),), fetchone=True)['c'],
        'active_cameras':   db_execute("SELECT COUNT(*) as c FROM cameras WHERE enabled=1", fetchone=True)['c'],
        'online_cameras':   sum(1 for cs in camera_streams.values() if cs.connected),
        'by_type':          {r['jenis'] or 'unknown': r['cnt'] for r in db_execute("SELECT jenis, COUNT(*) as cnt FROM data GROUP BY jenis", fetch=True)},
    }
    stats.update(get_compliance_stats())
    return jsonify(stats)

# Settings
@app.route('/api/settings', methods=['GET'])
@login_required
def api_settings_get():
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
@login_required
@demo_readonly
def api_settings_update():
    d = request.json
    for k in ['violation_delay', 'confidence', 'person_confidence', 'stream_fps']:
        if k in d:
            try:
                settings[k] = int(float(d[k])) if isinstance(settings[k], int) else float(d[k])
                db_execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", (k, str(settings[k])))
            except: pass
    if 'inference_enabled' in d:
        settings['inference_enabled'] = bool(d['inference_enabled'])
        db_execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)",
                   ('inference_enabled', '1' if settings['inference_enabled'] else '0'))
    return jsonify(settings)


# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    threading.Thread(target=load_model, daemon=True).start()
    threading.Thread(target=_violation_writer, daemon=True).start()
    threading.Thread(target=_backup_worker, daemon=True).start()
    threading.Thread(target=_archive_worker, daemon=True).start()
    # Inference worker — tambah NUM_WORKERS=2 jika kamera > 20
    NUM_WORKERS = 1
    for _ in range(NUM_WORKERS):
        threading.Thread(target=_inference_worker, daemon=True).start()
    start_all_cameras()
    local_ip = get_local_ip()
    print("=" * 60)
    print("  PPE Monitoring System - Web UI")
    print(f"  Local access    : http://localhost:5000")
    print(f"  Network access  : http://{local_ip}:5000")
    if DEMO_MODE:
        print(f"  Mode            : DEMO PUBLIK (auto-login guest, edit dinonaktifkan)")
    else:
        print(f"  Default login   : admin / (lihat README — wajib diganti di login pertama)")
    print(f"  Violation delay : {settings['violation_delay']}s")
    print(f"  Confidence      : {settings['confidence']}")
    print(f"  Stream FPS cap  : {settings['stream_fps']}")
    print(f"  DVRIP support   : {'YES' if DVRIP_AVAILABLE else 'NO (install python-dvr + av)'}")
    print("=" * 60)

    if os.environ.get('DEV_SERVER') == '1':
        # Werkzeug dev server — HANYA untuk development lokal cepat, bukan produksi
        # (single-threaded per-request overhead lebih tinggi, tidak dirancang untuk
        # menahan banyak koneksi MJPEG jangka panjang secara bersamaan).
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    else:
        from waitress import serve
        threads = int(os.environ.get('WEB_THREADS', '32'))
        print(f"  WSGI server     : waitress (threads={threads})")
        print("=" * 60)
        serve(app, host='0.0.0.0', port=5000, threads=threads)