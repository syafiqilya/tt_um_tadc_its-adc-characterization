`timescale 1ns / 1ps
`default_nettype none

// Converts the capture RAM into a documented little-endian UART stream.
module capture_streamer #(
    parameter integer SAMPLE_COUNT = 4096,
    parameter integer ADDR_WIDTH   = 12,
    parameter integer SYSTEM_CLOCK_HZ = 10_000_000,
    parameter integer ADC_CLOCK_HZ    = 1_000_000
) (
    input  wire                  clk,
    input  wire                  reset,
    input  wire                  start,
    output reg  [ADDR_WIDTH-1:0] mem_addr,
    input  wire [95:0]           mem_data,
    output reg                   uart_start,
    output reg  [7:0]            uart_data,
    input  wire                  uart_busy,
    output reg                   busy,
    output reg                   done
);
    localparam ST_IDLE            = 4'd0;
    localparam ST_HEADER_SEND     = 4'd1;
    localparam ST_HEADER_DRAIN    = 4'd2;
    localparam ST_READ_WAIT_1     = 4'd3;
    localparam ST_READ_WAIT_2     = 4'd4;
    localparam ST_RECORD_SEND     = 4'd5;
    localparam ST_RECORD_DRAIN    = 4'd6;
    localparam ST_FINISH          = 4'd7;
    localparam [15:0] SAMPLE_COUNT_VALUE = SAMPLE_COUNT;
    localparam [31:0] SYSTEM_CLOCK_VALUE = SYSTEM_CLOCK_HZ;
    localparam [31:0] ADC_CLOCK_VALUE    = ADC_CLOCK_HZ;
    localparam [ADDR_WIDTH-1:0] LAST_RECORD = SAMPLE_COUNT - 1;

    reg [3:0] state;
    reg [4:0] byte_index;
    reg [ADDR_WIDTH-1:0] record_index;
    reg [95:0] record_data;

    function [7:0] header_byte;
        input [4:0] index;
        begin
            case (index)
                0:  header_byte = 8'h54; // T
                1:  header_byte = 8'h41; // A
                2:  header_byte = 8'h44; // D
                3:  header_byte = 8'h43; // C
                4:  header_byte = 8'h01; // format version
                5:  header_byte = 8'd16; // bytes per record
                6:  header_byte = SAMPLE_COUNT_VALUE[7:0];
                7:  header_byte = SAMPLE_COUNT_VALUE[15:8];
                8:  header_byte = SYSTEM_CLOCK_VALUE[7:0];
                9:  header_byte = SYSTEM_CLOCK_VALUE[15:8];
                10: header_byte = SYSTEM_CLOCK_VALUE[23:16];
                11: header_byte = SYSTEM_CLOCK_VALUE[31:24];
                12: header_byte = ADC_CLOCK_VALUE[7:0];
                13: header_byte = ADC_CLOCK_VALUE[15:8];
                14: header_byte = ADC_CLOCK_VALUE[23:16];
                15: header_byte = ADC_CLOCK_VALUE[31:24];
                default: header_byte = 8'h00;
            endcase
        end
    endfunction

    function [7:0] record_byte;
        input [4:0] index;
        input [15:0] seq_num;
        input [95:0] rec;
        begin
            case (index)
                0:  record_byte = 8'ha5;
                1:  record_byte = 8'h5a;
                2:  record_byte = seq_num[7:0];
                3:  record_byte = seq_num[15:8];
                4:  record_byte = rec[7:0];
                5:  record_byte = rec[15:8];
                6:  record_byte = rec[71:64];
                7:  record_byte = rec[79:72];
                8:  record_byte = rec[87:80];
                9:  record_byte = rec[95:88];
                10: record_byte = rec[39:32];
                11: record_byte = rec[47:40];
                12: record_byte = rec[55:48];
                13: record_byte = rec[63:56];
                14: record_byte = rec[23:16];
                15: record_byte = rec[31:24];
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
            record_data  <= 96'd0;
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
                        if (byte_index == 15) begin
                            state <= ST_HEADER_DRAIN;
                        end else begin
                            byte_index <= byte_index + 1'b1;
                        end
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
                        uart_data  <= record_byte(
                            byte_index,
                            {{(16-ADDR_WIDTH){1'b0}}, record_index},
                            record_data
                        );
                        uart_start <= 1'b1;
                        if (byte_index == 15) begin
                            state <= ST_RECORD_DRAIN;
                        end else begin
                            byte_index <= byte_index + 1'b1;
                        end
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
