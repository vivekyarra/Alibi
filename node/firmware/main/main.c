// GRIDPRINT Node firmware (SPEC 10.4). ESP-IDF v5.x, ESP32.
//
// 1. A GPIO interrupt timestamps each mains zero crossing (one edge per cycle) with esp_timer_get_time()
//    (64-bit, 1 us resolution). A second GPIO interrupt timestamps the GPS PPS edge on the same timer.
//    The PPS interval gives the true length of one second on the local timer (timer disciplined by PPS).
// 2. For each UTC second the crossings between two PPS edges are filtered (glitch, band and median
//    filters in freq_calc.c) and converted to a frequency.
// 3. Each second a JSON message {zone, node_id, t_utc_s, freq_hz, quality, gps_lock} is published with
//    QoS 1 over MQTT/TLS (esp-mqtt) to AWS IoT Core topic gridprint/<zone>/<node_id>.
// 4. Messages go through a RAM FIFO. When offline they stay in the FIFO; after reconnect the FIFO is
//    drained oldest first (back-fill), at most CONFIG_GRIDPRINT_BACKFILL_RATE messages per second.
// Fallback (SPEC V11): without GPS lock, and if enabled, seconds are framed by SNTP time and sent with
//    quality "ntp" and gps_lock false. Their timing uncertainty is larger (see node/SELFTEST.md).
// The GPS position is never parsed, stored or sent (R4).

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mqtt_client.h"
#include "nvs_flash.h"

#include "freq_calc.h"
#include "nmea.h"
#include "sample_buffer.h"

static const char *TAG = "gridprint";

// Certificates embedded by main/CMakeLists.txt (EMBED_TXTFILES) from node/firmware/certs/.
extern const char root_ca_pem_start[] asm("_binary_AmazonRootCA1_pem_start");
extern const char device_crt_start[] asm("_binary_device_pem_crt_start");
extern const char private_key_start[] asm("_binary_private_pem_key_start");

#define EDGE_RING 512               // > 8 s of edges at 60 Hz
#define PPS_TOL_US 200              // accept PPS intervals of 1 s +- 200 us of local timer (+-200 ppm)
#define PROCESS_DELAY_US 50000      // wait 50 ms after a window ends before computing it
#define GPS_RMC_TIMEOUT_US 3000000  // GPS lock is lost after 3 s without a valid RMC sentence
#define PPS_TIMEOUT_US 1500000      // ... or 1.5 s without a PPS edge

typedef struct {
    int64_t utc_s;
    int64_t rx_us;
    int valid;
} rmc_msg_t;

static QueueHandle_t s_zc_q, s_pps_q, s_rmc_q;
static SemaphoreHandle_t s_buf_lock;
static sample_buffer_t s_buf;
static esp_mqtt_client_handle_t s_mqtt;
static volatile bool s_mqtt_connected;
static volatile bool s_ntp_synced;

// ---------------------------------------------------------------- interrupts

static void IRAM_ATTR zc_isr(void *arg)
{
    int64_t t = esp_timer_get_time();
    BaseType_t woken = pdFALSE;
    xQueueSendFromISR(s_zc_q, &t, &woken);
    if (woken) {
        portYIELD_FROM_ISR();
    }
}

static void IRAM_ATTR pps_isr(void *arg)
{
    int64_t t = esp_timer_get_time();
    BaseType_t woken = pdFALSE;
    xQueueSendFromISR(s_pps_q, &t, &woken);
    if (woken) {
        portYIELD_FROM_ISR();
    }
}

static void gpio_setup(void)
{
    gpio_config_t io = {
        .pin_bit_mask = (1ULL << CONFIG_GRIDPRINT_ZC_GPIO) | (1ULL << CONFIG_GRIDPRINT_PPS_GPIO),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_POSEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&io));
    ESP_ERROR_CHECK(gpio_install_isr_service(0));
    ESP_ERROR_CHECK(gpio_isr_handler_add(CONFIG_GRIDPRINT_ZC_GPIO, zc_isr, NULL));
    ESP_ERROR_CHECK(gpio_isr_handler_add(CONFIG_GRIDPRINT_PPS_GPIO, pps_isr, NULL));
}

// ---------------------------------------------------------------- GPS (NMEA RMC time only)

