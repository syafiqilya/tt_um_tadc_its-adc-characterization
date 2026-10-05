`timescale 1ns / 1ps
`default_nettype none

// Sends the capture RAM as TADC UART protocol version 3.
// Each record contains an ADC sample and its raw CKO timestamp. The PC performs
// all sample-rate and interval calculations.
module capture_streamer #(
    parameter integer SAMPLE_COUNT      = 4096,
    parameter integer ADDR_WIDTH        = 12,
    parameter integer TIMER_CLOCK_HZ    = 10_000_000,
    parameter integer ADC_CLOCK_HZ      = 1_000_000
) (
    input  wire                  clk,
    input  wire                  reset,
    input  wire                  start,
    output reg  [ADDR_WIDTH-1:0] mem_addr,
    input  wire [41:0]           mem_data,
    output reg                   uart_start,
    output reg  [7:0]            uart_data,
    input  wire                  uart_busy,
    output reg                   busy,
    output reg                   done
);
    localparam ST_IDLE         = 4'd0;
    localparam ST_HEADER_SEND  = 4'd1;
    localparam ST_HEADER_DRAIN = 4'd2;
    localparam ST_READ_WAIT_1  = 4'd3;
    localparam ST_READ_WAIT_2  = 4'd4;
    localparam ST_RECORD_SEND  = 4'd5;
    localparam ST_RECORD_DRAIN = 4'd6;
    localparam ST_FINISH       = 4'd7;

    localparam [15:0] SAMPLE_COUNT_VALUE      = SAMPLE_COUNT;
    localparam [31:0] TIMER_CLOCK_VALUE     = TIMER_CLOCK_HZ;
    localparam [31:0] ADC_CLOCK_VALUE       = ADC_CLOCK_HZ;
    localparam [ADDR_WIDTH-1:0] LAST_RECORD = SAMPLE_COUNT - 1;

    reg [3:0] state;
    reg [4:0] byte_index;
    reg [ADDR_WIDTH-1:0] record_index;
    reg [41:0] record_data;

    function [7:0] header_byte;
        input [4:0] index;
        begin
            case (index)
                0:  header_byte = 8'h54; // T
                1:  header_byte = 8'h41; // A
                2:  header_byte = 8'h44; // D
                3:  header_byte = 8'h43; // C
                4:  header_byte = 8'h03; // protocol version
                5:  header_byte = 8'd8;  // bytes per sample record
                6:  header_byte = SAMPLE_COUNT_VALUE[7:0];
                7:  header_byte = SAMPLE_COUNT_VALUE[15:8];
                8:  header_byte = TIMER_CLOCK_VALUE[7:0];
                9:  header_byte = TIMER_CLOCK_VALUE[15:8];
                10: header_byte = TIMER_CLOCK_VALUE[23:16];
                11: header_byte = TIMER_CLOCK_VALUE[31:24];
                12: header_byte = ADC_CLOCK_VALUE[7:0];
                13: header_byte = ADC_CLOCK_VALUE[15:8];
                14: header_byte = ADC_CLOCK_VALUE[23:16];
                15: header_byte = ADC_CLOCK_VALUE[31:24];
                default: header_byte = 8'h00;
            endcase
        end
    endfunction

    function [7:0] record_byte;
        input [2:0] index;
        input [41:0] sample;
        begin
            case (index)
                0: record_byte = 8'hA5;
                1: record_byte = 8'h5A;
                2: record_byte = sample[7:0];
                3: record_byte = {6'd0, sample[9:8]};
                4: record_byte = sample[17:10];
                5: record_byte = sample[25:18];
                6: record_byte = sample[33:26];
                7: record_byte = sample[41:34];
                default: record_byte = 8'h00;
            endcase
        end
    endfunction

    always @(posedge clk) begin
        uart_start <= 1'b0;

        if (reset) begin
            state        <= ST_IDLE;
            byte_index   <= 5'd0;
            record_index <= {ADDR_WIDTH{1'b0}};
            record_data  <= 42'd0;
            mem_addr     <= {ADDR_WIDTH{1'b0}};
            uart_data    <= 8'd0;
            busy         <= 1'b0;
            done         <= 1'b0;
        end else begin
            case (state)
                ST_IDLE: begin
                    busy <= 1'b0;
                    done <= 1'b0;
                    if (start) begin
                        busy         <= 1'b1;
                        byte_index   <= 5'd0;
                        record_index <= {ADDR_WIDTH{1'b0}};
                        mem_addr     <= {ADDR_WIDTH{1'b0}};
                        state        <= ST_HEADER_SEND;
                    end
                end

                ST_HEADER_SEND: begin
                    if (!uart_busy && !uart_start) begin
                        uart_data  <= header_byte(byte_index);
                        uart_start <= 1'b1;
                        if (byte_index == 15)
                            state <= ST_HEADER_DRAIN;
                        else
                            byte_index <= byte_index + 1'b1;
                    end
                end

                ST_HEADER_DRAIN: begin
                    if (!uart_busy && !uart_start) begin
                        mem_addr <= {ADDR_WIDTH{1'b0}};
                        state    <= ST_READ_WAIT_1;
                    end
                end

                ST_READ_WAIT_1: state <= ST_READ_WAIT_2;

                ST_READ_WAIT_2: begin
                    record_data <= mem_data;
                    byte_index  <= 5'd0;
                    state       <= ST_RECORD_SEND;
                end

                ST_RECORD_SEND: begin
                    if (!uart_busy && !uart_start) begin
                        uart_data  <= record_byte(byte_index[2:0], record_data);
                        uart_start <= 1'b1;
                        if (byte_index == 7)
                            state <= ST_RECORD_DRAIN;
                        else
                            byte_index <= byte_index + 1'b1;
                    end
                end

                ST_RECORD_DRAIN: begin
                    if (!uart_busy && !uart_start) begin
                        if (record_index == LAST_RECORD) begin
                            state <= ST_FINISH;
                        end else begin
                            record_index <= record_index + 1'b1;
                            mem_addr     <= record_index + 1'b1;
                            state        <= ST_READ_WAIT_1;
                        end
                    end
                end

                ST_FINISH: begin
                    busy  <= 1'b0;
                    done  <= 1'b1;
                    state <= ST_IDLE;
                end

                default: state <= ST_IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
