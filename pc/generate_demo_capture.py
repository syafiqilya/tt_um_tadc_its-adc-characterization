#!/usr/bin/env python3
"""Generate a sample-only TADC capture for testing the FFT software."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from tadc_io import write_capture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=Path("demo_capture.csv"))
    parser.add_argument("--samples", type=int, default=4096)
    parser.add_argument("--adc-clock-hz", type=int, default=1_000_000)
    parser.add_argument("--clocks-per-sample", type=int, default=26)
    parser.add_argument("--tone-bin", type=int, default=107)
    parser.add_argument("--bits", type=int, default=9)
    parser.add_argument("--noise-rms-codes", type=float, default=0.8)
    args = parser.parse_args()

    if args.samples < 8:
        raise ValueError("at least eight samples are required")
    if not 0 < args.tone_bin < args.samples // 2:
        raise ValueError("tone bin must be between DC and Nyquist")
    if args.adc_clock_hz <= 0 or args.clocks_per_sample <= 0:
        raise ValueError("clock values must be positive")

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
    rows = [
        {"sequence": sequence, "adc_code": int(code), "unstable": 0}
        for sequence, code in enumerate(codes)
    ]
    sample_rate = args.adc_clock_hz / args.clocks_per_sample
    metadata = {
        "schema": "tadc-sample-capture-v2",
        "format_version": 2,
        "record_size_bytes": 4,
        "record_count": args.samples,
        "adc_clock_hz": args.adc_clock_hz,
        "clocks_per_sample": args.clocks_per_sample,
        "nominal_sample_rate_hz": sample_rate,
        "sample_rate_kind": "nominal_from_adc_clock_division",
        "synthetic": True,
        "synthetic_tone_bin": args.tone_bin,
        "synthetic_tone_hz": args.tone_bin * sample_rate / args.samples,
    }
    metadata_path = write_capture(rows, metadata, args.output)
    print(f"Saved {args.output.resolve()}")
    print(f"Saved {metadata_path.resolve()}")
    print(f"Nominal sample rate: {sample_rate:.9f} samples/s")
    print(f"Synthetic tone: {metadata['synthetic_tone_hz']:.9f} Hz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
