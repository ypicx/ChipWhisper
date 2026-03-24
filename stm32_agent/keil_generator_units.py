from __future__ import annotations

import re


def _render_app_header(filename: str) -> str:
    app_headers = {
        "led.h": _render_led_h,
        "button.h": _render_button_h,
        "active_buzzer.h": _render_active_buzzer_h,
        "passive_buzzer.h": _render_passive_buzzer_h,
        "debug_uart.h": _render_debug_uart_h,
    }
    renderer = app_headers.get(filename)
    return renderer() if renderer is not None else _render_placeholder_header(filename, group="App")

def _render_app_source(filename: str) -> str:
    app_sources = {
        "led.c": _render_led_c,
        "button.c": _render_button_c,
        "active_buzzer.c": _render_active_buzzer_c,
        "passive_buzzer.c": _render_passive_buzzer_c,
        "debug_uart.c": _render_debug_uart_c,
    }
    renderer = app_sources.get(filename)
    return renderer() if renderer is not None else _render_placeholder_source(filename, group="App")

def _render_module_header(filename: str) -> str:
    module_headers = {
        "ssd1306.h": _render_ssd1306_h,
        "mpu6050.h": _render_mpu6050_h,
        "at24c02.h": _render_at24c02_h,
        "bh1750.h": _render_bh1750_h,
        "ds18b20.h": _render_ds18b20_h,
    }
    renderer = module_headers.get(filename)
    return renderer() if renderer is not None else _render_placeholder_header(filename, group="Modules")

def _render_module_source(filename: str) -> str:
    module_sources = {
        "ssd1306.c": _render_ssd1306_c,
        "mpu6050.c": _render_mpu6050_c,
        "at24c02.c": _render_at24c02_c,
        "bh1750.c": _render_bh1750_c,
        "ds18b20.c": _render_ds18b20_c,
    }
    renderer = module_sources.get(filename)
    return renderer() if renderer is not None else _render_placeholder_source(filename, group="Modules")

def _render_led_h() -> str:
    return """#ifndef __LED_H
#define __LED_H

#include "main.h"

void LED_InitPin(GPIO_TypeDef *port, uint16_t pin);
void LED_Write(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state);
void LED_Toggle(GPIO_TypeDef *port, uint16_t pin);

#endif
"""

def _render_led_c() -> str:
    return """#include "led.h"

void LED_InitPin(GPIO_TypeDef *port, uint16_t pin)
{
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_RESET);
}

void LED_Write(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state)
{
    HAL_GPIO_WritePin(port, pin, state);
}

void LED_Toggle(GPIO_TypeDef *port, uint16_t pin)
{
    HAL_GPIO_TogglePin(port, pin);
}
"""

def _render_button_h() -> str:
    return """#ifndef __BUTTON_H
#define __BUTTON_H

#include "main.h"

void Button_InitPin(GPIO_TypeDef *port, uint16_t pin);
GPIO_PinState Button_Read(GPIO_TypeDef *port, uint16_t pin);

#endif
"""

def _render_button_c() -> str:
    return """#include "button.h"

void Button_InitPin(GPIO_TypeDef *port, uint16_t pin)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    GPIO_InitStruct.Pin = pin;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(port, &GPIO_InitStruct);
}

GPIO_PinState Button_Read(GPIO_TypeDef *port, uint16_t pin)
{
    return HAL_GPIO_ReadPin(port, pin);
}
"""

def _render_active_buzzer_h() -> str:
    return """#ifndef __ACTIVE_BUZZER_H
#define __ACTIVE_BUZZER_H

#include "main.h"

void ActiveBuzzer_InitPin(GPIO_TypeDef *port, uint16_t pin);
void ActiveBuzzer_Set(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state);

#endif
"""

def _render_active_buzzer_c() -> str:
    return """#include "active_buzzer.h"

void ActiveBuzzer_InitPin(GPIO_TypeDef *port, uint16_t pin)
{
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_RESET);
}

void ActiveBuzzer_Set(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state)
{
    HAL_GPIO_WritePin(port, pin, state);
}
"""

def _render_passive_buzzer_h() -> str:
    return """#ifndef __PASSIVE_BUZZER_H
#define __PASSIVE_BUZZER_H

#include "main.h"

HAL_StatusTypeDef PassiveBuzzer_Init(TIM_HandleTypeDef *htim, uint32_t channel);
HAL_StatusTypeDef PassiveBuzzer_Start(TIM_HandleTypeDef *htim, uint32_t channel, uint16_t pulse);
HAL_StatusTypeDef PassiveBuzzer_Stop(TIM_HandleTypeDef *htim, uint32_t channel);

#endif
"""

