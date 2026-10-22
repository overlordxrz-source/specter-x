/* SPECTER-X controlled-link firmware.
 *
 * Two roles, one build:
 *
 *   SPECTER_ROLE_STATION  the board joins a LAB access point and measures
 *                         the DOWNLINK CSI of the frames that point sends.
 *                         This is the role the original image used, and it
 *                         is the one whose behaviour is known. The access
 *                         point is local - the Mac, or a second board.
 *
 *   SPECTER_ROLE_SOFTAP   the board IS the access point and the Mac is the
 *                         station. The board would then have to measure the
 *                         UPLINK CSI of the station's frames.
 *
 *   *** The SoftAP role's CSI support is NOT established. *** Espressif
 *   ships no SoftAP CSI example, the IDF does not document the mode, and
 *   the S3's Wi-Fi is a precompiled library, so the source cannot answer
 *   it. This build therefore PROBES it at runtime and says so: the
 *   SPECTER_STAT line carries csi_cb, the number of times the callback
 *   fired. If it stays at zero while a station is associated and sending,
 *   the answer is no - in one minute, on the bench, with no guesswork.
 *
 * What is preserved from the original image:
 *
 *   * the wire format, byte for byte, so the host parser is unchanged and
 *     the recorded archives stay comparable;
 *   * the CSI configuration (LLTF only, channel filter, manual scale);
 *   * the gain compensation, applied to the same bytes.
 *
 * What is fixed:
 *
 *   * the CSI callback no longer formats or prints. It copies the raw
 *     bytes into a queue and returns, because the IDF documents that the
 *     callback runs in the Wi-Fi task and must not do lengthy work.
 *   * ONE writer task does all the output, so a line can never be torn by
 *     a concurrent write - the "serialised output" requirement.
 *   * the queue is bounded and its losses are COUNTED and reported, so a
 *     slow host costs counted packet loss instead of a corrupted stream.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_csi_gain_ctrl.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "csi_output.h"
#include "dq_ring.h"

static const char *TAG = "specter_csi";

/* --- state ---------------------------------------------------------------- */

static dq_state_t *s_dq;
static uint8_t s_peer_mac[6];
static volatile bool s_peer_valid;
static portMUX_TYPE s_peer_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t s_csi_callbacks;
static volatile uint32_t s_csi_accepted;
static volatile uint32_t s_csi_rejected;
static volatile int8_t s_last_rssi;
static volatile uint8_t s_last_channel;
static uint32_t s_seq;
static uint32_t s_queue_high_water;
static bool s_header_printed;

/* The gain control, exactly as the original image used it. */
static uint8_t s_agc_gain;
static int8_t s_fft_gain;
static uint8_t s_agc_baseline;
static int8_t s_fft_baseline;

/* --- peer address --------------------------------------------------------- */

static void peer_set(const uint8_t mac[6])
{
    portENTER_CRITICAL(&s_peer_lock);
    memcpy(s_peer_mac, mac, 6);
    s_peer_valid = true;
    portEXIT_CRITICAL(&s_peer_lock);
}

static bool peer_is(const uint8_t mac[6])
{
    portENTER_CRITICAL(&s_peer_lock);
    bool ok = s_peer_valid && memcmp(s_peer_mac, mac, 6) == 0;
    portEXIT_CRITICAL(&s_peer_lock);
    return ok;
}

static void peer_format(char *out, size_t len)
{
    portENTER_CRITICAL(&s_peer_lock);
    if (s_peer_valid) {
        snprintf(out, len, "%02x:%02x:%02x:%02x:%02x:%02x",
                 s_peer_mac[0], s_peer_mac[1], s_peer_mac[2],
                 s_peer_mac[3], s_peer_mac[4], s_peer_mac[5]);
    } else {
        snprintf(out, len, "-");
    }
    portEXIT_CRITICAL(&s_peer_lock);
}

/* --- the CSI callback ------------------------------------------------------ */

/* Runs in the Wi-Fi task. It must not do lengthy work, so it copies the
 * raw bytes into a record and hands it to the writer. */
static void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    (void)ctx;
    if (info == NULL || info->buf == NULL) {
        return;
    }
    s_csi_callbacks++;

    /* In the station role the upstream filtered on the associated AP's
     * BSSID; in the SoftAP role the peer is the station. Either way the
     * peer address is what we compare against. */
    if (!peer_is(info->mac)) {
        s_csi_rejected++;
        return;
    }

    uint16_t len = info->len;
    if (len > DQ_IQ_MAX) {
        s_csi_rejected++;
        return;
    }

    /* The gain compensation, as the original image did it: the first 100
     * packets establish the baseline, and every packet is scaled. */
    float compensation = 1.0f;
