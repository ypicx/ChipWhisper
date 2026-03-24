#ifndef __UART_FRAME_H
#define __UART_FRAME_H

#include "main.h"

#define UART_FRAME_MAX_BYTES 128U

typedef struct
{
    const char *name;
    UART_HandleTypeDef *huart;
    uint8_t buffer[UART_FRAME_MAX_BYTES];
    uint16_t length;
    uint8_t delimiter;
    uint8_t overflowed;
    uint32_t idle_gap_ms;
    uint32_t last_rx_ms;
} UartFramePort;

void UartFrame_Init(UartFramePort *port, const char *name, UART_HandleTypeDef *huart);
void UartFrame_SetLineMode(UartFramePort *port, uint8_t delimiter, uint32_t idle_gap_ms);
void UartFrame_Reset(UartFramePort *port);
void UartFrame_Process(UartFramePort *port, uint32_t now_ms);
uint8_t UartFrame_Matches(const UartFramePort *port, const char *name);
void UartFrame_OnFrame(const UartFramePort *port, const uint8_t *data, uint16_t length, uint8_t overflowed);

#endif
