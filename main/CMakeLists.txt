idf_component_register(SRCS "main.c" "wifi_logger.c" "ota_server.c"
                       INCLUDE_DIRS "."
                       REQUIRES nvs_flash esp_wifi app_update mdns)