def _render_passive_buzzer_c() -> str:
    return """#include "passive_buzzer.h"

HAL_StatusTypeDef PassiveBuzzer_Init(TIM_HandleTypeDef *htim, uint32_t channel)
{
    __HAL_TIM_SET_COMPARE(htim, channel, 0);
    return HAL_TIM_PWM_Start(htim, channel);
}

HAL_StatusTypeDef PassiveBuzzer_Start(TIM_HandleTypeDef *htim, uint32_t channel, uint16_t pulse)
{
    __HAL_TIM_SET_COMPARE(htim, channel, pulse);
    return HAL_TIM_PWM_Start(htim, channel);
}

HAL_StatusTypeDef PassiveBuzzer_Stop(TIM_HandleTypeDef *htim, uint32_t channel)
{
    __HAL_TIM_SET_COMPARE(htim, channel, 0);
    return HAL_TIM_PWM_Stop(htim, channel);
}
"""

def _render_debug_uart_h() -> str:
    return """#ifndef __DEBUG_UART_H
#define __DEBUG_UART_H

#include "main.h"

HAL_StatusTypeDef DebugUart_Init(UART_HandleTypeDef *huart);
HAL_StatusTypeDef DebugUart_Write(UART_HandleTypeDef *huart, const uint8_t *data, uint16_t length, uint32_t timeout);
HAL_StatusTypeDef DebugUart_WriteLine(UART_HandleTypeDef *huart, const char *text, uint32_t timeout);

#endif
"""

def _render_debug_uart_c() -> str:
    return """#include "debug_uart.h"

#include <stddef.h>
#include <string.h>

HAL_StatusTypeDef DebugUart_Init(UART_HandleTypeDef *huart)
{
    return huart == NULL ? HAL_ERROR : HAL_OK;
}

HAL_StatusTypeDef DebugUart_Write(UART_HandleTypeDef *huart, const uint8_t *data, uint16_t length, uint32_t timeout)
{
    if (huart == NULL || data == NULL || length == 0U) {
        return HAL_ERROR;
    }
    return HAL_UART_Transmit(huart, (uint8_t *)data, length, timeout);
}

HAL_StatusTypeDef DebugUart_WriteLine(UART_HandleTypeDef *huart, const char *text, uint32_t timeout)
{
    HAL_StatusTypeDef status;
    static const uint8_t newline[] = "\\r\\n";

    if (text == NULL) {
        return HAL_ERROR;
    }

    status = DebugUart_Write(huart, (const uint8_t *)text, (uint16_t)strlen(text), timeout);
    if (status != HAL_OK) {
        return status;
    }
    return DebugUart_Write(huart, newline, (uint16_t)sizeof(newline) - 1U, timeout);
}
"""

def _render_ssd1306_h() -> str:
    return """#ifndef __SSD1306_H
#define __SSD1306_H

#include "main.h"

HAL_StatusTypeDef SSD1306_WriteCommand(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t command, uint32_t timeout);
HAL_StatusTypeDef SSD1306_WriteData(I2C_HandleTypeDef *hi2c, uint16_t address7, const uint8_t *data, uint16_t size, uint32_t timeout);
HAL_StatusTypeDef SSD1306_InitDefault(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef SSD1306_SetCursor(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t page, uint8_t column, uint32_t timeout);
HAL_StatusTypeDef SSD1306_Clear(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef SSD1306_WriteChar5x7(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t page,
    uint8_t column,
    char ch,
    uint32_t timeout
);
HAL_StatusTypeDef SSD1306_WriteString5x7(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t page,
    uint8_t column,
    const char *text,
    uint32_t timeout
);

#endif
"""

