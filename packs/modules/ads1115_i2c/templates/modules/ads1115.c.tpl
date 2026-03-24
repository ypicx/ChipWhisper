#include "ads1115.h"

HAL_StatusTypeDef ADS1115_StartSingleEnded(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t channel,
    uint32_t timeout
)
{
    uint16_t config;
    uint8_t payload[2];

    if (hi2c == NULL || channel > 3U) {
        return HAL_ERROR;
    }

    config = (uint16_t)(
        0x8000U
        | (uint16_t)((0x04U + channel) << 12)
        | 0x0200U
        | 0x0100U
        | 0x0080U
        | 0x0003U
    );
    payload[0] = (uint8_t)(config >> 8);
    payload[1] = (uint8_t)(config & 0xFFU);
    return HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0x01U, I2C_MEMADD_SIZE_8BIT, payload, 2U, timeout);
}

HAL_StatusTypeDef ADS1115_ReadConversion(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    int16_t *value,
    uint32_t timeout
)
{
    uint8_t payload[2] = {0};

    if (hi2c == NULL || value == NULL) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Mem_Read(hi2c, (uint16_t)(address7 << 1), 0x00U, I2C_MEMADD_SIZE_8BIT, payload, 2U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    *value = (int16_t)(((uint16_t)payload[0] << 8) | (uint16_t)payload[1]);
    return HAL_OK;
}
