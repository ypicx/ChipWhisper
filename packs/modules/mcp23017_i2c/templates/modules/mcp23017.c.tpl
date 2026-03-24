#include "mcp23017.h"

HAL_StatusTypeDef MCP23017_SetDirection(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t iodir_a,
    uint8_t iodir_b,
    uint32_t timeout
)
{
    uint8_t payload[2] = {iodir_a, iodir_b};
    if (hi2c == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0x00U, I2C_MEMADD_SIZE_8BIT, payload, 2U, timeout);
}

HAL_StatusTypeDef MCP23017_WriteGpio(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t value_a,
    uint8_t value_b,
    uint32_t timeout
)
{
    uint8_t payload[2] = {value_a, value_b};
    if (hi2c == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0x12U, I2C_MEMADD_SIZE_8BIT, payload, 2U, timeout);
}

HAL_StatusTypeDef MCP23017_ReadGpio(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t *value_a,
    uint8_t *value_b,
    uint32_t timeout
)
{
    uint8_t payload[2] = {0};
    if (hi2c == NULL || value_a == NULL || value_b == NULL) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Mem_Read(hi2c, (uint16_t)(address7 << 1), 0x12U, I2C_MEMADD_SIZE_8BIT, payload, 2U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    *value_a = payload[0];
    *value_b = payload[1];
    return HAL_OK;
}
