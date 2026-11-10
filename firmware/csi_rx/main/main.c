/*
 * CSI receiver (ESP32-S3)
 * Receives the ESP-NOW packets of the TX board, captures CSI (L-LTF, 64
 * subcarriers) and streams one text line per packet over the serial console:
 *
 * CSI,<idx>,<rx_seq>,<ts_us>,<rssi>,<noise_floor>,<rate>,<sig_mode>,<mcs>,
 *     <cwb>,<channel>,<first_word_invalid>,<len>,<base64(int8 I/Q buffer)>
 *
 * Status lines start with "STAT,".
 */
#include <string.h>
#include <stdio.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "esp_timer.h"
#include "mbedtls/base64.h"

static const char *TAG = "csi_rx";

static const uint8_t TX_MAC[6] = {0x1a, 0x00, 0x00, 0x00, 0x00, 0x01};
static const uint8_t RX_MAC[6] = {0x1a, 0x00, 0x00, 0x00, 0x00, 0x02};

#define CSI_MAX_LEN 384

typedef struct {
    int64_t ts_us;
    uint16_t rx_seq;
    int8_t rssi;
    int8_t noise_floor;
    uint8_t rate;
    uint8_t sig_mode;
    uint8_t mcs;
    uint8_t cwb;
    uint8_t channel;
    uint8_t fwi;
    uint16_t len;
    int8_t buf[CSI_MAX_LEN];
} csi_item_t;

static QueueHandle_t s_queue;
static volatile uint32_t s_rx_cnt, s_drop_cnt;

static void csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || memcmp(info->mac, TX_MAC, 6) != 0) {
        return;
    }
    static csi_item_t item; /* WiFi task context: single producer */
    const wifi_pkt_rx_ctrl_t *rx = &info->rx_ctrl;
    item.ts_us = esp_timer_get_time();
    item.rx_seq = info->rx_seq;
    item.rssi = rx->rssi;
    item.noise_floor = rx->noise_floor;
    item.rate = rx->rate;
    item.sig_mode = rx->sig_mode;
    item.mcs = rx->mcs;
    item.cwb = rx->cwb;
    item.channel = rx->channel;
    item.fwi = info->first_word_invalid;
    item.len = info->len > CSI_MAX_LEN ? CSI_MAX_LEN : info->len;
    memcpy(item.buf, info->buf, item.len);
    s_rx_cnt++;
    if (xQueueSend(s_queue, &item, 0) != pdTRUE) {
        s_drop_cnt++;
    }
}

static void print_task(void *arg)
{
    static csi_item_t item;
    static char b64[CSI_MAX_LEN * 2];
    static char line[CSI_MAX_LEN * 2 + 128];
    uint32_t idx = 0;
    int64_t last_stat = esp_timer_get_time();
    for (;;) {
        if (xQueueReceive(s_queue, &item, pdMS_TO_TICKS(500)) == pdTRUE) {
            size_t olen = 0;
            mbedtls_base64_encode((unsigned char *)b64, sizeof(b64), &olen,
                                  (const unsigned char *)item.buf, item.len);
            b64[olen] = 0;
            int n = snprintf(line, sizeof(line),
                             "CSI,%" PRIu32 ",%u,%" PRId64 ",%d,%d,%u,%u,%u,%u,%u,%u,%u,%s\n",
                             idx++, item.rx_seq, item.ts_us, item.rssi, item.noise_floor,
                             item.rate, item.sig_mode, item.mcs, item.cwb, item.channel,
                             item.fwi, item.len, b64);
            fwrite(line, 1, n, stdout);
        }
        int64_t now = esp_timer_get_time();
        if (now - last_stat > 5000000) {
            last_stat = now;
            printf("STAT,%" PRIu32 ",%" PRIu32 "\n", s_rx_cnt, s_drop_cnt);
        }
    }
}

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_mac(WIFI_IF_STA, RX_MAC));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT20));
    ESP_ERROR_CHECK(esp_wifi_set_channel(CONFIG_CSI_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE));
    /* ESP-NOW so the stack accepts the vendor action frames. */
    ESP_ERROR_CHECK(esp_now_init());
    /* Promiscuous mode makes sure CSI is reported for all frames on air. */
    wifi_promiscuous_filter_t filt = {.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_DATA};
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filt));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
}

static void csi_init(void)
{
    wifi_csi_config_t csi_cfg = {
        .lltf_en = true,
        .htltf_en = false,
        .stbc_htltf2_en = false,
        .ltf_merge_en = true,
        .channel_filter_en = true,
        .manu_scale = false,
        .shift = 0,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_rx_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    esp_log_level_set("wifi", ESP_LOG_WARN);
    s_queue = xQueueCreate(128, sizeof(csi_item_t));
    xTaskCreatePinnedToCore(print_task, "csi_print", 6144, NULL, 5, NULL, 1);

    wifi_init();
    csi_init();
    ESP_LOGI(TAG, "RX started on channel %d, waiting for TX 1a:00:00:00:00:01",
             CONFIG_CSI_WIFI_CHANNEL);
}
