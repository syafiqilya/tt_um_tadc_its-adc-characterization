## Cmod A7 Rev. B: 12 MHz input clock
set_property -dict { PACKAGE_PIN L17 IOSTANDARD LVCMOS33 } [get_ports { sysclk }]
create_clock -add -name sys_clk_pin -period 83.333 -waveform {0 41.666} [get_ports { sysclk }]

## Buttons: BTN0 resets; BTN1 starts/restarts a capture
set_property -dict { PACKAGE_PIN A18 IOSTANDARD LVCMOS33 } [get_ports { btn_reset }]
set_property -dict { PACKAGE_PIN B18 IOSTANDARD LVCMOS33 } [get_ports { btn_start }]

## LEDs: LED1=acquiring; LED2=transmitting or complete
set_property -dict { PACKAGE_PIN A17 IOSTANDARD LVCMOS33 } [get_ports { led[0] }]
set_property -dict { PACKAGE_PIN C16 IOSTANDARD LVCMOS33 } [get_ports { led[1] }]

## Cmod JA connected in the same order as Tiny Tapeout uo_out[7:0]
set_property -dict { PACKAGE_PIN G17 IOSTANDARD LVCMOS33 } [get_ports { adc_cko }]
set_property -dict { PACKAGE_PIN G19 IOSTANDARD LVCMOS33 } [get_ports { adc_data[8] }]
set_property -dict { PACKAGE_PIN N18 IOSTANDARD LVCMOS33 } [get_ports { adc_data[7] }]
set_property -dict { PACKAGE_PIN L18 IOSTANDARD LVCMOS33 } [get_ports { adc_data[6] }]
set_property -dict { PACKAGE_PIN H17 IOSTANDARD LVCMOS33 } [get_ports { adc_data[5] }]
set_property -dict { PACKAGE_PIN H19 IOSTANDARD LVCMOS33 } [get_ports { adc_data[4] }]
set_property -dict { PACKAGE_PIN J19 IOSTANDARD LVCMOS33 } [get_ports { adc_data[3] }]
set_property -dict { PACKAGE_PIN K18 IOSTANDARD LVCMOS33 } [get_ports { adc_data[2] }]

## Remaining ADC signals on Cmod DIP pins PIO1..PIO4
set_property -dict { PACKAGE_PIN M3  IOSTANDARD LVCMOS33 } [get_ports { adc_data[1] }]
set_property -dict { PACKAGE_PIN L3  IOSTANDARD LVCMOS33 } [get_ports { adc_data[0] }]
set_property -dict { PACKAGE_PIN A16 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 4 } [get_ports { adc_clk }]
set_property -dict { PACKAGE_PIN K3  IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 4 } [get_ports { adc_en }]

## FPGA TX -> onboard FT2232 USB-UART receive input
set_property -dict { PACKAGE_PIN J17 IOSTANDARD LVCMOS33 } [get_ports { uart_txd_in }]

## CKO is intentionally synchronized in RTL.
set_false_path -from [get_ports { adc_cko }]

## ADC parallel data is captured only after a synchronized CKO and settle delay.
set_false_path -from [get_ports { adc_data[*] }]
