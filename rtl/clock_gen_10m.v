`timescale 1ns / 1ps
`default_nettype none

// Generates the 10 MHz measurement clock used by the complete design.
// Cmod A7 Rev. B has a 12 MHz oscillator.  A later board with a 100 MHz
// oscillator can be selected by overriding INPUT_CLOCK_HZ at synthesis time.
module clock_gen_10m #(
    parameter integer INPUT_CLOCK_HZ = 12_000_000
) (
    input  wire clk_in,
    input  wire reset,
    output wire clk_10m,
    output wire locked
);

`ifdef SYNTHESIS
    wire clk_feedback;
    wire clk_feedback_buf;
    wire clk_10m_unbuffered;
    wire mmcm_locked;

    generate
        if (INPUT_CLOCK_HZ == 12_000_000) begin : gen_from_12m
            // 12 MHz / 1 * 50 = 600 MHz VCO; 600 MHz / 60 = 10 MHz.
            MMCME2_BASE #(
                .BANDWIDTH("OPTIMIZED"),
                .CLKIN1_PERIOD(83.333),
                .DIVCLK_DIVIDE(1),
                .CLKFBOUT_MULT_F(50.0),
                .CLKOUT0_DIVIDE_F(60.0),
                .STARTUP_WAIT("FALSE")
            ) mmcm_i (
                .CLKIN1(clk_in),
                .CLKFBIN(clk_feedback_buf),
                .RST(reset),
                .PWRDWN(1'b0),
                .CLKFBOUT(clk_feedback),
                .CLKOUT0(clk_10m_unbuffered),
                .LOCKED(mmcm_locked),
                .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(),
                .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
                .CLKOUT4(), .CLKOUT5(), .CLKOUT6()
            );
        end else if (INPUT_CLOCK_HZ == 100_000_000) begin : gen_from_100m
            // 100 MHz / 1 * 6 = 600 MHz VCO; 600 MHz / 60 = 10 MHz.
            MMCME2_BASE #(
                .BANDWIDTH("OPTIMIZED"),
                .CLKIN1_PERIOD(10.000),
                .DIVCLK_DIVIDE(1),
                .CLKFBOUT_MULT_F(6.0),
                .CLKOUT0_DIVIDE_F(60.0),
                .STARTUP_WAIT("FALSE")
            ) mmcm_i (
                .CLKIN1(clk_in),
                .CLKFBIN(clk_feedback_buf),
                .RST(reset),
                .PWRDWN(1'b0),
                .CLKFBOUT(clk_feedback),
                .CLKOUT0(clk_10m_unbuffered),
                .LOCKED(mmcm_locked),
                .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(),
                .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
                .CLKOUT4(), .CLKOUT5(), .CLKOUT6()
            );
        end else begin : gen_bad_frequency
            // Intentionally fails implementation for an unsupported clock.
            initial $error("INPUT_CLOCK_HZ must be 12 MHz or 100 MHz");
            assign clk_feedback = 1'b0;
            assign clk_10m_unbuffered = 1'b0;
            assign mmcm_locked = 1'b0;
        end
    endgenerate

    BUFG feedback_buf_i (.I(clk_feedback), .O(clk_feedback_buf));
    BUFG output_buf_i   (.I(clk_10m_unbuffered), .O(clk_10m));
    assign locked = mmcm_locked;
`else
    // HDL simulation drives clk_in at 10 MHz and bypasses Xilinx primitives.
    assign clk_10m = clk_in;
    assign locked = ~reset;
`endif

endmodule

`default_nettype wire
