`timescale 1ns / 1ps
`default_nettype none

module tadc_cmod_a7_top #(
    parameter integer INPUT_CLOCK_HZ = 12_000_000,
    parameter integer SAMPLE_COUNT   = 4096,
    parameter integer ADDR_WIDTH     = 12
) (
    input  wire       sysclk,
    input  wire       btn_reset,
    input  wire       btn_start,

    output wire       adc_clk,
    output reg        adc_en,
    input  wire       adc_cko,
    input  wire [8:0] adc_data,

    output wire       uart_txd_in,
    output wire [1:0] led
);
    localparam CTRL_WAIT    = 2'd0;
    localparam CTRL_CAPTURE = 2'd1;
    localparam CTRL_STREAM  = 2'd2;
    localparam CTRL_DONE    = 2'd3;

    wire clk_10m;
    wire clock_locked;
    reg [1:0] reset_sync;
    reg [1:0] start_sync;
    reg start_sync_d;
    wire reset = !clock_locked || reset_sync[1];
    wire start_rise = start_sync[1] & ~start_sync_d;

    reg [1:0] control_state;
    reg adc_clock_run;
    reg capture_arm;
    reg stream_start;
    wire adc_clk_rise;

    wire mem_we;
    wire [ADDR_WIDTH-1:0] mem_waddr;
    wire [95:0] mem_wdata;
    wire [ADDR_WIDTH-1:0] mem_raddr;
    reg  [95:0] mem_rdata;
    (* ram_style = "block" *) reg [95:0] capture_memory [0:SAMPLE_COUNT-1];

    wire capture_done;
    wire [ADDR_WIDTH:0] captured_count;
    wire streamer_busy;
    wire streamer_done;
    wire uart_start;
    wire [7:0] uart_data;
    wire uart_busy;
    wire uart_tx_line;

    clock_gen_10m #(
        .INPUT_CLOCK_HZ(INPUT_CLOCK_HZ)
    ) clock_gen_i (
        .clk_in(sysclk),
        .reset(1'b0),
        .clk_10m(clk_10m),
        .locked(clock_locked)
    );

    always @(posedge clk_10m) begin
        reset_sync   <= {reset_sync[0], btn_reset};
        start_sync   <= {start_sync[0], btn_start};
        start_sync_d <= start_sync[1];
    end

    adc_clock_gen adc_clock_i (
        .clk(clk_10m),
        .reset(reset),
        .run(adc_clock_run),
        .adc_clk(adc_clk),
        .adc_clk_rise(adc_clk_rise)
    );

    adc_capture #(
        .SAMPLE_COUNT(SAMPLE_COUNT),
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WAIT_TICKS(3)
    ) capture_i (
        .clk(clk_10m),
        .reset(reset),
        .arm(capture_arm),
        .active(control_state == CTRL_CAPTURE),
        .adc_clk_rise(adc_clk_rise),
        .adc_cko_async(adc_cko),
        .adc_data_async(adc_data),
        .mem_we(mem_we),
        .mem_waddr(mem_waddr),
        .mem_wdata(mem_wdata),
        .capture_done(capture_done),
        .captured_count(captured_count)
    );

    // True dual-purpose RAM: acquisition writes, streamer reads.
    always @(posedge clk_10m) begin
        if (mem_we)
            capture_memory[mem_waddr] <= mem_wdata;
        mem_rdata <= capture_memory[mem_raddr];
    end

    capture_streamer #(
        .SAMPLE_COUNT(SAMPLE_COUNT),
        .ADDR_WIDTH(ADDR_WIDTH),
        .SYSTEM_CLOCK_HZ(10_000_000),
        .ADC_CLOCK_HZ(1_000_000)
    ) streamer_i (
        .clk(clk_10m),
        .reset(reset),
        .start(stream_start),
        .mem_addr(mem_raddr),
        .mem_data(mem_rdata),
        .uart_start(uart_start),
        .uart_data(uart_data),
        .uart_busy(uart_busy),
        .busy(streamer_busy),
        .done(streamer_done)
    );

    uart_tx #(
        .CLOCK_HZ(10_000_000),
        .BAUD(1_000_000)
    ) uart_i (
        .clk(clk_10m),
        .reset(reset),
        .start(uart_start),
        .data(uart_data),
        .tx(uart_tx_line),
        .busy(uart_busy)
    );

    assign uart_txd_in = uart_tx_line;
    assign led[0] = (control_state == CTRL_CAPTURE);
    assign led[1] = (control_state == CTRL_STREAM) ||
                    (control_state == CTRL_DONE);

    always @(posedge clk_10m) begin
        capture_arm <= 1'b0;
        stream_start <= 1'b0;

        if (reset) begin
            control_state <= CTRL_WAIT;
            adc_clock_run <= 1'b0;
            adc_en        <= 1'b0;
        end else begin
            case (control_state)
                CTRL_WAIT: begin
                    adc_clock_run <= 1'b0;
                    adc_en        <= 1'b0;
                    if (start_rise) begin
                        capture_arm  <= 1'b1;
                        adc_clock_run <= 1'b1;
                        adc_en        <= 1'b1;
                        control_state <= CTRL_CAPTURE;
                    end
                end

                CTRL_CAPTURE: begin
                    if (capture_done) begin
                        adc_clock_run <= 1'b0;
                        adc_en        <= 1'b0;
                        stream_start  <= 1'b1;
                        control_state <= CTRL_STREAM;
                    end
                end

                CTRL_STREAM: begin
                    if (streamer_done)
                        control_state <= CTRL_DONE;
                end

                CTRL_DONE: begin
                    if (start_rise) begin
                        capture_arm   <= 1'b1;
                        adc_clock_run <= 1'b1;
                        adc_en        <= 1'b1;
                        control_state <= CTRL_CAPTURE;
                    end
                end

                default: control_state <= CTRL_WAIT;
            endcase
        end
    end
endmodule

`default_nettype wire
