#ifndef __ADS1115_H
#define __ADS1115_H

#include "main.h"

HAL_StatusTypeDef ADS1115_StartSingleEnded(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t channel,
    uint32_t timeout
);
HAL_StatusTypeDef ADS1115_ReadConversion(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    int16_t *value,
    uint32_t timeout
);

#endif
