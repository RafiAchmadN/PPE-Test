"""
Step 1: Ekstrak frame dari video menjadi gambar untuk dataset anotasi.

Output: dataset/frames/<nama_video>/<nama_video>_0000001.jpg

Usage:
  python workflow/step1_extract_frames.py
  python workflow/step1_extract_frames.py --fps 0.5
  python workflow/step1_extract_frames.py --fps 2 --no_skip_blur
  python workflow/step1_extract_frames.py --videos_dir videos --output dataset/frames
"""
import cv2
import argparse
from pathlib import Path


def is_blurry(frame, threshold):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var() < threshold


def extract_video(video_path, output_dir, fps_target, skip_blur, blur_threshold):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  [ERROR] Tidak bisa membuka: {video_path.name}")
        return 0

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    interval = max(1, round(src_fps / fps_target))

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem
    saved = skipped = frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % interval == 0:
            if skip_blur and is_blurry(frame, blur_threshold):
                skipped += 1
            else:
                out_path = output_dir / f"{stem}_{frame_idx:07d}.jpg"
                if not out_path.exists():
                    cv2.imwrite(str(out_path), frame)
                saved += 1
        frame_idx += 1
        if frame_idx % (interval * 20) == 0:
            pct = frame_idx / max(total, 1) * 100
            print(f"  [{video_path.name}] {pct:.0f}%  saved={saved}", end="\r")

    cap.release()
    print(f"  [{video_path.name}] Selesai: {saved} disimpan, {skipped} buram dilewati" + " " * 10)
    return saved


def main():
    parser = argparse.ArgumentParser("Step 1 – Video → Frames")
    parser.add_argument("--videos_dir", default="data/videos")
    parser.add_argument("--output", default="data/training/frames",
                        help="Folder output (default: data/training/frames)")
    parser.add_argument("--fps", type=float, default=1.0,
                        help="Jumlah frame per detik yang disimpan (default 1)")
    parser.add_argument("--no_skip_blur", action="store_true",
                        help="Simpan semua frame termasuk yang buram")
    parser.add_argument("--blur_threshold", type=float, default=100.0,
                        help="Nilai Laplacian variance di bawahnya = buram (default 100)")
    args = parser.parse_args()

    base = Path(__file__).parent.parent
    videos_dir = base / args.videos_dir
    output_base = base / args.output
    skip_blur = not args.no_skip_blur

    VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
    videos = sorted(p for p in videos_dir.iterdir() if p.suffix.lower() in VIDEO_EXTS)

    if not videos:
        print(f"[INFO] Tidak ada video di: {videos_dir}")
        return

    print(f"Ditemukan {len(videos)} video | FPS target: {args.fps} | Skip blur: {skip_blur}")
    print(f"Output: {output_base}\n")

    total = 0
    for v in videos:
        out_dir = output_base / v.stem
        total += extract_video(v, out_dir, args.fps, skip_blur, args.blur_threshold)

    all_frames = list(output_base.rglob("*.jpg"))
    print(f"\nTotal frame tersimpan: {total}")
    print(f"Lokasi: {output_base}")
    print("\nLangkah selanjutnya:")
    print("  Upload gambar di data/training/frames/ ke makesense.ai untuk anotasi,")
    print("  lalu jalankan: python workflow/step2_auto_annotate.py --makesense_zip <file.zip>")


if __name__ == "__main__":
    main()
