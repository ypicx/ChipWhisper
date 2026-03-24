#ifndef __ESP8266_H
#define __ESP8266_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* UART handle - override in app_config.h */
#ifndef ESP8266_UART_HANDLE
#define ESP8266_UART_HANDLE  huart2
#endif

/* Receive buffer size */
#ifndef ESP8266_RX_BUF_SIZE
#define ESP8266_RX_BUF_SIZE  512
#endif

/* AT command default timeout (ms) */
#define ESP8266_DEFAULT_TIMEOUT  2000
#define ESP8266_WIFI_TIMEOUT     10000

/* Return codes */
#define ESP8266_OK       0
#define ESP8266_ERR     -1
#define ESP8266_TIMEOUT -2

/**
 * @brief Initialize ESP8266 module. Sends AT to verify communication.
 * @return ESP8266_OK on success
 */
int8_t ESP8266_Init(void);

/**
 * @brief Send raw AT command and wait for expected response.
 * @param cmd       AT command string (e.g. "AT+RST")
 * @param resp      Expected response substring (e.g. "OK")
 * @param timeout   Timeout in ms
 * @return ESP8266_OK if response found, ESP8266_TIMEOUT otherwise
 */
int8_t ESP8266_SendAT(const char *cmd, const char *resp, uint32_t timeout);

/**
 * @brief Connect to WiFi access point (station mode).
 * @return ESP8266_OK on success
 */
int8_t ESP8266_ConnectWiFi(const char *ssid, const char *password);

/**
 * @brief Establish TCP connection to remote server.
 * @return ESP8266_OK on success
 */
int8_t ESP8266_ConnectTCP(const char *ip, uint16_t port);

/**
 * @brief Send data through established connection.
 * @return Number of bytes sent, or negative on error
 */
int16_t ESP8266_Send(const uint8_t *data, uint16_t len);

/**
 * @brief Read received data into buffer.
 * @return Number of bytes read (0 if no data)
 */
uint16_t ESP8266_Read(uint8_t *buf, uint16_t max_len);

/**
 * @brief Check if data is available to read.
 * @return 1 if data available, 0 if not
 */
uint8_t ESP8266_DataAvailable(void);

/**
 * @brief Close current TCP/UDP connection.
 */
void ESP8266_Disconnect(void);

/**
 * @brief Get local IP address string.
 * @param ip_buf  Output buffer (at least 16 bytes)
 */
void ESP8266_GetIP(char *ip_buf);

#ifdef __cplusplus
}
#endif

#endif /* __ESP8266_H */
