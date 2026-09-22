#!/usr/bin/env python3
"""Analyze TADC result timing and decide whether the sample cadence is stable."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import numpy as np

from tadc_io import default_output, load_capture, save_json, unwrap_u32


def analyze(capture: dict[str, Any], tolerance_ticks: int = 1) -> dict[str, Any]:
    sequence = capture["sequence"]
    expected_sequence = np.arange(sequence.size, dtype=np.int64)
    sequence_errors = int(np.count_nonzero(sequence != expected_sequence))

    normal = ~capture["first_record"]
    if np.count_nonzero(normal) == 0:
        raise ValueError("capture has no normal conversion intervals after the first record")

    periods = capture["period_ticks"][normal]
    adc_edges = capture["adc_clock_edges"][normal]
    system_hz = float(capture["system_clock_hz"])
    period_mean = float(np.mean(periods))
    period_median = float(np.median(periods))
    dominant_period_values, dominant_period_counts = np.unique(periods, return_counts=True)
    dominant_period = int(dominant_period_values[np.argmax(dominant_period_counts)])
    dominant_edges_values, dominant_edges_counts = np.unique(adc_edges, return_counts=True)
    dominant_edges = int(dominant_edges_values[np.argmax(dominant_edges_counts)])

    timing_outliers = np.abs(periods - dominant_period) > tolerance_ticks
    edge_outliers = adc_edges != dominant_edges

    unwrapped = unwrap_u32(capture["timestamp_ticks"])
    timestamp_periods = np.diff(unwrapped)
    reported_periods = capture["period_ticks"][1:]
    timestamp_mismatches = int(np.count_nonzero(timestamp_periods != reported_periods))

    unstable_count = int(np.count_nonzero(capture["unstable"]))
    max_deviation = int(np.max(np.abs(periods - dominant_period)))
    timing_stable = bool(
        sequence_errors == 0
        and unstable_count == 0
        and timestamp_mismatches == 0
        and not np.any(timing_outliers)
        and not np.any(edge_outliers)
    )

    if math.isclose(period_mean, 0.0):
        raise ValueError("mean conversion period is zero")
    sample_rate_hz = system_hz / period_mean
    report: dict[str, Any] = {
        "schema": "tadc-timing-report-v1",
        "source_csv": str(capture["path"]),
        "record_count": int(sequence.size),
        "analyzed_interval_count": int(periods.size),
        "system_clock_hz": system_hz,
        "counter_resolution_seconds": 1.0 / system_hz,
        "sample_rate_hz": sample_rate_hz,
        "mean_period_ticks": period_mean,
        "median_period_ticks": period_median,
        "dominant_period_ticks": dominant_period,
        "minimum_period_ticks": int(np.min(periods)),
        "maximum_period_ticks": int(np.max(periods)),
        "peak_deviation_ticks": max_deviation,
        "rms_period_jitter_ticks": float(np.std(periods)),
        "rms_period_jitter_seconds": float(np.std(periods)) / system_hz,
        "dominant_adc_clock_edges": dominant_edges,
        "minimum_adc_clock_edges": int(np.min(adc_edges)),
        "maximum_adc_clock_edges": int(np.max(adc_edges)),
        "period_outlier_count": int(np.count_nonzero(timing_outliers)),
        "adc_edge_outlier_count": int(np.count_nonzero(edge_outliers)),
        "unstable_data_count": unstable_count,
        "sequence_error_count": sequence_errors,
        "timestamp_period_mismatch_count": timestamp_mismatches,
        "allowed_period_deviation_ticks": tolerance_ticks,
        "timing_stable": timing_stable,
        "timing_classification": "stable" if timing_stable else "not_stable",
    }
    return report


def write_plot(capture: dict[str, Any], report: dict[str, Any], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    normal = ~capture["first_record"]
    periods = capture["period_ticks"][normal]
    edges = capture["adc_clock_edges"][normal]
    sample_numbers = capture["sequence"][normal]
    dominant = report["dominant_period_ticks"]

    figure, axes = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True)
    axes[0].plot(sample_numbers, periods, linewidth=0.8)
    axes[0].axhline(dominant, color="tab:red", linestyle="--", label="dominant")
    axes[0].set(title="Conversion interval", ylabel="10 MHz counter ticks")
    axes[0].legend()

    axes[1].hist(periods - dominant, bins=np.arange(periods.min() - dominant - 0.5, periods.max() - dominant + 1.5))
    axes[1].set(title="Period deviation histogram", xlabel="Ticks from dominant", ylabel="Count")

    axes[2].plot(sample_numbers, edges, linewidth=0.8)
    axes[2].set(title="ADC clock edges per result", xlabel="Sequence", ylabel="Rising edges")

    figure.suptitle(
        f"TADC timing: {report['timing_classification']} | "
        f"Fs={report['sample_rate_hz']:.6f} Hz"
    )
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="CSV produced by capture_tadc.py")
    parser.add_argument("--metadata", type=Path, help="override capture metadata JSON")
    parser.add_argument("-o", "--output", type=Path, help="timing-report JSON path")
    parser.add_argument("--plot", type=Path, help="timing plot PNG path")
    parser.add_argument("--no-plot", action="store_true", help="do not create a timing plot")
    parser.add_argument("--tolerance-ticks", type=int, default=1)
    args = parser.parse_args()

    capture = load_capture(args.capture, args.metadata)
    report = analyze(capture, args.tolerance_ticks)
    output = args.output or default_output(args.capture, "_timing.json")
    save_json(output, report)

    plot = args.plot or default_output(args.capture, "_timing.png")
    if not args.no_plot:
        write_plot(capture, report, plot)

    print(f"Timing classification: {report['timing_classification']}")
    print(f"Measured sample rate: {report['sample_rate_hz']:.9f} Hz")
    print(
        "Period ticks: "
        f"min={report['minimum_period_ticks']}, "
        f"dominant={report['dominant_period_ticks']}, "
        f"max={report['maximum_period_ticks']}"
    )
    print(f"ADC-clock edges/result: {report['dominant_adc_clock_edges']}")
    print(f"Unstable data records: {report['unstable_data_count']}")
    print(f"Saved {output.resolve()}")
    if not args.no_plot:
        print(f"Saved {plot.resolve()}")
    return 0 if report["timing_stable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
