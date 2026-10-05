#!/usr/bin/env python3
"""Calculate a TADC FFT and common ADC dynamic-performance metrics."""

from __future__ import annotations

import argparse
import csv
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np

from tadc_io import default_output, load_capture, save_json


def blackman_harris(sample_count: int) -> np.ndarray:
    if sample_count == 1:
        return np.ones(1)
    phase = 2.0 * np.pi * np.arange(sample_count) / (sample_count - 1)
    return (
        0.35875
        - 0.48829 * np.cos(phase)
        + 0.14128 * np.cos(2.0 * phase)
        - 0.01168 * np.cos(3.0 * phase)
    )


def make_window(name: str, sample_count: int) -> tuple[np.ndarray, int]:
    if name == "rectangular":
        return np.ones(sample_count), 0
    if name == "hann":
        return np.hanning(sample_count), 2
    if name == "blackmanharris":
        return blackman_harris(sample_count), 4
    raise ValueError(f"unsupported window: {name}")


def alias_bin(bin_number: int, sample_count: int) -> int:
    folded = bin_number % sample_count
    return sample_count - folded if folded > sample_count // 2 else folded


def neighborhood(center: int, radius: int, maximum: int) -> set[int]:
    return set(range(max(0, center - radius), min(maximum, center + radius) + 1))


def db10(ratio: float) -> float:
    return 10.0 * math.log10(max(ratio, np.finfo(float).tiny))