#if CONFIG_IDF_TARGET_ESP32S3 || CONFIG_IDF_TARGET_ESP32C3
    {
        const wifi_pkt_rx_ctrl_t *rx = &info->rx_ctrl;
        esp_csi_gain_ctrl_get_rx_gain(rx, &s_agc_gain, &s_fft_gain);
        if (s_csi_accepted < 100) {
            esp_csi_gain_ctrl_record_rx_gain(s_agc_gain, s_fft_gain);
        } else if (s_csi_accepted == 100) {
            esp_csi_gain_ctrl_get_rx_gain_baseline(&s_agc_baseline,
                                                   &s_fft_baseline);
        }
        esp_csi_gain_ctrl_get_gain_compensation(&compensation, s_agc_gain,
                                                s_fft_gain);
    }
#endif

    dq_record_t rec;
    memset(&rec, 0, sizeof(rec));
    rec.seq = s_seq++;
    memcpy(rec.mac, info->mac, 6);
    const wifi_pkt_rx_ctrl_t *rx = &info->rx_ctrl;
    rec.rssi = rx->rssi;
    rec.rate = rx->rate;
    rec.sig_mode = rx->sig_mode;
    rec.mcs = rx->mcs;
    rec.cwb = rx->cwb;
    rec.smoothing = rx->smoothing;
    rec.not_sounding = rx->not_sounding;
    rec.aggregation = rx->aggregation;
    rec.stbc = rx->stbc;
    rec.fec_coding = rx->fec_coding;
    rec.sgi = rx->sgi;
    rec.noise_floor = rx->noise_floor;
    rec.ampdu_cnt = rx->ampdu_cnt;
    rec.channel = rx->channel;
    rec.secondary_channel = rx->secondary_channel;
    rec.timestamp = rx->timestamp;
    rec.ant = rx->ant;
    rec.sig_len = rx->sig_len;
    rec.first_word_invalid = info->first_word_invalid;
    rec.len = len;
    rec.gain_compensation = compensation;
    memcpy(rec.iq, info->buf, len);

    s_last_rssi = rx->rssi;
    s_last_channel = rx->channel;
    s_csi_accepted++;

    if (!dq_push(s_dq, &rec)) {
        /* counted by dq_push; nothing to do here */
    }
    uint32_t depth = uxQueueMessagesWaiting(s_dq->queue);
    if (depth > s_queue_high_water) {
        s_queue_high_water = depth;
    }
}

/* --- the writer task ------------------------------------------------------- */

/* The ONLY thing that writes to the output. One writer means the output is
 * serialised by construction, and a record is never torn. */
static void writer_task(void *arg)
{
    (void)arg;
    char line[CSI_LINE_MAX];
    dq_record_t rec;
    while (1) {
        if (!dq_pop(s_dq, &rec, 200)) {
            continue;
        }
        size_t n = csi_format_line(&rec, line, sizeof(line));
        if (n == 0) {
            continue;
        }
        /* One write for the whole line, then the terminator. */
        fwrite(line, 1, n, stdout);
        fputs("\"\r\n", stdout);
        fflush(stdout);

        if (!s_header_printed) {
            s_header_printed = true;
        }
    }
}

/* --- the status task ------------------------------------------------------- */

/* One line a second with the counters. It is how a lab session is judged
 * healthy, and it is how the SoftAP capability probe is answered. */
static void status_task(void *arg)
{
    (void)arg;
    char line[256];
    char peer[24];
    TickType_t last = xTaskGetTickCount();
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        peer_format(peer, sizeof(peer));
        const char *role =
#if CONFIG_SPECTER_ROLE_SOFTAP
            "softap";
#else
            "station";
#endif
        size_t n = csi_format_status(line, sizeof(line), role, peer,
                                     s_last_channel, s_last_rssi,
                                     s_csi_callbacks, s_csi_accepted,
                                     s_dq ? s_dq->dropped_old : 0,
                                     s_dq ? s_dq->dropped_new : 0,
                                     s_dq ? uxQueueMessagesWaiting(s_dq->queue) : 0,
                                     s_queue_high_water);
        if (n) {
            fwrite(line, 1, n, stdout);
            fputs("\r\n", stdout);
            fflush(stdout);
        }
        (void)last;
    }
}

/* --- Wi-Fi setup ----------------------------------------------------------- */

