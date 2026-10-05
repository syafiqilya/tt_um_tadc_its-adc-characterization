#!/usr/bin/env python3
"""Shared file helpers for TADC sample captures and FFT reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np


REQUIRED_COLUMNS = {"sequence", "adc_code", "unstable", "timestamp_ticks"}


def metadata_path_for(csv_path: Path) -> Path:
    return csv_path.with_suffix(".meta.json")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_capture(
    rows: list[dict[str, int]],
    metadata: dict[str, Any],
    csv_path: Path,
    metadata_path: Path | None = None,
) -> Path:
    if not rows:
        raise ValueError("cannot write an empty capture")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "sequence",
                "adc_code",
                "unstable",
                "timestamp_ticks",
                "timestamp_us",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    selected_metadata = metadata_path or metadata_path_for(csv_path)
    payload = dict(metadata)
    payload["source_csv"] = csv_path.name
    save_json(selected_metadata, payload)
    return selected_metadata


def load_capture(csv_path: Path, metadata_path: Path | None = None) -> dict[str, Any]:
    csv_path = csv_path.resolve()
    with csv_path.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        rows = list(reader)
        columns = set(reader.fieldnames or [])

    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise ValueError(f"capture is missing required columns: {', '.join(missing)}")
    if not rows:
        raise ValueError("capture contains no samples")

    selected_metadata = metadata_path or metadata_path_for(csv_path)
    metadata: dict[str, Any] = {}
    if selected_metadata.exists():
        metadata = load_json(selected_metadata)

    def integers(name: str) -> np.ndarray:
        return np.asarray([int(row[name]) for row in rows], dtype=np.int64)

    timestamps = integers("timestamp_ticks")
    timer_clock_hz = metadata.get("timer_clock_hz")
    sample_rate = metadata.get("measured_sample_rate_hz")
    if sample_rate is None and timer_clock_hz and timestamps.size >= 2:
        unwrapped = unwrap_u32(timestamps)
        elapsed_ticks = int(unwrapped[-1] - unwrapped[0])
        if elapsed_ticks > 0:
            sample_rate = (timestamps.size - 1) * float(timer_clock_hz) / elapsed_ticks

    return {
        "path": csv_path,
        "metadata_path": selected_metadata if selected_metadata.exists() else None,
        "metadata": metadata,
        "sample_rate_hz": float(sample_rate) if sample_rate else None,
        "timer_clock_hz": float(timer_clock_hz) if timer_clock_hz else None,
        "sequence": integers("sequence"),
        "adc_code": integers("adc_code"),
        "unstable": integers("unstable").astype(bool),
        "timestamp_ticks": timestamps,
    }


def unwrap_u32(values: np.ndarray) -> np.ndarray:
    """Unwrap monotonically increasing unsigned 32-bit FPGA timestamps."""
    raw = np.asarray(values, dtype=np.uint64)
    if raw.size == 0:
        return np.asarray([], dtype=np.int64)
    unwrapped = np.empty(raw.size, dtype=np.int64)
    unwrapped[0] = int(raw[0])
    for index in range(1, raw.size):
        delta = (int(raw[index]) - int(raw[index - 1])) & 0xFFFFFFFF
        unwrapped[index] = unwrapped[index - 1] + delta
    return unwrapped


def summarize_timing(timestamp_ticks: np.ndarray, timer_clock_hz: float) -> dict[str, Any]:
    """Calculate sampling speed and interval statistics on the PC."""
    if timer_clock_hz <= 0:
        raise ValueError("timer clock must be positive")
    unwrapped = unwrap_u32(timestamp_ticks)
    if unwrapped.size < 2:
        raise ValueError("at least two timestamps are required")
    intervals = np.diff(unwrapped)
    if np.any(intervals <= 0):
        raise ValueError("timestamps are not strictly increasing")
    elapsed_ticks = int(unwrapped[-1] - unwrapped[0])
    sample_rate = (unwrapped.size - 1) * timer_clock_hz / elapsed_ticks
    interval_values, interval_counts = np.unique(intervals, return_counts=True)
    dominant_interval = int(interval_values[np.argmax(interval_counts)])
    tolerance_ticks = 1
    interval_outliers = np.abs(intervals - dominant_interval) > tolerance_ticks
    return {
        "timer_clock_hz": timer_clock_hz,
        "timer_resolution_seconds": 1.0 / timer_clock_hz,
        "interval_count": int(intervals.size),
        "elapsed_ticks_first_to_last": elapsed_ticks,
        "elapsed_seconds_first_to_last": elapsed_ticks / timer_clock_hz,
        "measured_sample_rate_hz": sample_rate,
        "mean_interval_ticks": float(np.mean(intervals)),
        "median_interval_ticks": float(np.median(intervals)),
        "dominant_interval_ticks": dominant_interval,
        "minimum_interval_ticks": int(np.min(intervals)),
        "maximum_interval_ticks": int(np.max(intervals)),
        "interval_tolerance_ticks": tolerance_ticks,
        "interval_outlier_count": int(np.count_nonzero(interval_outliers)),
        "timing_stable": bool(not np.any(interval_outliers)),
        "rms_interval_jitter_ticks": float(np.std(intervals)),
        "rms_interval_jitter_seconds": float(np.std(intervals)) / timer_clock_hz,
        "sample_rate_formula": "(sample_count - 1) * timer_clock_hz / (last_timestamp - first_timestamp)",
    }


def default_output(input_path: Path, suffix: str) -> Path:
    return input_path.with_name(f"{input_path.stem}{suffix}")
