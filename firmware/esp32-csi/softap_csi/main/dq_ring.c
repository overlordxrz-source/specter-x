#include "dq_ring.h"

#include <stdlib.h>
#include <string.h>

dq_state_t *dq_create(uint32_t depth, bool drop_oldest)
{
    dq_state_t *st = (dq_state_t *)calloc(1, sizeof(dq_state_t));
    if (st == NULL) {
        return NULL;
    }
    st->queue = xQueueCreate(depth, sizeof(dq_record_t));
    if (st->queue == NULL) {
        free(st);
        return NULL;
    }
    (void)drop_oldest;
    return st;
}

bool dq_push(dq_state_t *st, const dq_record_t *rec)
{
    if (st == NULL || st->queue == NULL) {
        return false;
    }
    st->pushed++;

    /* The queue must never make the Wi-Fi task wait. Try to take a slot;
     * if there is none, decide what to lose. */
    if (xQueueSend(st->queue, rec, 0) == pdTRUE) {
        return true;
    }

    /* The queue is full. For a live time series the newest data is the
     * useful data, so the OLDEST record is the one that goes - and the loss
     * is counted, never silent. */
    dq_record_t discard;
    if (xQueueReceive(st->queue, &discard, 0) == pdTRUE) {
        st->dropped_old++;
        if (xQueueSend(st->queue, rec, 0) == pdTRUE) {
            return true;
        }
    }
    /* Even the drop-oldest path failed: the record is lost, and counted. */
    st->dropped_new++;
    return false;
}

bool dq_pop(dq_state_t *st, dq_record_t *out, uint32_t timeout_ms)
{
    if (st == NULL || st->queue == NULL) {
        return false;
    }
    if (xQueueReceive(st->queue, out, pdMS_TO_TICKS(timeout_ms)) == pdTRUE) {
        st->written++;
        return true;
    }
    return false;
}
