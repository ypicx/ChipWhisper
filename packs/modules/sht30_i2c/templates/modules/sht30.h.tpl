#ifndef __SHT30_H
#define __SHT30_H

#include "main.h"

typedef struct
{
    float temperature_c;
    float humidity_rh;
} SHT30_Measurement;

HAL_StatusTypeDef SHT30_ReadMeasurement(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    SHT30_Measurement *measurement,
    uint32_t timeout
);

#endif
