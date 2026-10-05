#!/usr/bin/env python3
"""Shared file helpers for TADC sample captures and FFT reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np


REQUIRED_COLUMNS = {"sequence", "adc_code", "unstable"}


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
            fieldnames=["sequence", "adc_code", "unstable"],
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

    sample_rate = metadata.get("nominal_sample_rate_hz")
    if sample_rate is None:
        adc_clock = metadata.get("adc_clock_hz")
        clocks_per_sample = metadata.get("clocks_per_sample")
        if adc_clock and clocks_per_sample:
            sample_rate = float(adc_clock) / float(clocks_per_sample)

    return {
        "path": csv_path,
        "metadata_path": selected_metadata if selected_metadata.exists() else None,
        "metadata": metadata,
        "sample_rate_hz": float(sample_rate) if sample_rate else None,
        "sequence": integers("sequence"),
        "adc_code": integers("adc_code"),
        "unstable": integers("unstable").astype(bool),
    }


def default_output(input_path: Path, suffix: str) -> Path:
    return input_path.with_name(f"{input_path.stem}{suffix}")
