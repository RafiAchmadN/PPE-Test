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
from datetime import datetime, date
from functools import wraps
from urllib.parse import urlparse

# GPU diaktifkan — hapus override CUDA_VISIBLE_DEVICES agar torch bisa detect GPU

import cv2
import numpy as np
from flask import Flask, render_template, request, jsonify, Response, send_from_directory, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash

# --- Optional: dukungan DVR Xiongmai/Sofia (port 34567) ---
try:
    from dvrip import DVRIPCam
    _DVRIP_LIB_OK = True
except ImportError:
    _DVRIP_LIB_OK = False

try:
    import av  # PyAV untuk decode H264 dari Sofia stream
    _AV_LIB_OK = True
except ImportError:
    _AV_LIB_OK = False

DVRIP_AVAILABLE = _DVRIP_LIB_OK and _AV_LIB_OK

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_BASE_URL = os.environ.get('APP_BASE_URL', '').rstrip('/')
DATABASE_PATH = os.path.join(BASE_DIR, 'logging.db')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'data', 'violations')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'videos')
INFERENCE_SIZE = (640, 480)
ALLOWED_VIDEO_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v'}
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'ppe-monitor-default-change-me-2026')

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(APP_BASE_URL + '/login')
        return f(*args, **kwargs)
    return decorated

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
    'violation_delay': 1,       # seconds between captures per camera
    'confidence': 0.5,          # threshold untuk PPE class (helmet, rompi, dll)
    'person_confidence': 0.7,   # threshold khusus class Person (lebih tinggi = kurangi false detect)
    'inference_enabled': True,
    'stream_fps': 15,            # max fps for MJPEG stream
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

