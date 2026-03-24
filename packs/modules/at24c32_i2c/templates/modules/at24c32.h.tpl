#ifndef __AT24C32_H
#define __AT24C32_H

#include "main.h"

HAL_StatusTypeDef AT24C32_ReadBuffer(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t memory_address,
    uint8_t *buffer,
    uint16_t length,
    uint32_t timeout
);
HAL_StatusTypeDef AT24C32_WritePage(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t memory_address,
    const uint8_t *buffer,
    uint16_t length,
    uint32_t timeout
);
HAL_StatusTypeDef AT24C32_ReadByte(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t memory_address,
    uint8_t *value,
    uint32_t timeout
);
HAL_StatusTypeDef AT24C32_WriteByte(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t memory_address,
    uint8_t value,
    uint32_t timeout
);

#endif
