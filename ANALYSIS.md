# PC Capture, FFT, and Frequency-Sweep Guide

This guide is the shortest complete procedure for running the sample-only FPGA
design. The FPGA captures ADC codes; Python performs all frequency-domain
analysis.

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

The exact synthetic tone is FFT bin 107 using the nominal
`1 MHz / 26 = 38,461.5384615 samples/s` rate.

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

- `adc_capture.csv`: sequence, ADC code, and unstable flag;
- `adc_capture.meta.json`: capture size, 1 MHz ADC clock, 26 nominal clocks per
  sample, and nominal sample rate.

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

Because the FPGA no longer measures timing, the FFT frequency axis uses the
nominal sample rate from metadata. If an oscilloscope or frequency counter
provides a better result rate, override it:

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

At every point:

1. The PC prints the requested generator frequency.
2. Set CH1 and CH2 to that same frequency while keeping their required
   differential phase, offset, and amplitude.
3. Press Enter after the generator settles.
4. Press Cmod A7 BTN1.
5. Python receives the block, runs its FFT, and advances to the next point.

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

Keep all requested input frequencies below Nyquist, approximately 19.23 kHz
for the nominal sample rate.

## Interpreting the results

- Falling fundamental amplitude shows frequency-response roll-off.
- Falling SINAD/ENOB shows combined noise and distortion degradation.
- Falling SFDR shows a spur or harmonic becoming stronger.
- `unstable_sample_count > 0` means the parallel ADC bus changed between the
  FPGA's two reads; inspect CKO/data timing and wiring.
- A stationary or clipped code range indicates an analog-input, enable, clock,
  or output-bus problem.

The FFT frequency coordinate is nominal unless `--sample-rate-hz` is supplied.
The programmed generator frequencies in `sweep_summary.csv` remain the primary
x-axis values for the response sweep.
