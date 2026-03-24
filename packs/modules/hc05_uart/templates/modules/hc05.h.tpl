#ifndef __HC05_H
#define __HC05_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"
#include <stdarg.h>

/* UART handle - override in app_config.h */
#ifndef HC05_UART_HANDLE
#define HC05_UART_HANDLE  huart2
#endif

#ifndef HC05_RX_BUF_SIZE
#define HC05_RX_BUF_SIZE  256
#endif

/**
 * @brief Initialize HC-05 Bluetooth UART.
 * @param baud  Baud rate (default 9600 for data mode)
 */
void HC05_Init(uint32_t baud);

/**
 * @brief Send raw data.
 */
void HC05_Send(const uint8_t *data, uint16_t len);

/**
 * @brief Printf-style formatted send.
 */
void HC05_Printf(const char *fmt, ...);

/**
 * @brief Read received data into buffer.
 * @return Number of bytes read
 */
uint16_t HC05_Read(uint8_t *buf, uint16_t max_len);

/**
 * @brief Check if data is available.
 * @return 1 if data available
 */
uint8_t HC05_DataAvailable(void);

/**
 * @brief Send AT command (only works in AT mode with KEY pin HIGH).
 * @return 0 on success
 */
int8_t HC05_SendAT(const char *cmd, char *resp, uint16_t resp_size, uint32_t timeout);

#ifdef __cplusplus
}
#endif

#endif /* __HC05_H */
