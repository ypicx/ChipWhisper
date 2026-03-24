#ifndef __PCF8574_H
#define __PCF8574_H

#include "main.h"

HAL_StatusTypeDef PCF8574_WritePort(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t value, uint32_t timeout);
HAL_StatusTypeDef PCF8574_ReadPort(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t *value, uint32_t timeout);
HAL_StatusTypeDef PCF8574_WritePin(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t pin_index,
    GPIO_PinState state,
    uint32_t timeout
);

#endif
