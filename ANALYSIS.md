# TADC Timing and FFT Characterization

This guide takes a new PC from installation through timing validation,
coherent-tone selection, and FFT-based ADC measurements. The commands are
written for PowerShell and should also work in a normal terminal after replacing
the Windows virtual-environment activation command.

## 1. Install Python and dependencies

Install 64-bit Python 3.10 or newer. From the project root, run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

No Vivado installation is needed on the measurement PC. Vivado is required only
on the PC used to build and program the FPGA.

## 2. Verify the software without hardware

Run this complete synthetic-data test:

```powershell
python pc/generate_demo_capture.py
python pc/analyze_timing.py demo_capture.csv
python pc/plan_coherent_tone.py demo_capture_timing.json --target-hz 1000
python pc/analyze_fft.py demo_capture.csv --timing demo_capture_timing.json --tone demo_capture_tone.json
```

Expected results include:

- timing classification `stable`;
- sample rate close to `38461.538 Hz`;
- coherent FFT bin `107` near 1 kHz;
- creation of JSON reports, CSV spectrum data, and PNG plots.

## 3. Capture real hardware data

Connect the complete bench as described in `WIRING.md`, then program the FPGA.
Find the Cmod A7 UART port in Windows Device Manager, then run:

```powershell
python pc/capture_tadc.py COM6 -o timing_capture.csv
```

Press Cmod A7 BTN1 when requested. Replace `COM6` with the real port.

On Linux, list the detected ports before capture:

```bash
python pc/capture_tadc.py --list-ports
ls -l /dev/serial/by-id/
python pc/capture_tadc.py /dev/ttyUSB1 -o timing_capture.csv
```

Prefer the stable `/dev/serial/by-id/...` name when available. The Cmod's FTDI
device provides independent JTAG and UART functions, so do not assume that the
lowest `/dev/ttyUSB*` number is the UART interface.

The receiver creates two files:

- `timing_capture.csv`: one row per ADC result;
- `timing_capture.meta.json`: the FPGA clocks and capture format.

Keep these two files together.

The receiver waits indefinitely for the `TADC` header by default, allowing time
to press BTN1 and inspect the hardware. To impose a 30-second limit, add
`--wait-timeout 30`. The separate `--timeout` option controls how long an
already-started UART stream may stall.

### If no UART bytes arrive

Use the Cmod LEDs to locate the stage that stopped:

- LED1 never turns on after BTN1: check the programmed bitstream, BTN1, reset,
  and the correct 12 MHz/100 MHz board constraint selection.
- LED1 remains on: the FPGA has started, but has not collected 4096 `CKO`
  events. Check Tiny Tapeout project selection, its disabled onboard clock,
  FPGA `clk`/`EN`, `CKO`, common ground, and signal directions.
- LED2 turns on: acquisition completed and UART transmission started. If the PC
  sees no bytes, select the other Cmod FTDI serial interface, confirm
  1,000,000 baud, and check Linux serial-device permission.

For a temporary Fedora permission test, inspect the device ownership with
`ls -l /dev/ttyUSB1`. Use the distribution's normal serial-access group or a
udev rule for the permanent fix; do not run the capture program as root.

## 4. Analyze conversion timing

```powershell
python pc/analyze_timing.py timing_capture.csv
```

Outputs:

- `timing_capture_timing.json`: machine-readable timing report;
- `timing_capture_timing.png`: conversion-period and ADC-clock plots.

The first record is excluded from interval statistics because it measures from
`EN` assertion to the first `CKO`. The remaining records measure successive
`CKO` events. The default stable-timing tolerance is one 10 MHz counter tick,
or 100 ns. It can be changed with `--tolerance-ticks`.

A nonzero process exit code means the capture did not meet the stability test.
Inspect unstable-data flags, period outliers, and ADC-clock-edge counts before
using that capture for an FFT.

## 5. Calculate the coherent generator frequency

Choose the approximate desired input frequency. For example, to find the best
coherent tone near 1 kHz:

```powershell
python pc/plan_coherent_tone.py timing_capture_timing.json --target-hz 1000
```

The terminal prints the exact frequency to enter into the function generator.
The same value is saved in `timing_capture_tone.json` as
`programmed_frequency_hz`.

By default, the calculator refuses a timing report classified as unstable.
Correct the clock or interface problem first. `--allow-unstable-timing` exists
only for calculating a nominal frequency that will later use a windowed FFT.

If the generator has limited frequency resolution, include it. For a 0.001 Hz
setting step:

```powershell
python pc/plan_coherent_tone.py timing_capture_timing.json --target-hz 1000 --generator-resolution-hz 0.001
```

Mathematical coherence requires an integer number of input cycles in the FFT:

```text
input_frequency = selected_bin * sample_rate / sample_count
```

The tool also requires the selected FFT bin to be coprime with the record count
and avoids collisions through the requested harmonic order.

### Important clock requirement

The calculator makes the nominal frequencies coherent, but two independent
oscillators still drift. For a repeatable rectangular-window FFT, lock the
function generator and FPGA/ADC timing to the same reference. The current FPGA
build does not expose its internal 10 MHz clock; adding that output requires an
RTL and XDC revision. See `WIRING.md` before making any reference connection.

If there is no shared reference, use the automatic Blackman-Harris window and
treat the measurement as noncoherent.

## 6. Acquire FFT data

Set the function generator to the reported `programmed_frequency_hz`. Use a
clean sine wave that remains inside the ADC input range and common-mode limits.
Do not overdrive the Tiny Tapeout analog input.

Capture a new record:

```powershell
python pc/capture_tadc.py COM6 -o sine_capture.csv
python pc/analyze_timing.py sine_capture.csv
```

Use the new timing report when checking the final FFT:

```powershell
python pc/analyze_fft.py sine_capture.csv --timing sine_capture_timing.json --tone timing_capture_tone.json
```

Outputs:

- `sine_capture_fft.json`: FFT settings and performance measurements;
- `sine_capture_spectrum.csv`: frequency and amplitude for every FFT bin;
- `sine_capture_fft.png`: spectrum plot.

The JSON report includes fundamental amplitude, SNR, SINAD, THD, SFDR, ENOB,
DC code, code range, and harmonic-bin locations.

## Window selection

The FFT tool's default `--window auto` behavior is:

- rectangular when timing is stable and a coherent tone plan is supplied;
- four-term Blackman-Harris otherwise.

The coherence decision is recalculated using the sample rate in the final sine
capture. This catches drift between the initial timing measurement and the FFT
measurement.

Override it when necessary:

```powershell
python pc/analyze_fft.py sine_capture.csv --timing sine_capture_timing.json --window hann
```

Available windows are `rectangular`, `hann`, and `blackmanharris`.

## Interpreting failures

- `unstable_data_count > 0`: the parallel ADC bus changed between the FPGA's
  two reads. Check wiring and `CKO`-to-data settling time.
- Period outliers: check the ADC clock, `EN`, `CKO`, grounding, and FPGA input.
- ADC-edge outliers: conversions are taking different numbers of ADC clocks.
- Large FFT leakage with a rectangular window: the generator is not actually
  coherent or the sampling aperture is moving.
- Poor low-bit behavior: independently verify Tiny Tapeout `uio[1:0]`, because
  the ADC project may not enable those two output pads.

The FPGA timestamps `CKO`, which indicates externally visible result timing. It
does not expose each internal SAR comparison. A stable fixed delay between the
actual sampling aperture and `CKO` changes phase but not FFT magnitude; variable
delay appears as sampling jitter and degrades high-frequency SNR.