def _render_ssd1306_c() -> str:
    return """#include "ssd1306.h"

#include <stddef.h>

typedef struct {
    char ch;
    uint8_t cols[5];
} SSD1306_Font5x7Entry;

static const SSD1306_Font5x7Entry kSsd1306Font5x7[] = {
    {' ', {0x00, 0x00, 0x00, 0x00, 0x00}},
    {'-', {0x08, 0x08, 0x08, 0x08, 0x08}},
    {'.', {0x00, 0x60, 0x60, 0x00, 0x00}},
    {':', {0x00, 0x36, 0x36, 0x00, 0x00}},
    {'/', {0x20, 0x10, 0x08, 0x04, 0x02}},
    {'_', {0x40, 0x40, 0x40, 0x40, 0x40}},
    {'?', {0x02, 0x01, 0x51, 0x09, 0x06}},
    {'0', {0x3E, 0x51, 0x49, 0x45, 0x3E}},
    {'1', {0x00, 0x42, 0x7F, 0x40, 0x00}},
    {'2', {0x42, 0x61, 0x51, 0x49, 0x46}},
    {'3', {0x21, 0x41, 0x45, 0x4B, 0x31}},
    {'4', {0x18, 0x14, 0x12, 0x7F, 0x10}},
    {'5', {0x27, 0x45, 0x45, 0x45, 0x39}},
    {'6', {0x3C, 0x4A, 0x49, 0x49, 0x30}},
    {'7', {0x01, 0x71, 0x09, 0x05, 0x03}},
    {'8', {0x36, 0x49, 0x49, 0x49, 0x36}},
    {'9', {0x06, 0x49, 0x49, 0x29, 0x1E}},
    {'A', {0x7E, 0x11, 0x11, 0x11, 0x7E}},
    {'B', {0x7F, 0x49, 0x49, 0x49, 0x36}},
    {'C', {0x3E, 0x41, 0x41, 0x41, 0x22}},
    {'D', {0x7F, 0x41, 0x41, 0x22, 0x1C}},
    {'E', {0x7F, 0x49, 0x49, 0x49, 0x41}},
    {'F', {0x7F, 0x09, 0x09, 0x09, 0x01}},
    {'G', {0x3E, 0x41, 0x49, 0x49, 0x7A}},
    {'H', {0x7F, 0x08, 0x08, 0x08, 0x7F}},
    {'I', {0x00, 0x41, 0x7F, 0x41, 0x00}},
    {'J', {0x20, 0x40, 0x41, 0x3F, 0x01}},
    {'K', {0x7F, 0x08, 0x14, 0x22, 0x41}},
    {'L', {0x7F, 0x40, 0x40, 0x40, 0x40}},
    {'M', {0x7F, 0x02, 0x0C, 0x02, 0x7F}},
    {'N', {0x7F, 0x04, 0x08, 0x10, 0x7F}},
    {'O', {0x3E, 0x41, 0x41, 0x41, 0x3E}},
    {'P', {0x7F, 0x09, 0x09, 0x09, 0x06}},
    {'Q', {0x3E, 0x41, 0x51, 0x21, 0x5E}},
    {'R', {0x7F, 0x09, 0x19, 0x29, 0x46}},
    {'S', {0x46, 0x49, 0x49, 0x49, 0x31}},
    {'T', {0x01, 0x01, 0x7F, 0x01, 0x01}},
    {'U', {0x3F, 0x40, 0x40, 0x40, 0x3F}},
    {'V', {0x1F, 0x20, 0x40, 0x20, 0x1F}},
    {'W', {0x3F, 0x40, 0x38, 0x40, 0x3F}},
    {'X', {0x63, 0x14, 0x08, 0x14, 0x63}},
    {'Y', {0x07, 0x08, 0x70, 0x08, 0x07}},
    {'Z', {0x61, 0x51, 0x49, 0x45, 0x43}},
};

static void SSD1306_GetGlyph5x7(char ch, uint8_t out[5])
{
    uint32_t index;
    uint32_t glyph_count = (uint32_t)(sizeof(kSsd1306Font5x7) / sizeof(kSsd1306Font5x7[0]));

    if (ch >= 'a' && ch <= 'z') {
        ch = (char)(ch - 'a' + 'A');
    }

    for (index = 0; index < glyph_count; ++index) {
        if (kSsd1306Font5x7[index].ch == ch) {
            out[0] = kSsd1306Font5x7[index].cols[0];
            out[1] = kSsd1306Font5x7[index].cols[1];
            out[2] = kSsd1306Font5x7[index].cols[2];
            out[3] = kSsd1306Font5x7[index].cols[3];
            out[4] = kSsd1306Font5x7[index].cols[4];
            return;
        }
    }

    SSD1306_GetGlyph5x7('?', out);
}

static uint16_t SSD1306_DeviceAddress(uint16_t address7)
{
    return (uint16_t)(address7 << 1);
}

HAL_StatusTypeDef SSD1306_WriteCommand(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t command, uint32_t timeout)
{
    uint8_t frame[2] = {0x00, command};
    return HAL_I2C_Master_Transmit(hi2c, SSD1306_DeviceAddress(address7), frame, 2, timeout);
}

HAL_StatusTypeDef SSD1306_WriteData(I2C_HandleTypeDef *hi2c, uint16_t address7, const uint8_t *data, uint16_t size, uint32_t timeout)
{
    uint16_t index;
    for (index = 0; index < size; ++index) {
        uint8_t frame[2] = {0x40, data[index]};
        HAL_StatusTypeDef status = HAL_I2C_Master_Transmit(hi2c, SSD1306_DeviceAddress(address7), frame, 2, timeout);
        if (status != HAL_OK) {
            return status;
        }
    }
    return HAL_OK;
}

HAL_StatusTypeDef SSD1306_InitDefault(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    static const uint8_t init_sequence[] = {
        0xAE, 0x20, 0x00, 0x40, 0xA1, 0xC8, 0xA8, 0x3F,
        0xD3, 0x00, 0xDA, 0x12, 0xD5, 0x80, 0xD9, 0xF1,
        0xDB, 0x40, 0x8D, 0x14, 0xA4, 0xA6, 0xAF
    };
    uint16_t index;

    for (index = 0; index < (uint16_t)sizeof(init_sequence); ++index) {
        HAL_StatusTypeDef status = SSD1306_WriteCommand(hi2c, address7, init_sequence[index], timeout);
        if (status != HAL_OK) {
            return status;
        }
    }
    return HAL_OK;
}

HAL_StatusTypeDef SSD1306_SetCursor(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t page, uint8_t column, uint32_t timeout)
{
    HAL_StatusTypeDef status;

    status = SSD1306_WriteCommand(hi2c, address7, (uint8_t)(0xB0 | (page & 0x07U)), timeout);
    if (status != HAL_OK) {
        return status;
    }
    status = SSD1306_WriteCommand(hi2c, address7, (uint8_t)(0x00 | (column & 0x0FU)), timeout);
    if (status != HAL_OK) {
        return status;
    }
    return SSD1306_WriteCommand(hi2c, address7, (uint8_t)(0x10 | ((column >> 4) & 0x0FU)), timeout);
}

HAL_StatusTypeDef SSD1306_Clear(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    static const uint8_t clear_line[16] = {0};
    uint8_t page;
    uint8_t block;

    for (page = 0; page < 8U; ++page) {
        HAL_StatusTypeDef status = SSD1306_SetCursor(hi2c, address7, page, 0, timeout);
        if (status != HAL_OK) {
            return status;
        }
        for (block = 0; block < 8U; ++block) {
            status = SSD1306_WriteData(hi2c, address7, clear_line, (uint16_t)sizeof(clear_line), timeout);
            if (status != HAL_OK) {
                return status;
            }
        }
    }
    return HAL_OK;
}

HAL_StatusTypeDef SSD1306_WriteChar5x7(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t page,
    uint8_t column,
    char ch,
    uint32_t timeout
)
{
    uint8_t glyph[6] = {0};
    HAL_StatusTypeDef status;

    if (page >= 8U || column > 122U) {
        return HAL_ERROR;
    }

    SSD1306_GetGlyph5x7(ch, glyph);
    status = SSD1306_SetCursor(hi2c, address7, page, column, timeout);
    if (status != HAL_OK) {
        return status;
    }
    return SSD1306_WriteData(hi2c, address7, glyph, (uint16_t)sizeof(glyph), timeout);
}

HAL_StatusTypeDef SSD1306_WriteString5x7(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t page,
    uint8_t column,
    const char *text,
    uint32_t timeout
)
{
    HAL_StatusTypeDef status;

    if (text == NULL) {
        return HAL_ERROR;
    }

    while (*text != '\\0') {
        if (*text == '\\n') {
            ++page;
            column = 0U;
            ++text;
            continue;
        }

        if (page >= 8U) {
            return HAL_ERROR;
        }
        if (column > 122U) {
            ++page;
            column = 0U;
            if (page >= 8U) {
                return HAL_ERROR;
            }
        }

        status = SSD1306_WriteChar5x7(hi2c, address7, page, column, *text, timeout);
        if (status != HAL_OK) {
            return status;
        }

        column = (uint8_t)(column + 6U);
        ++text;
    }

    return HAL_OK;
}
"""

