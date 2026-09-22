`timescale 1ns / 1ps
`default_nettype none

// Generates a registered 1 MHz output clock from the 10 MHz system clock.
// adc_clk is only an external output; FPGA logic remains in the clk domain.
module adc_clock_gen #(
    parameter integer HALF_PERIOD_TICKS = 5
) (
    input  wire clk,
    input  wire reset,
    input  wire run,
    output reg  adc_clk,
    output reg  adc_clk_rise
);
    localparam integer COUNT_WIDTH = 4;
    localparam [COUNT_WIDTH-1:0] HALF_COUNT = HALF_PERIOD_TICKS - 1;
    reg [COUNT_WIDTH-1:0] divider_count;

    always @(posedge clk) begin
        adc_clk_rise <= 1'b0;

        if (reset || !run) begin
            divider_count <= {COUNT_WIDTH{1'b0}};
            adc_clk       <= 1'b0;
        end else if (divider_count == HALF_COUNT) begin
            divider_count <= {COUNT_WIDTH{1'b0}};
            adc_clk       <= ~adc_clk;
            if (!adc_clk)
                adc_clk_rise <= 1'b1;
        end else begin
            divider_count <= divider_count + 1'b1;
        end
    end
endmodule

`default_nettype wire
