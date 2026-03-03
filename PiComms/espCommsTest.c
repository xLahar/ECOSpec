#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/uart.h"
#include "driver/ledc.h"
#include "driver/i2s.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_spiffs.h"
#include <string.h>

static const char *TAG = "main";

/* ================= UART ================= */
#define UART_NUM UART_NUM_0
#define UART_BUF 256

/* ================= SERVO ================= */
#define SERVO_PIN   17
#define MIN_DUTY    410
#define MAX_DUTY    2048

/* ================= WAV / I2S ================= */
#define I2S_NUM       I2S_NUM_0
#define WAV_FILE_PATH "/spiffs/audio.wav"
#define READ_BUF_SIZE 4096

/* ================= UART HELPER ================= */
static void uart_print(const char *msg) {
    xSemaphoreTake(uart_mutex, portMAX_DELAY);
    uart_write_bytes(UART_NUM, msg, strlen(msg));
    xSemaphoreGive(uart_mutex);
}

/* ================= RTOS ================= */
static QueueHandle_t     servo_queue;
static QueueHandle_t     audio_queue;
static SemaphoreHandle_t uart_mutex;

/* ================= WAV HEADER ================= */
typedef struct __attribute__((packed)) {
    char     riff[4];
    uint32_t file_size;
    char     wave[4];
    char     fmt[4];
    uint32_t fmt_size;
    uint16_t audio_format;
    uint16_t num_channels;
    uint32_t sample_rate;
    uint32_t byte_rate;
    uint16_t block_align;
    uint16_t bits_per_sample;
    char     data[4];
    uint32_t data_size;
} wav_header_t;

/* ================= SPIFFS INIT ================= */
static void spiffs_init(void) {
    esp_vfs_spiffs_conf_t conf = {
        .base_path              = "/spiffs",
        .partition_label        = NULL,
        .max_files              = 5,
        .format_if_mount_failed = false,
    };
    ESP_ERROR_CHECK(esp_vfs_spiffs_register(&conf));
    ESP_LOGI(TAG, "SPIFFS mounted");
}

/* ================= SERVO INIT ================= */
static void servo_init(void) {
    ledc_timer_config_t timer = {
        .speed_mode      = LEDC_LOW_SPEED_MODE,
        .timer_num       = LEDC_TIMER_0,
        .duty_resolution = LEDC_TIMER_14_BIT,
        .freq_hz         = 50,
        .clk_cfg         = LEDC_USE_APB_CLK
    };
    ledc_timer_config(&timer);

    ledc_channel_config_t channel = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel    = LEDC_CHANNEL_0,
        .timer_sel  = LEDC_TIMER_0,
        .gpio_num   = SERVO_PIN,
        .duty       = MIN_DUTY,
        .hpoint     = 0
    };
    ledc_channel_config(&channel);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}

/* ================= SERVO TASK ================= */
static void servo_task(void *arg) {
    int duty = MIN_DUTY;
    bool cmd;
    bool zero = true;

    while (1) {
        if (xQueueReceive(servo_queue, &cmd, portMAX_DELAY)) {

            if (zero) {
                uart_print("Servo moving to max\r\n");
                while (duty < MAX_DUTY) {
                    duty += 7;
                    if (duty > MAX_DUTY) duty = MAX_DUTY;
                    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
                    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
                    vTaskDelay(pdMS_TO_TICKS(15));
                }
                zero = false;
            } else {
                uart_print("Servo moving to min\r\n");
                while (duty > MIN_DUTY) {
                    duty -= 7;
                    if (duty < MIN_DUTY) duty = MIN_DUTY;
                    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
                    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
                    vTaskDelay(pdMS_TO_TICKS(15));
                }
                zero = true;
            }

            uart_print("Servo done\r\n");
        }
    }
}

