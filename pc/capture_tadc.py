#!/usr/bin/env python3
"""Receive and decode one buffered TADC capture from the Cmod A7 UART."""

from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
import time
from pathlib import Path


HEADER = struct.Struct("<4sBBHII")
RECORD = struct.Struct("<2sHHIIH")


def read_exact(port, count: int, timeout_seconds: float) -> bytes:
    deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
    data = bytearray()
    while len(data) < count:
        chunk = port.read(count - len(data))
        if chunk:
            data.extend(chunk)
        elif deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError(
                f"stream stopped after {len(data)} of {count} expected bytes"
            )
    return bytes(data)


def find_header(
    port,
    wait_timeout_seconds: float,
    stream_timeout_seconds: float,
    status_interval_seconds: float = 5.0,
) -> bytes:
    deadline = (
        time.monotonic() + wait_timeout_seconds
        if wait_timeout_seconds > 0
        else None
    )
    next_status = time.monotonic() + status_interval_seconds
    window = bytearray()
    received_count = 0
    while True:
        byte = port.read(1)
        now = time.monotonic()
        if byte:
            received_count += 1
            window.extend(byte)
            if len(window) > 4:
                del window[0]
            if window == b"TADC":
                return b"TADC" + read_exact(
                    port,
                    HEADER.size - 4,
                    stream_timeout_seconds,
                )
        elif deadline is not None and now >= deadline:
            raise TimeoutError(
                f"no TADC header after {wait_timeout_seconds:g} seconds "
                f"({received_count} UART bytes observed)"
            )

        if now >= next_status:
            if received_count:
                print(
                    f"Still waiting for TADC header; {received_count} non-header "
                    "UART bytes observed. Check baud rate and selected port."
                )
            else:
                print(
                    "Still waiting; no UART bytes received. Press BTN1 and check "
                    "LED1/LED2, the selected serial port, and ADC CKO wiring."
                )
            next_status = now + status_interval_seconds


def print_serial_ports() -> int:
    try:
        from serial.tools import list_ports
    except ImportError:
        print("Install pyserial with: python -m pip install pyserial", file=sys.stderr)
        return 2

    ports = sorted(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return 1
    for port in ports:
        print(f"{port.device}\t{port.description}\t{port.hwid}")
    return 0


def print_no_data_help() -> None:
    print("", file=sys.stderr)
    print("Hardware checks:", file=sys.stderr)
    print("  LED1 never turns on: BTN1/start, bitstream, or FPGA clock problem.", file=sys.stderr)
    print("  LED1 stays on: capture is waiting for ADC CKO events.", file=sys.stderr)
    print("  LED2 turns on: capture completed; check serial port and 1,000,000 baud.", file=sys.stderr)
    print("  Linux: run --list-ports or inspect /dev/serial/by-id/.", file=sys.stderr)
    print("  Ensure the user has permission for the serial device (often dialout).", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", help="COM6 or /dev/ttyUSB1")
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="list detected serial ports and exit",
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("tadc_capture.csv"))
    parser.add_argument(
        "--metadata",
        type=Path,
        help="metadata JSON path (default: <output>.meta.json)",
    )
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="maximum stalled-stream time after the header (default: 10 s)",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=0.0,
        help="maximum time waiting for TADC header; 0 waits forever (default: 0)",
    )
    args = parser.parse_args()

    if args.list_ports:
        return print_serial_ports()
    if not args.port:
        parser.error("port is required unless --list-ports is used")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.wait_timeout < 0:
        parser.error("--wait-timeout cannot be negative")

    try:
        import serial
    except ImportError:
        print("Install pyserial with: python -m pip install pyserial", file=sys.stderr)
        return 2

    try:
        with serial.Serial(args.port, args.baud, timeout=0.25) as port:
            print(f"Opened {args.port} at {args.baud:,} baud.")
            print("Waiting for TADC stream; press BTN1 on the Cmod A7...")
            header_data = find_header(port, args.wait_timeout, args.timeout)
            magic, version, record_size, count, system_hz, adc_hz = HEADER.unpack(header_data)
            if magic != b"TADC" or version != 1 or record_size != RECORD.size:
                raise ValueError("unsupported or corrupt stream header")

            print(f"TADC header received; downloading {count} records...")
            rows = []
            for expected_sequence in range(count):
                raw = read_exact(port, RECORD.size, args.timeout)
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
    except TimeoutError as error:
        print(f"Capture timeout: {error}", file=sys.stderr)
        print_no_data_help()
        return 1
    except serial.SerialException as error:
        print(f"Serial-port error: {error}", file=sys.stderr)
        print_no_data_help()
        return 1
    except KeyboardInterrupt:
        print("\nCapture cancelled by user.", file=sys.stderr)
        return 130

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
