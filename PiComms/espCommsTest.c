#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "driver/uart.h"
#include "driver/ledc.h"
#include "driver/i2s.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_spiffs.h"
#include <string.h>

static const char *TAG = "main";

#define UART_NUM UART_NUM_0
#define UART_BUF 256

#define SERVO_PIN   GPIO_NUM_18
#define MIN_DUTY    410
#define MAX_DUTY    2048

// #define I2S_NUM       I2S_NUM_0
// #define WAV_FILE_PATH "/spiffs/audio.wav"
// #define READ_BUF_SIZE 4096

#define X9C_INC    GPIO_NUM_10
#define X9C_UD     GPIO_NUM_11
#define X9C_CS     GPIO_NUM_12
#define X9C_MAX_POS 127
#define X9C_MIN_POS 0
#define X9C_PULSE_DELAY 5
#define X9C_PINS ((1ULL << X9C_INC) | (1ULL << X9C_UD) | (1ULL << X9C_CS))
static bool x9c_wait_for_response = false;
static int x9c_pos = X9C_MIN_POS;

static QueueHandle_t uart_event_queue;
static QueueHandle_t servo_queue;
// static QueueHandle_t audio_queue;
static QueueHandle_t x9c_queue;
static SemaphoreHandle_t uart_mutex;

uint32_t angle_to_duty_cycle(uint8_t angle)
{
    if (angle > 180) angle = 180;
    // Map angle (0° -> 0.5ms, 180° -> 2.5ms)
    float pulse_width = 0.5 + (angle / 180.0) * 2.0;
    // Convert pulse width to duty cycle (12-bit resolution, 50Hz)
    uint32_t duty = (pulse_width / 20.0) * 4096;

    return duty;
}

static void uart_print(const char *msg) {
    xSemaphoreTake(uart_mutex, portMAX_DELAY);
    uart_write_bytes(UART_NUM, msg, strlen(msg));
    uart_wait_tx_done(UART_NUM, pdMS_TO_TICKS(100));
    xSemaphoreGive(uart_mutex);
}

// typedef struct __attribute__((packed)) {
//     char     riff[4];
//     uint32_t file_size;
//     char     wave[4];
//     char     fmt[4];
//     uint32_t fmt_size;
//     uint16_t audio_format;
//     uint16_t num_channels;
//     uint32_t sample_rate;
//     uint32_t byte_rate;
//     uint16_t block_align;
//     uint16_t bits_per_sample;
//     char     data[4];
//     uint32_t data_size;
// } wav_header_t;

// static void spiffs_init(void) {
//     esp_vfs_spiffs_conf_t conf = {
//         .base_path              = "/spiffs",
//         .partition_label        = NULL,
//         .max_files              = 5,
//         .format_if_mount_failed = true,
//     };
//     ESP_ERROR_CHECK(esp_vfs_spiffs_register(&conf));
//     ESP_LOGI(TAG, "SPIFFS mounted");
//     FILE *f = fopen("/spiffs/audio.wav", "rb");
// if (f) {
//     ESP_LOGI(TAG, "audio.wav found");
//     fclose(f);
// } else {
//     ESP_LOGI(TAG, "audio.wav NOT found");
// }
// }


static void x9c_pulse(void) {
    gpio_set_level(X9C_INC, 0);
    ets_delay_us(X9C_PULSE_DELAY);
    gpio_set_level(X9C_INC, 1);
    ets_delay_us(X9C_PULSE_DELAY);
}
static void x9c_init(void) {
    gpio_config_t cfg = {
        .mode = GPIO_MODE_OUTPUT,
        .pin_bit_mask = X9C_PINS,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };
    gpio_config(&cfg);

    gpio_set_level(X9C_CS, 0); // CS low to enable
    gpio_set_level(X9C_UD, 0); // Set direction to down

    for (int i = 0; i < X9C_MAX_POS; i++) {
        x9c_pulse();
    }
    x9c_pos = X9C_MAX_POS;

    gpio_set_level(X9C_CS, 1); // CS high to disable
}

void x9c_set_position(uint8_t pos) {
    if (pos < X9C_MIN_POS) pos = X9C_MIN_POS;
    if (pos > X9C_MAX_POS) pos = X9C_MAX_POS;

    char buf[32];
    snprintf(buf, sizeof(buf), "Setting X9C to position: %d\r\n", pos);
    uart_print(buf);

    int delta = pos - x9c_pos;
    if (delta == 0) return;

    gpio_set_level(X9C_CS, 0); // CS low to enable
    gpio_set_level(X9C_UD, delta > 0 ? 0 : 1); // Set direction

    for (int i = 0; i < abs(delta); i++) {
        x9c_pulse();
    }

    gpio_set_level(X9C_CS, 1); // CS high to disable
    x9c_pos = pos;
}

