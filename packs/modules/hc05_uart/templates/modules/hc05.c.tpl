/**
 * @file hc05.c
 * @brief HC-05 Bluetooth SPP module driver for STM32 HAL
 *
 * HC-05 is a transparent UART-to-Bluetooth bridge.
 * In data mode (KEY pin LOW): 9600 baud default, SPP profile.
 * In AT mode (KEY pin HIGH at power-on): 38400 baud, AT commands.
 *
 * Reference: HC-05 AT Command Set documentation
 *   AT             - Test
 *   AT+NAME=xxx    - Set device name
 *   AT+PSWD="1234" - Set PIN
 *   AT+UART=9600,0,0 - Set baud rate
 *   AT+ROLE=0      - Set slave mode
 */

#include "hc05.h"
#include <string.h>
#include <stdio.h>

extern UART_HandleTypeDef HC05_UART_HANDLE;

static uint8_t  s_rx_buf[HC05_RX_BUF_SIZE];
static volatile uint16_t s_rx_head = 0;
static volatile uint16_t s_rx_tail = 0;

void HC05_Init(uint32_t baud)
{
    (void)baud;  /* Baud rate should be configured in CubeMX */
    s_rx_head = 0;
    s_rx_tail = 0;
    memset(s_rx_buf, 0, sizeof(s_rx_buf));

    /* Start idle-line interrupt receive if supported */
    HAL_UARTEx_ReceiveToIdle_IT(&HC05_UART_HANDLE, s_rx_buf, HC05_RX_BUF_SIZE);
}

void HC05_Send(const uint8_t *data, uint16_t len)
{
    HAL_UART_Transmit(&HC05_UART_HANDLE, (uint8_t *)data, len, 1000);
}

void HC05_Printf(const char *fmt, ...)
{
    char buf[128];
    va_list args;
    va_start(args, fmt);
    int len = vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    if (len > 0)
        HC05_Send((uint8_t *)buf, (uint16_t)len);
}

uint16_t HC05_Read(uint8_t *buf, uint16_t max_len)
{
    uint16_t count = 0;
    uint8_t byte;

    /* Poll UART for available bytes */
    while (count < max_len)
    {
        if (HAL_UART_Receive(&HC05_UART_HANDLE, &byte, 1, 2) == HAL_OK)
        {
            buf[count++] = byte;
        }
        else
        {
            break;
        }
    }

    return count;
}

uint8_t HC05_DataAvailable(void)
{
    uint8_t byte;
    if (HAL_UART_Receive(&HC05_UART_HANDLE, &byte, 1, 1) == HAL_OK)
    {
        /* Push byte back into buffer for next Read() call */
        if (s_rx_head < HC05_RX_BUF_SIZE)
            s_rx_buf[s_rx_head++] = byte;
        return 1;
    }
    return (s_rx_head > s_rx_tail) ? 1 : 0;
}

int8_t HC05_SendAT(const char *cmd, char *resp, uint16_t resp_size, uint32_t timeout)
{
    char tx_buf[128];
    uint16_t idx = 0;
    uint8_t byte;
    uint32_t start;

    snprintf(tx_buf, sizeof(tx_buf), "%s\r\n", cmd);
    HAL_UART_Transmit(&HC05_UART_HANDLE, (uint8_t *)tx_buf, (uint16_t)strlen(tx_buf), 1000);

    start = HAL_GetTick();
    memset(resp, 0, resp_size);

    while ((HAL_GetTick() - start) < timeout)
    {
        if (HAL_UART_Receive(&HC05_UART_HANDLE, &byte, 1, 10) == HAL_OK)
        {
            if (idx < resp_size - 1)
                resp[idx++] = (char)byte;

            if (strstr(resp, "OK") || strstr(resp, "ERROR"))
                return (strstr(resp, "OK") != NULL) ? 0 : -1;
        }
    }

    return -1;  /* timeout */
}
