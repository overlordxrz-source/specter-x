# ESP32-S3 Wi-Fi CSI firmware (Stage 3)

Planned: ESP-IDF v5.x project based on Espressif's `esp-csi` examples
(https://github.com/espressif/esp-csi). The board runs as a station/sniffer,
enables `esp_wifi_set_csi(true)`, and streams one line per CSI callback over
USB-serial:

    CSI,<esp_timer_us>,<mac>,<rssi>,<channel>,<len>,<i0 q0 i1 q1 ...>

The host parser (`specter/sensors/wifi_csi`) turns these into Measurements with
`sensor="wifi_csi"`, `t_sensor` = ESP timer, and provenance = board MAC + firmware
git hash. Nothing here is built yet.
