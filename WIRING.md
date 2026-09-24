# Cmod A7, Tiny Tapeout ADC, and Function-Generator Wiring

This guide covers the complete bench connection for the
`tt_um_tadc_its` ADC-characterization project. Read the safety notes before
powering either board.

The official Tiny Tapeout project page identifies the external interface as
`EN`, `CKO`, `DATA[8:0]`, `VCM`, `VIN`, and `VIP`. It specifies a 0–1.8 V analog
input range. Its published transistor-level testbench uses `VCM = 0.9 V` and
equal-amplitude, opposite-phase sine waves on `VIP` and `VIN`, with a 50 ohm
series resistor on each input.

References:

- [Tiny Tapeout project page](https://www.tinytapeout.com/chips/ttsky25b/tt_um_tadc_its)
- [Tiny Tapeout demoboard quickstart](https://www.tinytapeout.com/guides/get-started-demoboard/)
- [Tiny Tapeout external-control example](https://tinytapeout.com/guides/analog-discovery/)
- [Tiny Tapeout MicroPython firmware](https://github.com/TinyTapeout/tt-micropython-firmware)
- [Original ADC repository](https://github.com/mthudaa/its_10b_tadc)
- [Published ADC transient testbench](https://github.com/mthudaa/its_10b_tadc/blob/main/xschem/adc_tb.sch)
- [Cmod A7 constraints used by this project](constraints/cmod_a7_rev_b_12mhz.xdc)

## Complete connection overview

```text
                                      USB
                               +------ PC
                               |
                      +--------+---------+
                      |     Cmod A7      |
                      |                  |
                      | PIO3: ADC CLK ---+----------------> TT project clk
                      | PIO4: ADC EN  ---+----------------> TT ui_in[0]
                      | JA1:  CKO      <--+---------------- TT uo_out[0]
                      | JA2..JA10      <--+---------------- TT DATA[8:2]
                      | PIO1..PIO2     <--+---------------- TT DATA[1:0]
                      +--------+---------+
                               |
                              GND
                               |
             +-----------------+--------------------+
             |                                      |
      +------+----------+                  +--------+---------+
      | Tiny Tapeout    |                  | Function generator|
      | demoboard       |                  |                   |
      |                 |<-- VIP (F) ------| CH1, 0 degrees    |
      | tt_um_tadc_its  |<-- VIN (G) ------| CH2, 180 degrees  |
      |                 |<-- VCM (D) ------| quiet 0.9 V DC    |
      +-----------------+                  +-------------------+
```

The Cmod A7 USB connection supplies the FPGA, programs it, and carries the
captured UART data. No separate USB-to-UART wiring is required.

## Which device controls what?

The Tiny Tapeout carrier-board RP2040/RP2350 still powers and selects the
`tt_um_tadc_its` project. After the carrier has selected the project and
released its project I/O, the Cmod A7 controls the ADC `clk` and `EN`, reads
`CKO` and `DATA[8:0]`, counts the timing, and sends the capture to the PC.

The supplied FPGA design does **not** drive Tiny Tapeout's project-selection
management signals (`ctrl_ena`, `ctrl_sel_inc`, or `ctrl_sel_rst_n`) and does
not automatically configure the carrier-board controller. This division is
intentional: use the carrier for project selection and the FPGA for the actual
ADC measurement.

## Required carrier-board setup

Do this before allowing the FPGA to drive PIO3 (`clk`) or PIO4 (`EN`). Power
the Tiny Tapeout carrier through its normal USB connector, open its MicroPython
REPL, and enter:

```python
from ttboard.mode import RPMode

tt.shuttle.tt_um_tadc_its.enable()
tt.clock_project_stop()
tt.mode = RPMode.ASIC_MANUAL_INPUTS
tt.reset_project(False)
```

Select the project first and then set `ASIC_MANUAL_INPUTS`, because selecting a
project can load its configured operating mode. Manual-input mode stops the
RP2040-generated project clock and releases the ordinary project inputs so
external hardware can drive them. Keep the board out of `ASIC_RP_CONTROL`
while the FPGA is connected to `clk` and `EN`.

On carrier/firmware versions that support manual-clock monitoring, also use:

```python
tt.manual_project_clock.monitoring = False
```

This prevents the carrier's manual-clock handler from generating a clock edge
during FPGA control. If the named project attribute is unavailable, locate the
installed name with `tt.shuttle.find("tadc")` and enable the returned project.

Never permit the RP2040 and FPGA to drive the same net simultaneously. For the
first bring-up, keep PIO3 and PIO4 disconnected (or keep the Cmod A7 unpowered)
until the commands above have completed. Leave the carrier DIP-switch inputs
off and do not attach another input-driving PMOD at the same time.

## Digital wiring

Use short jumper wires. Connect a ground wire before connecting any signal
wires.

| Cmod A7 header | FPGA package pin | Direction at FPGA | Tiny Tapeout signal | ADC meaning |
|---|---:|---|---|---|
| JA1 | G17 | Input | `uo_out[0]` | `CKO`, result-ready event |
| JA2 | G19 | Input | `uo_out[1]` | `DATA[8]`, MSB |
| JA3 | N18 | Input | `uo_out[2]` | `DATA[7]` |
| JA4 | L18 | Input | `uo_out[3]` | `DATA[6]` |
| JA7 | H17 | Input | `uo_out[4]` | `DATA[5]` |
| JA8 | H19 | Input | `uo_out[5]` | `DATA[4]` |
| JA9 | J19 | Input | `uo_out[6]` | `DATA[3]` |
| JA10 | K18 | Input | `uo_out[7]` | `DATA[2]` |
| PIO1 | M3 | Input | `uio[0]` | `DATA[1]` |
| PIO2 | L3 | Input | `uio[1]` | `DATA[0]`, LSB |
| PIO3 | A16 | Output | project `clk` | 1 MHz ADC clock |
| PIO4 | K3 | Output | `ui_in[0]` | ADC `EN` |
| Any marked GND | — | — | Any marked GND | Common digital/analog ground |

The FPGA and Tiny Tapeout digital interfaces are 3.3 V logic. Do not insert a
5 V logic source. Do not connect the Cmod A7 3.3 V supply pin to an ADC analog
input.

Before connecting PIO3 or PIO4, complete **Required carrier-board setup**
above. Two outputs driving one wire can damage a board.

`DATA[1:0]` deserve special attention. The submitted ADC schematic does not
clearly drive Tiny Tapeout `uio_oe[1:0]` high. If these two bits do not move in
silicon, verify `uio[1:0]` with an oscilloscope or logic analyzer before blaming
the FPGA receiver.

## Analog pin locations

The official project page maps the ADC's analog inputs as follows:

| Tiny Tapeout analog signal | `ua` index | Demoboard PCB pin |
|---|---:|---|
| `VCM` | `ua[0]` | D |
| `VIN` | `ua[1]` | G |
| `VIP` | `ua[2]` | F |

Confirm the D/G/F labels on the actual demoboard revision before wiring. These
letters are not Cmod A7 header names.

## Recommended two-channel differential stimulus

Use two phase-locked generator channels:

| Setting | Channel 1 to `VIP` | Channel 2 to `VIN` |
|---|---:|---:|
| Waveform | Sine | Sine |
| Frequency | Coherent frequency from `plan_coherent_tone.py` | Same |
| Phase | 0 degrees | 180 degrees |
| DC offset | 0.9 V | 0.9 V |
| Starting amplitude | 0.4 Vpp | 0.4 Vpp |
| Output/load setting | High-Z load | High-Z load |

Also connect a quiet 0.9 V DC source to `VCM`. Connect both generator ground
shields and the 0.9 V source return to the common board ground.

Start at the small amplitude above. Verify both pins with an oscilloscope, then
increase amplitude as required. At every instant:

```text
0 V <= VIP <= 1.8 V
0 V <= VIN <= 1.8 V
VCM approximately 0.9 V
```

For a near-full-scale differential test, the published simulation uses up to
0.9 V peak per input around 0.9 V. Real bench overshoot can exceed the rails, so
do not begin at that level. Use approximately 47–51 ohm series resistance close
to each analog pin and confirm the actual pin voltage before enabling `EN`.

Generator amplitude depends on whether its display assumes a 50 ohm load or a
high-impedance load. The number shown on the generator is not sufficient;
measure `VIP` and `VIN` at the board.

## Single-channel generator fallback

If only one generator channel is available:

1. Connect a quiet 0.9 V reference to both `VCM` and `VIN`.
2. Drive `VIP` with a sine wave centered at 0.9 V.
3. Begin with 0.4 Vpp and verify the waveform at `VIP`.
4. Connect the generator shield and reference return to common ground.

This produces a single-ended differential input. It is useful for bring-up but
does not reproduce the fully differential stimulus used by the published ADC
simulation. Use the two-channel arrangement for final dynamic measurements.

## Clock coherence and reference wiring

The current FPGA design sends only the 1 MHz ADC clock on Cmod A7 PIO3. It does
**not** expose the internal 10 MHz system clock on a header. Therefore there is
currently no external-reference wire between the Cmod A7 and function
generator.

The Python tools can calculate the correct nominal generator frequency and will
detect drift in the final capture. Without a shared reference, use the automatic
Blackman-Harris FFT window.

For strict hardware coherence, a future FPGA revision should route a properly
buffered 10 MHz reference to an unused Cmod pin and add an XDC constraint. Only
then should it be connected to a generator's external-reference input, after
checking the generator's accepted voltage, impedance, and frequency. Do not
connect an arbitrary Cmod pin to the reference input.

## Power-up and bring-up sequence

1. Turn off the function-generator outputs and unplug both boards.
2. Connect Cmod A7 ground, Tiny Tapeout ground, generator grounds, and the
   0.9 V reference return.
3. Leave the FPGA-to-Tiny-Tapeout signal wires disconnected for first setup.
4. Connect `VCM`, `VIP`, and `VIN` through the analog network.
5. Check for accidental shorts with a multimeter.
6. Power the Tiny Tapeout demoboard through USB.
7. Run all commands in **Required carrier-board setup** above. Confirm that the
   project is selected, the carrier clock is stopped, and manual-input mode is
   active.
8. With both boards sharing ground, connect the digital signal wires exactly
   as listed above, then connect/program the Cmod A7 through USB.
9. With ADC `EN` low, enable the analog source and scope `VCM`, `VIP`, and
   `VIN`; confirm they remain between 0 and 1.8 V.
10. Start `capture_tadc.py`, press Cmod A7 BTN1, and inspect the first capture's
    timing and unstable-data flags.

Power the two boards from their own intended USB/power inputs. Share ground,
but do not tie their 3.3 V supply outputs together unless a separately reviewed
power plan requires it.
