# Watchdog eksternal untuk MAPPER (lihat monitor.py) — sengaja base image
# minimal, cuma pakai stdlib Python (urllib), tidak butuh pip install apa pun.
FROM python:3.11-alpine
WORKDIR /app
COPY monitor.py .
CMD ["python", "monitor.py"]
