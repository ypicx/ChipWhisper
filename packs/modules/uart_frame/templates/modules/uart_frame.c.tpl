#include "uart_frame.h"

#include <string.h>

static uint8_t UartFrame_TimeReached(uint32_t now_ms, uint32_t timestamp_ms)
{
    return ((int32_t)(now_ms - timestamp_ms) >= 0) ? 1U : 0U;
}

static void UartFrame_Emit(UartFramePort *port)
{
    if (port == NULL) {
        return;
    }

    if (port->length < UART_FRAME_MAX_BYTES) {
        port->buffer[port->length] = 0U;
    } else {
        port->buffer[UART_FRAME_MAX_BYTES - 1U] = 0U;
    }

    if (port->length > 0U || port->overflowed) {
        UartFrame_OnFrame(port, port->buffer, port->length, port->overflowed);
    }
    UartFrame_Reset(port);
}

void UartFrame_Init(UartFramePort *port, const char *name, UART_HandleTypeDef *huart)
{
    if (port == NULL) {
        return;
    }

    port->name = name;
    port->huart = huart;
    port->delimiter = 10U;
    port->idle_gap_ms = 20U;
    UartFrame_Reset(port);
}

void UartFrame_SetLineMode(UartFramePort *port, uint8_t delimiter, uint32_t idle_gap_ms)
{
    if (port == NULL) {
        return;
    }

    port->delimiter = delimiter;
    port->idle_gap_ms = idle_gap_ms;
}

void UartFrame_Reset(UartFramePort *port)
{
    if (port == NULL) {
        return;
    }

    port->length = 0U;
    port->overflowed = 0U;
    port->last_rx_ms = 0U;
    memset(port->buffer, 0, sizeof(port->buffer));
}

void UartFrame_Process(UartFramePort *port, uint32_t now_ms)
{
    uint8_t byte;

    if (port == NULL || port->huart == NULL) {
        return;
    }

    while (HAL_UART_Receive(port->huart, &byte, 1U, 0U) == HAL_OK) {
        port->last_rx_ms = now_ms;
        if (byte == port->delimiter) {
            UartFrame_Emit(port);
            continue;
        }

        if (port->length < (UART_FRAME_MAX_BYTES - 1U)) {
            port->buffer[port->length] = byte;
            port->length = (uint16_t)(port->length + 1U);
        } else {
            port->overflowed = 1U;
        }
    }

    if (port->idle_gap_ms > 0U
        && port->length > 0U
        && UartFrame_TimeReached(now_ms, port->last_rx_ms + port->idle_gap_ms)) {
        UartFrame_Emit(port);
    }
}

uint8_t UartFrame_Matches(const UartFramePort *port, const char *name)
{
    if (port == NULL || port->name == NULL || name == NULL) {
        return 0U;
    }
    return (strcmp(port->name, name) == 0) ? 1U : 0U;
}

__weak void UartFrame_OnFrame(const UartFramePort *port, const uint8_t *data, uint16_t length, uint8_t overflowed)
{
    (void)port;
    (void)data;
    (void)length;
    (void)overflowed;
}
