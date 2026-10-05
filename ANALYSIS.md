# PC Capture, FFT, and Frequency-Sweep Guide

This guide is the shortest complete procedure for running the timestamped FPGA
design. The FPGA captures ADC codes and raw CKO timestamps; Python calculates
sampling speed and performs all frequency-domain analysis.

## 1. Install once

Install 64-bit Python 3.10 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux activation:

```bash
source .venv/bin/activate
```

## 2. Confirm the software without hardware

```powershell
python pc/generate_demo_capture.py
python pc/analyze_fft.py demo_capture.csv --expected-frequency-hz 1004.732572115
```

The commands should create:

- `demo_capture.csv` and `demo_capture.meta.json`;
- `demo_capture_fft.json`;
- `demo_capture_spectrum.csv`;
- `demo_capture_fft.png`.

The exact synthetic tone is FFT bin 107. The synthetic timestamps produce a
measured `10 MHz / 260 = 38,461.5384615 samples/s` rate.

## 3. Prepare the hardware

Follow `WIRING.md`. In particular, select the Tiny Tapeout project and release
the carrier input drivers before connecting FPGA `clk` or `EN`:

```python
from ttboard.mode import RPMode

tt.shuttle.tt_um_tadc_its.enable()
tt.clock_project_stop()
tt.mode = RPMode.ASIC_MANUAL_INPUTS
tt.reset_project(False)
```

Then connect common ground, ADC digital signals, and analog stimulus. Keep
`VIP`, `VIN`, and `VCM` within the ADC's 0–1.8 V analog range.

## 4. Capture one block

List ports if needed:

```powershell
python pc/capture_tadc.py --list-ports
```

Windows example:

```powershell
python pc/capture_tadc.py COM6 -o adc_capture.csv
```

Linux example:

```bash
python pc/capture_tadc.py /dev/ttyUSB1 -o adc_capture.csv
```

After starting the command, press Cmod A7 BTN1. The program waits indefinitely
for BTN1 by default. It creates:

- `adc_capture.csv`: sequence, ADC code, unstable flag, and raw timestamp;
- `adc_capture.meta.json`: timer and ADC clocks, measured sampling speed,
  interval range, and timestamp-jitter statistics calculated by Python.

Python calculates the sampling speed with:

```text
Fs = (sample_count - 1) * timer_clock_hz
     / (last_timestamp - first_timestamp)
```

Using `sample_count - 1` is essential because 4096 captured samples contain
4095 sample-to-sample intervals. The startup delay before the first CKO is not
included.

If LED1 remains on, the FPGA has not received 4096 CKO events. Check the
selected TT project, carrier manual-input mode, 1 MHz `clk`, `EN`, `CKO`, and
common ground. If LED2 turns on but the PC receives nothing, check the FTDI
UART port and 1,000,000 baud.

## 5. Analyze one FFT

Set the function generator to a stable sine wave. For a 1 kHz input:

```powershell
python pc/analyze_fft.py adc_capture.csv --expected-frequency-hz 1000
```

Outputs:

- `adc_capture_fft.json`: amplitude, SNR, SINAD, THD, SFDR, ENOB, and code
  range;
- `adc_capture_spectrum.csv`: one row per FFT bin;
- `adc_capture_fft.png`: spectrum plot.

The default `blackmanharris` window limits leakage when the function generator
and FPGA use independent oscillators. A rectangular window should be used only
when the captured waveform is known to be coherent.

The FFT frequency axis uses the measured CKO result rate from that same
capture. If a calibrated oscilloscope or frequency counter provides a better
rate, override it:

```powershell
python pc/analyze_fft.py adc_capture.csv `
  --sample-rate-hz 38460.9 `
  --expected-frequency-hz 1000
```

## 6. Run the frequency sweep

The generic sweep is manual so it works with any two-channel function
generator. Example: 12 logarithmically spaced points from 100 Hz to 15 kHz:

```powershell
python pc/fft_frequency_sweep.py COM6 `
  --start-hz 100 `
  --stop-hz 15000 `
  --points 12 `
  --spacing log `
  --output-dir sweep_results
```

To sweep around an estimated analog tone or response region, use a center and
a plus/minus span. For example, 5 kHz ±500 Hz:

```powershell
python pc/fft_frequency_sweep.py COM6 `
  --center-hz 5000 `
  --plus-minus-hz 500 `
  --points 11 `
  --spacing linear `
  --output-dir sweep_around_5k
```

This center must be an expected **input tone or response frequency**, not the
ADC sampling speed. Sweeping around `Fs` produces aliases. If alias behavior is
the intended experiment, predict the observed baseband frequency with
`abs(input_frequency - k*Fs)`.

At every point:

1. The PC prints the requested generator frequency.
2. Set CH1 and CH2 to that same frequency while keeping their required
   differential phase, offset, and amplitude.
3. Press Enter after the generator settles.
4. Press Cmod A7 BTN1.
5. Python receives the block, runs its FFT, and advances to the next point.

Python recalculates the sampling speed from the timestamps at every sweep
point, so oscillator drift is reflected in each FFT frequency axis.

Do not change amplitude or DC offset during a frequency-response sweep. Check
the waveforms at the ADC pins because generator output amplitude can vary with
load and frequency.

The output directory contains every raw capture, metadata file, FFT report,
spectrum, and optional point plot. The main results are:

- `sweep_summary.csv`: easy to open in a spreadsheet;
- `sweep_summary.json`: machine-readable results;
- `sweep_summary.png`: amplitude, SINAD, SFDR, and ENOB versus generator
  frequency.

Useful variations:

```powershell
# Linear instead of logarithmic spacing
python pc/fft_frequency_sweep.py COM6 --start-hz 100 --stop-hz 15000 --points 20 --spacing linear

# Use an independently measured sample rate
python pc/fft_frequency_sweep.py COM6 --start-hz 100 --stop-hz 15000 --points 12 --sample-rate-hz 38460.9

# Skip individual FFT PNG files but keep the final summary plot
python pc/fft_frequency_sweep.py COM6 --start-hz 100 --stop-hz 15000 --points 12 --no-point-plots
```

For ordinary ADC characterization, keep all requested input frequencies below
the measured Nyquist rate, approximately 19.23 kHz when `Fs` is 38.46
ksample/s.

## Interpreting the results

- Falling fundamental amplitude shows frequency-response roll-off.
- Falling SINAD/ENOB shows combined noise and distortion degradation.
- Falling SFDR shows a spur or harmonic becoming stronger.
- `timing_stable = false` means one or more CKO intervals differ from the
  dominant interval by more than one 100 ns timer tick. Inspect the interval
  statistics before trusting a conventional uniformly sampled FFT.
- `unstable_sample_count > 0` means the parallel ADC bus changed between the
  FPGA's two reads; inspect CKO/data timing and wiring.
- A stationary or clipped code range indicates an analog-input, enable, clock,
  or output-bus problem.

The timestamp is attached to result-ready `CKO`, not directly to the internal
sample-and-hold aperture. It accurately measures average output cadence when
each CKO represents one conversion and conversion latency is consistent, but
it cannot reveal aperture jitter hidden inside the ADC. Individual intervals
have 100 ns resolution; the 4095-interval average gives much finer rate
resolution. Absolute frequency accuracy remains limited by the Cmod oscillator.

The FFT frequency coordinate uses the per-capture timestamp measurement unless
`--sample-rate-hz` is supplied. The programmed generator frequencies in
`sweep_summary.csv` remain the primary x-axis values for the response sweep.
