#!/usr/bin/env python3
"""Receive and decode one buffered TADC capture from the Cmod A7 UART."""

from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from pathlib import Path


HEADER = struct.Struct("<4sBBHII")
RECORD = struct.Struct("<2sHHIIH")


def read_exact(port, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = port.read(count - len(data))
        if not chunk:
            raise TimeoutError(f"received {len(data)} of {count} expected bytes")
        data.extend(chunk)
    return bytes(data)


def find_header(port) -> bytes:
    window = bytearray()
    while True:
        byte = read_exact(port, 1)
        window.extend(byte)
        if len(window) > 4:
            del window[0]
        if window == b"TADC":
            return b"TADC" + read_exact(port, HEADER.size - 4)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="COM port, for example COM6")
    parser.add_argument("-o", "--output", type=Path, default=Path("tadc_capture.csv"))
    parser.add_argument(
        "--metadata",
        type=Path,
        help="metadata JSON path (default: <output>.meta.json)",
    )
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    try:
        import serial
    except ImportError:
        print("Install pyserial with: python -m pip install pyserial", file=sys.stderr)
        return 2

    with serial.Serial(args.port, args.baud, timeout=args.timeout) as port:
        print("Waiting for TADC stream; press BTN1 on the Cmod A7...")
        header_data = find_header(port)
        magic, version, record_size, count, system_hz, adc_hz = HEADER.unpack(header_data)
        if magic != b"TADC" or version != 1 or record_size != RECORD.size:
            raise ValueError("unsupported or corrupt stream header")

        rows = []
        for expected_sequence in range(count):
            raw = read_exact(port, RECORD.size)
            sync, sequence, code_flags, timestamp, period, adc_edges = RECORD.unpack(raw)
            if sync != b"\xA5\x5A":
                raise ValueError(f"bad record sync at sequence {expected_sequence}")
            if sequence != expected_sequence:
                raise ValueError(f"expected sequence {expected_sequence}, received {sequence}")

            code = code_flags & 0x1FF
            unstable = bool(code_flags & (1 << 9))
            first = bool(code_flags & (1 << 10))
            rows.append(
                {
                    "sequence": sequence,
                    "adc_code": code,
                    "unstable": int(unstable),
                    "first_record": int(first),
                    "timestamp_ticks": timestamp,
                    "timestamp_us": timestamp * 1e6 / system_hz,
                    "period_ticks": period,
                    "period_us": period * 1e6 / system_hz,
                    "adc_clock_edges": adc_edges,
                }
            )

    with args.output.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    metadata_path = args.metadata or args.output.with_suffix(".meta.json")
    metadata = {
        "schema": "tadc-capture-v1",
        "format_version": version,
        "record_size_bytes": record_size,
        "record_count": count,
        "system_clock_hz": system_hz,
        "adc_clock_hz": adc_hz,
        "counter_tick_seconds": 1.0 / system_hz,
        "source_csv": args.output.name,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    periods = [row["period_ticks"] for row in rows[1:]] or [rows[0]["period_ticks"]]
    unstable_count = sum(row["unstable"] for row in rows)
    print(f"Received {count} samples")
    print(f"System clock: {system_hz} Hz; ADC clock: {adc_hz} Hz")
    print(f"Period ticks: min={min(periods)}, max={max(periods)}")
    print(f"Unstable data flags: {unstable_count}")
    print(f"Saved {args.output.resolve()}")
    print(f"Saved {metadata_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
