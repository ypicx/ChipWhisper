#include "sht30.h"

static uint8_t SHT30_CalculateCrc(const uint8_t *data, uint8_t length)
{
    uint8_t crc = 0xFFU;
    uint8_t index;
    uint8_t bit_index;

    for (index = 0U; index < length; ++index) {
        crc ^= data[index];
        for (bit_index = 0U; bit_index < 8U; ++bit_index) {
            if ((crc & 0x80U) != 0U) {
                crc = (uint8_t)((crc << 1U) ^ 0x31U);
            } else {
                crc <<= 1U;
            }
        }
    }
    return crc;
}

HAL_StatusTypeDef SHT30_ReadMeasurement(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    SHT30_Measurement *measurement,
    uint32_t timeout
)
{
    uint8_t command[2] = {0x24U, 0x00U};
    uint8_t payload[6] = {0};
    uint16_t temp_raw;
    uint16_t hum_raw;

    if (hi2c == NULL || measurement == NULL) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), command, 2U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    HAL_Delay(20);
    if (HAL_I2C_Master_Receive(hi2c, (uint16_t)(address7 << 1), payload, (uint16_t)sizeof(payload), timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (SHT30_CalculateCrc(&payload[0], 2U) != payload[2] || SHT30_CalculateCrc(&payload[3], 2U) != payload[5]) {
        return HAL_ERROR;
    }

    temp_raw = (uint16_t)(((uint16_t)payload[0] << 8) | (uint16_t)payload[1]);
    hum_raw = (uint16_t)(((uint16_t)payload[3] << 8) | (uint16_t)payload[4]);
    measurement->temperature_c = -45.0f + (175.0f * (float)temp_raw / 65535.0f);
    measurement->humidity_rh = 100.0f * (float)hum_raw / 65535.0f;
    return HAL_OK;
}
