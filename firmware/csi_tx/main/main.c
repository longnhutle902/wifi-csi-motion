/*
 * CSI transmitter (ESP32-S3)
 * Sends ESP-NOW broadcast packets at a fixed rate (default 50 Hz) on a fixed
 * channel with a fixed PHY rate (HT20 MCS0) so the receiver can measure CSI.
 */
#include <string.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "esp_timer.h"

static const char *TAG = "csi_tx";

/* Fixed, locally administered MAC so the receiver can filter on it. */
static const uint8_t TX_MAC[6] = {0x1a, 0x00, 0x00, 0x00, 0x00, 0x01};
static const uint8_t BCAST[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

#define CSI_MAGIC 0x43534921u /* "CSI!" */

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint32_t seq;
    int64_t tx_time_us;
} csi_payload_t;

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_mac(WIFI_IF_STA, TX_MAC));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20));
    ESP_ERROR_CHECK(esp_wifi_set_channel(CONFIG_CSI_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_max_tx_power(CONFIG_CSI_TX_POWER_QDBM));
}

static void espnow_init(void)
{
    ESP_ERROR_CHECK(esp_now_init());
    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, BCAST, 6);
    peer.channel = CONFIG_CSI_WIFI_CHANNEL;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
    /* Fixed HT20 MCS0 rate -> HT packets with stable LTF for CSI. */
    ESP_ERROR_CHECK(esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_MCS0_LGI));
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    wifi_init();
    espnow_init();

    const TickType_t period = pdMS_TO_TICKS(1000 / CONFIG_CSI_SEND_RATE_HZ);
    ESP_LOGI(TAG, "TX started: channel %d, %d Hz, MAC 1a:00:00:00:00:01",
             CONFIG_CSI_WIFI_CHANNEL, CONFIG_CSI_SEND_RATE_HZ);

    csi_payload_t pl = {.magic = CSI_MAGIC, .seq = 0};
    uint32_t fail = 0;
    TickType_t last = xTaskGetTickCount();
    for (;;) {
        pl.seq++;
        pl.tx_time_us = esp_timer_get_time();
        if (esp_now_send(BCAST, (const uint8_t *)&pl, sizeof(pl)) != ESP_OK) {
            fail++;
        }
        if ((pl.seq % (CONFIG_CSI_SEND_RATE_HZ * 10)) == 0) {
            ESP_LOGI(TAG, "sent=%" PRIu32 " fail=%" PRIu32, pl.seq, fail);
        }
        vTaskDelayUntil(&last, period);
    }
}
