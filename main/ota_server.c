#include <string.h>
#include <errno.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "esp_ota_ops.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "lwip/err.h"
#include "lwip/sockets.h"
#include "lwip/sys.h"
#include <lwip/netdb.h>

#include "ota_server.h"

#define OTA_TCP_PORT  3232
#define OTA_RECV_BUF  4096

static const char *TAG_OTA = "ota_server";

static void ota_task(void *pvParameters) {
    char addr_str[64];
    int addr_family = AF_INET;
    int ip_protocol = IPPROTO_IP;
    struct sockaddr_storage dest_addr;

    struct sockaddr_in *dest_addr_ip4 = (struct sockaddr_in *)&dest_addr;
    dest_addr_ip4->sin_addr.s_addr = htonl(INADDR_ANY);
    dest_addr_ip4->sin_family = AF_INET;
    dest_addr_ip4->sin_port = htons(OTA_TCP_PORT);

    int listen_sock = socket(addr_family, SOCK_STREAM, ip_protocol);
    if (listen_sock < 0) {
        ESP_LOGE(TAG_OTA, "Unable to create socket: errno %d", errno);
        vTaskDelete(NULL);
        return;
    }

    int opt = 1;
    setsockopt(listen_sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    int err = bind(listen_sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    if (err != 0) {
        ESP_LOGE(TAG_OTA, "Socket unable to bind: errno %d", errno);
        goto CLEAN_UP_LISTEN;
    }

    err = listen(listen_sock, 1);
    if (err != 0) {
        ESP_LOGE(TAG_OTA, "Error during listen: errno %d", errno);
        goto CLEAN_UP_LISTEN;
    }

    ESP_LOGI(TAG_OTA, "OTA TCP server listening on port %d", OTA_TCP_PORT);

    while (1) {
        struct sockaddr_storage source_addr;
        socklen_t addr_len = sizeof(source_addr);
        int sock = accept(listen_sock, (struct sockaddr *)&source_addr, &addr_len);
        if (sock < 0) {
            ESP_LOGE(TAG_OTA, "Unable to accept connection: errno %d", errno);
            break;
        }

        if (source_addr.ss_family == PF_INET) {
            inet_ntoa_r(((struct sockaddr_in *)&source_addr)->sin_addr, addr_str, sizeof(addr_str) - 1);
        }
        ESP_LOGI(TAG_OTA, "Client connected: %s", addr_str);

        // Begin OTA
        const esp_partition_t *update_partition = esp_ota_get_next_update_partition(NULL);
        if (!update_partition) {
            ESP_LOGE(TAG_OTA, "No valid OTA partition");
            shutdown(sock, 0);
            close(sock);
            continue;
        }

        ESP_LOGI(TAG_OTA, "Writing to partition subtype %d at offset 0x%lx", update_partition->subtype, (unsigned long)update_partition->address);

        esp_ota_handle_t update_handle = 0;
        if (esp_ota_begin(update_partition, OTA_SIZE_UNKNOWN, &update_handle) != ESP_OK) {
            ESP_LOGE(TAG_OTA, "esp_ota_begin failed");
            shutdown(sock, 0);
            close(sock);
            continue;
        }

        uint8_t *buffer = (uint8_t *)malloc(OTA_RECV_BUF);
        if (!buffer) {
            ESP_LOGE(TAG_OTA, "Failed to allocate buffer");
            esp_ota_end(update_handle);
            shutdown(sock, 0);
            close(sock);
            continue;
        }

        bool write_failed = false;
        ssize_t len;
        size_t total = 0;
        while ((len = recv(sock, buffer, OTA_RECV_BUF, 0)) > 0) {
            if (esp_ota_write(update_handle, buffer, len) != ESP_OK) {
                ESP_LOGE(TAG_OTA, "esp_ota_write failed at %d bytes", (int)total);
                write_failed = true;
                break;
            }
            total += (size_t)len;
        }

        free(buffer);

        if (len < 0) {
            ESP_LOGE(TAG_OTA, "recv failed: errno %d", errno);
            write_failed = true;
        }

        if (!write_failed) {
            if (esp_ota_end(update_handle) != ESP_OK) {
                ESP_LOGE(TAG_OTA, "esp_ota_end failed");
                write_failed = true;
            }
        } else {
            esp_ota_end(update_handle);
        }

        if (!write_failed) {
            if (esp_ota_set_boot_partition(update_partition) != ESP_OK) {
                ESP_LOGE(TAG_OTA, "esp_ota_set_boot_partition failed");
            } else {
                ESP_LOGI(TAG_OTA, "OTA update successful (%d bytes). Rebooting...", (int)total);
                shutdown(sock, 0);
                close(sock);
                vTaskDelay(pdMS_TO_TICKS(1000));
                esp_restart();
            }
        }

        shutdown(sock, 0);
        close(sock);
    }

CLEAN_UP_LISTEN:
    close(listen_sock);
    vTaskDelete(NULL);
}

void ota_server_start(void) {
    xTaskCreate(ota_task, "ota_server", 4096, NULL, 5, NULL);
}
