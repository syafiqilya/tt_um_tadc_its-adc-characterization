#!/usr/bin/env python3
"""Receive one sample-only TADC capture from the Cmod A7 UART."""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path
from typing import Any

from tadc_io import write_capture


HEADER = struct.Struct("<4sBBHII")
RECORD = struct.Struct("<2sH")
PROTOCOL_VERSION = 2


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
                    f"Still waiting for TADC v2 header; {received_count} "
                    "non-header UART bytes observed. Check the bitstream and baud rate."
                )
            else:
                print(
                    "Still waiting; no UART bytes received. Press BTN1 and check "
                    "LED1/LED2, the serial port, and ADC CKO wiring."
                )
            next_status = now + status_interval_seconds


def receive_capture(
    port,
    wait_timeout_seconds: float = 0.0,
    stream_timeout_seconds: float = 10.0,
) -> tuple[list[dict[str, int]], dict[str, Any]]:
    header_data = find_header(port, wait_timeout_seconds, stream_timeout_seconds)
    magic, version, record_size, count, adc_hz, clocks_per_sample = HEADER.unpack(
        header_data
    )
    if magic != b"TADC":
        raise ValueError("corrupt stream header")
    if version != PROTOCOL_VERSION:
        raise ValueError(
            f"FPGA uses TADC protocol v{version}; this software requires v{PROTOCOL_VERSION}. "
            "Rebuild/program the FPGA from the same repository revision."
        )
    if record_size != RECORD.size:
        raise ValueError(
            f"stream record size is {record_size}, expected {RECORD.size} bytes"
        )
    if count == 0 or adc_hz == 0 or clocks_per_sample == 0:
        raise ValueError("header contains an invalid zero-valued field")

    print(f"TADC header received; downloading {count} ADC samples...")
    rows: list[dict[str, int]] = []
    for sequence in range(count):
        raw = read_exact(port, RECORD.size, stream_timeout_seconds)
        sync, code_flags = RECORD.unpack(raw)
        if sync != b"\xA5\x5A":
            raise ValueError(f"bad record sync at sample {sequence}")
        if code_flags & ~0x03FF:
            raise ValueError(f"reserved record bits are nonzero at sample {sequence}")
        rows.append(
            {
                "sequence": sequence,
                "adc_code": code_flags & 0x01FF,
                "unstable": int(bool(code_flags & 0x0200)),
            }
        )

    sample_rate = float(adc_hz) / float(clocks_per_sample)
    metadata: dict[str, Any] = {
        "schema": "tadc-sample-capture-v2",
        "format_version": version,
        "record_size_bytes": record_size,
        "record_count": count,
        "adc_clock_hz": adc_hz,
        "clocks_per_sample": clocks_per_sample,
        "nominal_sample_rate_hz": sample_rate,
        "sample_rate_kind": "nominal_from_adc_clock_division",
    }
    return rows, metadata


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
    print("  LED1 never turns on: check BTN1, bitstream, or FPGA clock.", file=sys.stderr)
    print("  LED1 stays on: the FPGA is waiting for 4096 ADC CKO events.", file=sys.stderr)
    print("  LED2 turns on: capture completed; check port and 1,000,000 baud.", file=sys.stderr)
    print("  Confirm Tiny Tapeout manual-input mode and common ground.", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", help="COM6 or /dev/ttyUSB1")
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("-o", "--output", type=Path, default=Path("tadc_capture.csv"))
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--wait-timeout", type=float, default=0.0)
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
            print("Waiting for TADC samples; press BTN1 on the Cmod A7...")
            rows, metadata = receive_capture(
                port,
                wait_timeout_seconds=args.wait_timeout,
                stream_timeout_seconds=args.timeout,
            )
    except TimeoutError as error:
        print(f"Capture timeout: {error}", file=sys.stderr)
        print_no_data_help()
        return 1
    except serial.SerialException as error:
        print(f"Serial-port error: {error}", file=sys.stderr)
        print_no_data_help()
        return 1
    except (ValueError, struct.error) as error:
        print(f"Capture format error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCapture cancelled by user.", file=sys.stderr)
        return 130

    metadata_path = write_capture(rows, metadata, args.output, args.metadata)
    unstable_count = sum(row["unstable"] for row in rows)
    print(f"Received {len(rows)} ADC samples")
    print(f"ADC clock: {metadata['adc_clock_hz']:,} Hz")
    print(f"Nominal sample rate: {metadata['nominal_sample_rate_hz']:.9f} samples/s")
    print(f"Unstable sample flags: {unstable_count}")
    print(f"Saved {args.output.resolve()}")
    print(f"Saved {metadata_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
