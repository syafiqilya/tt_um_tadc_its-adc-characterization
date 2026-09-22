#!/usr/bin/env python3
"""Shared capture-file helpers for the TADC characterization tools."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np


REQUIRED_COLUMNS = {
    "sequence",
    "adc_code",
    "unstable",
    "first_record",
    "timestamp_ticks",
    "period_ticks",
    "adc_clock_edges",
}


def metadata_path_for(csv_path: Path) -> Path:
    return csv_path.with_suffix(".meta.json")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _infer_system_clock(rows: list[dict[str, str]]) -> float | None:
    estimates: list[float] = []
    for row in rows:
        try:
            ticks = float(row["period_ticks"])
            period_us = float(row["period_us"])
        except (KeyError, TypeError, ValueError):
            continue
        if ticks > 0 and period_us > 0:
            estimates.append(ticks * 1e6 / period_us)
    return float(np.median(estimates)) if estimates else None


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
        raise ValueError("capture contains no records")

    selected_metadata = metadata_path or metadata_path_for(csv_path)
    metadata: dict[str, Any] = {}
    if selected_metadata.exists():
        metadata = load_json(selected_metadata)

    system_clock_hz = metadata.get("system_clock_hz") or _infer_system_clock(rows)
    if not system_clock_hz:
        raise ValueError(
            "system clock is unavailable; keep the .meta.json file beside the CSV "
            "or include period_us in the CSV"
        )

    def integers(name: str) -> np.ndarray:
        return np.asarray([int(row[name]) for row in rows], dtype=np.int64)

    return {
        "path": csv_path,
        "metadata_path": selected_metadata if selected_metadata.exists() else None,
        "metadata": metadata,
        "system_clock_hz": float(system_clock_hz),
        "sequence": integers("sequence"),
        "adc_code": integers("adc_code"),
        "unstable": integers("unstable").astype(bool),
        "first_record": integers("first_record").astype(bool),
        "timestamp_ticks": integers("timestamp_ticks"),
        "period_ticks": integers("period_ticks"),
        "adc_clock_edges": integers("adc_clock_edges"),
    }


def unwrap_u32(values: np.ndarray) -> np.ndarray:
    """Unwrap a sequence of unsigned 32-bit timestamps into int64 ticks."""
    raw = np.asarray(values, dtype=np.int64)
    result = np.empty_like(raw)
    offset = 0
    previous = int(raw[0])
    result[0] = previous
    for index in range(1, raw.size):
        current = int(raw[index])
        if current < previous and previous - current > (1 << 31):
            offset += 1 << 32
        result[index] = current + offset
        previous = current
    return result


def default_output(input_path: Path, suffix: str) -> Path:
    return input_path.with_name(f"{input_path.stem}{suffix}")
