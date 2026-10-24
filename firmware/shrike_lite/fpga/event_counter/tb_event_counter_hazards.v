`timescale 1ns/1ps

// Adversarial companion to tb_event_counter.v.
//
// 1. An event during a read must NOT alter the snapshot already being shifted.
// 2. A host pause longer than the FPGA idle reload interval WILL replace the
//    shift register mid-read. The test reports that hazard explicitly; the
//    physical host must bound every bit interval below 1 ms (IDLE_CYCLES/50MHz).
module tb_event_counter_hazards;
    localparam integer IDLE_CYCLES = 64;
    localparam integer CLK_HALF_NS = 10;
    localparam integer BIT_NS = 200;

    reg clk = 0;
    reg event_in = 0;
    reg rd_clk = 0;
    wire rd_data;
    wire rd_data_en;
    wire clk_en;

    reg [63:0] expected_old;
    reg [63:0] second_snapshot;
    reg [63:0] expected_current;
    reg [63:0] coherence_bits;
    reg [63:0] hazard_bits;
    integer i;
    integer errors = 0;

    specter_sync_event_counter #(.IDLE_CYCLES(IDLE_CYCLES)) dut (
        .clk(clk), .event_in(event_in), .rd_clk(rd_clk),
        .rd_data(rd_data), .rd_data_en(rd_data_en), .clk_en(clk_en)
    );

    always #CLK_HALF_NS clk = ~clk;

    task read_bit;
        begin
            #BIT_NS rd_clk = 1;
            #BIT_NS rd_clk = 0;
        end
    endtask

    initial begin
        // Post-configuration zero state for deterministic simulation.
        dut.timestamp = 32'd0;
        dut.last_timestamp = 32'd0;
        dut.event_count = 32'd0;
        dut.event_sync = 3'd0;
        dut.rd_sync = 3'd0;
        dut.idle_count = 32'd0;
        dut.shift_reg = 64'd0;
        dut.shift_count = 7'd0;

        // First event, then let the idle snapshot load.
        #2000 event_in = 1;
        #400 event_in = 0;
        #2000;
        repeat (IDLE_CYCLES * 3) @(posedge clk);
        expected_old = {dut.event_count, dut.last_timestamp};

        // Read 64 bits, injecting a second event after ten bits. The event
        // must be excluded from this already-loaded snapshot.
        coherence_bits = 64'd0;
        for (i = 0; i < 64; i = i + 1) begin
            coherence_bits = {coherence_bits[62:0], rd_data};
            read_bit();
            if (i == 9) begin
                event_in = 1;
                #400 event_in = 0;
            end
        end
        if (coherence_bits !== expected_old) begin
            $display("FAIL: event during read altered the shifted snapshot");
            errors = errors + 1;
        end else begin
            $display("PASS: event during read left the active snapshot coherent");
        end

        // The next idle reload must include the second event.
        repeat (IDLE_CYCLES * 3) @(posedge clk);
        second_snapshot = 64'd0;
        for (i = 0; i < 64; i = i + 1) begin
            second_snapshot = {second_snapshot[62:0], rd_data};
            read_bit();
        end
        if (second_snapshot[63:32] !== 32'd2) begin
            $display("FAIL: post-event snapshot count %0d != 2", second_snapshot[63:32]);
            errors = errors + 1;
        end

        // Start a read, pause beyond the idle threshold, then finish it. This
        // deliberately corrupts the word; the test passes only if the hazard
        // is observed.
        repeat (IDLE_CYCLES * 3) @(posedge clk);
        expected_current = {dut.event_count, dut.last_timestamp};
        hazard_bits = 64'd0;
        for (i = 0; i < 20; i = i + 1) begin
            hazard_bits = {hazard_bits[62:0], rd_data};
            read_bit();
        end
        repeat (IDLE_CYCLES * 2) @(posedge clk);  // > idle reload interval
        for (i = 20; i < 64; i = i + 1) begin
            hazard_bits = {hazard_bits[62:0], rd_data};
            read_bit();
        end
        if (hazard_bits === expected_current) begin
            $display("FAIL: mid-read idle reload was not reproduced");
            errors = errors + 1;
        end else begin
            $display("PASS: mid-read pause reproduces a non-coherent mixed snapshot");
        end

        if (errors == 0) begin
            $display("PASS: event-counter CDC/idle hazard controls");
        end else begin
            $display("FAIL: %0d hazard checks failed", errors);
        end
        $finish;
    end

    initial begin
        #500000;
        $display("FAIL: hazard simulation timeout");
        $finish;
    end

endmodule
