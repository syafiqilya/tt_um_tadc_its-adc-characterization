# Tiny Tapeout TADC — Cmod A7 Sample Capture and FFT Sweep

This project uses a Cmod A7 FPGA to control and capture the
`tt_um_tadc_its` ADC. The FPGA collects 4096 ordered nine-bit ADC codes and
sends them to a PC over the Cmod USB-UART interface. All FFT calculations and
frequency-sweep reporting run in Python on the PC.

The FPGA does **not** calculate conversion time, periods, timestamps, jitter,
or FFT values.

## Architecture

```text
Cmod oscillator -> MMCM -> 10 MHz internal FPGA logic clock
                              |
                              +-> divide by 10 -> 1 MHz -> TT project clk

Tiny Tapeout CKO + DATA[8:0]
            -> FPGA synchronizer and sample RAM
            -> UART protocol v2
            -> PC CSV
            -> Python FFT / frequency sweep
```

The 10 MHz clock remains necessary for FPGA logic, CKO synchronization, and
the 1 Mbaud UART. Only the divided 1 MHz clock is sent to the ADC.

## Important ADC integration notes

1. The project is described as a 10-bit ADC, but the submitted interface
   exposes `DATA[8:0]`; this controller therefore captures nine bits.
2. `DATA[1:0]` use Tiny Tapeout `uio[1:0]`. If these bits do not move on real
   silicon, check the pad output-enable state with an oscilloscope or logic
   analyzer.
3. The PC uses the nominal model of 26 ADC clocks per result, giving
   `1,000,000 / 26 = 38,461.5384615` samples/s. Because the FPGA no longer
   measures result timing, use `--sample-rate-hz` if an independently measured
   sample rate is available.

## FPGA clocking

- Cmod A7 Rev. B oscillator: 12 MHz.
- Optional Rev. C constraint: 100 MHz; use only after checking the board.
- FPGA internal logic clock: 10 MHz from the Xilinx MMCM.
- Tiny Tapeout ADC clock: 1 MHz on Cmod PIO3.
- UART: 1,000,000 baud, 8-N-1.

## Wiring and Tiny Tapeout carrier setup

Follow [WIRING.md](WIRING.md) before powering the bench. It includes the full
pin table, analog connections, voltage limits, grounding, and the required
Tiny Tapeout `ASIC_MANUAL_INPUTS` commands.

The carrier RP2040/RP2350 selects `tt_um_tadc_its`; the FPGA does not drive the
Tiny Tapeout project-selection management signals.

## FPGA operation

1. Select `tt_um_tadc_its`, stop the carrier clock, and place the carrier in
   `ASIC_MANUAL_INPUTS` as documented in `WIRING.md`.
2. Connect common ground first, then the FPGA/ADC signals.
3. Program the Cmod A7.
4. Start the PC receiver.
5. Press Cmod A7 BTN1.
6. LED1 stays on while the FPGA waits for and captures 4096 CKO results.
7. The FPGA stops ADC `clk`, lowers `EN`, and LED2 turns on while UART data is
   sent.
8. LED2 remains on when finished. Press BTN1 for another capture. BTN0 resets
   the FPGA controller.

For each synchronized CKO rising edge, the FPGA waits three internal 10 MHz
ticks, reads the nine-bit bus twice, and stores the second value. A flag is
stored if the two reads disagree. This is a data-validity check, not a timing
measurement.

## UART protocol version 2

All multibyte fields are little-endian.

The 16-byte header is:

| Offset | Size | Description |
|---:|---:|---|
| 0 | 4 | ASCII `TADC` |
| 4 | 1 | Protocol version: `2` |
| 5 | 1 | Record size: `4` bytes |
| 6 | 2 | Sample count |
| 8 | 4 | ADC clock frequency in Hz |
| 12 | 4 | Nominal ADC clocks per sample |

Each four-byte sample record is:

| Offset | Size | Description |
|---:|---:|---|
| 0 | 2 | Sync bytes `A5 5A` |
| 2 | 2 | Bits 8:0 ADC code; bit 9 unstable-data flag |

Sample sequence is implicit from record order. The version-2 bitstream and
version-2 Python software must be used together.

## Create the Vivado project

Vivado is needed only on the FPGA workstation. For the standard Rev. B Cmod
A7-35T:

```powershell
vivado -mode batch -source scripts/create_vivado_project.tcl -tclargs rev_b 35t
```

Build the bitstream immediately:

```powershell
vivado -mode batch -source scripts/create_vivado_project.tcl -tclargs rev_b 35t build
```

Use `15t` for a Cmod A7-15T. Use `rev_c` only for a board confirmed to have the
100 MHz oscillator.

## Install the PC software

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Linux, activate with `source .venv/bin/activate`.

## Capture one ADC block

```powershell
python pc/capture_tadc.py COM6 -o adc_capture.csv
```

On Linux:

```bash
python pc/capture_tadc.py --list-ports
python pc/capture_tadc.py /dev/ttyUSB1 -o adc_capture.csv
```

The receiver writes `adc_capture.csv` and `adc_capture.meta.json`.

## Analyze one FFT

```powershell
python pc/analyze_fft.py adc_capture.csv --expected-frequency-hz 1000
```

This creates an FFT JSON report, spectrum CSV, and PNG plot. The default
Blackman-Harris window is appropriate when the generator and FPGA do not share
a frequency reference.

## Run an FFT frequency sweep

The sweep program is generator-independent and uses a manual setting prompt at
each point:

```powershell
python pc/fft_frequency_sweep.py COM6 `
  --start-hz 100 `
  --stop-hz 15000 `
  --points 12 `
  --spacing log `
  --output-dir sweep_results
```

For each point, set both differential generator channels to the displayed
frequency, press Enter, and then press FPGA BTN1. The program saves every raw
capture and FFT, plus:

- `sweep_summary.csv`;
- `sweep_summary.json`;
- `sweep_summary.png` containing amplitude, SINAD, SFDR, and ENOB versus input
  frequency.

See [ANALYSIS.md](ANALYSIS.md) for the complete friend-ready procedure.

## Test without hardware

```powershell
python pc/generate_demo_capture.py
python pc/analyze_fft.py demo_capture.csv --expected-frequency-hz 1004.732572115
```

## RTL simulation

With Icarus Verilog installed:

```powershell
iverilog -g2012 -o build/tb.vvp rtl/*.v sim/tb_tadc_cmod_a7_top.v
vvp build/tb.vvp
```

Expected output:

```text
PASS: captured and transmitted 8 ADC records
```

Vivado was intentionally not installed on the development PC.
