"""
Step 2: Auto-annotate gambar menggunakan model YOLO (best.pt).

Alur:
  1. (Opsional) Ekstrak label dari ZIP makesense.ai → dataset/raw/labels/
  2. Untuk gambar yang BELUM punya label → jalankan model untuk auto-labeling
  3. Cetak laporan: berapa % sudah ter-anotasi, mana yang butuh review manual

Jalankan step ini berulang setelah setiap batch anotasi makesense.ai sampai
semua gambar ter-anotasi (loop "Ada" pada diagram alur).

Usage:
  python workflow/step2_auto_annotate.py
  python workflow/step2_auto_annotate.py --makesense_zip annotations.zip
  python workflow/step2_auto_annotate.py --images dataset/frames --conf 0.55
"""
import shutil
import zipfile
import argparse
from pathlib import Path


SUPPORTED_IMG = {".jpg", ".jpeg", ".png"}


def import_makesense_zip(zip_path, labels_out):
    """Ekstrak label dari ZIP makesense.ai ke labels_out/."""
    zip_path = Path(zip_path)
    if not zip_path.exists():
        print(f"[ERROR] ZIP tidak ditemukan: {zip_path}")
        return 0

    labels_out.mkdir(parents=True, exist_ok=True)
    imported = 0
    with zipfile.ZipFile(zip_path) as z:
        txt_files = [n for n in z.namelist() if n.endswith(".txt")]
        for name in txt_files:
            content = z.read(name).decode().strip()
            stem = Path(name).stem
            dest = labels_out / f"{stem}.txt"
            dest.write_text(content)
            imported += 1

    print(f"[Makesense] {imported} label diekstrak dari {zip_path.name}")
    return imported


def copy_images(src_dir, images_out):
    """Salin semua gambar dari src_dir (rekursif) ke images_out/ tanpa duplikat."""
    images_out.mkdir(parents=True, exist_ok=True)
    copied = skipped = 0
    for img in sorted(src_dir.rglob("*")):
        if img.suffix.lower() in SUPPORTED_IMG:
            dest = images_out / img.name
            if not dest.exists():
                shutil.copy(img, dest)
                copied += 1
            else:
                skipped += 1
    print(f"[Copy] {copied} gambar disalin, {skipped} sudah ada")
    return copied + skipped


def auto_annotate(images_out, labels_out, model_path, conf_threshold):
    """Jalankan YOLO pada gambar yang belum punya label."""
    from ultralytics import YOLO

    labels_out.mkdir(parents=True, exist_ok=True)
    all_imgs = sorted(p for p in images_out.iterdir() if p.suffix.lower() in SUPPORTED_IMG)
    unlabeled = [p for p in all_imgs if not (labels_out / f"{p.stem}.txt").exists()]

    if not unlabeled:
        print("[AutoAnnotate] Semua gambar sudah punya label.")
        return 0, []

    print(f"[AutoAnnotate] Memproses {len(unlabeled)} gambar tanpa label...")
    model = YOLO(str(model_path))

    annotated = uncertain = 0
    uncertain_list = []

    for i, img_path in enumerate(unlabeled, 1):
        results = model.predict(str(img_path), conf=conf_threshold, verbose=False, device="cpu")
        result = results[0]
        h, w = result.orig_shape

        lines = []
        max_conf = 0.0
        for box in result.boxes:
            cls_id = int(box.cls[0])
            c = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = ((x1 + x2) / 2) / w
            cy = ((y1 + y2) / 2) / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            max_conf = max(max_conf, c)

        lbl_file = labels_out / f"{img_path.stem}.txt"
        lbl_file.write_text("\n".join(lines))

        if lines:
            annotated += 1
            if max_conf < 0.70:
                uncertain += 1
                uncertain_list.append(img_path.name)
        # Gambar tanpa deteksi tetap disimpan sebagai negative sample (file kosong)

        if i % 100 == 0:
            print(f"  {i}/{len(unlabeled)}", end="\r")

    print(f"[AutoAnnotate] {annotated} gambar dianotasi, {uncertain} confidence rendah (<0.70)")
    return annotated, uncertain_list


def main():
    parser = argparse.ArgumentParser("Step 2 – Auto-Annotate")
    parser.add_argument("--images", default="data/training/frames",
                        help="Folder gambar (boleh rekursif, default: data/training/frames)")
    parser.add_argument("--raw", default="data/training/raw",
                        help="Folder output pasangan image+label")
    parser.add_argument("--makesense_zip", default=None,
                        help="ZIP anotasi dari makesense.ai (opsional)")
    parser.add_argument("--model", default="best.pt")
    parser.add_argument("--conf", type=float, default=0.50,
                        help="Confidence threshold untuk auto-annotate (default 0.50)")
    args = parser.parse_args()

    base = Path(__file__).parent.parent
    images_src = base / args.images
    raw_dir = base / args.raw
    images_out = raw_dir / "images"
    labels_out = raw_dir / "labels"
    model_path = base / args.model

    if not images_src.exists():
        print(f"[ERROR] Folder gambar tidak ada: {images_src}")
        print("Jalankan step1_extract_frames.py terlebih dahulu (output ke data/training/frames/).")
        return
    if not model_path.exists():
        print(f"[ERROR] Model tidak ada: {model_path}")
        return

    # 1. Salin gambar
    total_imgs = copy_images(images_src, images_out)

    # 2. Import label dari makesense.ai
    if args.makesense_zip:
        import_makesense_zip(args.makesense_zip, labels_out)

    # 3. Auto-annotate sisa gambar
    _, uncertain_list = auto_annotate(images_out, labels_out, model_path, args.conf)

    # 4. Laporan
    imgs = list(images_out.glob("*.jpg")) + list(images_out.glob("*.png"))
    lbls = list(labels_out.glob("*.txt"))
    labeled_count = len(lbls)
    missing = len(imgs) - labeled_count

    print(f"\n{'='*55}")
    print(f"LAPORAN ANOTASI")
    print(f"{'='*55}")
    print(f"Total gambar     : {len(imgs)}")
    print(f"Sudah berlabel   : {labeled_count}")
    print(f"Belum berlabel   : {missing}")
    print(f"Confidence rendah: {len(uncertain_list)}")

    if uncertain_list:
        unc_file = raw_dir / "review_needed.txt"
        unc_file.write_text("\n".join(uncertain_list))
        print(f"  → Daftar: {unc_file}")

    if missing > 0 or uncertain_list:
        print(f"\nMasih ada gambar yang perlu perhatian.")
        print("Opsi:")
        print("  A) Upload ke makesense.ai, download ZIP, jalankan ulang step ini dengan:")
        print("     python workflow/step2_auto_annotate.py --makesense_zip <file.zip>")
        print("  B) Jika sudah cukup, lanjut ke step berikutnya:")
        print("     python workflow/step3_split_dataset.py")
    else:
        print(f"\nSemua gambar ter-anotasi!")
        print("Lanjut ke: python workflow/step3_split_dataset.py")


if __name__ == "__main__":
    main()
