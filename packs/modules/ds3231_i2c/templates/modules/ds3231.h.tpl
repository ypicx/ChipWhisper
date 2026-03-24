#ifndef __DS3231_H
#define __DS3231_H

#include "main.h"

typedef struct
{
    uint8_t seconds;
    uint8_t minutes;
    uint8_t hours;
    uint8_t day_of_week;
    uint8_t day_of_month;
    uint8_t month;
    uint8_t year;
} DS3231_DateTime;

HAL_StatusTypeDef DS3231_ReadDateTime(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    DS3231_DateTime *date_time,
    uint32_t timeout
);
HAL_StatusTypeDef DS3231_WriteDateTime(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    const DS3231_DateTime *date_time,
    uint32_t timeout
);

#endif
