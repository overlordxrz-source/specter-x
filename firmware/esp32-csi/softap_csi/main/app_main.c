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
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "esp_csi_gain_ctrl.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "csi_output.h"
#include "dq_ring.h"
#include "lab_credentials.h"

static const char *TAG = "specter_csi";

/* --- frame classification --------------------------------------------------
 *
 * The Wi-Fi driver does not expose the 802.11 frame type, so the only
 * discriminator available for "did this frame carry a payload" is the
 * SIGNAL LENGTH. A frame with no payload is exactly 28 bytes - a 24-byte
 * MAC header plus the 4-byte frame check sequence - and every payload
 * frame observed on this link has been longer.
 *
 * The 29..32 band is counted SEPARATELY rather than guessed into either
 * side, because a short QoS null frame would land there and would
 * otherwise be silently counted as payload. The counts are reported on
 * the status line so the assumption can be audited on every run instead
 * of being trusted once.
 */
#define SIG_LEN_NULL_DATA_MAX 28
#define SIG_LEN_AMBIGUOUS_MAX 32

/* --- state ---------------------------------------------------------------- */

static dq_state_t *s_dq;
static uint8_t s_peer_mac[6];
static volatile bool s_peer_valid;
static portMUX_TYPE s_peer_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t s_csi_callbacks;
static volatile uint32_t s_csi_accepted;
static volatile uint32_t s_csi_rejected;
static volatile uint32_t s_frames_data;
static volatile uint32_t s_frames_null;
static volatile uint32_t s_frames_ambiguous;
static volatile int8_t s_last_rssi;
static volatile uint8_t s_last_channel;
static uint32_t s_seq;
static uint32_t s_queue_high_water;
static uint32_t s_flash_kb;
static uint32_t s_flash_phys_kb;
static bool s_header_printed;

/* --- the one output path --------------------------------------------------
 *
 * The captured evidence shows a status line cut in half with a second copy
 * of its own text spliced into the gap. That is what two writers and a
 * buffered stdio produce: fwrite() of a 500-byte line goes out in
 * stdio-sized chunks, and the other task's output lands between two of
 * them. The fix is not a bigger buffer, it is ONE write() per line:
 *
 *   * stdout is unbuffered, so a line is never split by the stdio layer;
 *   * every line - data, status and log - goes out through console_emit(),
 *     which issues a single write() for the whole line;
 *   * a mutex orders the lines, so a status line cannot appear in the
 *     middle of a data line.
 *
 * The write is then atomic as far as the UART driver is concerned, which
 * is what makes a record impossible to tear.
 */
static SemaphoreHandle_t s_out_lock;

static void console_emit(const char *buf, size_t len)
{
    if (buf == NULL || len == 0) {
        return;
    }
    if (s_out_lock != NULL) {
        xSemaphoreTake(s_out_lock, portMAX_DELAY);
    }
    size_t off = 0;
    while (off < len) {
        ssize_t n = write(fileno(stdout), buf + off, len - off);
        if (n <= 0) {
            break;      /* the port is gone; a stuck console must not wedge
                         * the radio */
        }
        off += (size_t)n;
    }
    if (s_out_lock != NULL) {
        xSemaphoreGive(s_out_lock);
    }
}

/* The IDF's own log lines go to stdout too, so they have to share the one
 * path or they can still land in the middle of a record. */
