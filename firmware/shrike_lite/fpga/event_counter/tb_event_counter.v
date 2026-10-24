`timescale 1ns/1ps

module tb_specter_sync_event_counter;
    localparam integer IDLE_CYCLES = 64;
    localparam integer CLK_HALF_NS = 10;  // nominal 50 MHz
    localparam integer BIT_NS = 200;

    reg clk = 0;
    reg event_in = 0;
    reg rd_clk = 0;
    wire rd_data;
    wire rd_data_en;
    wire clk_en;

    reg [63:0] snapshot;
    integer i;
    integer errors = 0;
    reg [31:0] first_event_ts;
    reg [31:0] second_event_ts;

    specter_sync_event_counter #(
        .IDLE_CYCLES(IDLE_CYCLES)
    ) dut (
        .clk(clk),
        .event_in(event_in),
        .rd_clk(rd_clk),
        .rd_data(rd_data),
        .rd_data_en(rd_data_en),
        .clk_en(clk_en)
    );

    always #CLK_HALF_NS clk = ~clk;

    task read_snapshot;
        begin
            // Wait long enough for the design's idle reload.
            repeat (IDLE_CYCLES * 3) @(posedge clk);
            snapshot = 64'd0;
            for (i = 0; i < 64; i = i + 1) begin
                snapshot = {snapshot[62:0], rd_data};
                #BIT_NS rd_clk = 1;
                #BIT_NS rd_clk = 0;
            end
            repeat (IDLE_CYCLES * 2) @(posedge clk);
        end
    endtask

    initial begin
        // Model the FPGA's post-configuration zero state for simulation.
        dut.timestamp = 32'd0;
        dut.last_timestamp = 32'd0;
        dut.event_count = 32'd0;
        dut.event_sync = 3'd0;
        dut.rd_sync = 3'd0;
        dut.idle_count = 32'd0;
        dut.shift_reg = 64'd0;
        dut.shift_count = 7'd0;

        if (clk_en !== 1'b1 || rd_data_en !== 1'b1) begin
            $display("FAIL: clock/data enables are not high");
            errors = errors + 1;
        end

        // First known pulse: 400 ns high, well above two 20 ns clocks.
        #2000 event_in = 1;
        #400 event_in = 0;
        #2000;
        read_snapshot();
        first_event_ts = snapshot[31:0];
        if (snapshot[63:32] !== dut.event_count) begin
            $display("FAIL: first snapshot event_count %0d != %0d",
                     snapshot[63:32], dut.event_count);
            errors = errors + 1;
        end
        if (snapshot[63:32] !== 32'd1) begin
            $display("FAIL: first event_count expected 1, got %0d", snapshot[63:32]);
            errors = errors + 1;
        end
        if (snapshot[31:0] !== dut.last_timestamp) begin
            $display("FAIL: first snapshot timestamp mismatch");
            errors = errors + 1;
        end

        // Second pulse after a known interval.
        #5000 event_in = 1;
        #400 event_in = 0;
        #2000;
        read_snapshot();
        second_event_ts = snapshot[31:0];
        if (snapshot[63:32] !== 32'd2) begin
            $display("FAIL: second event_count expected 2, got %0d", snapshot[63:32]);
            errors = errors + 1;
        end
        if (snapshot[31:0] !== dut.last_timestamp) begin
            $display("FAIL: second snapshot timestamp mismatch");
            errors = errors + 1;
        end
        if (second_event_ts <= first_event_ts) begin
            $display("FAIL: timestamp did not advance");
            errors = errors + 1;
        end

        // A third idle read must still produce the coherent latest snapshot.
        read_snapshot();
        if (snapshot[63:32] !== 32'd2) begin
            $display("FAIL: idle reread count expected 2, got %0d", snapshot[63:32]);
            errors = errors + 1;
        end

        if (errors == 0) begin
            $display("PASS: event counter snapshot, count and timestamp checks");
        end else begin
            $display("FAIL: %0d checks failed", errors);
        end
        $finish;
    end

endmodule