def calculate_metrics(
    codes: np.ndarray,
    sample_rate_hz: float,
    bit_count: int,
    window_name: str,
    expected_bin: int | None,
    harmonic_count: int,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    sample_count = codes.size
    if sample_count < 8:
        raise ValueError("at least eight ADC samples are required")
    if sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive")

    window, integration_radius = make_window(window_name, sample_count)
    centered = codes.astype(float) - float(np.mean(codes))
    spectrum = np.fft.rfft(centered * window)
    bin_power = np.abs(spectrum) ** 2
    frequencies = np.fft.rfftfreq(sample_count, 1.0 / sample_rate_hz)

    one_sided_amplitude = 2.0 * np.abs(spectrum) / np.sum(window)
    one_sided_amplitude[0] *= 0.5
    if sample_count % 2 == 0:
        one_sided_amplitude[-1] *= 0.5
    full_scale_peak = (2**bit_count - 1) / 2.0
    amplitude_dbfs = 20.0 * np.log10(
        np.maximum(one_sided_amplitude / full_scale_peak, np.finfo(float).tiny)
    )

    if expected_bin is None:
        fundamental_bin = int(np.argmax(bin_power[1:]) + 1)
    else:
        if not 1 <= expected_bin < bin_power.size:
            raise ValueError("expected tone is outside the usable FFT range")
        search_radius = max(1, integration_radius)
        low = max(1, expected_bin - search_radius)
        high = min(bin_power.size - 1, expected_bin + search_radius)
        fundamental_bin = int(np.argmax(bin_power[low : high + 1]) + low)

    maximum_bin = bin_power.size - 1
    fundamental_bins = neighborhood(fundamental_bin, integration_radius, maximum_bin)
    fundamental_bins.discard(0)
    fundamental_power = float(sum(bin_power[index] for index in fundamental_bins))

    harmonic_bins_by_order: dict[str, int] = {}
    harmonic_bins: set[int] = set()
    for order in range(2, harmonic_count + 1):
        center = alias_bin(order * fundamental_bin, sample_count)
        harmonic_bins_by_order[str(order)] = center
        if center != 0:
            harmonic_bins.update(neighborhood(center, integration_radius, maximum_bin))
    harmonic_bins -= fundamental_bins
    harmonic_bins.discard(0)

    considered = set(range(1, maximum_bin + 1))
    noise_bins = considered - fundamental_bins - harmonic_bins
    distortion_power = float(sum(bin_power[index] for index in harmonic_bins))
    noise_power = float(sum(bin_power[index] for index in noise_bins))
    noise_and_distortion = noise_power + distortion_power

    spur_candidates = considered - fundamental_bins
    largest_spur_bin = (
        max(spur_candidates, key=lambda index: bin_power[index])
        if spur_candidates
        else 0
    )
    largest_spur_power = float(bin_power[largest_spur_bin]) if largest_spur_bin else 0.0

    sinad_db = db10(fundamental_power / noise_and_distortion)
    metrics: dict[str, Any] = {
        "schema": "tadc-fft-report-v2",
        "sample_count": int(sample_count),
        "sample_rate_hz": sample_rate_hz,
        "sample_rate_kind": "nominal_unless_overridden",
        "nyquist_hz": sample_rate_hz / 2.0,
        "bin_width_hz": sample_rate_hz / sample_count,
        "adc_bits": bit_count,
        "window": window_name,
        "window_coherent_gain": float(np.mean(window)),
        "fundamental_bin": fundamental_bin,
        "fundamental_frequency_hz": float(frequencies[fundamental_bin]),
        "fundamental_amplitude_dbfs": float(amplitude_dbfs[fundamental_bin]),
        "harmonic_bins": harmonic_bins_by_order,
        "snr_db": db10(fundamental_power / noise_power),
        "sinad_db": sinad_db,
        "thd_db": db10(distortion_power / fundamental_power),
        "sfdr_db": db10(fundamental_power / largest_spur_power),
        "enob_bits": (sinad_db - 1.76) / 6.02,
        "largest_spur_bin": largest_spur_bin,
        "largest_spur_frequency_hz": float(frequencies[largest_spur_bin]),
        "dc_code": float(np.mean(codes)),
        "minimum_code": int(np.min(codes)),
        "maximum_code": int(np.max(codes)),
        "peak_to_peak_codes": int(np.max(codes) - np.min(codes)),
    }
    return metrics, frequencies, amplitude_dbfs


def write_plot(
    frequencies: np.ndarray,
    amplitude_dbfs: np.ndarray,
    metrics: dict[str, Any],
    path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(11, 6), constrained_layout=True)
    axis.plot(frequencies, amplitude_dbfs, linewidth=0.8)
    axis.set(
        title=(
            f"TADC FFT | {metrics['window']} window | "
            f"SINAD={metrics['sinad_db']:.2f} dB | ENOB={metrics['enob_bits']:.2f} bits"
        ),
        xlabel="Frequency (Hz, nominal sample-rate scale)",
        ylabel="Amplitude (dBFS)",
        xlim=(0, metrics["nyquist_hz"]),
        ylim=(-140, 5),
    )
    axis.grid(True, alpha=0.3)
    axis.axvline(metrics["fundamental_frequency_hz"], color="tab:red", linestyle="--")
    figure.savefig(path, dpi=160)
    plt.close(figure)


def write_spectrum(
    path: Path,
    frequencies: np.ndarray,
    amplitude_dbfs: np.ndarray,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["frequency_hz", "amplitude_dbfs"])
        writer.writerows(zip(frequencies, amplitude_dbfs, strict=True))


def analyze_capture(
    capture: dict[str, Any],
    sample_rate_hz: float,
    bit_count: int = 9,
    window_name: str = "blackmanharris",
    expected_frequency_hz: float | None = None,
    harmonic_count: int = 5,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    sequence = capture["sequence"]
    if not np.array_equal(sequence, np.arange(sequence.size)):
        raise ValueError("sequence numbers are not contiguous; FFT ordering is invalid")
    if np.any(capture["unstable"]):
        warnings.warn("capture contains unstable sample flags")

    expected_bin: int | None = None
    if expected_frequency_hz is not None:
        if not 0 < expected_frequency_hz < sample_rate_hz / 2.0:
            raise ValueError("expected frequency must be between DC and Nyquist")
        expected_bin = int(round(expected_frequency_hz * sequence.size / sample_rate_hz))

    metrics, frequencies, amplitude_dbfs = calculate_metrics(
        capture["adc_code"],
        sample_rate_hz,
        bit_count,
        window_name,
        expected_bin,
        harmonic_count,
    )
    metrics.update(
        {
            "source_csv": str(capture["path"]),
            "expected_frequency_hz": expected_frequency_hz,
            "unstable_sample_count": int(np.count_nonzero(capture["unstable"])),
        }
    )
    return metrics, frequencies, amplitude_dbfs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument(
        "--sample-rate-hz",
        type=float,
        help="override nominal sample rate stored beside the capture",
    )
    parser.add_argument("--expected-frequency-hz", type=float)
    parser.add_argument("--bits", type=int, default=9)
    parser.add_argument("--harmonics", type=int, default=5)
    parser.add_argument(
        "--window",
        choices=("rectangular", "hann", "blackmanharris"),
        default="blackmanharris",
    )
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--plot", type=Path)
    parser.add_argument("--spectrum-csv", type=Path)
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    capture = load_capture(args.capture, args.metadata)
    sample_rate_hz = args.sample_rate_hz or capture["sample_rate_hz"]
    if not sample_rate_hz:
        raise ValueError(
            "sample rate is unavailable; keep the .meta.json file beside the CSV "
            "or provide --sample-rate-hz"
        )

    metrics, frequencies, amplitude_dbfs = analyze_capture(
        capture,
        sample_rate_hz=float(sample_rate_hz),
        bit_count=args.bits,
        window_name=args.window,
        expected_frequency_hz=args.expected_frequency_hz,
        harmonic_count=args.harmonics,
    )

    output = args.output or default_output(args.capture, "_fft.json")
    plot = args.plot or default_output(args.capture, "_fft.png")
    spectrum_csv = args.spectrum_csv or default_output(args.capture, "_spectrum.csv")
    save_json(output, metrics)
    write_spectrum(spectrum_csv, frequencies, amplitude_dbfs)
    if not args.no_plot:
        write_plot(frequencies, amplitude_dbfs, metrics, plot)

    print(f"Sample rate used: {metrics['sample_rate_hz']:.9f} samples/s")
    print(f"Window: {metrics['window']}")
    print(
        f"Fundamental: bin {metrics['fundamental_bin']}, "
        f"{metrics['fundamental_frequency_hz']:.9f} Hz, "
        f"{metrics['fundamental_amplitude_dbfs']:.3f} dBFS"
    )
    print(f"SNR:   {metrics['snr_db']:.3f} dB")
    print(f"SINAD: {metrics['sinad_db']:.3f} dB")
    print(f"THD:   {metrics['thd_db']:.3f} dB")
    print(f"SFDR:  {metrics['sfdr_db']:.3f} dB")
    print(f"ENOB:  {metrics['enob_bits']:.3f} bits")
    print(f"Saved {output.resolve()}")
    print(f"Saved {spectrum_csv.resolve()}")
    if not args.no_plot:
        print(f"Saved {plot.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