/* ================= AUDIO TASK ================= */
static void audio_task(void *arg) {
    bool cmd;

    while (1) {
        if (xQueueReceive(audio_queue, &cmd, portMAX_DELAY)) {

            FILE *f = fopen(WAV_FILE_PATH, "rb");
            if (!f) { uart_print("ERR: no wav file\r\n"); continue; }

            wav_header_t hdr;
            fread(&hdr, sizeof(hdr), 1, f);

            if (strncmp(hdr.riff, "RIFF", 4) || strncmp(hdr.wave, "WAVE", 4) || hdr.audio_format != 1) {
                uart_print("ERR: bad wav\r\n");
                fclose(f);
                continue;
            }

            // Init I2S with WAV's sample rate
            i2s_config_t i2s_cfg = {
                .mode                 = I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_DAC_BUILT_IN,
                .sample_rate          = hdr.sample_rate,
                .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
                .channel_format       = I2S_CHANNEL_FMT_RIGHT_LEFT,
                .communication_format = I2S_COMM_FORMAT_STAND_MSB,
                .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
                .dma_buf_count        = 8,
                .dma_buf_len          = 512,
                .tx_desc_auto_clear   = true,
            };
            i2s_driver_install(I2S_NUM, &i2s_cfg, 0, NULL);
            i2s_set_dac_mode(I2S_DAC_CHANNEL_RIGHT_EN);

            uart_print("Playing audio\r\n");

            static uint8_t  buf[READ_BUF_SIZE];
            static uint16_t buf16[READ_BUF_SIZE];
            size_t written;

            while (true) {
                int n = fread(buf, 1, sizeof(buf), f);
                if (n <= 0) break;

                if (hdr.bits_per_sample == 8) {
                    for (int i = 0; i < n; i++) buf16[i] = (uint16_t)buf[i] << 8;
                    i2s_write(I2S_NUM, buf16, n * 2, &written, portMAX_DELAY);
                } else {
                    i2s_write(I2S_NUM, buf, n, &written, portMAX_DELAY);
                }
            }

            fclose(f);
            i2s_zero_dma_buffer(I2S_NUM);
            i2s_driver_uninstall(I2S_NUM);
            uart_print("Audio done\r\n");
        }
    }
}

/* ================= UART RX TASK ================= */
static QueueHandle_t uart_event_queue;

static void uart_rx_task(void *arg) {
    uart_event_t event;
    uint8_t rx[UART_BUF];
    char line[32];
    int idx = 0;

    while (1) {
        // Block here until the UART ISR signals data has arrived
        if (xQueueReceive(uart_event_queue, &event, portMAX_DELAY)) {
            if (event.type != UART_DATA) continue;

            int len = uart_read_bytes(UART_NUM, rx, event.size, pdMS_TO_TICKS(10));

            for (int i = 0; i < len; i++) {
                char c = rx[i];

                if (c == '\r' || c == '\n') {
                    line[idx] = 0;
                    idx = 0;

                    if (strcmp(line, "1") == 0) {
                        bool cmd = true;
                        if (xQueueSend(servo_queue, &cmd, 0)) {
                            uart_print("OK: servo\r\n");
                        } else {
                            uart_print("BUSY\r\n");
                        }
                    } else if (strcmp(line, "2") == 0) {
                        bool cmd = true;
                        if (xQueueSend(audio_queue, &cmd, 0)) {
                            uart_print("OK: audio\r\n");
                        } else {
                            uart_print("BUSY\r\n");
                        }
                    } else if (strlen(line)) {
                        uart_print("?\r\n");
                    }

                } else if (idx < (int)sizeof(line) - 1) {
                    line[idx++] = c;
                }
            }
        }
    }
}

/* ================= MAIN ================= */
void app_main(void) {
    uart_config_t cfg = {
        .baud_rate  = 115200,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE
    };
    uart_driver_install(UART_NUM, UART_BUF * 2, 0, 10, &uart_event_queue, 0);
    uart_param_config(UART_NUM, &cfg);
    uart_set_pin(UART_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    spiffs_init();
    servo_init();

    servo_queue = xQueueCreate(1, sizeof(bool));
    audio_queue = xQueueCreate(1, sizeof(bool));
    uart_mutex  = xSemaphoreCreateMutex();

    xTaskCreate(uart_rx_task, "uart_rx", 4096,  NULL, 10, NULL);
    xTaskCreate(servo_task,   "servo",   4096,  NULL,  9, NULL);
    xTaskCreatePinnedToCore(audio_task, "audio", 8192, NULL, 8, NULL, 1); // pinned to core 1
}