`timescale 1ns / 1ps
`default_nettype none

// Captures one nine-bit ADC code for each synchronized CKO rising edge.
// No conversion timestamps, periods, or ADC-clock-edge counts are stored.
module adc_capture #(
    parameter integer SAMPLE_COUNT    = 4096,
    parameter integer ADDR_WIDTH      = 12,
    parameter integer DATA_WAIT_TICKS = 3
) (
    input  wire                  clk,
    input  wire                  reset,
    input  wire                  arm,
    input  wire                  active,
    input  wire                  adc_cko_async,
    input  wire [8:0]            adc_data_async,
    output reg                   mem_we,
    output reg  [ADDR_WIDTH-1:0] mem_waddr,
    output reg  [9:0]            mem_wdata,
    output reg                   capture_done
);
    localparam ST_IDLE   = 2'd0;
    localparam ST_WAIT   = 2'd1;
    localparam ST_SAMPLE = 2'd2;
    localparam ST_VERIFY = 2'd3;
    localparam [ADDR_WIDTH-1:0] LAST_ADDRESS = SAMPLE_COUNT - 1;

    (* ASYNC_REG = "TRUE" *) reg cko_meta;
    (* ASYNC_REG = "TRUE" *) reg cko_sync;
    reg cko_sync_d;

    reg [1:0] state;
    reg [3:0] wait_count;
    reg [8:0] data_first;

    wire cko_rise = cko_sync & ~cko_sync_d;

    always @(posedge clk) begin
        if (reset) begin
            cko_meta   <= 1'b0;
            cko_sync   <= 1'b0;
            cko_sync_d <= 1'b0;
        end else begin
            cko_meta   <= adc_cko_async;
            cko_sync   <= cko_meta;
            cko_sync_d <= cko_sync;
        end
    end

    always @(posedge clk) begin
        mem_we <= 1'b0;

        if (reset) begin
            state        <= ST_IDLE;
            wait_count   <= 4'd0;
            data_first   <= 9'd0;
            mem_waddr    <= {ADDR_WIDTH{1'b0}};
            mem_wdata    <= 10'd0;
            capture_done <= 1'b0;
        end else if (arm) begin
            state        <= ST_IDLE;
            wait_count   <= 4'd0;
            mem_waddr    <= {ADDR_WIDTH{1'b0}};
            capture_done <= 1'b0;
        end else if (active && !capture_done) begin
            case (state)
                ST_IDLE: begin
                    if (cko_rise) begin
                        wait_count <= DATA_WAIT_TICKS[3:0];
                        state      <= ST_WAIT;
                    end
                end

                ST_WAIT: begin
                    if (wait_count == 0)
                        state <= ST_SAMPLE;
                    else
                        wait_count <= wait_count - 1'b1;
                end

                ST_SAMPLE: begin
                    data_first <= adc_data_async;
                    state      <= ST_VERIFY;
                end

                ST_VERIFY: begin
                    // Bit 9 reports that the two consecutive reads disagreed.
                    // Bits 8:0 contain the ADC code from the second read.
                    mem_wdata <= {
                        (data_first != adc_data_async),
                        adc_data_async
                    };
                    mem_we <= 1'b1;
                    state  <= ST_IDLE;

                    if (mem_waddr == LAST_ADDRESS) begin
                        capture_done <= 1'b1;
                    end else begin
                        mem_waddr <= mem_waddr + 1'b1;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