def _render_mpu6050_h() -> str:
    return """#ifndef __MPU6050_H
#define __MPU6050_H

#include "main.h"

HAL_StatusTypeDef MPU6050_WriteRegister(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t reg, uint8_t value, uint32_t timeout);
HAL_StatusTypeDef MPU6050_ReadRegister(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t reg, uint8_t *value, uint32_t timeout);
HAL_StatusTypeDef MPU6050_ReadRegisters(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t reg, uint8_t *buffer, uint16_t length, uint32_t timeout);
HAL_StatusTypeDef MPU6050_ReadWhoAmI(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t *value, uint32_t timeout);
HAL_StatusTypeDef MPU6050_Wake(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef MPU6050_ReadAccelRaw(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    int16_t *accel_x,
    int16_t *accel_y,
    int16_t *accel_z,
    uint32_t timeout
);

#endif
"""

def _render_mpu6050_c() -> str:
    return """#include "mpu6050.h"

#include <stddef.h>

static uint16_t MPU6050_DeviceAddress(uint16_t address7)
{
    return (uint16_t)(address7 << 1);
}

HAL_StatusTypeDef MPU6050_WriteRegister(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t reg, uint8_t value, uint32_t timeout)
{
    return HAL_I2C_Mem_Write(hi2c, MPU6050_DeviceAddress(address7), reg, I2C_MEMADD_SIZE_8BIT, &value, 1, timeout);
}

HAL_StatusTypeDef MPU6050_ReadRegister(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t reg, uint8_t *value, uint32_t timeout)
{
    if (value == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Mem_Read(hi2c, MPU6050_DeviceAddress(address7), reg, I2C_MEMADD_SIZE_8BIT, value, 1, timeout);
}

HAL_StatusTypeDef MPU6050_ReadRegisters(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t reg, uint8_t *buffer, uint16_t length, uint32_t timeout)
{
    if (buffer == NULL || length == 0U) {
        return HAL_ERROR;
    }
    return HAL_I2C_Mem_Read(hi2c, MPU6050_DeviceAddress(address7), reg, I2C_MEMADD_SIZE_8BIT, buffer, length, timeout);
}

HAL_StatusTypeDef MPU6050_ReadWhoAmI(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t *value, uint32_t timeout)
{
    return MPU6050_ReadRegister(hi2c, address7, 0x75, value, timeout);
}

HAL_StatusTypeDef MPU6050_Wake(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    return MPU6050_WriteRegister(hi2c, address7, 0x6B, 0x00, timeout);
}

HAL_StatusTypeDef MPU6050_ReadAccelRaw(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    int16_t *accel_x,
    int16_t *accel_y,
    int16_t *accel_z,
    uint32_t timeout
)
{
    uint8_t buffer[6];
    HAL_StatusTypeDef status;

    if (accel_x == NULL || accel_y == NULL || accel_z == NULL) {
        return HAL_ERROR;
    }

    status = MPU6050_ReadRegisters(hi2c, address7, 0x3B, buffer, (uint16_t)sizeof(buffer), timeout);
    if (status != HAL_OK) {
        return status;
    }

    *accel_x = (int16_t)((buffer[0] << 8) | buffer[1]);
    *accel_y = (int16_t)((buffer[2] << 8) | buffer[3]);
    *accel_z = (int16_t)((buffer[4] << 8) | buffer[5]);
    return HAL_OK;
}
"""