static void gps_task(void *arg)
{
    const uart_port_t port = (uart_port_t)CONFIG_GRIDPRINT_GPS_UART_NUM;
    uart_config_t cfg = {
        .baud_rate = CONFIG_GRIDPRINT_GPS_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(port, 2048, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(port, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(port, CONFIG_GRIDPRINT_GPS_TX_GPIO, CONFIG_GRIDPRINT_GPS_RX_GPIO,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    char line[128];
    int len = 0;
    uint8_t buf[64];
    for (;;) {
        int n = uart_read_bytes(port, buf, sizeof(buf), pdMS_TO_TICKS(100));
        for (int i = 0; i < n; i++) {
            char c = (char)buf[i];
            if (c == '$') {
                len = 0;
            }
            if (c == '\n' || c == '\r') {
                if (len > 0) {
                    line[len] = '\0';
                    rmc_msg_t m = {.rx_us = esp_timer_get_time()};
                    if (nmea_parse_rmc(line, &m.utc_s, &m.valid)) {
                        xQueueSend(s_rmc_q, &m, 0);
                    }
                }
                len = 0;
            } else if (len < (int)sizeof(line) - 1) {
                line[len++] = c;
            }
        }
    }
}

// ---------------------------------------------------------------- timing and frequency

static int64_t s_edges[EDGE_RING];
static int s_edge_head, s_edge_count;  // ring of the latest edges; owned by timing_task

static void edge_push(int64_t t)
{
    s_edges[(s_edge_head + s_edge_count) % EDGE_RING] = t;
    if (s_edge_count < EDGE_RING) {
        s_edge_count++;
    } else {
        s_edge_head = (s_edge_head + 1) % EDGE_RING;
    }
}

// Copy edges in [t0 - 2 nominal periods, t1) to out (ascending). Returns the count.
static int edges_between(int64_t t0, int64_t t1, int64_t *out, int max)
{
    const int64_t pre = 2 * 1000000 / CONFIG_GRIDPRINT_NOMINAL_HZ;
    int n = 0;
    for (int i = 0; i < s_edge_count && n < max; i++) {
        int64_t t = s_edges[(s_edge_head + i) % EDGE_RING];
        if (t >= t0 - pre && t < t1) {
            out[n++] = t;
        }
    }
    return n;
}

static void emit(int64_t utc_s, int64_t t0, int64_t t1, double us_per_s, bool gps)
{
    static int64_t tmp[FREQ_MAX_PERIODS + 8];
    int n = edges_between(t0, t1, tmp, (int)(sizeof(tmp) / sizeof(tmp[0])));
    freq_result_t r;
    freq_from_edges(tmp, n, t0, t1, us_per_s, (double)CONFIG_GRIDPRINT_NOMINAL_HZ, &r);
    if (!r.ok) {
        ESP_LOGW(TAG, "t=%" PRId64 " no estimate: edges=%d glitches=%d periods=%d rejected=%d", utc_s, r.n_edges,
                 r.n_glitches, r.n_periods, r.n_rejected);
        return;
    }
    sample_t s = {.t_utc_s = utc_s, .freq_hz = r.freq_hz, .quality = gps ? 0 : 1, .gps_lock = gps ? 1 : 0};
    xSemaphoreTake(s_buf_lock, portMAX_DELAY);
    sb_push(&s_buf, &s);
    int queued = s_buf.count;
    uint32_t dropped = s_buf.dropped;
    xSemaphoreGive(s_buf_lock);
    ESP_LOGI(TAG, "t=%" PRId64 " f=%.6f q=%s periods=%d rejected=%d queued=%d dropped=%" PRIu32, utc_s, r.freq_hz,
             gps ? "gps" : "ntp", r.n_periods, r.n_rejected, queued, dropped);
}

static void timing_task(void *arg)
{
    int64_t pps_prev = 0, pps_last = 0;          // local timer at the last two PPS edges
    int64_t label_pps = 0, label_utc = -1;       // a PPS edge with a known UTC second
    int64_t last_rmc_valid_us = -GPS_RMC_TIMEOUT_US;
    int64_t last_emitted = -1;
    int64_t pend_t0 = 0, pend_t1 = 0, pend_utc = -1;
    double pend_scale = 1e6;
    for (;;) {
        int64_t t;
        while (xQueueReceive(s_zc_q, &t, 0) == pdTRUE) {
            edge_push(t);
        }
        while (xQueueReceive(s_pps_q, &t, 0) == pdTRUE) {
            pps_prev = pps_last;
            pps_last = t;
            int64_t iv = pps_last - pps_prev;
            int64_t utc0 = -1;
            if (label_utc >= 0 && pps_prev > 0) {
                double k = (double)(pps_prev - label_pps) / 1e6;
                int64_t ki = (int64_t)(k + (k >= 0 ? 0.5 : -0.5));
                if (ki >= 0 && ki < 10 && (k - (double)ki) < 0.01 && (k - (double)ki) > -0.01) {
                    utc0 = label_utc + ki;
                }
            }
            bool rmc_ok = (t - last_rmc_valid_us) < GPS_RMC_TIMEOUT_US;
            if (pps_prev > 0 && iv > 1000000 - PPS_TOL_US && iv < 1000000 + PPS_TOL_US && utc0 >= 0 && rmc_ok) {
                pend_t0 = pps_prev;
                pend_t1 = pps_last;
                pend_utc = utc0;
                pend_scale = (double)iv;
            }
        }
        rmc_msg_t m;
        while (xQueueReceive(s_rmc_q, &m, 0) == pdTRUE) {
            if (!m.valid) {
                continue;
            }
            last_rmc_valid_us = m.rx_us;
            // The RMC sentence describes the latest PPS edge before it (checked in SELFTEST.md).
            if (pps_last > 0 && m.rx_us > pps_last && m.rx_us - pps_last < 1000000) {
                label_pps = pps_last;
                label_utc = m.utc_s + CONFIG_GRIDPRINT_NMEA_PPS_OFFSET_S;
            }
        }
        int64_t now = esp_timer_get_time();
        bool gps_lock = (now - pps_last) < PPS_TIMEOUT_US && (now - last_rmc_valid_us) < GPS_RMC_TIMEOUT_US &&
                        label_utc >= 0;
        if (pend_utc >= 0 && now > pend_t1 + PROCESS_DELAY_US) {
            if (pend_utc > last_emitted) {
                emit(pend_utc, pend_t0, pend_t1, pend_scale, true);
                last_emitted = pend_utc;
            }
            pend_utc = -1;
        }
#if CONFIG_GRIDPRINT_NTP_FALLBACK
        if (!gps_lock && s_ntp_synced) {
            struct timeval tv;
            int64_t a = esp_timer_get_time();
            gettimeofday(&tv, NULL);
            int64_t b = esp_timer_get_time();
            int64_t off = (int64_t)tv.tv_sec * 1000000 + tv.tv_usec - (a + b) / 2;  // utc_us - local_us
            int64_t utc_now = b + off;
            int64_t s = utc_now / 1000000 - 1;  // the last whole second that has ended
            int64_t t1 = (s + 1) * 1000000 - off;
            if (s > last_emitted && b > t1 + PROCESS_DELAY_US) {
                emit(s, s * 1000000 - off, t1, 1e6, false);
                last_emitted = s;
            }
        }
#endif
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

// ---------------------------------------------------------------- network

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && (id == WIFI_EVENT_STA_START || id == WIFI_EVENT_STA_DISCONNECTED)) {
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ESP_LOGI(TAG, "Wi-Fi connected");
    }
}

static void wifi_start(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL, NULL));
    wifi_config_t wc = {0};
    strncpy((char *)wc.sta.ssid, CONFIG_GRIDPRINT_WIFI_SSID, sizeof(wc.sta.ssid) - 1);
    strncpy((char *)wc.sta.password, CONFIG_GRIDPRINT_WIFI_PASSWORD, sizeof(wc.sta.password) - 1);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());
}

static void mqtt_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED:
        s_mqtt_connected = true;
        ESP_LOGI(TAG, "MQTT connected");
        break;
    case MQTT_EVENT_DISCONNECTED:
        s_mqtt_connected = false;
        ESP_LOGW(TAG, "MQTT disconnected; buffering");
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGW(TAG, "MQTT error");
        break;
    default:
        break;
    }
}

