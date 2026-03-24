#ifndef __PCF8591_H
#define __PCF8591_H

#include "main.h"

HAL_StatusTypeDef PCF8591_ReadAdcChannel(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t channel,
    uint8_t *value,
    uint32_t timeout
);
HAL_StatusTypeDef PCF8591_WriteDac(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t value,
    uint32_t timeout
);

#endif
