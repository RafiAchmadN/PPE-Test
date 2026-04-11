import os
import sys
import json
import time
import queue
import sqlite3
import threading
import traceback
from datetime import datetime, date

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

import cv2
import numpy as np
from flask import Flask, render_template, request, jsonify, Response, send_from_directory

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'logging.db')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'foto')
INFERENCE_SIZE = (640, 480)

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder='static', template_folder='templates')

# Runtime settings (adjustable via UI)
settings = {
    'violation_delay': 30,      # seconds between captures per camera
    'confidence': 0.5,
    'inference_enabled': True,
    'stream_fps': 15,           # max fps for MJPEG stream
}

# ─── DATABASE ────────────────────────────────────────────────────────────────

_db_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def db_execute(query, params=(), fetch=False, fetchone=False):
    with _db_lock:
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
        # Backfill from Bukti filename
        conn.execute("UPDATE data SET jenis='no-helmet' WHERE Bukti LIKE '%tanpahelm%'")
        conn.execute("UPDATE data SET jenis='no-vest' WHERE Bukti LIKE '%tanpavest%'")
        conn.commit()
        print("[MIGRATE] Done. Backfilled jenis from existing Bukti filenames.")

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
_model_type = None   # 'v5' or 'ultralytics'
_model_names = {}

def load_model():
    global _model, _model_type, _model_names
    with _model_lock:
        if _model is not None:
            return _model, _model_type

        model_path = os.path.join(BASE_DIR, 'best.pt')
        fallback_path = os.path.join(BASE_DIR, 'yolo11n.pt')

        # ── Try ultralytics first (handles v5/v8/v11 .pt) ──
        try:
            from ultralytics import YOLO
            _model = YOLO(model_path)
            _model.to('cpu')
            _model_names = _model.names
            _model_type = 'ultralytics'
            print(f"[MODEL] Loaded {model_path} (ultralytics)")
            print(f"[MODEL] Classes: {_model_names}")
            return _model, _model_type
        except Exception as e:
            print(f"[MODEL] ultralytics best.pt failed: {e}")

        # ── Try torch.hub YOLOv5 ──
        try:
            import torch
            _model = torch.hub.load('ultralytics/yolov5', 'custom', path=model_path, force_reload=False)
            _model.cpu()
            _model.conf = settings['confidence']
            _model_names = _model.names
            _model_type = 'v5'
            print(f"[MODEL] Loaded {model_path} (YOLOv5 torch.hub)")
            print(f"[MODEL] Classes: {_model_names}")
            return _model, _model_type
        except Exception as e:
            print(f"[MODEL] torch.hub failed: {e}")

        # ── Fallback yolo11n.pt ──
        try:
            from ultralytics import YOLO
            _model = YOLO(fallback_path)
            _model.to('cpu')
            _model_names = _model.names
            _model_type = 'ultralytics'
            print(f"[MODEL] Fallback to {fallback_path}")
            print(f"[MODEL] Classes: {_model_names}")
            return _model, _model_type
        except Exception as e:
            print(f"[MODEL] ALL model loads failed: {e}")
            return None, None


def _classify(cls_id, cls_name):
    """Map class to violation type by name first, then ID fallback."""
    n = (cls_name or '').lower().replace('-', '_')
    if 'no_helmet' in n or 'tanpahelm' in n:
        return 'no-helmet'
    if 'no_vest' in n or 'tanpavest' in n:
        return 'no-vest'
    # Fallback: original best.pt mapping
    if cls_id == 1: return 'no-helmet'
    if cls_id == 2: return 'no-vest'
    return None