static int console_log_vprintf(const char *fmt, va_list args)
{
    char buf[512];
    int n = vsnprintf(buf, sizeof(buf), fmt, args);
    if (n <= 0) {
        return n;
    }
    if (n >= (int)sizeof(buf)) {
        /* Truncate, but terminate the line: a truncated log line must not
         * merge with the next one. */
        n = (int)sizeof(buf) - 1;
        buf[n - 1] = '\n';
    }
    console_emit(buf, (size_t)n);
    return n;
}

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

    /* Classify the frame. The driver gives no frame type, so the signal
     * length is the discriminator - and the counts are reported rather than
     * assumed. */
    if (rx->sig_len <= SIG_LEN_NULL_DATA_MAX) {
        s_frames_null++;
    } else if (rx->sig_len <= SIG_LEN_AMBIGUOUS_MAX) {
        s_frames_ambiguous++;
    } else {
        s_frames_data++;
    }

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
    char line[CSI_LINE_MAX + 2];
    dq_record_t rec;
    while (1) {
        if (!dq_pop(s_dq, &rec, 200)) {
            continue;
        }
        size_t n = csi_format_line(&rec, line, sizeof(line) - 1);
        if (n == 0) {
            continue;
        }
        /* The terminator goes in the SAME buffer, so the whole record -
         * payload and terminator - leaves in ONE write. The formatter has
         * already closed the quoted IQ tail, so the terminator must not
         * add another quote. */
        line[n] = '\n';
        console_emit(line, n + 1);

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
        /* "printed" must be what actually reached the wire, not what was
         * accepted: the difference is the rejections plus the queue losses,
         * and the preflight uses it to separate the two. The data/null/
         * ambiguous counts separate the frames that carried a payload from
         * the station's empty ones, which is a different question again. */
        size_t n = csi_format_status(line, sizeof(line) - 1, role, peer,
                                     s_last_channel, s_last_rssi,
                                     s_csi_callbacks, s_dq ? s_dq->written : 0,
                                     s_csi_rejected,
                                     s_frames_data, s_frames_null,
                                     s_frames_ambiguous, s_flash_kb,
                                     s_flash_phys_kb,
                                     s_dq ? s_dq->dropped_old : 0,
                                     s_dq ? s_dq->dropped_new : 0,
                                     s_dq ? uxQueueMessagesWaiting(s_dq->queue) : 0,
                                     s_queue_high_water);
        if (n) {
            line[n] = '\n';
            console_emit(line, n + 1);
        }
        (void)last;
    }
}

/* --- the lab credential ---------------------------------------------------- */

/* The passphrase is compiled in from a generated header that the build puts
 * in the BUILD DIRECTORY, so it never enters the source tree and never
 * reaches Git. The image that carries it is therefore a SECRET ARTEFACT:
 * anyone holding it can associate with the lab network. The flash backups
 * taken before this change contain no credential and stay safe. */
static const char *lab_credential(void)
{
    if (SPECTER_LAB_PSK[0] != '\0') {
        return SPECTER_LAB_PSK;
    }
    return NULL;
}

static const char *lab_auth_mode(void)
{
    return (lab_credential() != NULL) ? "WPA2" : "OPEN";
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
    const char *cred = lab_credential();
    if (cred != NULL) {
        memcpy(cfg.ap.password, cred, strlen(cred));
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
    if (cred != NULL) {
        ESP_LOGI(TAG, "SoftAP '%s' on channel %u, %s, waiting for a station",
                 CONFIG_SPECTER_LAB_SSID, CONFIG_SPECTER_LAB_CHANNEL,
                 lab_auth_mode());
    } else {
        /* An open lab network is a deliberate, exceptional choice. Say so
         * loudly, every boot, because it is invisible from the outside. */
        ESP_LOGW(TAG, "SoftAP '%s' is OPEN - no credential was compiled in. "
                 "The build refuses to do this by default.",
                 CONFIG_SPECTER_LAB_SSID);
    }
}
#else
static void wifi_station_start(void)
{
    wifi_config_t cfg = { 0 };
    memcpy(cfg.sta.ssid, CONFIG_SPECTER_LAB_SSID, strlen(CONFIG_SPECTER_LAB_SSID));
    const char *cred = lab_credential();
    if (cred != NULL) {
        memcpy(cfg.sta.password, cred, strlen(cred));
    }
    cfg.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &cfg));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "station: scanning for '%s' (%s)", CONFIG_SPECTER_LAB_SSID,
             lab_auth_mode());
}
#endif

/* esp_event_base_t is itself a pointer (const char *), so the handler takes
 * it by value - declaring it as esp_event_base_t * made every
 * `base == WIFI_EVENT` comparison a comparison of distinct pointer types. */
