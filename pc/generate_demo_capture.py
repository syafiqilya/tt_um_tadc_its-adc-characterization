#!/usr/bin/env python3
"""Generate a deterministic capture so the analysis tools can be tested without hardware."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from tadc_io import metadata_path_for, save_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=Path("demo_capture.csv"))
    parser.add_argument("--samples", type=int, default=4096)
    parser.add_argument("--system-hz", type=int, default=10_000_000)
    parser.add_argument("--period-ticks", type=int, default=260)
    parser.add_argument("--adc-clock-edges", type=int, default=26)
    parser.add_argument("--tone-bin", type=int, default=107)
    parser.add_argument("--bits", type=int, default=9)
    parser.add_argument("--noise-rms-codes", type=float, default=0.8)
    args = parser.parse_args()

    if not 0 < args.tone_bin < args.samples // 2:
        raise ValueError("tone bin must be between DC and Nyquist")

    rng = np.random.default_rng(20260922)
    index = np.arange(args.samples)
    maximum_code = 2**args.bits - 1
    midpoint = maximum_code / 2.0
    phase = 2.0 * np.pi * args.tone_bin * index / args.samples
    signal = (
        midpoint
        + 0.90 * midpoint * np.sin(phase)
        + 0.0025 * midpoint * np.sin(2.0 * phase + 0.3)
        + rng.normal(0.0, args.noise_rms_codes, args.samples)
    )
    codes = np.clip(np.rint(signal), 0, maximum_code).astype(int)
    timestamps = np.cumsum(np.full(args.samples, args.period_ticks, dtype=np.uint64))

    fieldnames = [
        "sequence",
        "adc_code",
        "unstable",
        "first_record",
        "timestamp_ticks",
        "timestamp_us",
        "period_ticks",
        "period_us",
        "adc_clock_edges",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for sequence, (code, timestamp) in enumerate(zip(codes, timestamps, strict=True)):
            writer.writerow(
                {
                    "sequence": sequence,
                    "adc_code": int(code),
                    "unstable": 0,
                    "first_record": int(sequence == 0),
                    "timestamp_ticks": int(timestamp & np.uint64(0xFFFFFFFF)),
                    "timestamp_us": float(timestamp) * 1e6 / args.system_hz,
                    "period_ticks": args.period_ticks,
                    "period_us": args.period_ticks * 1e6 / args.system_hz,
                    "adc_clock_edges": args.adc_clock_edges,
                }
            )

    sample_rate = args.system_hz / args.period_ticks
    metadata_path = metadata_path_for(args.output)
    save_json(
        metadata_path,
        {
            "schema": "tadc-capture-v1",
            "record_count": args.samples,
            "system_clock_hz": args.system_hz,
            "adc_clock_hz": 1_000_000,
            "counter_tick_seconds": 1.0 / args.system_hz,
            "source_csv": args.output.name,
            "synthetic": True,
            "synthetic_tone_bin": args.tone_bin,
            "synthetic_tone_hz": args.tone_bin * sample_rate / args.samples,
        },
    )
    print(f"Saved {args.output.resolve()}")
    print(f"Saved {metadata_path.resolve()}")
    print(f"Synthetic sample rate: {sample_rate:.9f} Hz")
    print(f"Synthetic coherent tone: {args.tone_bin * sample_rate / args.samples:.9f} Hz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
