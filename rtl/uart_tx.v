`timescale 1ns / 1ps
`default_nettype none

// 8-N-1 UART transmitter. CLOCK_HZ must be an integer multiple of BAUD.
module uart_tx #(
    parameter integer CLOCK_HZ = 10_000_000,
    parameter integer BAUD     = 1_000_000
) (
    input  wire       clk,
    input  wire       reset,
    input  wire       start,
    input  wire [7:0] data,
    output reg        tx,
    output reg        busy
);
    localparam integer CLKS_PER_BIT = CLOCK_HZ / BAUD;
    reg [15:0] baud_count;
    reg [3:0]  bit_index;
    reg [9:0]  shift_register;

    always @(posedge clk) begin
        if (reset) begin
            tx             <= 1'b1;
            busy           <= 1'b0;
            baud_count     <= 16'd0;
            bit_index      <= 4'd0;
            shift_register <= 10'h3ff;
        end else if (!busy) begin
            tx <= 1'b1;
            if (start) begin
                // Shift order: start, data[0]..data[7], stop.
                shift_register <= {1'b1, data, 1'b0};
                tx             <= 1'b0;
                busy           <= 1'b1;
                baud_count     <= CLKS_PER_BIT - 1;
                bit_index      <= 4'd0;
            end
        end else if (baud_count != 0) begin
            baud_count <= baud_count - 1'b1;
        end else if (bit_index == 9) begin
            tx         <= 1'b1;
            busy       <= 1'b0;
            baud_count <= 16'd0;
        end else begin
            shift_register <= {1'b1, shift_register[9:1]};
            tx             <= shift_register[1];
            bit_index      <= bit_index + 1'b1;
            baud_count     <= CLKS_PER_BIT - 1;
        end
    end
endmodule

`default_nettype wire
