// Shrike Lite FPGA proof-of-life: blink the onboard FPGA LED on F16.
//
// Follows the manufacturer's Verilog attributes and output-enable convention:
//   https://vicharak-in.github.io/shrike/verilog_style_guide.html
//
// Do not generate/load a bitstream until the board revision and electrical
// setup have been reviewed. Nominal 50 MHz oscillator, divider ~1 Hz.

(* top *) module specter_sync_blink (
    (* iopad_external_pin, clkbuf_inhibit *) input clk,
    (* iopad_external_pin *) output led,
    (* iopad_external_pin *) output led_en,
    (* iopad_external_pin *) output clk_en
);

    reg [31:0] divider = 32'd0;
    reg led_state = 1'b0;

    assign led_en = 1'b1;
    assign clk_en = 1'b1;

    always @(posedge clk) begin
        if (divider == 32'd24_999_999) begin
            divider <= 32'd0;
            led_state <= ~led_state;
        end else begin
            divider <= divider + 32'd1;
        end
    end

    assign led = led_state;

endmodule
