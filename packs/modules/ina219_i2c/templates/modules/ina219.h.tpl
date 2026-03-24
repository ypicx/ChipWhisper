#ifndef __INA219_H
#define __INA219_H

#include "main.h"

HAL_StatusTypeDef INA219_ConfigDefault(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef INA219_ReadShuntVoltageUv(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    int32_t *microvolts,
    uint32_t timeout
);
HAL_StatusTypeDef INA219_ReadBusVoltageMv(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t *millivolts,
    uint32_t timeout
);

#endif