static void mqtt_start(void)
{
    static char uri[160];
    snprintf(uri, sizeof(uri), "mqtts://%s:8883", CONFIG_GRIDPRINT_IOT_ENDPOINT);
    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = uri,
        .broker.verification.certificate = root_ca_pem_start,
        .credentials.client_id = CONFIG_GRIDPRINT_NODE_ID,
        .credentials.authentication.certificate = device_crt_start,
        .credentials.authentication.key = private_key_start,
    };
    s_mqtt = esp_mqtt_client_init(&cfg);
    ESP_ERROR_CHECK(esp_mqtt_client_register_event(s_mqtt, ESP_EVENT_ANY_ID, mqtt_event, NULL));
    ESP_ERROR_CHECK(esp_mqtt_client_start(s_mqtt));
}

static void uplink_task(void *arg)
{
    char topic[96];
    char payload[200];
    snprintf(topic, sizeof(topic), "gridprint/%s/%s", CONFIG_GRIDPRINT_ZONE, CONFIG_GRIDPRINT_NODE_ID);
    const int gap_ms = 1000 / CONFIG_GRIDPRINT_BACKFILL_RATE;
    for (;;) {
        sample_t s;
        int have = 0;
        if (s_mqtt_connected) {
            xSemaphoreTake(s_buf_lock, portMAX_DELAY);
            have = sb_peek(&s_buf, &s);
            xSemaphoreGive(s_buf_lock);
        }
        if (have) {
            int len = snprintf(payload, sizeof(payload),
                               "{\"zone\":\"%s\",\"node_id\":\"%s\",\"t_utc_s\":%" PRId64
                               ",\"freq_hz\":%.6f,\"quality\":\"%s\",\"gps_lock\":%s}",
                               CONFIG_GRIDPRINT_ZONE, CONFIG_GRIDPRINT_NODE_ID, s.t_utc_s, s.freq_hz,
                               s.quality == 0 ? "gps" : "ntp", s.gps_lock ? "true" : "false");
            int msg_id = esp_mqtt_client_publish(s_mqtt, topic, payload, len, 1, 0);
            if (msg_id >= 0) {
                xSemaphoreTake(s_buf_lock, portMAX_DELAY);
                sb_pop(&s_buf);  // the producer only appends, so the oldest item is still `s`
                xSemaphoreGive(s_buf_lock);
            } else {
                vTaskDelay(pdMS_TO_TICKS(500));
            }
        }
        vTaskDelay(pdMS_TO_TICKS(gap_ms > 0 ? gap_ms : 1));
    }
}

