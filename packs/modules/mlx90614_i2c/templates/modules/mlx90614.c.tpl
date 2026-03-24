#include "mlx90614.h"

static HAL_StatusTypeDef MLX90614_ReadWord(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t register_address,
    uint16_t *value,
    uint32_t timeout
)
{
    uint8_t payload[3] = {0};

    if (hi2c == NULL || value == NULL) {
        return HAL_ERROR;
    }
    if (HAL_I2C_Mem_Read(hi2c, (uint16_t)(address7 << 1), register_address, I2C_MEMADD_SIZE_8BIT, payload, 3U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    *value = (uint16_t)(((uint16_t)payload[1] << 8) | (uint16_t)payload[0]);
    return HAL_OK;
}

static float MLX90614_RawToTempC(uint16_t raw_value)
{
    return ((float)raw_value * 0.02f) - 273.15f;
}

HAL_StatusTypeDef MLX90614_ReadAmbientTempC(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    float *temperature_c,
    uint32_t timeout
)
{
    uint16_t raw_value = 0U;
    if (temperature_c == NULL || MLX90614_ReadWord(hi2c, address7, 0x06U, &raw_value, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    *temperature_c = MLX90614_RawToTempC(raw_value);
    return HAL_OK;
}

HAL_StatusTypeDef MLX90614_ReadObjectTempC(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    float *temperature_c,
    uint32_t timeout
)
{
    uint16_t raw_value = 0U;
    if (temperature_c == NULL || MLX90614_ReadWord(hi2c, address7, 0x07U, &raw_value, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    *temperature_c = MLX90614_RawToTempC(raw_value);
    return HAL_OK;
}