def _render_at24c02_h() -> str:
    return """#ifndef __AT24C02_H
#define __AT24C02_H

#include "main.h"

HAL_StatusTypeDef AT24C02_WriteByte(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t mem_addr, uint8_t value, uint32_t timeout);
HAL_StatusTypeDef AT24C02_ReadByte(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t mem_addr, uint8_t *value, uint32_t timeout);

#endif
"""

def _render_at24c02_c() -> str:
    return """#include "at24c02.h"

#include <stddef.h>

static uint16_t AT24C02_DeviceAddress(uint16_t address7)
{
    return (uint16_t)(address7 << 1);
}

HAL_StatusTypeDef AT24C02_WriteByte(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t mem_addr, uint8_t value, uint32_t timeout)
{
    HAL_StatusTypeDef status = HAL_I2C_Mem_Write(hi2c, AT24C02_DeviceAddress(address7), mem_addr, I2C_MEMADD_SIZE_8BIT, &value, 1, timeout);
    if (status != HAL_OK) {
        return status;
    }
    HAL_Delay(5);
    return HAL_OK;
}

HAL_StatusTypeDef AT24C02_ReadByte(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t mem_addr, uint8_t *value, uint32_t timeout)
{
    if (value == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Mem_Read(hi2c, AT24C02_DeviceAddress(address7), mem_addr, I2C_MEMADD_SIZE_8BIT, value, 1, timeout);
}
"""

