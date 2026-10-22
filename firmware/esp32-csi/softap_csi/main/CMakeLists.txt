idf_component_register(
    SRCS "app_main.c"
          "dq_ring.c"
          "csi_output.c"
    INCLUDE_DIRS "."
    REQUIRES esp_wifi esp_netif esp_event nvs_flash lwip
)
