"""
Step 3: Split dataset 70 / 25 / 5 (train / val / test).

Input : dataset/raw/images + dataset/raw/labels
Output: dataset/split/ + dataset/split/data.yaml

Usage:
  python workflow/step3_split_dataset.py
  python workflow/step3_split_dataset.py --raw dataset/raw --output dataset/split
"""
import shutil
import random
import yaml
import argparse
from pathlib import Path

TRAIN_RATIO = 0.70
VAL_RATIO   = 0.25
# test = sisa (~0.05)

SUPPORTED_IMG = {".jpg", ".jpeg", ".png"}


def main():
    parser = argparse.ArgumentParser("Step 3 – Split Dataset 70/25/5")
    parser.add_argument("--raw", default="data/training/raw")
    parser.add_argument("--output", default="data/training/split")
    parser.add_argument("--labels_txt", default="data/training/labels.txt")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    base = Path(__file__).parent.parent
    raw_dir    = base / args.raw
    out_dir    = base / args.output
    labels_txt = base / args.labels_txt

    images_dir = raw_dir / "images"
    labels_dir = raw_dir / "labels"

    if not images_dir.exists():
        print(f"[ERROR] Tidak ada: {images_dir}")
        print("Jalankan step2_auto_annotate.py terlebih dahulu (output ke data/training/raw/).")
        return

    if not labels_txt.exists():
        print(f"[ERROR] File class names tidak ada: {labels_txt}")
        return

    with open(labels_txt) as f:
        class_names = [l.strip() for l in f if l.strip()]

    # Kumpulkan pasangan image+label yang valid
    valid = []
    no_label = []
    for img in sorted(images_dir.iterdir()):
        if img.suffix.lower() not in SUPPORTED_IMG:
            continue
        lbl = labels_dir / f"{img.stem}.txt"
        if lbl.exists():
            valid.append(img.stem)
        else:
            no_label.append(img.name)

    print(f"Pasangan valid   : {len(valid)}")
    if no_label:
        print(f"Tanpa label (skip): {len(no_label)}")

    if not valid:
        print("[ERROR] Tidak ada pasangan image+label yang valid.")
        return

    # Split
    random.seed(args.seed)
    random.shuffle(valid)
    n       = len(valid)
    n_train = int(n * TRAIN_RATIO)
    n_val   = int(n * VAL_RATIO)

    splits = {
        "train": valid[:n_train],
        "val":   valid[n_train : n_train + n_val],
        "test":  valid[n_train + n_val :],
    }

    for split_name, stems in splits.items():
        pct = len(stems) / n * 100
        print(f"  {split_name:5s}: {len(stems):4d} gambar ({pct:.1f}%)")

    # Hapus output lama kalau ada agar tidak tercampur dengan split berbeda
    if out_dir.exists():
        shutil.rmtree(out_dir)

    # Salin file
    for split_name, stems in splits.items():
        img_out = out_dir / "images" / split_name
        lbl_out = out_dir / "labels" / split_name
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for stem in stems:
            # Cari ekstensi gambar (jpg/png)
            img_src = images_dir / f"{stem}.jpg"
            if not img_src.exists():
                img_src = next(
                    (images_dir / f"{stem}{ext}" for ext in SUPPORTED_IMG
                     if (images_dir / f"{stem}{ext}").exists()), None
                )
            if img_src is None:
                print(f"  [WARN] Gambar tidak ditemukan: {stem}")
                continue

            lbl_src = labels_dir / f"{stem}.txt"
            shutil.copy(img_src, img_out / img_src.name)
            shutil.copy(lbl_src, lbl_out / f"{stem}.txt")

    # data.yaml
    data_yaml = {
        "path":  str(out_dir.resolve()),
        "train": "images/train",
        "val":   "images/val",
        "test":  "images/test",
        "nc":    len(class_names),
        "names": class_names,
    }
    yaml_path = out_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(data_yaml, f, default_flow_style=False, allow_unicode=True)

    print(f"\nSplit selesai → {out_dir}")
    print(f"data.yaml     → {yaml_path}")
    print(f"Classes ({len(class_names)}): {class_names}")
    print("\nLanjut ke: python workflow/step4_train.py")


if __name__ == "__main__":
    main()
