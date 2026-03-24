#include "pcf8591.h"

HAL_StatusTypeDef PCF8591_ReadAdcChannel(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t channel,
    uint8_t *value,
    uint32_t timeout
)
{
    uint8_t control;
    uint8_t dummy = 0U;

    if (hi2c == NULL || value == NULL || channel > 3U) {
        return HAL_ERROR;
    }
    control = (uint8_t)(0x40U | channel);
    if (HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), &control, 1U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Master_Receive(hi2c, (uint16_t)(address7 << 1), &dummy, 1U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    return HAL_I2C_Master_Receive(hi2c, (uint16_t)(address7 << 1), value, 1U, timeout);
}

HAL_StatusTypeDef PCF8591_WriteDac(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t value,
    uint32_t timeout
)
{
    uint8_t payload[2] = {0x40U, value};

    if (hi2c == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), payload, 2U, timeout);
}
