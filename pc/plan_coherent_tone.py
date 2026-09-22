#!/usr/bin/env python3
"""Choose a function-generator frequency coherent with a measured sample rate."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from tadc_io import load_json, save_json


def alias_bin(bin_number: int, sample_count: int) -> int:
    folded = bin_number % sample_count
    return sample_count - folded if folded > sample_count // 2 else folded


def harmonics_are_distinct(k: int, sample_count: int, maximum_harmonic: int) -> bool:
    bins = [alias_bin(order * k, sample_count) for order in range(1, maximum_harmonic + 1)]
    return 0 not in bins and len(set(bins)) == len(bins)


def choose_bin(sample_rate: float, sample_count: int, target_hz: float, maximum_harmonic: int) -> int:
    candidates = [
        k
        for k in range(1, sample_count // 2)
        if math.gcd(k, sample_count) == 1
        and harmonics_are_distinct(k, sample_count, maximum_harmonic)
    ]
    if not candidates:
        raise ValueError("no valid coherent FFT bin satisfies the requested constraints")
    return min(candidates, key=lambda k: abs(k * sample_rate / sample_count - target_hz))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timing_report", type=Path)
    parser.add_argument("--target-hz", type=float, required=True)
    parser.add_argument("--samples", type=int, help="FFT length; default is capture record count")
    parser.add_argument("--max-harmonic", type=int, default=5)
    parser.add_argument(
        "--generator-resolution-hz",
        type=float,
        default=0.0,
        help="round frequency to this generator step; zero keeps the exact value",
    )
    parser.add_argument("--max-cycle-error", type=float, default=0.01)
    parser.add_argument(
        "--allow-unstable-timing",
        action="store_true",
        help="calculate a nominal tone even when the timing report is not stable",
    )
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    timing = load_json(args.timing_report)
    if not timing.get("timing_stable") and not args.allow_unstable_timing:
        raise ValueError(
            "timing report is not stable; correct the hardware timing or use "
            "--allow-unstable-timing for a nominal, noncoherent estimate"
        )
    sample_rate = float(timing["sample_rate_hz"])
    sample_count = args.samples or int(timing["record_count"])
    if sample_count < 8:
        raise ValueError("at least eight samples are required")
    if not 0 < args.target_hz < sample_rate / 2:
        raise ValueError(f"target frequency must be between 0 and Nyquist ({sample_rate / 2:g} Hz)")

    selected_bin = choose_bin(sample_rate, sample_count, args.target_hz, args.max_harmonic)
    ideal_hz = selected_bin * sample_rate / sample_count
    programmed_hz = ideal_hz
    if args.generator_resolution_hz > 0:
        programmed_hz = round(ideal_hz / args.generator_resolution_hz) * args.generator_resolution_hz

    actual_cycles = programmed_hz * sample_count / sample_rate
    residual_cycles = actual_cycles - selected_bin
    phase_slip_degrees = residual_cycles * 360.0
    report = {
        "schema": "tadc-coherent-tone-v1",
        "source_timing_report": str(args.timing_report.resolve()),
        "sample_rate_hz": sample_rate,
        "sample_count": sample_count,
        "bin_width_hz": sample_rate / sample_count,
        "requested_frequency_hz": args.target_hz,
        "selected_bin": selected_bin,
        "ideal_frequency_hz": ideal_hz,
        "generator_resolution_hz": args.generator_resolution_hz,
        "programmed_frequency_hz": programmed_hz,
        "cycles_in_capture": actual_cycles,
        "residual_cycle_error": residual_cycles,
        "phase_slip_degrees": phase_slip_degrees,
        "maximum_cycle_error": args.max_cycle_error,
        "frequency_setting_is_coherent": abs(residual_cycles) <= args.max_cycle_error,
        "source_timing_stable": bool(timing.get("timing_stable")),
        "requires_shared_frequency_reference": True,
        "maximum_checked_harmonic": args.max_harmonic,
        "harmonic_bins": {
            str(order): alias_bin(order * selected_bin, sample_count)
            for order in range(2, args.max_harmonic + 1)
        },
    }
    output = args.output or args.timing_report.with_name(
        args.timing_report.stem.removesuffix("_timing") + "_tone.json"
    )
    save_json(output, report)

    print(f"Measured sample rate: {sample_rate:.9f} Hz")
    print(f"FFT samples: {sample_count}; bin width: {sample_rate / sample_count:.9f} Hz")
    print(f"Selected bin: {selected_bin}")
    print(f"Set the function generator to: {programmed_hz:.12g} Hz")
    print(f"Capture phase slip: {phase_slip_degrees:.6g} degrees")
    print(f"Frequency setting coherent: {report['frequency_setting_is_coherent']}")
    print("Use a shared frequency reference for repeatable hardware coherence.")
    print(f"Saved {output.resolve()}")
    return 0 if report["frequency_setting_is_coherent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
