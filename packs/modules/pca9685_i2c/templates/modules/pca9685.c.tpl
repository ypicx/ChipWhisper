#include "pca9685.h"

HAL_StatusTypeDef PCA9685_Init(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    uint8_t mode1 = 0x00U;
    if (hi2c == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0x00U, I2C_MEMADD_SIZE_8BIT, &mode1, 1U, timeout);
}

HAL_StatusTypeDef PCA9685_SetPwmFrequencyHz(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint16_t frequency_hz,
    uint32_t timeout
)
{
    uint8_t old_mode = 0U;
    uint8_t prescale;
    uint8_t new_mode;

    if (hi2c == NULL || frequency_hz == 0U) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Mem_Read(hi2c, (uint16_t)(address7 << 1), 0x00U, I2C_MEMADD_SIZE_8BIT, &old_mode, 1U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    prescale = (uint8_t)((25000000UL / (4096UL * frequency_hz)) - 1UL);
    new_mode = (uint8_t)((old_mode & 0x7FU) | 0x10U);
    if (HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0x00U, I2C_MEMADD_SIZE_8BIT, &new_mode, 1U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0xFEU, I2C_MEMADD_SIZE_8BIT, &prescale, 1U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0x00U, I2C_MEMADD_SIZE_8BIT, &old_mode, 1U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    HAL_Delay(1);
    old_mode = (uint8_t)(old_mode | 0xA1U);
    return HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), 0x00U, I2C_MEMADD_SIZE_8BIT, &old_mode, 1U, timeout);
}

HAL_StatusTypeDef PCA9685_SetPwm(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t channel,
    uint16_t on_count,
    uint16_t off_count,
    uint32_t timeout
)
{
    uint8_t payload[4];
    uint8_t register_address;

    if (hi2c == NULL || channel > 15U) {
        return HAL_ERROR;
    }
    register_address = (uint8_t)(0x06U + (4U * channel));
    payload[0] = (uint8_t)(on_count & 0xFFU);
    payload[1] = (uint8_t)(on_count >> 8);
    payload[2] = (uint8_t)(off_count & 0xFFU);
    payload[3] = (uint8_t)(off_count >> 8);
    return HAL_I2C_Mem_Write(hi2c, (uint16_t)(address7 << 1), register_address, I2C_MEMADD_SIZE_8BIT, payload, 4U, timeout);
}
