// SPECTER-SYNC Phase 0 event counter (design only; not hardware-validated).
//
// Event input: F1 on the Shrike Lite header (3.3 V CMOS only).
// Readout:     F18 read clock input from RP2040 GPIO14;
//              F17 serial data output to RP2040 GPIO15.
//
// The counter runs on the FPGA's nominal internal 50 MHz oscillator. The
// oscillator is UNVERIFIED and uncalibrated; 20 ns is a nominal tick, not an
// accuracy claim. The 32-bit counter wraps every ~85.9 s at nominal frequency.
//
// Readout protocol:
//   - hold read clock low for > IDLE_CYCLES/50MHz seconds;
//   - FPGA reloads {event_count, last_timestamp};
//   - host samples data while clock is low and raises the clock for each bit;
//   - 64 rising edges shift out event_count[31:0] then timestamp[31:0].
//
// The host must stop and wait for the idle reload before a new snapshot.

(* top *) module specter_sync_event_counter #(
    parameter integer IDLE_CYCLES = 50000
) (
    (* iopad_external_pin, clkbuf_inhibit *) input clk,
    (* iopad_external_pin *) input event_in,
    (* iopad_external_pin *) input rd_clk,
    (* iopad_external_pin *) output rd_data,
    (* iopad_external_pin *) output rd_data_en,
    (* iopad_external_pin *) output clk_en
);

    reg [31:0] timestamp;
    reg [31:0] last_timestamp;
    reg [31:0] event_count;

    reg [2:0] event_sync;
    reg [2:0] rd_sync;
    reg [31:0] idle_count;
    reg [63:0] shift_reg;
    reg [6:0] shift_count;

    wire event_rise = event_sync[1] & ~event_sync[2];
    wire rd_rise = rd_sync[1] & ~rd_sync[2];
    wire idle_reload = (idle_count == IDLE_CYCLES - 1);

    assign clk_en = 1'b1;
    assign rd_data_en = 1'b1;
    assign rd_data = shift_reg[63];

    always @(posedge clk) begin
        timestamp <= timestamp + 32'd1;
    end

    always @(posedge clk) begin
        event_sync <= {event_sync[1:0], event_in};
    end

    always @(posedge clk) begin
        if (event_rise) begin
            event_count <= event_count + 32'd1;
            last_timestamp <= timestamp;
        end
    end

    always @(posedge clk) begin
        rd_sync <= {rd_sync[1:0], rd_clk};
    end

    always @(posedge clk) begin
        if (rd_rise) begin
            idle_count <= 32'd0;
        end else if (idle_count < IDLE_CYCLES - 1) begin
            idle_count <= idle_count + 32'd1;
        end
    end

    always @(posedge clk) begin
        if (rd_rise) begin
            if (shift_count < 7'd64) begin
                shift_reg <= {shift_reg[62:0], 1'b0};
                shift_count <= shift_count + 7'd1;
            end
        end else if (idle_reload) begin
            shift_reg <= {event_count, last_timestamp};
            shift_count <= 7'd0;
        end
    end

endmodule