def run_inference(frame):
    """Returns (annotated_frame, violations_list)."""
    model, mtype = load_model()
    if model is None:
        return frame, []

    resized = cv2.resize(frame, INFERENCE_SIZE)
    violations = []

    try:
        if mtype == 'v5':
            model.conf = settings['confidence']
            results = model(resized)
            annotated = np.squeeze(results.render())
            coor = results.xyxy[0]
            names = model.names if hasattr(model, 'names') else {}
            for i in range(len(coor)):
                cls_id = int(coor[i][5].item())
                conf = float(coor[i][4].item())
                cls_name = names.get(cls_id, '') if isinstance(names, dict) else (names[cls_id] if cls_id < len(names) else '')
                vt = _classify(cls_id, cls_name)
                if vt:
                    violations.append({'type': vt, 'conf': conf})

        elif mtype == 'ultralytics':
            results = model.predict(resized, conf=settings['confidence'], verbose=False, device='cpu')
            result = results[0]
            annotated = result.plot()
            names = _model_names or {}
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                cls_name = names.get(cls_id, '')
                vt = _classify(cls_id, cls_name)
                if vt:
                    violations.append({'type': vt, 'conf': conf})
        else:
            annotated = resized
    except Exception as e:
        print(f"[INFERENCE] Error: {e}")
        annotated = resized

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
        self.thread = threading.Thread(target=self._loop, daemon=True)
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

        # Regular URL (RTSP, HTTP MJPEG, etc.)
        return url, None

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
                    cap = cv2.VideoCapture(src)
                    # Set timeouts for network streams (not webcams)
                    if isinstance(src, str):
                        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)   # 10s open timeout
                        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000)   # 10s read timeout
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)              # minimize buffer lag

                    if not cap.isOpened():
                        err_detail = "Cannot open stream"
                        if isinstance(src, int):
                            err_detail = f"Webcam {src} not found"
                        elif 'rtsp://' in str(src):
                            err_detail = "RTSP unreachable (check network/credentials)"
                        elif 'http' in str(src):
                            err_detail = "HTTP stream unreachable"
                        self.error_msg = err_detail
                        print(f"[CAM {self.cam_id}] {err_detail}")
                        if cap: cap.release(); cap = None
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, 60)
                        continue

                    self.connected = True
                    self.error_msg = ""
                    retry_delay = 3
                    print(f"[CAM {self.cam_id}] Connected: {self.name}")
                except Exception as e:
                    self.error_msg = f"OpenCV error: {str(e)[:60]}"
                    print(f"[CAM {self.cam_id}] {self.error_msg}")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
                    continue

            ret, frame = cap.read()
            if not ret:
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

            # Inference
            if settings['inference_enabled']:
                try:
                    annotated, violations = run_inference(frame)
                except:
                    annotated, violations = frame, []

                # Record violation with delay
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
                        db_execute(
                            "INSERT INTO data (Tanggal, Waktu, Lokasi, Bukti, jenis) VALUES (?,?,?,?,?)",
                            (tgl, wkt, self.name, fname, v['type'])
                        )
                        print(f"[VIOLATION] {self.name}: {v['type']} conf={v['conf']:.2f} -> {fname}")
                    except Exception as e:
                        print(f"[VIOLATION] Save error: {e}")
                    self.last_violation_time = time.time()

                with self.lock:
                    self.frame = annotated
            else:
                with self.lock:
                    self.frame = frame

            # Throttle
            time.sleep(1.0 / max(settings['stream_fps'], 1))

        if cap: cap.release()

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/foto/<path:filename>')
def serve_foto(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

# Camera CRUD
@app.route('/api/cameras', methods=['GET'])
def api_cameras_list():
    rows = db_execute("SELECT * FROM cameras ORDER BY id", fetch=True)
    for c in rows:
        cs = camera_streams.get(c['id'])
        if cs:
            info = cs.get_info()
            c['online'] = info['connected']
            c['fps'] = info['fps']
            c['error'] = info['error']
        else:
            c['online'] = False; c['fps'] = 0; c['error'] = 'Not started'
    return jsonify(rows)

@app.route('/api/cameras', methods=['POST'])
def api_cameras_create():
    d = request.json
    name = d.get('name','').strip(); url = d.get('url','').strip()
    if not name or not url:
        return jsonify({'error': 'Name and URL required'}), 400
    cid = db_execute("INSERT INTO cameras (name, url) VALUES (?,?)", (name, url))
    cs = CameraStream(cid, url, name); camera_streams[cid] = cs; cs.start()
    return jsonify({'id': cid}), 201

@app.route('/api/cameras/<int:cid>', methods=['PUT'])
def api_cameras_update(cid):
    d = request.json
    name = d.get('name','').strip(); url = d.get('url','').strip(); enabled = d.get('enabled', 1)
    if not name or not url:
        return jsonify({'error': 'Name and URL required'}), 400
    db_execute("UPDATE cameras SET name=?, url=?, enabled=? WHERE id=?", (name, url, enabled, cid))
    restart_camera(cid)
    return jsonify({'ok': True})

@app.route('/api/cameras/<int:cid>', methods=['DELETE'])
def api_cameras_delete(cid):
    stop_camera(cid)
    db_execute("DELETE FROM cameras WHERE id=?", (cid,))
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
def video_feed(cid):
    return Response(gen_mjpeg(cid), mimetype='multipart/x-mixed-replace; boundary=frame')

# Logs
@app.route('/api/logs', methods=['GET'])
def api_logs():
    s = request.args.get('start', date.today().replace(day=1).isoformat())
    e = request.args.get('end', date.today().isoformat())
    return jsonify(db_execute("SELECT * FROM data WHERE Tanggal BETWEEN ? AND ? ORDER BY id DESC", (s, e), fetch=True))

@app.route('/api/stats', methods=['GET'])
def api_stats():
    return jsonify({
        'total_violations': db_execute("SELECT COUNT(*) as c FROM data", fetchone=True)['c'],
        'today_violations': db_execute("SELECT COUNT(*) as c FROM data WHERE Tanggal=?", (date.today().isoformat(),), fetchone=True)['c'],
        'active_cameras': db_execute("SELECT COUNT(*) as c FROM cameras WHERE enabled=1", fetchone=True)['c'],
        'online_cameras': sum(1 for cs in camera_streams.values() if cs.connected),
        'by_type': {r['jenis'] or 'unknown': r['cnt'] for r in db_execute("SELECT jenis, COUNT(*) as cnt FROM data GROUP BY jenis", fetch=True)},
    })

# Settings
@app.route('/api/settings', methods=['GET'])
def api_settings_get():
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
def api_settings_update():
    d = request.json
    for k in ['violation_delay', 'confidence', 'stream_fps']:
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
    start_all_cameras()
    print("=" * 60)
    print("  PPE Monitoring System - Web UI")
    print(f"  Violation delay : {settings['violation_delay']}s")
    print(f"  Confidence      : {settings['confidence']}")
    print(f"  Stream FPS cap  : {settings['stream_fps']}")
    print("  Open http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)