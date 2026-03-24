#ifndef __AHT20_H
#define __AHT20_H

#include "main.h"

typedef struct
{
    float temperature_c;
    float humidity_rh;
} AHT20_Measurement;

HAL_StatusTypeDef AHT20_Init(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout);
HAL_StatusTypeDef AHT20_ReadMeasurement(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    AHT20_Measurement *measurement,
    uint32_t timeout
);

#endif
