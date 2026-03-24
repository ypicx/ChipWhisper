#include "mcp4017.h"

HAL_StatusTypeDef MCP4017_SetWiper(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t value, uint32_t timeout)
{
    uint8_t data;

    if (hi2c == NULL) {
        return HAL_ERROR;
    }

    data = (uint8_t)(value & 0x7FU);
    return HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), &data, 1U, timeout);
}

HAL_StatusTypeDef MCP4017_ReadWiper(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t *value, uint32_t timeout)
{
    uint8_t data = 0U;
    HAL_StatusTypeDef status;

    if (hi2c == NULL || value == NULL) {
        return HAL_ERROR;
    }

    status = HAL_I2C_Master_Receive(hi2c, (uint16_t)((address7 << 1) | 0x01U), &data, 1U, timeout);
    if (status == HAL_OK) {
        *value = (uint8_t)(data & 0x7FU);
    }
    return status;
}
