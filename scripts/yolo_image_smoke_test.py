#!/usr/bin/env python3
"""Run a headless YOLO image inference smoke test."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path or name.")
    parser.add_argument("--source", required=True, help="Input image path.")
    parser.add_argument("--output-dir", default="data/outputs/yolo_smoke_test", help="Output directory.")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size.")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold.")
    parser.add_argument("--device", default="0", help="Device, e.g. 0, cpu.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        raise FileNotFoundError(f"Input image not found: {source}")

    print("=== Environment ===")
    print(f"torch: {torch.__version__}")
    print(f"cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"cuda device: {torch.cuda.get_device_name(0)}")

    print("\n=== Loading model ===")
    model = YOLO(args.model)

    print("\n=== Running inference ===")
    results = model.predict(
        source=str(source),
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        project=str(output_dir.parent),
        name=output_dir.name,
        exist_ok=True,
        save=True,
        verbose=False,
    )

    result = results[0]
    names = result.names
    boxes = result.boxes

    print("\n=== Detections ===")
    if boxes is None or len(boxes) == 0:
        print("No detections.")
    else:
        for i, box in enumerate(boxes):
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            xyxy = [round(float(v), 2) for v in box.xyxy[0].tolist()]
            print(f"{i:02d}: {names[cls_id]} conf={conf:.3f} bbox_xyxy={xyxy}")

    print("\n=== Speed ===")
    print(f"preprocess_ms: {result.speed.get('preprocess', float('nan')):.2f}")
    print(f"inference_ms: {result.speed.get('inference', float('nan')):.2f}")
    print(f"postprocess_ms: {result.speed.get('postprocess', float('nan')):.2f}")

    print("\n=== Output ===")
    print(f"saved_dir: {output_dir}")


if __name__ == "__main__":
    main()
