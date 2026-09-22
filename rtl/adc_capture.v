`timescale 1ns / 1ps
`default_nettype none

// Synchronizes CKO, timestamps each result, waits for the parallel bus to
// settle, samples it twice, and writes one 96-bit record per conversion.
module adc_capture #(
    parameter integer SAMPLE_COUNT = 4096,
    parameter integer ADDR_WIDTH   = 12,
    parameter integer DATA_WAIT_TICKS = 3
) (
    input  wire                  clk,
    input  wire                  reset,
    input  wire                  arm,
    input  wire                  active,
    input  wire                  adc_clk_rise,
    input  wire                  adc_cko_async,
    input  wire [8:0]            adc_data_async,
    output reg                   mem_we,
    output reg  [ADDR_WIDTH-1:0] mem_waddr,
    output reg  [95:0]           mem_wdata,
    output reg                   capture_done,
    output reg  [ADDR_WIDTH:0]   captured_count
);
    localparam ST_IDLE   = 2'd0;
    localparam ST_WAIT   = 2'd1;
    localparam ST_SAMPLE = 2'd2;
    localparam ST_VERIFY = 2'd3;
    localparam [ADDR_WIDTH:0] LAST_SAMPLE_COUNT = SAMPLE_COUNT - 1;

    (* ASYNC_REG = "TRUE" *) reg cko_meta;
    (* ASYNC_REG = "TRUE" *) reg cko_sync;
    reg cko_sync_d;

    reg [1:0] state;
    reg [3:0] wait_count;
    reg [8:0] data_first;
    reg [31:0] timestamp_counter;
    reg [31:0] previous_cko_timestamp;
    reg [15:0] adc_edge_counter;
    reg [15:0] previous_adc_edge_counter;
    reg [31:0] event_timestamp;
    reg [31:0] event_period;
    reg [15:0] event_adc_edges;
    reg        first_record;

    wire cko_rise = cko_sync & ~cko_sync_d;

    always @(posedge clk) begin
        if (reset) begin
            cko_meta  <= 1'b0;
            cko_sync  <= 1'b0;
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
            state                     <= ST_IDLE;
            wait_count                <= 4'd0;
            data_first                <= 9'd0;
            timestamp_counter         <= 32'd0;
            previous_cko_timestamp    <= 32'd0;
            adc_edge_counter          <= 16'd0;
            previous_adc_edge_counter <= 16'd0;
            event_timestamp           <= 32'd0;
            event_period              <= 32'd0;
            event_adc_edges           <= 16'd0;
            first_record              <= 1'b1;
            mem_waddr                 <= {ADDR_WIDTH{1'b0}};
            mem_wdata                 <= 96'd0;
            capture_done              <= 1'b0;
            captured_count            <= {(ADDR_WIDTH+1){1'b0}};
        end else begin
            timestamp_counter <= timestamp_counter + 1'b1;

            if (active && adc_clk_rise)
                adc_edge_counter <= adc_edge_counter + 1'b1;

            if (arm) begin
                state                     <= ST_IDLE;
                wait_count                <= 4'd0;
                previous_cko_timestamp    <= timestamp_counter;
                adc_edge_counter          <= 16'd0;
                previous_adc_edge_counter <= 16'd0;
                first_record              <= 1'b1;
                mem_waddr                 <= {ADDR_WIDTH{1'b0}};
                capture_done              <= 1'b0;
                captured_count            <= {(ADDR_WIDTH+1){1'b0}};
            end else if (active && !capture_done) begin
                case (state)
                    ST_IDLE: begin
                        if (cko_rise) begin
                            event_timestamp <= timestamp_counter;
                            event_period    <= timestamp_counter - previous_cko_timestamp;
                            event_adc_edges <= adc_edge_counter - previous_adc_edge_counter;
                            previous_cko_timestamp    <= timestamp_counter;
                            previous_adc_edge_counter <= adc_edge_counter;
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
                        // Record layout:
                        // [95:64] timestamp, [63:32] period,
                        // [31:16] ADC-clock edges, [15:0] code/flags.
                        // code/flags[8:0] = ADC code
                        // code/flags[9]   = samples did not agree
                        // code/flags[10]  = first result after EN
                        mem_wdata <= {
                            event_timestamp,
                            event_period,
                            event_adc_edges,
                            5'd0,
                            first_record,
                            (data_first != adc_data_async),
                            adc_data_async
                        };
                        mem_we         <= 1'b1;
                        captured_count <= captured_count + 1'b1;
                        first_record   <= 1'b0;
                        state          <= ST_IDLE;

                        if (captured_count == LAST_SAMPLE_COUNT) begin
                            capture_done <= 1'b1;
                        end else begin
                            mem_waddr <= mem_waddr + 1'b1;
                        end
                    end

                    default: state <= ST_IDLE;
                endcase
            end
        end
    end
endmodule

`default_nettype wire
