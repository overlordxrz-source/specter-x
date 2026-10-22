#include "csi_output.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

/* The line is built with an append helper rather than one big printf, so
 * the number of fields cannot drift out of step with the number of values.
 * The field order is Espressif's `csi_recv_router`, unchanged. */
typedef struct {
    char  *buf;
    size_t len;
    size_t cap;
    bool   overflow;
} line_t;

static void line_init(line_t *l, char *buf, size_t cap)
{
    l->buf = buf;
    l->len = 0;
    l->cap = cap;
    l->overflow = false;
    if (cap) {
        buf[0] = '\0';
    }
}

static void line_addf(line_t *l, const char *fmt, ...)
{
    if (l->overflow) {
        return;
    }
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(l->buf + l->len, l->cap - l->len, fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= l->cap - l->len) {
        l->overflow = true;
        return;
    }
    l->len += (size_t)n;
}

const char *csi_output_header(void)
{
    return "type,id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,"
           "not_sounding,aggregation,stbc,fec_coding,sgi,noise_floor,"
           "ampdu_cnt,channel,secondary_channel,local_timestamp,ant,sig_len,"
           "rx_format,len,first_word,data";
}

size_t csi_format_line(const dq_record_t *rec, char *out, size_t out_len)
{
    if (rec == NULL || out == NULL || out_len < 8) {
        return 0;
    }
    if (rec->len > DQ_IQ_MAX) {
        return 0;
    }

    line_t l;
    line_init(&l, out, out_len);

    line_addf(&l, "CSI_DATA,%" PRIu32 ",%02x:%02x:%02x:%02x:%02x:%02x",
              rec->seq,
              rec->mac[0], rec->mac[1], rec->mac[2],
              rec->mac[3], rec->mac[4], rec->mac[5]);
    /* 3..21: the radio metadata, in the upstream's order */
    line_addf(&l, ",%d", (int)rec->rssi);              /* rssi */
    line_addf(&l, ",%u", (unsigned)rec->rate);          /* rate */
    line_addf(&l, ",%u", (unsigned)rec->sig_mode);      /* sig_mode */
    line_addf(&l, ",%u", (unsigned)rec->mcs);           /* mcs */
    line_addf(&l, ",%u", (unsigned)rec->cwb);           /* cwb */
    line_addf(&l, ",%u", (unsigned)rec->smoothing);     /* smoothing */
    line_addf(&l, ",%u", (unsigned)rec->not_sounding);  /* not_sounding */
    line_addf(&l, ",%u", (unsigned)rec->aggregation);   /* aggregation */
    line_addf(&l, ",%u", (unsigned)rec->stbc);          /* stbc */
    line_addf(&l, ",%u", (unsigned)rec->fec_coding);    /* fec_coding */
    line_addf(&l, ",%u", (unsigned)rec->sgi);           /* sgi */
    line_addf(&l, ",%d", (int)rec->noise_floor);        /* noise_floor */
    line_addf(&l, ",%u", (unsigned)rec->ampdu_cnt);     /* ampdu_cnt */
    line_addf(&l, ",%u", (unsigned)rec->channel);       /* channel */
    line_addf(&l, ",%u", (unsigned)rec->secondary_channel); /* secondary_channel */
    line_addf(&l, ",%" PRIu32, rec->timestamp);         /* local_timestamp */
    line_addf(&l, ",%u", (unsigned)rec->ant);           /* ant */
    line_addf(&l, ",%u", (unsigned)rec->sig_len);       /* sig_len */
    /* The upstream prints sig_mode a SECOND time here, in the slot its
     * header calls "rx_format". The host parser documents it, so it is
     * preserved rather than "fixed". */
    line_addf(&l, ",%u", (unsigned)rec->sig_mode);          /* sig_mode */
    /* 22, 23 */
    line_addf(&l, ",%u,%u", (unsigned)rec->len,
              rec->first_word_invalid ? 1u : 0u);
    /* the IQ tail, quoted */
    line_addf(&l, ",\"[");
    for (uint16_t i = 0; i < rec->len; i++) {
        /* The same arithmetic as the upstream: the compensated value is
         * cast to int16_t and printed as a decimal. */
        int16_t v = (int16_t)(rec->gain_compensation * (float)rec->iq[i]);
        line_addf(&l, "%s%d", (i == 0) ? "" : ",", (int)v);
    }
    line_addf(&l, "]\"");
    if (l.overflow) {
        return 0;
    }
    return l.len;
}

size_t csi_format_status(char *out, size_t out_len, const char *role,
                          const char *peer_mac, uint8_t channel, int8_t rssi,
                          uint32_t csi_callbacks, uint32_t printed,
                          uint32_t rejected,
                          uint32_t frames_data, uint32_t frames_null,
                          uint32_t frames_ambiguous, uint32_t flash_kb,
                          uint32_t flash_phys_kb,
                          uint32_t dropped_old, uint32_t dropped_new,
                          uint32_t queue_depth, uint32_t queue_high_water)
{
    if (out == NULL || out_len == 0) {
        return 0;
    }
    line_t l;
    line_init(&l, out, out_len);
    line_addf(&l, "SPECTER_STAT,role=%s,peer=%s,ch=%u,rssi=%d",
              role ? role : "?", (peer_mac && peer_mac[0]) ? peer_mac : "-",
              (unsigned)channel, (int)rssi);
    /* The three counts that answer three different questions:
     *   csi_cb   how often the callback fired at all
     *   printed  how many records reached the wire
     *   rej      how many callbacks were rejected (not our peer, or too
     *             long) and therefore produced nothing
     * The frame counts split what did reach the wire into the frames that
     * carried a payload and the station's empty ones, so a host can stop
     * counting a null-data frame as if it were traffic. */
    line_addf(&l, ",csi_cb=%" PRIu32, csi_callbacks);
    line_addf(&l, ",printed=%" PRIu32, printed);
    line_addf(&l, ",rej=%" PRIu32, rejected);
    line_addf(&l, ",data=%" PRIu32, frames_data);
    line_addf(&l, ",null=%" PRIu32, frames_null);
    line_addf(&l, ",amb=%" PRIu32, frames_ambiguous);
    line_addf(&l, ",flash_kb=%" PRIu32, flash_kb);
    line_addf(&l, ",flash_phys_kb=%" PRIu32, flash_phys_kb);
    line_addf(&l, ",drop_old=%" PRIu32, dropped_old);
    line_addf(&l, ",drop_new=%" PRIu32, dropped_new);
    line_addf(&l, ",q=%" PRIu32, queue_depth);
    line_addf(&l, ",q_high=%" PRIu32, queue_high_water);
    if (l.overflow) {
        return 0;
    }
    return l.len;
}
