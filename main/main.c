#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "wifi_logger.h"

static const char *TAG = "main_app";

void app_main(void)
{
    wifi_logger_start();

    int i = 0;
    while(1) {
        ESP_LOGI(TAG, "Message count: %d", i++);
        vTaskDelay(5000 / portTICK_PERIOD_MS);
    }
}
