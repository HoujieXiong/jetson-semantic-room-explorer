#!/usr/bin/env python3
"""Benchmark YOLO PyTorch image inference on Jetson."""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from pathlib import Path

import torch
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path or name.")
    parser.add_argument("--source", required=True, help="Input image path.")
    parser.add_argument("--output-csv", default="benchmarks/yolo_pytorch_baseline.csv")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", default="0")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--runs", type=int, default=50)
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def cuda_sync_if_needed() -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        raise FileNotFoundError(f"Input image not found: {source}")

    print("=== Environment ===")
    print(f"torch: {torch.__version__}")
    print(f"cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"cuda device: {torch.cuda.get_device_name(0)}")

    model = YOLO(args.model)

    print("\n=== Warmup ===")
    for i in range(args.warmup):
        _ = model.predict(
            source=str(source),
            imgsz=args.imgsz,
            conf=args.conf,
            device=args.device,
            save=False,
            verbose=False,
        )
        cuda_sync_if_needed()
        print(f"warmup {i + 1}/{args.warmup}")

    print("\n=== Benchmark ===")
    rows: list[dict[str, float | int | str]] = []
    total_ms_values: list[float] = []
    inference_ms_values: list[float] = []

    for i in range(args.runs):
        start = time.perf_counter()
        results = model.predict(
            source=str(source),
            imgsz=args.imgsz,
            conf=args.conf,
            device=args.device,
            save=False,
            verbose=False,
        )
        cuda_sync_if_needed()
        total_ms = (time.perf_counter() - start) * 1000.0

        result = results[0]
        preprocess_ms = float(result.speed.get("preprocess", float("nan")))
        inference_ms = float(result.speed.get("inference", float("nan")))
        postprocess_ms = float(result.speed.get("postprocess", float("nan")))
        detections = 0 if result.boxes is None else len(result.boxes)

        row = {
            "run": i + 1,
            "model": args.model,
            "source": str(source),
            "device": args.device,
            "imgsz": args.imgsz,
            "conf": args.conf,
            "detections": detections,
            "preprocess_ms": preprocess_ms,
            "inference_ms": inference_ms,
            "postprocess_ms": postprocess_ms,
            "total_wall_ms": total_ms,
        }
        rows.append(row)
        total_ms_values.append(total_ms)
        inference_ms_values.append(inference_ms)
        print(f"run {i + 1}/{args.runs}: inference={inference_ms:.2f}ms total={total_ms:.2f}ms detections={detections}")

    with output_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("\n=== Summary ===")
    print(f"runs: {args.runs}")
    print(f"inference_mean_ms: {statistics.mean(inference_ms_values):.2f}")
    print(f"inference_median_ms: {statistics.median(inference_ms_values):.2f}")
    print(f"inference_p95_ms: {percentile(inference_ms_values, 95):.2f}")
    print(f"total_mean_ms: {statistics.mean(total_ms_values):.2f}")
    print(f"total_median_ms: {statistics.median(total_ms_values):.2f}")
    print(f"total_p95_ms: {percentile(total_ms_values, 95):.2f}")
    print(f"fps_from_total_mean: {1000.0 / statistics.mean(total_ms_values):.2f}")
    print(f"csv: {output_csv}")


if __name__ == "__main__":
    main()
