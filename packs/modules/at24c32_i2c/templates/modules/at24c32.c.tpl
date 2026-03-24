#include "at24c32.h"

HAL_StatusTypeDef AT24C32_ReadBuffer(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t memory_address,
    uint8_t *buffer,
    uint16_t length,
    uint32_t timeout
)
{
    if (hi2c == NULL || buffer == NULL || length == 0U) {
        return HAL_ERROR;
    }
    return HAL_I2C_Mem_Read(
        hi2c,
        (uint16_t)(address7 << 1),
        memory_address,
        I2C_MEMADD_SIZE_16BIT,
        buffer,
        length,
        timeout
    );
}

HAL_StatusTypeDef AT24C32_WritePage(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t memory_address,
    const uint8_t *buffer,
    uint16_t length,
    uint32_t timeout
)
{
    HAL_StatusTypeDef status;

    if (hi2c == NULL || buffer == NULL || length == 0U || length > 32U) {
        return HAL_ERROR;
    }
    status = HAL_I2C_Mem_Write(
        hi2c,
        (uint16_t)(address7 << 1),
        memory_address,
        I2C_MEMADD_SIZE_16BIT,
        (uint8_t *)buffer,
        length,
        timeout
    );
    if (status == HAL_OK) {
        HAL_Delay(10);
    }
    return status;
}

HAL_StatusTypeDef AT24C32_ReadByte(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t memory_address,
    uint8_t *value,
    uint32_t timeout
)
{
    return AT24C32_ReadBuffer(hi2c, address7, memory_address, value, 1U, timeout);
}

HAL_StatusTypeDef AT24C32_WriteByte(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t memory_address,
    uint8_t value,
    uint32_t timeout
)
{
    return AT24C32_WritePage(hi2c, address7, memory_address, &value, 1U, timeout);
}
