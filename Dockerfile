FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3-pip \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3 /usr/bin/python

# Deno -- dibutuhkan yt-dlp buat resolve URL YouTube (kamera dari link YouTube).
# YouTube sekarang wajib eksekusi JS asli buat decode signature/n-param video,
# tanpa JS runtime yt-dlp cuma bisa warning "No supported JavaScript runtime
# could be found" dan gagal dapat URL stream-nya. Deno dipilih karena cuma
# 1 binary statis (~100MB), jauh lebih ringan daripada install Node.js penuh.
RUN curl -fsSL https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip \
    && unzip -o /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip \
    && chmod +x /usr/local/bin/deno

WORKDIR /app

# PyTorch dengan CUDA 12.8 (support RTX 5060 Blackwell sm_120)
RUN pip install --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cu128

RUN pip install --no-cache-dir \
    flask==3.1.3 \
    flask-cors==6.0.5 \
    flask-limiter==3.9.2 \
    waitress==3.0.2 \
    opencv-python-headless==4.13.0.92 \
    ultralytics==8.4.14 \
    numpy \
    yt-dlp \
    pillow \
    requests \
    werkzeug

COPY . .

RUN mkdir -p foto data/violations data/videos

EXPOSE 5000

CMD ["python", "app_web.py"]
