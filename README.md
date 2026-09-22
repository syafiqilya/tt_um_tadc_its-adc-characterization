# Tiny Tapeout Time-Domain ADC — Cmod A7 Controller

This Vivado-ready Verilog design controls `tt_um_tadc_its`, measures each
externally visible conversion interval, buffers 4096 records, and sends the
capture to a PC through the Cmod A7 USB-UART bridge.

## Important ADC integration risks

The ADC repository has three inconsistencies that cannot be corrected in the
FPGA design:

1. The documentation says 10-bit, but the actual interface and SAR/CDAC logic
   expose only `DATA[8:0]`, so this controller captures nine bits.
2. `DATA[1:0]` use Tiny Tapeout `uio[1:0]`. The submitted analog schematic
   connects `uio_out[1:0]`, but does not visibly drive `uio_oe[1:0]` high.
   If those output-enable nets are floating in silicon, the two least
   significant bits may not be driven at the pads. Check them with an
   oscilloscope or logic analyzer during initial bring-up and ask the ADC
   designer to confirm the integrated `uio_oe` state.
3. The project declares a 1 MHz clock, while its 5.2 us conversion claim
   corresponds to 26 clocks at 5 MHz. Start at 1 MHz as implemented here and
   use the captured `adc_clock_edges` and `period_ticks` fields to determine
   the real silicon behavior.

## Implemented clocking

- Cmod A7 input oscillator: 12 MHz by default (Rev. B).
- Xilinx MMCM output/system clock: 10 MHz.
- ADC clock: registered 1 MHz square wave derived from the 10 MHz domain.
- Counter resolution: 100 ns.
- UART: 1,000,000 baud, 8-N-1.

The FPGA has only one internal logic clock domain. The 1 MHz ADC clock is an
external output, not a fabric clock.

Two clock constraints and MMCM configurations are supplied:

- `cmod_a7_rev_b_12mhz.xdc`: default official Rev. B 12 MHz oscillator.
- `cmod_a7_rev_c_100mhz.xdc`: use only after confirming a 100 MHz oscillator
  is actually fitted to the board.

## Wiring

Connect all grounds before connecting signals. Stop the Tiny Tapeout
demoboard's own project clock and ensure its RP2040 is not driving the same
input lines as the FPGA.

| Cmod A7 connection | FPGA package pin | Tiny Tapeout signal | ADC function |
|---|---:|---|---|
| JA1 | G17 | `uo_out[0]` | `CKO` |
| JA2 | G19 | `uo_out[1]` | `DATA[8]` |
| JA3 | N18 | `uo_out[2]` | `DATA[7]` |
| JA4 | L18 | `uo_out[3]` | `DATA[6]` |
| JA7 | H17 | `uo_out[4]` | `DATA[5]` |
| JA8 | H19 | `uo_out[5]` | `DATA[4]` |
| JA9 | J19 | `uo_out[6]` | `DATA[3]` |
| JA10 | K18 | `uo_out[7]` | `DATA[2]` |
| PIO1 | M3 | `uio[0]` | `DATA[1]` |
| PIO2 | L3 | `uio[1]` | `DATA[0]` |
| PIO3 | A16 | project `clk` | 1 MHz ADC clock |
| PIO4 | K3 | `ui_in[0]` | `EN` |

The Tiny Tapeout demoboard digital interface and Cmod A7 GPIO are both 3.3 V.
This does not apply to the ADC analog pins: `VIP`, `VIN`, and `VCM` must stay
inside the ADC's approximately 0–1.8 V analog range.

## Operation

1. Select `tt_um_tadc_its` on the Tiny Tapeout demoboard.
2. Stop the demoboard's automatic project clock.
3. Connect the FPGA and ADC digital signals and common ground.
4. Program the Cmod A7.
5. Open the PC receiver at 1,000,000 baud.
6. Press Cmod A7 BTN1.
7. LED1 remains on while 4096 records are acquired.
8. The ADC is disabled and LED2 turns on while the block is transmitted.
9. LED2 remains on after completion. Press BTN1 to acquire another block.
10. BTN0 resets the controller.

The first record measures time from FPGA `EN` assertion to the first
synchronized `CKO`. Later records measure time between successive `CKO`
events. CKO passes through a two-flip-flop synchronizer, so absolute timing
contains a fixed synchronization delay and approximately ±1 system-clock
quantization.

## Captured fields

Each RAM entry contains:

- 32-bit free-running CKO timestamp;
- 32-bit period since the previous CKO (100 ns ticks);
- 16-bit count of 1 MHz ADC rising edges since the previous CKO;
- nine-bit ADC code;
- an unstable-data flag;
- a first-record flag.

After synchronized CKO assertion, the controller waits three 10 MHz cycles,
samples the parallel data twice on consecutive cycles, and flags the record if
the two words differ.

## UART format

All multibyte integers are little-endian.

The 16-byte stream header is:

| Offset | Size | Description |
|---:|---:|---|
| 0 | 4 | ASCII `TADC` |
| 4 | 1 | Format version, currently 1 |
| 5 | 1 | Record size, 16 bytes |
| 6 | 2 | Record count |
| 8 | 4 | FPGA system-clock frequency |
| 12 | 4 | ADC clock frequency |

Every 16-byte record is:

| Offset | Size | Description |
|---:|---:|---|
| 0 | 2 | Sync bytes `A5 5A` |
| 2 | 2 | Sequence number |
| 4 | 2 | Code/flags: bits 8:0 code, bit 9 unstable, bit 10 first |
| 6 | 4 | Timestamp ticks |
| 10 | 4 | Period ticks |
| 14 | 2 | ADC rising-edge count |

## Create the Vivado project

For the standard Rev. B 12 MHz Cmod A7-35T:

```powershell
vivado -mode batch -source scripts/create_vivado_project.tcl -tclargs rev_b 35t
```

To create the project and immediately build the bitstream:

```powershell
vivado -mode batch -source scripts/create_vivado_project.tcl -tclargs rev_b 35t build
```

For a confirmed 100 MHz board:

```powershell
vivado -mode batch -source scripts/create_vivado_project.tcl -tclargs rev_c 35t
```

Use `15t` instead of `35t` as the second argument for a Cmod A7-15T.

## PC capture

Install the only PC dependency:

```powershell
python -m pip install -r requirements.txt
```

Then receive one capture:

```powershell
python pc/capture_tadc.py COM6 -o tadc_capture.csv
```

Replace `COM6` with the Cmod A7 FTDI UART port shown by Windows.

## Simulation

The supplied testbench bypasses the Xilinx MMCM and drives the design with a
10 MHz simulation clock. It models one ADC result every 26 rising edges and
checks the complete UART stream.

With Icarus Verilog installed:

```powershell
iverilog -g2012 -o build/tb.vvp rtl/*.v sim/tb_tadc_cmod_a7_top.v
vvp build/tb.vvp
```

The expected result is:

```text
PASS: captured and transmitted 8 ADC records
```

The RTL and testbench have also been parsed and elaborated together with zero
diagnostics using slang 11.0. Vivado was intentionally not installed or run on
the development PC; implementation and hardware programming are left for the
destination FPGA workstation.
