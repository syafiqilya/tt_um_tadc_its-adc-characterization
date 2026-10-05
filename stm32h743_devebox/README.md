# STM32H743VIT6 DevEBox TADC Controller

This directory ports the Cmod A7 capture behavior to the DevEBox
STM32H743VIT6 board. It uses STM32Cube HAL and USB Device CDC while preserving
TADC protocol version 3, so the existing `pc/capture_tadc.py`,
`pc/analyze_fft.py`, and `pc/fft_frequency_sweep.py` programs work unchanged.

## Hardware architecture

- TIM3 CH1 produces the 1 MHz ADC clock on PA6.
- TIM2 is a 32-bit 10 MHz free-running counter.
- TIM2 CH1 hardware input capture latches the exact counter value when CKO
  rises on PA0. Interrupt latency therefore does not alter the timestamp.
- DATA[8:0] uses contiguous PE15:PE7 pins and is read with one GPIO register
  access.
- PC0 drives ADC `EN`.
- Onboard K1 (PE3, active low) starts a capture.
- Onboard D2 (PA1, active low) is on during acquisition.
- Native USB on PA11/PA12 sends the same version-3 CDC byte stream used by the
  FPGA project.

## Tiny Tapeout wiring

Connect ground first. Do not connect the two boards' 3.3 V power outputs.

| DevEBox signal | Header location | Direction | Tiny Tapeout signal |
|---|---|---|---|
| PA6 | Header 1 pin 28 | Output | Project `clk` (1 MHz) |
| PC0 | Header 1 pin 38 | Output | `ui_in[0]` / ADC `EN` |
| PA0 | Header 1 pin 34 | Input capture | `uo_out[0]` / CKO |
| PE15 | Header 1 pin 13 | Input | `uo_out[1]` / DATA[8] |
| PE14 | Header 1 pin 14 | Input | `uo_out[2]` / DATA[7] |
| PE13 | Header 1 pin 15 | Input | `uo_out[3]` / DATA[6] |
| PE12 | Header 1 pin 16 | Input | `uo_out[4]` / DATA[5] |
| PE11 | Header 1 pin 17 | Input | `uo_out[5]` / DATA[4] |
| PE10 | Header 1 pin 18 | Input | `uo_out[6]` / DATA[3] |
| PE9 | Header 1 pin 19 | Input | `uo_out[7]` / DATA[2] |
| PE8 | Header 1 pin 20 | Input | `uio[0]` / DATA[1] |
| PE7 | Header 1 pin 21 | Input | `uio[1]` / DATA[0] |
| GND | Header 1 pin 3 or 4 | — | Tiny Tapeout GND |

The DevEBox and Tiny Tapeout digital pins are 3.3 V logic. The ADC analog pins
remain limited to their documented 0–1.8 V range.

Before connecting PA6 or PC0, select `tt_um_tadc_its`, stop the carrier clock,
and put the Tiny Tapeout carrier in `ASIC_MANUAL_INPUTS` as described in the
repository's main `WIRING.md`.

## STM32CubeMX configuration

Create a project for `STM32H743VITx`, then use the settings below.

### Clock tree

- HSE: crystal/resonator, 25 MHz.
- SYSCLK: 400 MHz.
- HCLK: 200 MHz.
- APB1 peripheral clock: 100 MHz; APB1 timer clock: 200 MHz.
- USB kernel clock: 48 MHz, typically from PLL3Q.
- TIM2 and TIM3 kernel source: APB1 timer clock.

The firmware constants assume these timer clocks. With a 200 MHz timer clock:

- TIM2 prescaler `19` produces the 10 MHz timestamp counter.
- TIM3 prescaler `0`, period `199`, and pulse `100` produce a 1 MHz 50% PWM.

### TIM2: CKO timestamp input

- Channel 1: Input Capture direct mode.
- Pin: PA0, AF1.
- Edge: rising.
- Prescaler: `19`.
- Counter period: `0xFFFFFFFF`.
- Clock division: DIV1.
- Input filter: 0 initially; use a small filter only if CKO is noisy.
- Enable the TIM2 global interrupt.

### TIM3: ADC clock output

- Channel 1: PWM Generation CH1.
- Pin: PA6, AF2.
- Prescaler: `0`.
- Counter period: `199`.
- Pulse: `100`.
- PWM polarity: high.
- Do not start PWM automatically; the firmware starts it with each capture.

### GPIO

- PE7 through PE15: digital inputs, no pull.
- PC0: push-pull output, initial low, low speed.
- PE3: input with pull-up for onboard K1.
- PA1: push-pull output, initial high for onboard active-low D2.

### USB

- Enable `USB_OTG_HS` in Device Only mode with the internal full-speed PHY.
- PA11 is USB D- and PA12 is USB D+ through the board's J5 connector.
- Enable USB Device middleware and select CDC class.
- Keep USB DMA disabled unless cache-coherency handling is added.
- CubeMX should generate `hUsbDeviceHS` and `CDC_Transmit_HS()`.

## Add the application to the generated project

Copy:

- `Core/Inc/tadc_capture.h` into the generated `Core/Inc` directory;
- `Core/Src/tadc_capture.c` into the generated `Core/Src` directory.

In the generated `main.c`, add:

```c
#include "tadc_capture.h"
```

After all generated peripheral initialization calls, including
`MX_USB_DEVICE_Init()`, add:

```c
tadc_capture_init();
```

In the main loop add:

```c
while (1)
{
    tadc_capture_task();
}
```

Do not define a second `HAL_TIM_IC_CaptureCallback()` elsewhere. The callback
in `tadc_capture.c` handles TIM2 CH1.

## Operation

1. Connect and configure the Tiny Tapeout board in manual-input mode.
2. Program the STM32 using SWD.
3. Connect the DevEBox J5 USB connector to the PC.
4. Start the PC receiver using the USB CDC port:

```bash
python pc/capture_tadc.py /dev/ttyACM0 -o adc_capture.csv
```

On Windows use the assigned COM port. The baud argument is ignored by native
USB CDC, but leaving the Python default does no harm.

5. Press onboard K1. D2 turns on during acquisition.
6. After 4096 CKO events, the firmware stops `EN` and the 1 MHz ADC clock, then
   streams the header and timestamped records to the PC.

The PC calculates the sample rate from 4095 first-to-last CKO intervals and
uses that measured rate for FFT analysis.

## Important limitations

- CKO is result-ready timing, not direct access to the ADC's internal sampling
  aperture.
- TIM2 provides exact edge capture, but its 10 MHz counter has 100 ns
  resolution.
- Absolute rate accuracy is limited by the board's 25 MHz oscillator and PLL.
- The board's USB 5 V rail has no input-power isolation. Do not power the board
  simultaneously from J5 USB and an external 5 V source.
- `tadc_capture.c` expects the CubeMX-generated USB HS-device names
  `hUsbDeviceHS` and `CDC_Transmit_HS`. If CubeMX generates FS names, change
  those two identifiers consistently.

## References

- [DevEBox STM32H7XX-M board pinout and schematic](https://stm32-base.org/boards/STM32H743VIT6-STM32H7XX-M.html)
- [STM32H743VI product documentation](https://www.st.com/en/microcontrollers-microprocessors/stm32h743vi.html)
- [STM32H743 datasheet and alternate-function table](https://www.st.com/resource/en/datasheet/stm32h743ii.pdf)
- [ST STM32H743 USB CDC example](https://github.com/STMicroelectronics/STM32CubeH7/tree/master/Projects/STM32H743I-EVAL/Applications/USB_Device/CDC_Standalone)
