// GRIDPRINT calibration rig (SPEC 10.5): drive an LED at an exact, crystal-derived frequency.
// ESP-IDF v5.x, ESP32. The LEDC timer is clocked from the APB clock (80 MHz, derived from the
// 40 MHz crystal through the PLL). We select it explicitly (LEDC_USE_APB_CLK) so the internal RC
// oscillator is never used. With 200 Hz and a 10-bit duty resolution the divider is 80e6 / (200 * 1024)
// = 390.625. The ESP32 LEDC divider has 8 fractional bits (0.625 = 160/256), so this ratio is exact on average
// (fractional division adds small cycle-to-cycle jitter). Not yet measured: RIG_GUIDE.md step 5 checks
// the output with a frequency counter or oscilloscope before filming.
// The output is a 50 % duty square wave on CONFIG_RIG_LED_GPIO, which drives the LED transistor.

#include "driver/ledc.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "rig";

void app_main(void)
{
    ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = CONFIG_RIG_LED_FREQUENCY_HZ,
        .clk_cfg = LEDC_USE_APB_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer));
    ledc_channel_config_t ch = {
        .gpio_num = CONFIG_RIG_LED_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = 512,  // 50 % of 1024
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&ch));
    uint32_t actual = ledc_get_freq(LEDC_LOW_SPEED_MODE, LEDC_TIMER_0);
    for (;;) {
        ESP_LOGI(TAG, "LED on GPIO %d: requested %d Hz, LEDC reports %u Hz, 50 %% duty", CONFIG_RIG_LED_GPIO,
                 CONFIG_RIG_LED_FREQUENCY_HZ, (unsigned)actual);
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
