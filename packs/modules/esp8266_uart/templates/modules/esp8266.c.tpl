/**
 * @file esp8266.c
 * @brief ESP8266 WiFi module driver via UART AT commands
 *
 * Reference: Espressif ESP8266 AT Instruction Set v3.0
 * Common AT commands:
 *   AT              - Test AT startup
 *   AT+RST          - Restart module
 *   AT+CWMODE=1     - Set station mode
 *   AT+CWJAP="ssid","pwd" - Connect to AP
 *   AT+CIPSTART="TCP","ip",port - TCP connection
 *   AT+CIPSEND=len  - Enter send mode
 *   AT+CIPCLOSE     - Close connection
 *   AT+CIFSR        - Get local IP
 *
 * UART idle-line interrupt is used for receive detection.
 */

#include "esp8266.h"
#include <string.h>
#include <stdio.h>

extern UART_HandleTypeDef ESP8266_UART_HANDLE;

static uint8_t  s_rx_buf[ESP8266_RX_BUF_SIZE];
static volatile uint16_t s_rx_len = 0;
static volatile uint8_t  s_rx_ready = 0;

/* ---- Internal UART helpers ---- */

static void ESP8266_ClearRx(void)
{
    s_rx_len = 0;
    s_rx_ready = 0;
    memset(s_rx_buf, 0, sizeof(s_rx_buf));
}

static void ESP8266_SendString(const char *str)
{
    HAL_UART_Transmit(&ESP8266_UART_HANDLE,
                      (uint8_t *)str, (uint16_t)strlen(str), 1000);
}

static int8_t ESP8266_WaitResponse(const char *expected, uint32_t timeout_ms)
{
    uint32_t start = HAL_GetTick();
    uint16_t idx = 0;
    uint8_t byte;

    s_rx_len = 0;

    while ((HAL_GetTick() - start) < timeout_ms)
    {
        if (HAL_UART_Receive(&ESP8266_UART_HANDLE, &byte, 1, 10) == HAL_OK)
        {
            if (idx < ESP8266_RX_BUF_SIZE - 1)
                s_rx_buf[idx++] = byte;
            s_rx_buf[idx] = '\0';
            s_rx_len = idx;

            if (strstr((char *)s_rx_buf, expected) != NULL)
                return ESP8266_OK;
        }
    }

    return ESP8266_TIMEOUT;
}

/* ---- Public API ---- */

int8_t ESP8266_Init(void)
{
    ESP8266_ClearRx();

    /* Test basic AT communication */
    if (ESP8266_SendAT("AT", "OK", ESP8266_DEFAULT_TIMEOUT) != ESP8266_OK)
        return ESP8266_ERR;

    /* Disable echo */
    ESP8266_SendAT("ATE0", "OK", ESP8266_DEFAULT_TIMEOUT);

    /* Set station mode */
    ESP8266_SendAT("AT+CWMODE=1", "OK", ESP8266_DEFAULT_TIMEOUT);

    return ESP8266_OK;
}

int8_t ESP8266_SendAT(const char *cmd, const char *resp, uint32_t timeout)
{
    ESP8266_ClearRx();
    ESP8266_SendString(cmd);
    ESP8266_SendString("\r\n");
    return ESP8266_WaitResponse(resp, timeout);
}

int8_t ESP8266_ConnectWiFi(const char *ssid, const char *password)
{
    char cmd[128];

    snprintf(cmd, sizeof(cmd), "AT+CWJAP=\"%s\",\"%s\"", ssid, password);
    return ESP8266_SendAT(cmd, "WIFI GOT IP", ESP8266_WIFI_TIMEOUT);
}

int8_t ESP8266_ConnectTCP(const char *ip, uint16_t port)
{
    char cmd[128];

    snprintf(cmd, sizeof(cmd), "AT+CIPSTART=\"TCP\",\"%s\",%u", ip, port);
    return ESP8266_SendAT(cmd, "CONNECT", ESP8266_WIFI_TIMEOUT);
}

int16_t ESP8266_Send(const uint8_t *data, uint16_t len)
{
    char cmd[32];

    snprintf(cmd, sizeof(cmd), "AT+CIPSEND=%u", len);
    if (ESP8266_SendAT(cmd, ">", 5000) != ESP8266_OK)
        return -1;

    HAL_UART_Transmit(&ESP8266_UART_HANDLE, (uint8_t *)data, len, 5000);

    if (ESP8266_WaitResponse("SEND OK", 5000) != ESP8266_OK)
        return -1;

    return (int16_t)len;
}

uint16_t ESP8266_Read(uint8_t *buf, uint16_t max_len)
{
    /* Check for +IPD,<len>:<data> pattern in buffer */
    char *ipd = strstr((char *)s_rx_buf, "+IPD,");
    if (ipd == NULL)
        return 0;

    uint16_t data_len = 0;
    char *colon = strchr(ipd, ':');
    if (colon == NULL)
        return 0;

    /* Parse length */
    data_len = (uint16_t)atoi(ipd + 5);
    if (data_len > max_len)
        data_len = max_len;

    /* Copy data after colon */
    memcpy(buf, colon + 1, data_len);
    ESP8266_ClearRx();

    return data_len;
}

uint8_t ESP8266_DataAvailable(void)
{
    /* Poll UART for any pending data */
    uint8_t byte;
    while (HAL_UART_Receive(&ESP8266_UART_HANDLE, &byte, 1, 1) == HAL_OK)
    {
        if (s_rx_len < ESP8266_RX_BUF_SIZE - 1)
        {
            s_rx_buf[s_rx_len++] = byte;
            s_rx_buf[s_rx_len] = '\0';
        }
    }

    return (strstr((char *)s_rx_buf, "+IPD,") != NULL) ? 1 : 0;
}

void ESP8266_Disconnect(void)
{
    ESP8266_SendAT("AT+CIPCLOSE", "OK", ESP8266_DEFAULT_TIMEOUT);
}

void ESP8266_GetIP(char *ip_buf)
{
    ip_buf[0] = '\0';
    ESP8266_ClearRx();
    ESP8266_SendAT("AT+CIFSR", "OK", ESP8266_DEFAULT_TIMEOUT);

    /* Parse STAIP from response: +CIFSR:STAIP,"x.x.x.x" */
    char *start = strstr((char *)s_rx_buf, "STAIP,\"");
    if (start)
    {
        start += 7;
        char *end = strchr(start, '"');
        if (end && (end - start) < 16)
        {
            memcpy(ip_buf, start, (size_t)(end - start));
            ip_buf[end - start] = '\0';
        }
    }
}
