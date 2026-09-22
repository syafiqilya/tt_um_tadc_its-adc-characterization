`timescale 1ns / 1ps
`default_nettype none

module tb_tadc_cmod_a7_top;
    localparam integer SAMPLE_COUNT = 8;
    localparam integer TOTAL_BYTES  = 16 + 16 * SAMPLE_COUNT;

    reg clk = 1'b0;
    reg btn_reset = 1'b0;
    reg btn_start = 1'b0;
    reg adc_cko = 1'b0;
    reg [8:0] adc_data = 9'd0;
    wire adc_clk;
    wire adc_en;
    wire uart_tx;
    wire [1:0] led;

    reg [7:0] received [0:TOTAL_BYTES-1];
    integer received_count = 0;
    integer adc_edge_count = 0;
    integer generated_code = 0;
    integer i;
    reg [7:0] rx_byte;

    // Simulation bypasses the MMCM, so clk is already 10 MHz.
    always #50 clk = ~clk;

    tadc_cmod_a7_top #(
        .INPUT_CLOCK_HZ(12_000_000),
        .SAMPLE_COUNT(SAMPLE_COUNT),
        .ADDR_WIDTH(3)
    ) dut (
        .sysclk(clk),
        .btn_reset(btn_reset),
        .btn_start(btn_start),
        .adc_clk(adc_clk),
        .adc_en(adc_en),
        .adc_cko(adc_cko),
        .adc_data(adc_data),
        .uart_txd_in(uart_tx),
        .led(led)
    );

    // Behavioral ADC: emit one result for every 26 ADC rising edges.
    always @(posedge adc_clk) begin
        if (!adc_en) begin
            adc_edge_count <= 0;
        end else if (adc_edge_count == 25) begin
            adc_edge_count <= 0;
            generated_code <= generated_code + 1;
            fork
                begin
                    #120;
                    adc_data <= generated_code[8:0] + 9'd1;
                    adc_cko  <= 1'b1;
                    #400;
                    adc_cko  <= 1'b0;
                end
            join_none
        end else begin
            adc_edge_count <= adc_edge_count + 1;
        end
    end

    // UART decoder at 1 Mbaud: sample in the center of each data bit.
    always begin
        @(negedge uart_tx);
        #1500;
        for (i = 0; i < 8; i = i + 1) begin
            rx_byte[i] = uart_tx;
            #1000;
        end
        #500;
        if (received_count < TOTAL_BYTES) begin
            received[received_count] = rx_byte;
            received_count = received_count + 1;
        end
    end

    initial begin
        $dumpfile("tadc_cmod_a7.vcd");
        $dumpvars(0, tb_tadc_cmod_a7_top);

        #500;
        btn_reset = 1'b1;
        #500;
        btn_reset = 1'b0;
        #1000;
        btn_start = 1'b1;
        #500;
        btn_start = 1'b0;

        wait (received_count == TOTAL_BYTES);
        #2000;

        if (received[0] !== 8'h54 || received[1] !== 8'h41 ||
            received[2] !== 8'h44 || received[3] !== 8'h43) begin
            $display("FAIL: stream header magic is wrong");
            $fatal(1, "stream header magic is wrong");
        end

        if (received[4] !== 8'h01 || received[5] !== 8'd16 ||
            received[6] !== SAMPLE_COUNT[7:0]) begin
            $display("FAIL: stream header fields are wrong");
            $fatal(1, "stream header fields are wrong");
        end

        for (i = 0; i < SAMPLE_COUNT; i = i + 1) begin
            if (received[16 + i*16] !== 8'ha5 ||
                received[17 + i*16] !== 8'h5a) begin
                $display("FAIL: record %0d sync word is wrong", i);
                $fatal(1, "record sync word is wrong");
            end
            if (received[18 + i*16] !== i[7:0]) begin
                $display("FAIL: record %0d sequence is wrong", i);
                $fatal(1, "record sequence is wrong");
            end
            if (received[20 + i*16] !== (i[7:0] + 8'd1)) begin
                $display("FAIL: record %0d ADC code is wrong", i);
                $fatal(1, "record ADC code is wrong");
            end
        end

        $display("PASS: captured and transmitted %0d ADC records", SAMPLE_COUNT);
        $finish;
    end

    initial begin
        #10_000_000;
        $display("FAIL: simulation timeout");
        $fatal(1, "simulation timeout");
    end
endmodule

`default_nettype wire
