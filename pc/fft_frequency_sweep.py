#!/usr/bin/env python3
"""Run a manual function-generator frequency sweep and analyze every capture."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from analyze_fft import analyze_capture, write_plot, write_spectrum
from capture_tadc import print_no_data_help, receive_capture
from tadc_io import load_capture, save_json, write_capture


SUMMARY_FIELDS = [
    "point",
    "stimulus_frequency_hz",
    "fft_fundamental_frequency_hz",
    "fundamental_amplitude_dbfs",
    "snr_db",
    "sinad_db",
    "thd_db",
    "sfdr_db",
    "enob_bits",
    "minimum_code",
    "maximum_code",
    "peak_to_peak_codes",
    "unstable_sample_count",
    "capture_csv",
]


def frequency_points(start_hz: float, stop_hz: float, points: int, spacing: str) -> np.ndarray:
    if start_hz <= 0 or stop_hz <= 0:
        raise ValueError("sweep frequencies must be positive")
    if stop_hz < start_hz:
        raise ValueError("--stop-hz must be greater than or equal to --start-hz")
    if points < 1:
        raise ValueError("--points must be at least one")
    if points == 1:
        return np.asarray([start_hz], dtype=float)
    if spacing == "log":
        return np.geomspace(start_hz, stop_hz, points)
    return np.linspace(start_hz, stop_hz, points)


def frequency_tag(frequency_hz: float) -> str:
    text = f"{frequency_hz:.6f}".rstrip("0").rstrip(".")
    return text.replace(".", "p") + "Hz"


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary_plot(path: Path, rows: list[dict[str, Any]], logarithmic: bool) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    stimulus = np.asarray([row["stimulus_frequency_hz"] for row in rows])
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    traces = (
        ("fundamental_amplitude_dbfs", "Amplitude (dBFS)"),
        ("sinad_db", "SINAD (dB)"),
        ("sfdr_db", "SFDR (dB)"),
        ("enob_bits", "ENOB (bits)"),
    )
    for axis, (field, label) in zip(axes.flat, traces, strict=True):
        axis.plot(stimulus, [row[field] for row in rows], marker="o")
        axis.set(xlabel="Function-generator frequency (Hz)", ylabel=label)
        axis.grid(True, alpha=0.3)
        if logarithmic:
            axis.set_xscale("log")
    figure.suptitle("TADC FFT frequency sweep")
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="Cmod A7 UART port, for example COM6 or /dev/ttyUSB1")
    parser.add_argument("--start-hz", type=float, required=True)
    parser.add_argument("--stop-hz", type=float, required=True)
    parser.add_argument("--points", type=int, default=10)
    parser.add_argument("--spacing", choices=("linear", "log"), default="log")
    parser.add_argument("--output-dir", type=Path, default=Path("fft_sweep"))
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--wait-timeout", type=float, default=0.0)
    parser.add_argument("--settle-seconds", type=float, default=0.2)
    parser.add_argument("--sample-rate-hz", type=float)
    parser.add_argument("--bits", type=int, default=9)
    parser.add_argument("--harmonics", type=int, default=5)
    parser.add_argument(
        "--window",
        choices=("rectangular", "hann", "blackmanharris"),
        default="blackmanharris",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="do not wait for Enter before each point; still waits for FPGA BTN1 data",
    )
    parser.add_argument("--no-point-plots", action="store_true")
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.wait_timeout < 0 or args.settle_seconds < 0:
        parser.error("timeouts and settling delay cannot be negative")
    frequencies = frequency_points(args.start_hz, args.stop_hz, args.points, args.spacing)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import serial
    except ImportError:
        print("Install pyserial with: python -m pip install pyserial", file=sys.stderr)
        return 2

    summary_rows: list[dict[str, Any]] = []
    try:
        with serial.Serial(args.port, args.baud, timeout=0.25) as port:
            print(f"Opened {args.port} at {args.baud:,} baud.")
            print(f"Sweep contains {len(frequencies)} point(s).")

            for point, stimulus_hz in enumerate(frequencies, start=1):
                print("")
                print(f"Point {point}/{len(frequencies)}: {stimulus_hz:.12g} Hz")
                if not args.no_prompt:
                    input(
                        "Set both function-generator channels to this frequency, "
                        "wait for stable output, then press Enter..."
                    )
                if args.settle_seconds:
                    time.sleep(args.settle_seconds)
                print("Press BTN1 on the Cmod A7; waiting for the sample block...")
                rows, metadata = receive_capture(
                    port,
                    wait_timeout_seconds=args.wait_timeout,
                    stream_timeout_seconds=args.timeout,
                )

                sample_rate_hz = args.sample_rate_hz or float(
                    metadata["nominal_sample_rate_hz"]
                )
                if stimulus_hz >= sample_rate_hz / 2.0:
                    raise ValueError(
                        f"{stimulus_hz:g} Hz is at/above Nyquist "
                        f"({sample_rate_hz / 2.0:g} Hz)"
                    )

                stem = f"point_{point:03d}_{frequency_tag(float(stimulus_hz))}"
                capture_csv = args.output_dir / f"{stem}.csv"
                metadata.update(
                    {
                        "stimulus_frequency_hz": float(stimulus_hz),
                        "sweep_point": point,
                    }
                )
                write_capture(rows, metadata, capture_csv)
                capture = load_capture(capture_csv)
                metrics, fft_frequency, amplitude_dbfs = analyze_capture(
                    capture,
                    sample_rate_hz=sample_rate_hz,
                    bit_count=args.bits,
                    window_name=args.window,
                    expected_frequency_hz=float(stimulus_hz),
                    harmonic_count=args.harmonics,
                )
                metrics["stimulus_frequency_hz"] = float(stimulus_hz)
                metrics["sample_rate_override_used"] = args.sample_rate_hz is not None

                report_path = args.output_dir / f"{stem}_fft.json"
                spectrum_path = args.output_dir / f"{stem}_spectrum.csv"
                plot_path = args.output_dir / f"{stem}_fft.png"
                save_json(report_path, metrics)
                write_spectrum(spectrum_path, fft_frequency, amplitude_dbfs)
                if not args.no_point_plots:
                    write_plot(fft_frequency, amplitude_dbfs, metrics, plot_path)

                summary = {
                    "point": point,
                    "stimulus_frequency_hz": float(stimulus_hz),
                    "fft_fundamental_frequency_hz": metrics["fundamental_frequency_hz"],
                    "fundamental_amplitude_dbfs": metrics["fundamental_amplitude_dbfs"],
                    "snr_db": metrics["snr_db"],
                    "sinad_db": metrics["sinad_db"],
                    "thd_db": metrics["thd_db"],
                    "sfdr_db": metrics["sfdr_db"],
                    "enob_bits": metrics["enob_bits"],
                    "minimum_code": metrics["minimum_code"],
                    "maximum_code": metrics["maximum_code"],
                    "peak_to_peak_codes": metrics["peak_to_peak_codes"],
                    "unstable_sample_count": metrics["unstable_sample_count"],
                    "capture_csv": capture_csv.name,
                }
                summary_rows.append(summary)
                print(
                    f"Captured: amplitude={summary['fundamental_amplitude_dbfs']:.3f} dBFS, "
                    f"SINAD={summary['sinad_db']:.3f} dB, "
                    f"ENOB={summary['enob_bits']:.3f} bits"
                )
    except TimeoutError as error:
        print(f"Capture timeout: {error}", file=sys.stderr)
        print_no_data_help()
        return 1
    except serial.SerialException as error:
        print(f"Serial-port error: {error}", file=sys.stderr)
        print_no_data_help()
        return 1
    except ValueError as error:
        print(f"Sweep error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSweep cancelled by user.", file=sys.stderr)
        if not summary_rows:
            return 130

    if not summary_rows:
        print("No sweep points were completed.", file=sys.stderr)
        return 1

    summary_csv = args.output_dir / "sweep_summary.csv"
    summary_json = args.output_dir / "sweep_summary.json"
    summary_plot = args.output_dir / "sweep_summary.png"
    write_summary_csv(summary_csv, summary_rows)
    save_json(
        summary_json,
        {
            "schema": "tadc-fft-frequency-sweep-v1",
            "spacing": args.spacing,
            "window": args.window,
            "completed_points": len(summary_rows),
            "points": summary_rows,
        },
    )
    write_summary_plot(summary_plot, summary_rows, args.spacing == "log")
    print("")
    print(f"Completed {len(summary_rows)} sweep point(s).")
    print(f"Saved {summary_csv.resolve()}")
    print(f"Saved {summary_json.resolve()}")
    print(f"Saved {summary_plot.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
