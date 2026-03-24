#include "ds1307.h"

static uint8_t DS1307_BcdToBin(uint8_t value)
{
    return (uint8_t)(((value >> 4) * 10U) + (value & 0x0FU));
}

static uint8_t DS1307_BinToBcd(uint8_t value)
{
    return (uint8_t)(((value / 10U) << 4) | (value % 10U));
}

HAL_StatusTypeDef DS1307_ReadDateTime(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    DS1307_DateTime *date_time,
    uint32_t timeout
)
{
    uint8_t register_address = 0x00U;
    uint8_t payload[7] = {0};
    HAL_StatusTypeDef status;

    if (hi2c == NULL || date_time == NULL) {
        return HAL_ERROR;
    }

    status = HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), &register_address, 1U, timeout);
    if (status != HAL_OK) {
        return status;
    }
    status = HAL_I2C_Master_Receive(hi2c, (uint16_t)(address7 << 1), payload, (uint16_t)sizeof(payload), timeout);
    if (status != HAL_OK) {
        return status;
    }

    date_time->seconds = DS1307_BcdToBin((uint8_t)(payload[0] & 0x7FU));
    date_time->minutes = DS1307_BcdToBin((uint8_t)(payload[1] & 0x7FU));
    date_time->hours = DS1307_BcdToBin((uint8_t)(payload[2] & 0x3FU));
    date_time->day_of_week = DS1307_BcdToBin((uint8_t)(payload[3] & 0x07U));
    date_time->day_of_month = DS1307_BcdToBin((uint8_t)(payload[4] & 0x3FU));
    date_time->month = DS1307_BcdToBin((uint8_t)(payload[5] & 0x1FU));
    date_time->year = DS1307_BcdToBin(payload[6]);
    return HAL_OK;
}

HAL_StatusTypeDef DS1307_WriteDateTime(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    const DS1307_DateTime *date_time,
    uint32_t timeout
)
{
    uint8_t payload[8] = {0};

    if (hi2c == NULL || date_time == NULL) {
        return HAL_ERROR;
    }

    payload[0] = 0x00U;
    payload[1] = DS1307_BinToBcd((uint8_t)(date_time->seconds & 0x7FU));
    payload[2] = DS1307_BinToBcd(date_time->minutes);
    payload[3] = DS1307_BinToBcd(date_time->hours);
    payload[4] = DS1307_BinToBcd(date_time->day_of_week);
    payload[5] = DS1307_BinToBcd(date_time->day_of_month);
    payload[6] = DS1307_BinToBcd(date_time->month);
    payload[7] = DS1307_BinToBcd(date_time->year);

    return HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), payload, (uint16_t)sizeof(payload), timeout);
}
