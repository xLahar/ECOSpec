#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/uart.h"
#include "driver/ledc.h"
#include "esp_system.h"
#include <string.h>

/* ================= UART0 ================= */
#define UART_NUM UART_NUM_0
#define UART_BUF 256

/* ================= SERVO ================= */
#define SERVO_PIN 17
#define MIN_DUTY  410
#define MAX_DUTY  2048
#define CENTER_DUTY ((MIN_DUTY + MAX_DUTY) / 2)

/* ================= RTOS ================= */
static QueueHandle_t servo_queue;

/* ================= SERVO INIT ================= */
static void servo_init(void)
{
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
static void servo_task(void *arg)
{
  int duty = MIN_DUTY;
  bool cmd;
  bool zero = true;

  while (1) {
    if (xQueueReceive(servo_queue, &cmd, portMAX_DELAY)) {

      if (zero) {
        uart_write_bytes(UART_NUM, "Servo moving to max\r\n", strlen("Servo moving to max\r\n"));

        while (duty < MAX_DUTY) {
          duty += 7;
          if (duty > MAX_DUTY) duty = MAX_DUTY;
            ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
            ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
            vTaskDelay(pdMS_TO_TICKS(15));
          }

        zero = false;

      } else {
          uart_write_bytes(UART_NUM, "Servo moving to min\r\n", trlen("Servo moving to min\r\n"));

          while (duty > MIN_DUTY) {
            duty -= 7;
            if (duty < MIN_DUTY) duty = MIN_DUTY;
              ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
              ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
              vTaskDelay(pdMS_TO_TICKS(15));
          }
          zero = true;
        }

            uart_write_bytes(UART_NUM, "Servo done\r\n", strlen("Servo done\r\n"));
        }
    }
}

/* ================= UART RX TASK ================= */
static void uart_rx_task(void *arg)
{
    uint8_t rx[UART_BUF];
    char line[32];
    int idx = 0;

    while (1) {
        int len = uart_read_bytes(UART_NUM, rx, sizeof(rx), pdMS_TO_TICKS(100));

        for (int i = 0; i < len; i++) {
            char c = rx[i];

            if (c == '\r' || c == '\n') {
                line[idx] = 0;
                idx = 0;

                if (strcmp(line, "1") == 0) {
                    bool cmd = true;
                    if (xQueueSend(servo_queue, &cmd, 0)) {
                        uart_write_bytes(UART_NUM, "OK\r\n", 4);
                    } else {
                        uart_write_bytes(UART_NUM, "BUSY\r\n", 6);
                    }
                } else if (strlen(line)) {
                    uart_write_bytes(UART_NUM, "?\r\n", 3);
                }

            } else if (idx < sizeof(line) - 1) {
                line[idx++] = c;
            }
        }
    }
}

/* ================= MAIN ================= */
void app_main(void)
{
    uart_config_t cfg = {
        .baud_rate  = 115200,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE
    };

    uart_driver_install(UART_NUM, UART_BUF * 2, 0, 0, NULL, 0);
    uart_param_config(UART_NUM, &cfg);
    uart_set_pin(UART_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    servo_queue = xQueueCreate(1, sizeof(bool));

    servo_init();

    xTaskCreate(uart_rx_task, "uart_rx", 4096, NULL, 10, NULL);
    xTaskCreate(servo_task, "servo", 4096, NULL, 9, NULL);
}
