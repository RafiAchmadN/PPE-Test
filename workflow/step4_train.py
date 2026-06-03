"""
Step 4: Training YOLOv11 dengan Transfer Learning + Augmentasi.

Loop otomatis: jika mAP@0.95 < 0.80 setelah training, ulangi dengan
model terbaik dari round sebelumnya sebagai titik awal (Transfer Learning).

Usage:
  python workflow/step4_train.py
  python workflow/step4_train.py --epochs 150 --device 0
  python workflow/step4_train.py --epochs 100 --batch 8 --device cpu
  python workflow/step4_train.py --max_rounds 5 --epochs 50
"""
import shutil
import argparse
from pathlib import Path

MAP95_TARGET = 0.80  # threshold loop: lanjut training jika mAP@0.95 < nilai ini


def detect_device():
    try:
        import torch
        return "0" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def run_training(data_yaml, base_model, epochs, imgsz, batch, device, out_dir, run_name):
    from ultralytics import YOLO

    print(f"\n{'='*60}")
    print(f"  Training: {run_name}")
    print(f"  Model awal   : {base_model.name}")
    print(f"  Dataset      : {data_yaml}")
    print(f"  Epochs       : {epochs}  |  Batch: {batch}  |  imgSz: {imgsz}")
    print(f"  Device       : {device}")
    print(f"{'='*60}\n")

    model = YOLO(str(base_model))
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=str(out_dir),
        name=run_name,
        exist_ok=True,

        # Augmentasi (built-in ultralytics)
        hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
        degrees=10,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        flipud=0.05,
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.1,

        # Transfer learning / learning rate
        freeze=0,
        lr0=0.001,
        lrf=0.01,
        warmup_epochs=3,
        patience=30,

        # Output
        save_period=10,
        plots=True,
        verbose=True,
    )
    return results


def read_map95(results):
    try:
        return float(results.results_dict.get("metrics/mAP50-95(B)", 0))
    except Exception:
        return 0.0


def main():
    parser = argparse.ArgumentParser("Step 4 – Train YOLOv11")
    parser.add_argument("--data",       default="data/training/split/data.yaml")
    parser.add_argument("--model",      default="best.pt",
                        help="Model awal transfer learning (default: best.pt)")
    parser.add_argument("--epochs",     type=int,   default=100)
    parser.add_argument("--imgsz",      type=int,   default=640)
    parser.add_argument("--batch",      type=int,   default=16)
    parser.add_argument("--device",     default=None,
                        help="cpu | 0 | 0,1 (auto-detect jika tidak diisi)")
    parser.add_argument("--max_rounds", type=int,   default=3,
                        help="Maksimal pengulangan jika mAP belum tercapai")
    parser.add_argument("--target_map", type=float, default=MAP95_TARGET)
    args = parser.parse_args()

    base = Path(__file__).parent.parent
    data_yaml  = base / args.data
    model_path = base / args.model
    runs_dir   = base / "runs" / "ppe_train"
    device     = args.device or detect_device()

    if not data_yaml.exists():
        print(f"[ERROR] data.yaml tidak ada: {data_yaml}")
        print("Jalankan step3_split_dataset.py terlebih dahulu (output ke data/training/split/).")
        return
    if not model_path.exists():
        print(f"[ERROR] Model tidak ada: {model_path}")
        return

    print(f"Device otomatis: {device}")
    print(f"Target mAP@0.95: {args.target_map}")

    best_map   = 0.0
    best_weights = None

    for rnd in range(1, args.max_rounds + 1):
        run_name = f"round_{rnd}"

        # Gunakan best.pt dari round sebelumnya jika ada
        if rnd > 1 and best_weights and best_weights.exists():
            model_path = best_weights
            print(f"\n[Round {rnd}] Lanjut dari: {model_path}")

        results = run_training(
            data_yaml, model_path,
            args.epochs, args.imgsz, args.batch,
            device, runs_dir, run_name
        )

        map95 = read_map95(results)
        best_map = max(best_map, map95)
        best_weights = runs_dir / run_name / "weights" / "best.pt"

        print(f"\nmAP@0.95 = {map95:.4f}  (target >= {args.target_map})")

        if map95 >= args.target_map:
            print(f"Target tercapai di Round {rnd}!")
            break
        elif rnd < args.max_rounds:
            print(f"Belum mencapai target. Melanjutkan Round {rnd + 1}...")
        else:
            print(f"Sudah {args.max_rounds} round. mAP terbaik: {best_map:.4f}")
            if best_map < args.target_map:
                print("Saran: tambah data atau perbesar epochs.")

    # Salin best.pt ke folder utama
    if best_weights and best_weights.exists():
        dest = base / "best.pt"
        shutil.copy(best_weights, dest)
        print(f"\nModel terbaik disalin ke: {dest}")
        print(f"mAP@0.95 terbaik: {best_map:.4f}")

        if best_map >= args.target_map:
            print("\nModel siap digunakan di app_web.py.")
            print("Jalankan: python app_web.py")
        else:
            print(f"\nmAP masih di bawah target ({args.target_map}).")
            print("Saran: tambah data anotasi lalu ulangi dari step2.")


if __name__ == "__main__":
    main()