static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t id, void *data)
{
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
#if !CONFIG_SPECTER_ROLE_SOFTAP
        /* esp_wifi_start() brings the station up with the configured AP, so
         * there is nothing to scan for and a scan would only delay the link. */
        esp_wifi_connect();
#endif
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
        wifi_event_sta_connected_t *e = (wifi_event_sta_connected_t *)data;
        peer_set(e->bssid);
        ESP_LOGI(TAG, "peer %02x:%02x:%02x:%02x:%02x:%02x connected",
                 e->bssid[0], e->bssid[1], e->bssid[2],
                 e->bssid[3], e->bssid[4], e->bssid[5]);
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        /* The campus link's failure mode was a disconnect followed by five
         * minutes of CSI silence (checkpoint 011). A lab link must not
         * inherit that: reconnect, and say so in the log. */
        ESP_LOGW(TAG, "peer disconnected - reconnecting");
        esp_wifi_connect();
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
    /* ONE output path, set up before anything can print. stdout is
     * unbuffered so that a line is never split by the stdio layer, and the
     * IDF's log lines are routed through the same writer so they cannot
     * land in the middle of a record. */
    setvbuf(stdout, NULL, _IONBF, 0);
    s_out_lock = xSemaphoreCreateMutex();
    if (s_out_lock != NULL) {
        esp_log_set_vprintf(console_log_vprintf);
    }

    /* The flash size the runtime actually has, and the size the chip
     * physically has. The app image header says 16 MB, but the size the
     * ROM gives the driver comes from the BOOTLOADER's header, and the
     * bootloader in this device was built for 2 MB - so the device runs
     * with a 2 MB flash and says so. Reporting both numbers is better
     * than leaving it to be inferred from a warning: the difference
     * between them is exactly the defect. */
    uint32_t runtime_bytes = 0;
    uint32_t physical_bytes = 0;
    if (esp_flash_get_size(esp_flash_default_chip, &runtime_bytes) == ESP_OK) {
        s_flash_kb = runtime_bytes / 1024;
    }
    if (esp_flash_get_physical_size(esp_flash_default_chip, &physical_bytes)
        == ESP_OK) {
        s_flash_phys_kb = physical_bytes / 1024;
    }
    ESP_LOGI(TAG, "flash: %u kB available at runtime, %u kB on the chip",
             (unsigned)s_flash_kb, (unsigned)s_flash_phys_kb);
    if (s_flash_phys_kb > s_flash_kb) {
        ESP_LOGW(TAG,
                 "the runtime sees less flash than the chip has: the "
                 "BOOTLOADER's header decides, and this one says %u kB",
                 (unsigned)s_flash_kb);
    }

    /* NVS is not needed by this firmware: the lab credentials are compiled
     * in and the driver is told to keep its state in RAM, so the device does
     * not write to flash. It is initialised anyway because the Wi-Fi driver
     * may look for calibration data, and a corrupt NVS is repaired here
     * rather than allowed to abort the boot. */
    esp_err_t nvs = nvs_flash_init();
    if (nvs != ESP_OK) {
        ESP_LOGW(TAG, "nvs init: %s - erasing the nvs partition",
                 esp_err_to_name(nvs));
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    /* The netif must match the role. The station role needs a DHCP client;
     * the SoftAP role needs the AP netif, which is what gives the board
     * 192.168.4.1 and runs the DHCP server the Mac expects. Creating the
     * station netif in SoftAP mode leaves the AP with no IP stack at all,
     * so the Mac associates and then gets no address. */
#if CONFIG_SPECTER_ROLE_SOFTAP
    esp_netif_create_default_wifi_ap();
#else
    esp_netif_create_default_wifi_sta();
#endif

    /* esp_wifi_init() MUST come before set_mode / set_config / start. The
     * upstream example got it indirectly from example_connect(); this
     * firmware is standalone, so it has to do it itself. Without it every
     * esp_wifi_* call returns ESP_ERR_WIFI_NOT_INIT and ESP_ERROR_CHECK
     * aborts the boot - the board would reset in a loop. */
    wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));
    /* Keep the driver's state in RAM: nothing needs to survive a reboot,
     * and a research device should not be writing to flash. */
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

    s_dq = dq_create(CONFIG_SPECTER_CSI_QUEUE_DEPTH, true);
    ESP_ERROR_CHECK(s_dq ? ESP_OK : ESP_ERR_NO_MEM);

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    /* The writer and the status task are started before the radio, so the
     * output path is ready before the first packet can arrive. */
    /* 6 KB: the line buffer is 2 KB after the HT40 case was allowed for. */
    xTaskCreate(writer_task, "csi_writer", 6144, NULL, 4, NULL);
    xTaskCreate(status_task, "csi_status", 3072, NULL, 3, NULL);

#if CONFIG_SPECTER_ROLE_SOFTAP
    wifi_softap_start();
#else
    wifi_station_start();
#endif
    wifi_csi_init();

    ESP_LOGI(TAG, "SPECTER-X controlled-link firmware ready");
    ESP_LOGI(TAG, "lab network %s, %s", CONFIG_SPECTER_LAB_SSID,
             lab_auth_mode());
    ESP_LOGI(TAG, "the wire format is Espressif's csi_recv_router, unchanged");
}
