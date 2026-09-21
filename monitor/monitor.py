#!/usr/bin/env python3
"""
MAPPER — Watchdog eksternal (docs/SAAS_READINESS_AUDIT.md §I2/§I6).

Proses TERPISAH dari app_web.py secara sengaja — kalau backend-nya benar-benar
crash/container mati, sebuah thread di dalam proses yang sama ikut mati juga
dan tidak akan sempat lapor apa-apa. Watchdog ini jalan di container lain,
jadi tetap bisa mendeteksi & melapor walau ppe-backend sudah tidak merespons
sama sekali (bukan cuma "macet tapi masih hidup" — itu bagian /healthz).

Tiap CHECK_INTERVAL_SEC detik:
  1. GET HEALTHZ_URL. Gagal/non-2xx berturut-turut >= DOWN_ALERT_THRESHOLD kali
     -> alert "app_down" (sekali saat transisi, lalu diulang tiap
     REPEAT_ALERT_SEC selama masih down, bukan setiap interval).
  2. Baca baris BARU di INCIDENTS_LOG (ditulis app_web.py lewat log_incident())
     sejak posisi baca terakhir, teruskan tiap baris jadi alert.
  3. Kirim ke Telegram kalau TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID diisi;
     kalau tidak, cukup dicatat lokal (kebaca lewat `docker logs ppe-monitor`
     atau MONITOR_LOG) — supaya tetap berguna sebelum sempat setup Telegram.

Semua keputusan (down/recover) dicatat ke MONITOR_LOG (JSON per baris) —
itu jadi rujukan kalau nanti perlu ditelusuri "kapan backend-nya sempat mati
dan berapa lama", terpisah dari incidents.log punya app_web.py sendiri.
"""
import os
import sys
import json
import time
import traceback
import urllib.request
import urllib.error
from datetime import datetime

HEALTHZ_URL          = os.environ.get('HEALTHZ_URL', 'http://ppe-backend:5000/healthz')
INCIDENTS_LOG         = os.environ.get('INCIDENTS_LOG', '/app/data/logs/incidents.log')
MONITOR_LOG           = os.environ.get('MONITOR_LOG', '/app/data/logs/monitor.log')
STATE_FILE            = os.environ.get('MONITOR_STATE_FILE', '/app/data/logs/monitor_state.json')
CHECK_INTERVAL_SEC     = int(os.environ.get('CHECK_INTERVAL_SEC', '60'))
DOWN_ALERT_THRESHOLD   = int(os.environ.get('DOWN_ALERT_THRESHOLD', '2'))
REPEAT_ALERT_SEC       = int(os.environ.get('REPEAT_ALERT_SEC', '1800'))  # 30 menit
REQUEST_TIMEOUT_SEC    = int(os.environ.get('REQUEST_TIMEOUT_SEC', '10'))

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID   = os.environ.get('TELEGRAM_CHAT_ID', '').strip()


def _load_state():
    try:
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def _log_local(severity, code, message, **details):
    entry = {
        'ts': datetime.now().isoformat(timespec='seconds'),
        'severity': severity,
        'code': code,
        'message': message,
    }
    if details:
        entry['details'] = details
    print(f"[MONITOR:{severity.upper()}] {code}: {message}", flush=True)
    try:
        os.makedirs(os.path.dirname(MONITOR_LOG), exist_ok=True)
        with open(MONITOR_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except OSError as e:
        print(f"[MONITOR] Gagal tulis {MONITOR_LOG}: {e}", flush=True)


def send_alert(severity, code, message, **details):
    _log_local(severity, code, message, **details)
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    prefix = '\U0001F534' if severity == 'critical' else '\U0001F7E1'
    text = f"{prefix} [MAPPER PPE] {code}\n{message}"
    if details:
        text += "\n" + json.dumps(details, ensure_ascii=False)
    try:
        payload = json.dumps({'chat_id': TELEGRAM_CHAT_ID, 'text': text}).encode('utf-8')
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
            data=payload, headers={'Content-Type': 'application/json'},
        )
        urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC)
    except Exception as e:
        print(f"[MONITOR] Gagal kirim Telegram: {e}", flush=True)


def check_healthz(state):
    try:
        with urllib.request.urlopen(HEALTHZ_URL, timeout=REQUEST_TIMEOUT_SEC) as resp:
            ok = resp.status < 500
            body = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        ok = False
        body = {'status': 'unreachable', 'error': str(e)}

    if ok:
        if state.get('consecutive_failures', 0) >= DOWN_ALERT_THRESHOLD:
            downtime = time.time() - state.get('down_since', time.time())
            send_alert('critical', 'app_recovered',
                        f'Backend MAPPER kembali online setelah down {downtime:.0f}s')
        state['consecutive_failures'] = 0
        state['down_since'] = None
    else:
        state['consecutive_failures'] = state.get('consecutive_failures', 0) + 1
        if state['consecutive_failures'] == DOWN_ALERT_THRESHOLD:
            state['down_since'] = time.time()
            send_alert('critical', 'app_down',
                        f'Backend MAPPER tidak bisa diakses ({HEALTHZ_URL})',
                        error=body.get('error') or body.get('status'))
        elif state['consecutive_failures'] > DOWN_ALERT_THRESHOLD:
            down_since = state.get('down_since') or time.time()
            if (time.time() - down_since >= REPEAT_ALERT_SEC
                    and time.time() - state.get('last_down_repeat', 0) >= REPEAT_ALERT_SEC):
                state['last_down_repeat'] = time.time()
                since_str = datetime.fromtimestamp(down_since).isoformat(timespec='seconds')
                send_alert('critical', 'app_down', f'Backend MAPPER MASIH down sejak {since_str}')
    return state


def check_incidents_log(state):
    """Baca baris baru dari incidents.log (ditulis app_web.py) sejak posisi
    terakhir. Deteksi rotasi (RotatingFileHandler) lewat ukuran file yang
    tiba-tiba lebih kecil dari offset tersimpan -> baca ulang dari awal."""
    if not os.path.isfile(INCIDENTS_LOG):
        return state
    try:
        size = os.path.getsize(INCIDENTS_LOG)
        offset = state.get('incidents_offset', 0)
        if size < offset:
            offset = 0  # file dirotasi/ditulis ulang sejak pembacaan terakhir
        with open(INCIDENTS_LOG, 'r', encoding='utf-8') as f:
            f.seek(offset)
            new_lines = f.readlines()
            state['incidents_offset'] = f.tell()
        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            send_alert(entry.get('severity', 'warning'), entry.get('code', 'unknown'),
                       entry.get('message', line), **(entry.get('details') or {}))
    except OSError as e:
        print(f"[MONITOR] Gagal baca {INCIDENTS_LOG}: {e}", flush=True)
    return state


def main():
    print("=" * 60, flush=True)
    print("  MAPPER Watchdog - memantau /healthz + incidents.log", flush=True)
    print(f"  Target          : {HEALTHZ_URL}", flush=True)
    print(f"  Interval        : {CHECK_INTERVAL_SEC}s", flush=True)
    telegram_status = 'AKTIF' if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else \
        'NONAKTIF (cuma log lokal - isi TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID untuk aktifkan)'
    print(f"  Telegram alert  : {telegram_status}", flush=True)
    print("=" * 60, flush=True)

    state = _load_state()
    while True:
        try:
            state = check_healthz(state)
            state = check_incidents_log(state)
            _save_state(state)
        except Exception:
            print("[MONITOR] Error tak terduga:", flush=True)
            traceback.print_exc()
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == '__main__':
    main()