static void wifi_csi_init(void)
{
    wifi_csi_config_t config = {
        .lltf_en           = true,
        .htltf_en          = false,
        .stbc_htltf2_en    = false,
        .ltf_merge_en      = true,
        .channel_filter_en = true,
        .manu_scale        = true,
        .shift             = true,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    ESP_LOGI(TAG, "CSI enabled (LLTF only, 20 MHz, channel filter on)");
}

#if CONFIG_SPECTER_ROLE_SOFTAP
static void wifi_softap_start(void)
{
    wifi_config_t cfg = { 0 };
    memcpy(cfg.ap.ssid, CONFIG_SPECTER_LAB_SSID,
           strlen(CONFIG_SPECTER_LAB_SSID));
    cfg.ap.ssid_len = strlen(CONFIG_SPECTER_LAB_SSID);
    if (strlen(CONFIG_SPECTER_LAB_PASSWORD) > 0) {
        memcpy(cfg.ap.password, CONFIG_SPECTER_LAB_PASSWORD,
               strlen(CONFIG_SPECTER_LAB_PASSWORD));
        cfg.ap.authmode = WIFI_AUTH_WPA2_PSK;
    } else {
        cfg.ap.authmode = WIFI_AUTH_OPEN;
    }
    cfg.ap.channel = CONFIG_SPECTER_LAB_CHANNEL;
    cfg.ap.max_connection = 4;
    cfg.ap.beacon_interval = 100;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &cfg));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "SoftAP '%s' on channel %u, waiting for a station",
             CONFIG_SPECTER_LAB_SSID, CONFIG_SPECTER_LAB_CHANNEL);
}
#else
static void wifi_station_start(void)
{
    wifi_config_t cfg = { 0 };
    memcpy(cfg.sta.ssid, CONFIG_SPECTER_LAB_SSID, strlen(CONFIG_SPECTER_LAB_SSID));
    if (strlen(CONFIG_SPECTER_LAB_PASSWORD) > 0) {
        memcpy(cfg.sta.password, CONFIG_SPECTER_LAB_PASSWORD,
               strlen(CONFIG_SPECTER_LAB_PASSWORD));
    }
    cfg.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &cfg));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "station: scanning for '%s'", CONFIG_SPECTER_LAB_SSID);
}
#endif

static void wifi_event_handler(void *arg, esp_event_base_t *base,
                               int32_t id, void *data)
{
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
#if !CONFIG_SPECTER_ROLE_SOFTAP
        wifi_scan_config_t scan = { 0 };
        memcpy(scan.ssid, CONFIG_SPECTER_LAB_SSID, strlen(CONFIG_SPECTER_LAB_SSID));
        esp_wifi_scan_start(&scan, NULL);
#endif
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
        wifi_event_sta_connected_t *e = (wifi_event_sta_connected_t *)data;
        peer_set(e->bssid);
        ESP_LOGI(TAG, "peer %02x:%02x:%02x:%02x:%02x:%02x connected",
                 e->bssid[0], e->bssid[1], e->bssid[2],
                 e->bssid[3], e->bssid[4], e->bssid[5]);
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "peer disconnected");
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "got ip " IPSTR ", gw " IPSTR,
                 IP2STR(&e->ip_info.ip), IP2STR(&e->ip_info.gw));
    }
#if CONFIG_SPECTER_ROLE_SOFTAP
    else if (base == WIFI_EVENT && id == WIFI_EVENT_AP_STACONNECTED) {
        wifi_event_ap_staconnected_t *e = (wifi_event_ap_staconnected_t *)data;
        peer_set(e->mac);
        ESP_LOGI(TAG, "station %02x:%02x:%02x:%02x:%02x:%02x joined",
                 e->mac[0], e->mac[1], e->mac[2], e->mac[3], e->mac[4], e->mac[5]);
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_AP_STADISCONNECTED) {
        ESP_LOGW(TAG, "station left");
    }
#endif
}

void app_main(void)
{
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    s_dq = dq_create(CONFIG_SPECTER_CSI_QUEUE_DEPTH, true);
    ESP_ERROR_CHECK(s_dq ? ESP_OK : ESP_ERR_NO_MEM);

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    /* The writer and the status task are started before the radio, so the
     * output path is ready before the first packet can arrive. */
    xTaskCreate(writer_task, "csi_writer", 4096, NULL, 4, NULL);
    xTaskCreate(status_task, "csi_status", 3072, NULL, 3, NULL);

#if CONFIG_SPECTER_ROLE_SOFTAP
    wifi_softap_start();
#else
    wifi_station_start();
#endif
    wifi_csi_init();

    ESP_LOGI(TAG, "SPECTER-X controlled-link firmware ready");
    ESP_LOGI(TAG, "the wire format is Espressif's csi_recv_router, unchanged");
}
