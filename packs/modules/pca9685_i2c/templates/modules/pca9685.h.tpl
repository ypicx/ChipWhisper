#ifndef __PCA9685_H
#define __PCA9685_H

#include "main.h"

HAL_StatusTypeDef PCA9685_Init(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef PCA9685_SetPwmFrequencyHz(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t frequency_hz,
    uint32_t timeout
);
HAL_StatusTypeDef PCA9685_SetPwm(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t channel,
    uint16_t on_count,
    uint16_t off_count,
    uint32_t timeout
);

#endif
