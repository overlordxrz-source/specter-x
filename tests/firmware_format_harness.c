/* Host harness for the firmware's wire formatter.
 *
 * It compiles the REAL `firmware/esp32-csi/softap_csi/main/csi_output.c`
 * against a two-line FreeRTOS stub and prints exactly what the device
 * would print. `tests/test_firmware_format_native.py` then parses that
 * output with the REAL host parser.
 *
 * That is the only way to prove the wire format without hardware: the C
 * code runs, and its bytes are fed to the Python that will read them.
 */
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "csi_output.h"

static void fill(dq_record_t *r, uint32_t seq, uint16_t len, bool fwi)
{
    memset(r, 0, sizeof(*r));
    r->seq = seq;
    const uint8_t mac[6] = { 0xb8, 0x62, 0x1f, 0xe5, 0xac, 0x62 };
    memcpy(r->mac, mac, 6);
    r->rssi = -62;
    r->rate = 11;
    r->sig_mode = 1;
    r->mcs = 6;
    r->cwb = 0;
    r->smoothing = 0;
    r->not_sounding = 1;
    r->aggregation = 0;
    r->stbc = 0;
    r->fec_coding = 0;
    r->sgi = 1;
    r->noise_floor = -96;
    r->ampdu_cnt = 0;
    r->channel = 6;
    r->secondary_channel = 0;
    r->timestamp = 3122514817u;   /* the real packet that broke %d */
    r->ant = 0;
    r->sig_len = 67;
    r->first_word_invalid = fwi;
    r->len = len;
    r->gain_compensation = 1.0f;
    for (uint16_t i = 0; i < len; i++) {
        r->iq[i] = (int8_t)((i % 5) - 2);
    }
}

static void emit(const dq_record_t *r)
{
    char line[CSI_LINE_MAX];
    size_t n = csi_format_line(r, line, sizeof(line));
    if (n == 0) {
        printf("FORMAT_FAILED\n");
        return;
    }
    /* the same terminator the writer task uses: a newline, and nothing
     * else - the formatter already closed the quoted IQ tail. */
    fwrite(line, 1, n, stdout);
    fputs("\n", stdout);
}

int main(void)
{
    printf("%s\n", csi_output_header());

    dq_record_t a;
    fill(&a, 42, 128, false);
    emit(&a);

    dq_record_t b;
    fill(&b, 43, 4, true);
    b.gain_compensation = 0.5f;
    b.iq[0] = 10;
    b.iq[1] = -20;
    b.iq[2] = 30;
    b.iq[3] = -40;
    emit(&b);

    /* the HT40 case: 256 CSI bytes, which is a much longer line */
    dq_record_t c;
    fill(&c, 44, 256, false);
    emit(&c);

    char status[256];
    size_t n = csi_format_status(status, sizeof(status), "softap",
                                 "b8:62:1f:e5:ac:62", 6, -62,
                                 1200, 1180, 5, 980, 200, 0, 16384,
                                 16384, 0, 0, 2, 7);
    if (n) {
        fwrite(status, 1, n, stdout);
        fputs("\n", stdout);
    }
    return 0;
}