static void ntp_task(void *arg)
{
    esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG(CONFIG_GRIDPRINT_NTP_SERVER);
    ESP_ERROR_CHECK(esp_netif_sntp_init(&cfg));
    for (;;) {
        if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000)) == ESP_OK && !s_ntp_synced) {
            s_ntp_synced = true;
            ESP_LOGI(TAG, "SNTP time synchronized");
        }
        vTaskDelay(pdMS_TO_TICKS(60000));
    }
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    ESP_LOGI(TAG, "GRIDPRINT Node %s zone %s nominal %d Hz", CONFIG_GRIDPRINT_NODE_ID, CONFIG_GRIDPRINT_ZONE,
             CONFIG_GRIDPRINT_NOMINAL_HZ);
    sample_t *storage = malloc(sizeof(sample_t) * CONFIG_GRIDPRINT_BUFFER_SECONDS);  // heap, not .bss
    if (storage == NULL) {
        ESP_LOGE(TAG, "cannot allocate the offline buffer; lower GRIDPRINT_BUFFER_SECONDS");
        abort();
    }
    sb_init(&s_buf, storage, CONFIG_GRIDPRINT_BUFFER_SECONDS);
    s_buf_lock = xSemaphoreCreateMutex();
    s_zc_q = xQueueCreate(256, sizeof(int64_t));
    s_pps_q = xQueueCreate(8, sizeof(int64_t));
    s_rmc_q = xQueueCreate(8, sizeof(rmc_msg_t));
    gpio_setup();
    xTaskCreate(timing_task, "timing", 6144, NULL, 10, NULL);
    xTaskCreate(gps_task, "gps", 4096, NULL, 9, NULL);
    wifi_start();
    mqtt_start();
    xTaskCreate(uplink_task, "uplink", 6144, NULL, 5, NULL);
    xTaskCreate(ntp_task, "ntp", 4096, NULL, 4, NULL);
}
