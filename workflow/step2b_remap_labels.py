"""
Step 2b: Remap class ID label dari model lama ke labels.txt baru.

Mapping:
  OLD best.pt (7 class)      → NEW labels.txt (5 class)
  ─────────────────────────────────────────────────────
  0: Person              → 0: Person
  1: boots               → DROP (hapus bounding box ini)
  2: helmet              → 1: helmet
  3: no_boot             → DROP (hapus bounding box ini)
  4: no_helmet           → 2: no_helmet
  5: no_seragam_dinas    → 4: no_rompi
  6: seragam_dinas       → 3: rompi

Jalankan sekali sebelum step3_split_dataset.py.

Usage:
  python workflow/step2b_remap_labels.py
  python workflow/step2b_remap_labels.py --labels data/training/raw/labels --dry_run
"""
import argparse
import shutil
from pathlib import Path

# OLD class ID → NEW class ID  (None = drop / hapus deteksi ini)
CLASS_MAP = {
    0: 0,     # Person      → Person
    1: None,  # boots       → DROP
    2: 1,     # helmet      → helmet
    3: None,  # no_boot     → DROP
    4: 2,     # no_helmet   → no_helmet
    5: 4,     # no_seragam_dinas → no_rompi
    6: 3,     # seragam_dinas   → rompi
}


def remap_file(label_path: Path, dry_run: bool) -> dict:
    text = label_path.read_text().strip()
    if not text:
        return {"kept": 0, "dropped": 0, "unchanged": True}

    new_lines = []
    dropped = 0
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        old_id = int(parts[0])
        new_id = CLASS_MAP.get(old_id)
        if new_id is None:
            dropped += 1
        else:
            new_lines.append(f"{new_id} " + " ".join(parts[1:]))

    if not dry_run:
        label_path.write_text("\n".join(new_lines))

    return {"kept": len(new_lines), "dropped": dropped, "unchanged": False}


def main():
    parser = argparse.ArgumentParser("Step 2b – Remap Class ID Label")
    parser.add_argument("--labels", default="data/training/raw/labels",
                        help="Folder label YOLO .txt (default: data/training/raw/labels)")
    parser.add_argument("--dry_run", action="store_true",
                        help="Preview saja, jangan tulis file")
    parser.add_argument("--backup", action="store_true",
                        help="Buat backup folder labels_backup/ sebelum remap")
    args = parser.parse_args()

    base = Path(__file__).parent.parent
    labels_dir = base / args.labels

    if not labels_dir.exists():
        print(f"[ERROR] Folder tidak ditemukan: {labels_dir}")
        return

    if args.backup and not args.dry_run:
        backup_dir = labels_dir.parent / "labels_backup"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.copytree(labels_dir, backup_dir)
        print(f"[Backup] Disimpan ke: {backup_dir}")

    txt_files = sorted(labels_dir.glob("*.txt"))
    if not txt_files:
        print(f"[ERROR] Tidak ada file .txt di: {labels_dir}")
        return

    total_kept = total_dropped = total_modified = 0

    for f in txt_files:
        stat = remap_file(f, args.dry_run)
        total_kept    += stat["kept"]
        total_dropped += stat["dropped"]
        if not stat["unchanged"]:
            total_modified += 1

    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{'='*50}")
    print(f"{mode}HASIL REMAP")
    print(f"{'='*50}")
    print(f"File diproses  : {len(txt_files)}")
    print(f"File diubah    : {total_modified}")
    print(f"Bbox dipertahan: {total_kept}")
    print(f"Bbox dihapus   : {total_dropped}  (boots & no_boot)")
    if args.dry_run:
        print("\nMode dry_run: tidak ada file yang diubah.")
        print("Jalankan tanpa --dry_run untuk terapkan perubahan.")
    else:
        print("\nRemap selesai.")
        print("Lanjut ke: python workflow/step3_split_dataset.py")


if __name__ == "__main__":
    main()
