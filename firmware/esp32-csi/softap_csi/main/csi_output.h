/* The wire format.
 *
 * This is Espressif's `csi_recv_router` line, reproduced exactly, so that
 * the host parser in specter/sensors/esp32/dispatcher.py needs no change
 * and the recorded archives stay comparable:
 *
 *   type,id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,not_sounding,
 *   aggregation,stbc,fec_coding,sgi,noise_floor,ampdu_cnt,channel,
 *   secondary_channel,local_timestamp,ant,sig_len,rx_format,len,first_word,data
 *
 *   CSI_DATA,<id>,<mac>,<19 values>,<len>,<first_word_invalid>,"[v,v,...]"
 *
 * Two upstream quirks are preserved on purpose, because the host parser
 * documents them:
 *
 *   * the "rx_format" slot (21) holds a SECOND copy of sig_mode - the
 *     upstream's printf passes sig_mode twice;
 *   * the values are the gain-compensated bytes, printed as decimals:
 *     (int16_t)(compensate_gain * (int8_t)buf[i]).
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "dq_ring.h"

#ifdef __cplusplus
extern "C" {
#endif

/*: The longest line this build can produce: 128 values of up to 5
 *  characters, plus the header fields. */
#define CSI_LINE_MAX 1024

/*! The CSV header the upstream prints once, before the first packet. */
const char *csi_output_header(void);

/*! Format one record as a wire line (without the terminator).
 *  Returns the number of bytes written, or 0 if the record is unusable. */
size_t csi_format_line(const dq_record_t *rec, char *out, size_t out_len);

/*! Format the periodic status line: the counters that say whether the
 *  link is healthy, including the queue's own losses. */
size_t csi_format_status(char *out, size_t out_len, const char *role,
                          const char *peer_mac, uint8_t channel, int8_t rssi,
                          uint32_t csi_callbacks, uint32_t printed,
                          uint32_t dropped_old, uint32_t dropped_new,
                          uint32_t queue_depth, uint32_t queue_high_water);

#ifdef __cplusplus
}
#endif