def _render_bh1750_h() -> str:
    return """#ifndef __BH1750_H
#define __BH1750_H

#include "main.h"

HAL_StatusTypeDef BH1750_SendCommand(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t command, uint32_t timeout);
HAL_StatusTypeDef BH1750_ReadRaw(I2C_HandleTypeDef *hi2c, uint16_t address7, uint16_t *raw, uint32_t timeout);
HAL_StatusTypeDef BH1750_PowerOn(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef BH1750_StartContinuousHighRes(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
float BH1750_ConvertToLux(uint16_t raw);
HAL_StatusTypeDef BH1750_ReadLux(I2C_HandleTypeDef *hi2c, uint16_t address7, float *lux, uint32_t timeout);

#endif
"""

def _render_bh1750_c() -> str:
    return """#include "bh1750.h"

#include <stddef.h>

static uint16_t BH1750_DeviceAddress(uint16_t address7)
{
    return (uint16_t)(address7 << 1);
}

HAL_StatusTypeDef BH1750_SendCommand(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t command, uint32_t timeout)
{
    return HAL_I2C_Master_Transmit(hi2c, BH1750_DeviceAddress(address7), &command, 1, timeout);
}

HAL_StatusTypeDef BH1750_ReadRaw(I2C_HandleTypeDef *hi2c, uint16_t address7, uint16_t *raw, uint32_t timeout)
{
    uint8_t buffer[2];
    HAL_StatusTypeDef status;

    if (raw == NULL) {
        return HAL_ERROR;
    }

    status = HAL_I2C_Master_Receive(hi2c, BH1750_DeviceAddress(address7), buffer, 2, timeout);
    if (status != HAL_OK) {
        return status;
    }

    *raw = (uint16_t)((buffer[0] << 8) | buffer[1]);
    return HAL_OK;
}

HAL_StatusTypeDef BH1750_PowerOn(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    return BH1750_SendCommand(hi2c, address7, 0x01, timeout);
}

HAL_StatusTypeDef BH1750_StartContinuousHighRes(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    return BH1750_SendCommand(hi2c, address7, 0x10, timeout);
}

float BH1750_ConvertToLux(uint16_t raw)
{
    return (float)raw / 1.2f;
}

HAL_StatusTypeDef BH1750_ReadLux(I2C_HandleTypeDef *hi2c, uint16_t address7, float *lux, uint32_t timeout)
{
    uint16_t raw = 0U;
    HAL_StatusTypeDef status;

    if (lux == NULL) {
        return HAL_ERROR;
    }

    status = BH1750_ReadRaw(hi2c, address7, &raw, timeout);
    if (status != HAL_OK) {
        return status;
    }

    *lux = BH1750_ConvertToLux(raw);
    return HAL_OK;
}
"""

def _render_ds18b20_h() -> str:
    return """#ifndef __DS18B20_H
#define __DS18B20_H

#include "main.h"

void DS18B20_DriveLow(GPIO_TypeDef *port, uint16_t pin);
void DS18B20_ReleaseBus(GPIO_TypeDef *port, uint16_t pin);
GPIO_PinState DS18B20_ReadLine(GPIO_TypeDef *port, uint16_t pin);

#endif
"""

def _render_ds18b20_c() -> str:
    return """#include "ds18b20.h"

void DS18B20_DriveLow(GPIO_TypeDef *port, uint16_t pin)
{
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_RESET);
}

void DS18B20_ReleaseBus(GPIO_TypeDef *port, uint16_t pin)
{
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_SET);
}

GPIO_PinState DS18B20_ReadLine(GPIO_TypeDef *port, uint16_t pin)
{
    return HAL_GPIO_ReadPin(port, pin);
}
"""

def _render_placeholder_header(filename: str, group: str) -> str:
    guard = re.sub(r"[^A-Za-z0-9]", "_", filename).upper()
    return f"""#ifndef __{guard}
#define __{guard}

/* TODO: implement {group} header {filename}. */

#endif
"""

def _render_placeholder_source(filename: str, group: str) -> str:
    header = filename[:-2] + ".h" if filename.endswith(".c") else ""
    include = f'#include "{header}"\n\n' if header else ""
    return f"""{include}/* TODO: implement {group} source {filename}. */
"""