def _violation_writer():
    """Thread khusus menulis violations ke DB — camera thread tidak perlu tunggu DB."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
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
            continue
        except Exception as e:
            print(f"[DB WRITER] {e}")
            try: conn.close()
            except: pass
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")

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

    # Default admin password: admin123
    row = conn.execute("SELECT value FROM app_settings WHERE key='admin_pw_hash'").fetchone()
    if not row:
        conn.execute("INSERT INTO app_settings (key,value) VALUES ('admin_pw_hash',?)",
                     (generate_password_hash('admin123'),))
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
_inference_sem = threading.Semaphore(2)  # maks 2 kamera inference bersamaan

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
    model, mtype = load_model()
    if model is None:
        return frame, []

    violations = []
    try:
        with _inference_sem:  # maks 2 inference bersamaan, sisanya tunggu
            if mtype == 'ultralytics':
                import torch
                min_conf = min(settings['confidence'], settings['person_confidence'])
                try:
                    results = model.predict(
                        frame,
                        conf=min_conf,
                        imgsz=640,
                        verbose=False,
                        device=_device
                    )
                except RuntimeError as cuda_err:
                    if 'no kernel image' in str(cuda_err).lower() or 'cudaerror' in str(cuda_err).lower():
                        global _device
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

                # Filter per class — gunakan torch tensor untuk boolean indexing
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

    # ── Helper bersama: jalankan inference + logging untuk SEMUA jenis stream ──
    def _handle_frame(self, frame):
        """Run inference, log violations if any, store latest frame for streaming."""
        if frame is None:
            return
        if settings['inference_enabled']:
            try:
                annotated, violations = run_inference(frame)
            except Exception:
                annotated, violations = frame, []

            delay = settings['violation_delay']
            if violations and (time.time() - self.last_violation_time >= delay):
                v = violations[0]
                ts = time.strftime("%m%d%H%M%S")
                tgl = time.strftime("%Y-%m-%d")
                wkt = datetime.now().strftime("%H:%M:%S")
                prefix = "tanpahelm" if v['type'] == 'no-helmet' else "tanpavest"
                fname = f'{prefix}_{self.name.replace(" ", "")}_{ts}.jpg'
                fpath = os.path.join(OUTPUT_FOLDER, fname)
                try:
                    cv2.imwrite(fpath, annotated)
                    _violation_queue.put((tgl, wkt, self.name, fname, v['type']))
                    print(f"[VIOLATION] {self.name}: {v['type']} conf={v['conf']:.2f} -> {fname}")
                except Exception as e:
                    print(f"[VIOLATION] Save error: {e}")
                self.last_violation_time = time.time()

            with self.lock:
                self.frame = annotated
        else:
            with self.lock:
                self.frame = frame

    def _loop(self):
        cap = None
        retry_delay = 3
        fc = 0
        ft = time.time()

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

            # FPS
            fc += 1
            el = time.time() - ft
            if el >= 2:
                self.fps = fc / el
                fc = 0; ft = time.time()

            # Inference + violation logging (via shared helper)
            self._handle_frame(frame)

            # Throttle
            time.sleep(1.0 / max(settings['stream_fps'], 1))

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
                        self._handle_frame(img)
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
                _, buf = cv2.imencode('.jpg', self.frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
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

# ─── FLASK ROUTES ────────────────────────────────────────────────────────────

# Auth routes (not protected)
@app.route('/login', methods=['GET'])
def login_page():
    if session.get('logged_in'):
        return redirect(APP_BASE_URL + '/')
    return render_template('login.html', app_base=APP_BASE_URL)

@app.route('/login', methods=['POST'])
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(APP_BASE_URL + '/login')

@app.route('/')
@login_required
def index():
    base = os.environ.get('APP_BASE_URL', '').rstrip('/')
    return render_template('index.html', app_base=base)

@app.route('/foto/<path:filename>')
@login_required
def serve_foto(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

@app.route('/api/info')
@login_required
def api_info():
    ip = get_local_ip()
    return jsonify({'local_ip': ip, 'port': 5000, 'access_url': f'http://{ip}:5000'})

@app.route('/api/auth/change-password', methods=['POST'])
@login_required
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
    return jsonify({'ok': True})

# Camera CRUD
@app.route('/api/cameras', methods=['GET'])
@login_required
def api_cameras_list():
    rows = db_execute("SELECT * FROM cameras ORDER BY id", fetch=True)
    for c in rows:
        cs = camera_streams.get(c['id'])
        if cs:
            info = cs.get_info()
            c['online'] = info['connected']
            c['fps']    = info['fps']
            c['error']  = info['error']
        else:
            c['online'] = False; c['fps'] = 0; c['error'] = 'Not started'
    return jsonify(rows)

@app.route('/api/cameras', methods=['POST'])
@login_required
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
def api_cameras_delete(cid):
    stop_camera(cid)
    db_execute("DELETE FROM cameras WHERE id=?", (cid,))
    return jsonify({'ok': True})

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
    s = request.args.get('start', date.today().replace(day=1).isoformat())
    e = request.args.get('end',   date.today().isoformat())
    rows = db_execute("SELECT * FROM data WHERE Tanggal BETWEEN ? AND ? ORDER BY id DESC", (s, e), fetch=True)
    for r in rows:
        r['file_exists'] = os.path.isfile(os.path.join(OUTPUT_FOLDER, r.get('Bukti', '')))
    return jsonify(rows)

@app.route('/api/stats', methods=['GET'])
@login_required
def api_stats():
    return jsonify({
        'total_violations': db_execute("SELECT COUNT(*) as c FROM data", fetchone=True)['c'],
        'today_violations': db_execute("SELECT COUNT(*) as c FROM data WHERE Tanggal=?", (date.today().isoformat(),), fetchone=True)['c'],
        'active_cameras':   db_execute("SELECT COUNT(*) as c FROM cameras WHERE enabled=1", fetchone=True)['c'],
        'online_cameras':   sum(1 for cs in camera_streams.values() if cs.connected),
        'by_type':          {r['jenis'] or 'unknown': r['cnt'] for r in db_execute("SELECT jenis, COUNT(*) as cnt FROM data GROUP BY jenis", fetch=True)},
    })

# Settings
@app.route('/api/settings', methods=['GET'])
@login_required
def api_settings_get():
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
@login_required
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
    start_all_cameras()
    local_ip = get_local_ip()
    print("=" * 60)
    print("  PPE Monitoring System - Web UI")
    print(f"  Local access    : http://localhost:5000")
    print(f"  Network access  : http://{local_ip}:5000")
    print(f"  Default login   : admin / admin123")
    print(f"  Violation delay : {settings['violation_delay']}s")
    print(f"  Confidence      : {settings['confidence']}")
    print(f"  Stream FPS cap  : {settings['stream_fps']}")
    print(f"  DVRIP support   : {'YES' if DVRIP_AVAILABLE else 'NO (install python-dvr + av)'}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)