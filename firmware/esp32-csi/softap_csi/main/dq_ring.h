/* The record queue between the Wi-Fi callback and the writer.
 *
 * The ESP-IDF documentation is explicit about the constraint this exists to
 * satisfy:
 *
 *   "The CSI receiving callback function runs from Wi-Fi task. So, do not do
 *    lengthy operations in the callback function. Instead, post necessary
 *    data to a queue and handle it from a lower priority task."
 *
 * The original image printed the whole CSV line - 128 numbers formatted -
 * inside that callback. That is the behaviour behind the host-side
 * "packet loss" and "wedged link" in checkpoint 008: the Wi-Fi task was
 * blocked inside printf, so the CSI stopped being produced.
 *
 * Here the callback only copies the raw CSI bytes and the radio metadata
 * into a record and pushes it. The formatting happens in the writer task.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

#ifdef __cplusplus
extern "C" {
#endif

/*: The largest CSI buffer this build will carry, in bytes. The S3's
 *  802.11n 20 MHz LLTF is 128 bytes; 256 leaves room for an HT40 frame. */
#define DQ_IQ_MAX 256

/*: One CSI record: the radio metadata and the RAW CSI bytes, copied whole.
 *  The gain compensation is applied by the writer, not here, so the value
 *  that reaches the wire is the same value the original image printed. */
typedef struct {
    uint32_t seq;              /* the record counter, for gap detection */
    uint8_t  mac[6];           /* the source MAC of the CSI data */
    int8_t   rssi;
    uint8_t  rate;
    uint8_t  sig_mode;
    uint8_t  mcs;
    uint8_t  cwb;
    uint8_t  smoothing;
    uint8_t  not_sounding;
    uint8_t  aggregation;
    uint8_t  stbc;
    uint8_t  fec_coding;
    uint8_t  sgi;
    int8_t   noise_floor;
    uint8_t  ampdu_cnt;
    uint8_t  channel;
    uint8_t  secondary_channel;
    uint32_t timestamp;        /* the device's own microsecond counter */
    uint8_t  ant;
    uint16_t sig_len;
    bool     first_word_invalid;
    uint16_t len;              /* the valid CSI length, in BYTES */
    float    gain_compensation;/* the gain factor to apply to the bytes */
    int8_t   iq[DQ_IQ_MAX];
} dq_record_t;

/* --- the queue ------------------------------------------------------------ */

typedef struct {
    QueueHandle_t queue;
    uint32_t      pushed;       /* records the callback handed over */
    uint32_t      written;      /* records the writer formatted and printed */
    uint32_t      dropped_old;  /* the oldest record, dropped for a newer one */
    uint32_t      dropped_new;  /* the newest record, dropped for a full queue */
    uint32_t      malformed;    /* records the callback rejected */
} dq_state_t;

/*! Create the queue. Returns NULL on failure. */
dq_state_t *dq_create(uint32_t depth, bool drop_oldest);

/*! Hand a record to the writer. Never blocks: the Wi-Fi task must not be
 *  held up. Returns true if the record was queued. */
bool dq_push(dq_state_t *st, const dq_record_t *rec);

/*! Wait for a record. Returns false if the timeout expired. */
bool dq_pop(dq_state_t *st, dq_record_t *out, uint32_t timeout_ms);

#ifdef __cplusplus
}
#endif
