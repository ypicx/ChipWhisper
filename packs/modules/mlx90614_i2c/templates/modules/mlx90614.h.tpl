#ifndef __MLX90614_H
#define __MLX90614_H

#include "main.h"

HAL_StatusTypeDef MLX90614_ReadAmbientTempC(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    float *temperature_c,
    uint32_t timeout
);
HAL_StatusTypeDef MLX90614_ReadObjectTempC(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    float *temperature_c,
    uint32_t timeout
);

#endif