static void x9c_task(void *arg) {
    uint8_t pos;

    while (1) {
        if (xQueueReceive(x9c_queue, &pos, portMAX_DELAY)) {
            x9c_set_position(pos);
            uart_print("X9C done\r\n");
        }
    }
};

static void servo_init(void)
{
    ledc_timer_config_t timer = {
        .speed_mode = LEDC_HIGH_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_12_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 50,
        .clk_cfg = LEDC_AUTO_CLK
    };
    ledc_timer_config(&timer);

    ledc_channel_config_t channel = {
        .gpio_num = SERVO_PIN,
        .speed_mode = LEDC_HIGH_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0
    };
    ledc_channel_config(&channel);
}

/* ================= SERVO TASK ================= */
static void servo_task(void *arg) {
    int duty = MIN_DUTY;
    bool cmd;
    bool zero = true;

    while (1) {
        if (xQueueReceive(servo_queue, &cmd, portMAX_DELAY)) {
            if (zero) {
                uart_print("Servo moving to max in 10 deg. increments\r\n");
                for(int angle = 0 ; angle <= 180 ; angle += 10)
                {
                    ledc_set_duty(LEDC_HIGH_SPEED_MODE, LEDC_CHANNEL_0, angle_to_duty_cycle(angle));
                    ledc_update_duty(LEDC_HIGH_SPEED_MODE, LEDC_CHANNEL_0);
                    vTaskDelay(pdMS_TO_TICKS(1000));
                }
                uart_print("Servo at max\r\n");
                zero = false;
            } else {
                uart_print("Servo moving to min in 10 deg. increments\r\n");
                for(int angle = 170 ; angle >= 10 ; angle -= 10)
                {
                    ESP_LOGI(TAG, "Moving to %d degrees\n", angle);
                    ledc_set_duty(LEDC_HIGH_SPEED_MODE, LEDC_CHANNEL_0, angle_to_duty_cycle(angle));
                    ledc_update_duty(LEDC_HIGH_SPEED_MODE, LEDC_CHANNEL_0);
                    vTaskDelay(pdMS_TO_TICKS(1000));
                }
                uart_print("Servo at min\r\n");
                zero = true;
            }
            uart_print("Servo done\r\n");
        }
    }
}

// static void audio_task(void *arg) {
//     bool cmd;

//     while (1) {
//         if (xQueueReceive(audio_queue, &cmd, portMAX_DELAY)) {

//             FILE *f = fopen(WAV_FILE_PATH, "rb");
//             if (!f) { uart_print("ERR: no wav file\r\n"); continue; }

//             wav_header_t hdr;
//             fread(&hdr, sizeof(hdr), 1, f);

//             if (strncmp(hdr.riff, "RIFF", 4) || strncmp(hdr.wave, "WAVE", 4) || hdr.audio_format != 1) {
//                 uart_print("ERR: bad wav\r\n");
//                 fclose(f);
//                 continue;
//             }

//             i2s_config_t i2s_cfg = {
//                 .mode                 = I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_DAC_BUILT_IN,
//                 .sample_rate          = hdr.sample_rate,
//                 .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
//                 .channel_format       = I2S_CHANNEL_FMT_ONLY_RIGHT,
//                 .communication_format = I2S_COMM_FORMAT_I2S_MSB,
//                 .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
//                 .dma_buf_count        = 8,
//                 .dma_buf_len          = 1024,
//                 .use_apll             = false,
//                 .tx_desc_auto_clear   = true,
//             };
//             i2s_driver_install(I2S_NUM, &i2s_cfg, 0, NULL);
//             i2s_set_dac_mode(I2S_DAC_CHANNEL_RIGHT_EN);

//             i2s_set_clk(I2S_NUM,
//             hdr.sample_rate,
//             I2S_BITS_PER_SAMPLE_16BIT,
//             I2S_CHANNEL_MONO);

//             uart_print("Playing audio\r\n");

//             static uint8_t  buf[READ_BUF_SIZE];
//             static uint16_t buf16[READ_BUF_SIZE];
//             size_t written;

//             while (true) {
//                 int n = fread(buf, 1, sizeof(buf), f);
//                 if (n <= 0) break;

