#include "ina219.h"

static HAL_StatusTypeDef INA219_ReadRegister(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t register_address,
    uint16_t *value,
    uint32_t timeout
)
{
    uint8_t buffer[2] = {0};

    if (hi2c == NULL || value == NULL) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Mem_Read(hi2c, (uint16_t)(address7 << 1), register_address, I2C_MEMADD_SIZE_8BIT, buffer, 2U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    *value = (uint16_t)(((uint16_t)buffer[0] << 8) | (uint16_t)buffer[1]);
    return HAL_OK;
}

HAL_StatusTypeDef INA219_ConfigDefault(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    uint8_t payload[2] = {0x39U, 0x9FU};
    if (hi2c == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0x00U, I2C_MEMADD_SIZE_8BIT, payload, 2U, timeout);
}

HAL_StatusTypeDef INA219_ReadShuntVoltageUv(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    int32_t *microvolts,
    uint32_t timeout
)
{
    uint16_t raw_value = 0U;
    if (INA219_ReadRegister(hi2c, address7, 0x01U, &raw_value, timeout) != HAL_OK || microvolts == NULL) {
        return HAL_ERROR;
    }
    *microvolts = (int32_t)((int16_t)raw_value) * 10;
    return HAL_OK;
}

HAL_StatusTypeDef INA219_ReadBusVoltageMv(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t *millivolts,
    uint32_t timeout
)
{
    uint16_t raw_value = 0U;
    if (INA219_ReadRegister(hi2c, address7, 0x02U, &raw_value, timeout) != HAL_OK || millivolts == NULL) {
        return HAL_ERROR;
    }
    *millivolts = (uint16_t)(((raw_value >> 3) & 0x1FFFU) * 4U);
    return HAL_OK;
}
