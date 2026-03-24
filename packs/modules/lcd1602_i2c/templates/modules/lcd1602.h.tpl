#ifndef __LCD1602_H
#define __LCD1602_H

#include "main.h"

HAL_StatusTypeDef LCD1602_Init(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef LCD1602_Clear(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef LCD1602_SetCursor(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t row,
    uint8_t column,
    uint32_t timeout
);
HAL_StatusTypeDef LCD1602_WriteString(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    const char *text,
    uint32_t timeout
);

#endif