//                 if (hdr.bits_per_sample == 16) {
//                     int samples = n / 2;
//                     int16_t *s16 = (int16_t *)buf;
//                     for (int i = 0; i < samples; i++) {
//                         // Convert signed 16-bit to unsigned 8-bit for DAC
//                         buf16[i] = (uint16_t)((s16[i] + 32768) >> 8) << 8;
//                     }
//                     i2s_write(I2S_NUM, buf16, samples * 2, &written, portMAX_DELAY);
//                 } else {
//                     // 8-bit unsigned, shift up for DAC
//                     for (int i = 0; i < n; i++) buf16[i] = (uint16_t)buf[i] << 8;
//                     i2s_write(I2S_NUM, buf16, n * 2, &written, portMAX_DELAY);
//                 }
//             }

//             fclose(f);
//             i2s_zero_dma_buffer(I2S_NUM);
//             i2s_driver_uninstall(I2S_NUM);
//             uart_print("Audio done\r\n");
//         }
//     }
// }

static void uart_rx_task(void *arg) {
    uart_event_t event;
    uint8_t rx[UART_BUF];
    char line[32];
    int idx = 0;


    while (1) {
        if (xQueueReceive(uart_event_queue, &event, portMAX_DELAY)) {
            if (event.type != UART_DATA) continue;

            int len = uart_read_bytes(UART_NUM, rx, event.size, pdMS_TO_TICKS(10));

            for (int i = 0; i < len; i++) {
                char c = rx[i];

                if (c == '\r' || c == '\n') {
                    line[idx] = 0;
                    idx = 0;

                    if (x9c_wait_for_response) {
                        char clean_line[16];
                        int j = 0;
                        for (int i = 0; i < (int)strlen(line) && j < (int)sizeof(clean_line)-1; i++) {
                            if (line[i] >= '0' && line[i] <= '9') {
                                clean_line[j++] = line[i];
                            }
                        }
                        clean_line[j] = '\0';

                        if (clean_line[0] == '\0') {
                            uart_print("Invalid input, must be 0-127\r\n");
                            x9c_wait_for_response = false;
                            continue;
                        }

                        uint8_t pos = (uint8_t)atoi(clean_line);

                        if (xQueueSend(x9c_queue, &pos, 0)) {
                            char msg[64];
                            snprintf(msg, sizeof(msg), "Queued pos %d\r\n", pos);
                            uart_print(msg);
                        } else {
                            uart_print("X9C BUSY\r\n");
                        }

                        x9c_wait_for_response = false;
                    }

                    if (strcmp(line, "1") == 0) {
                        bool cmd = true;
                        if (xQueueSend(servo_queue, &cmd, 0)) {
                            uart_print("OK: servo\r\n");
                        } else {
                            uart_print("BUSY\r\n");
                        }
                    } 
                    else if (strcmp(line, "2") == 0) {
                        bool cmd = true;
                        uart_print("Audio command received, but audio task is disabled in this code\r\n");
                        // if (xQueueSend(audio_queue, &cmd, 0)) {
                        //     uart_print("OK: audio\r\n");
                        // } else {
                        //     uart_print("BUSY\r\n");
                        // }
                    }
                    else if (strcmp(line, "3") == 0) {
                        uart_print("OK: x9c\r\n");
                        uart_print("Enter X9C position (0-127): ");
                        x9c_wait_for_response = true;
                    }
                    else {
                        uart_print("?\r\n");
                    }
                }
                else if (idx < (int)sizeof(line) - 1) {
                    line[idx++] = c;
                }
                
            }
        }
    }
}

void app_main(void) {

    servo_queue = xQueueCreate(1, sizeof(bool));
    // audio_queue = xQueueCreate(1, sizeof(bool));
    x9c_queue   = xQueueCreate(1, sizeof(uint8_t));
    uart_mutex  = xSemaphoreCreateMutex();
    ESP_LOGI(TAG, "queues ok");

    // UART init
    uart_config_t cfg = {
        .baud_rate  = 115200,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE
    };
    uart_driver_install(UART_NUM, UART_BUF * 2, 0, 10, &uart_event_queue, 0);
    uart_param_config(UART_NUM, &cfg);
    uart_set_pin(UART_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    ESP_LOGI(TAG, "uart ok");

    // spiffs_init();
    // ESP_LOGI(TAG, "spiffs ok");

    servo_init();
    ESP_LOGI(TAG, "servo ok");

    x9c_init();
    ESP_LOGI(TAG, "x9c ok");

    xTaskCreate(uart_rx_task, "uart_rx", 4096,  NULL, 10, NULL);
    xTaskCreate(servo_task,   "servo",   4096,  NULL,  9, NULL);
    // xTaskCreatePinnedToCore(audio_task, "audio", 8192, NULL, 8, NULL, 1);
    xTaskCreate(x9c_task, "x9c_task", 4096, NULL, 9, NULL);
    ESP_LOGI(TAG, "tasks ok");
}
