#include "aht20.h"

static HAL_StatusTypeDef AHT20_WriteCommand(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    const uint8_t *command,
    uint16_t length,
    uint32_t timeout
)
{
    if (hi2c == NULL || command == NULL || length == 0U) {
        return HAL_ERROR;
    }
    return HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), (uint8_t *)command, length, timeout);
}

HAL_StatusTypeDef AHT20_Init(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    static const uint8_t init_command[] = {0xBEU, 0x08U, 0x00U};

    HAL_Delay(40);
    return AHT20_WriteCommand(hi2c, address7, init_command, (uint16_t)sizeof(init_command), timeout);
}

HAL_StatusTypeDef AHT20_ReadMeasurement(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    AHT20_Measurement *measurement,
    uint32_t timeout
)
{
    static const uint8_t trigger_command[] = {0xACU, 0x33U, 0x00U};
    uint8_t payload[6] = {0};
    uint32_t humidity_raw;
    uint32_t temperature_raw;
    HAL_StatusTypeDef status;

    if (hi2c == NULL || measurement == NULL) {
        return HAL_ERROR;
    }

    status = AHT20_WriteCommand(hi2c, address7, trigger_command, (uint16_t)sizeof(trigger_command), timeout);
    if (status != HAL_OK) {
        return status;
    }

    HAL_Delay(80);
    status = HAL_I2C_Master_Receive(hi2c, (uint16_t)(address7 << 1), payload, (uint16_t)sizeof(payload), timeout);
    if (status != HAL_OK) {
        return status;
    }
    if ((payload[0] & 0x80U) != 0U) {
        return HAL_BUSY;
    }

    humidity_raw = ((uint32_t)payload[1] << 12)
        | ((uint32_t)payload[2] << 4)
        | ((uint32_t)(payload[3] & 0xF0U) >> 4);
    temperature_raw = ((uint32_t)(payload[3] & 0x0FU) << 16)
        | ((uint32_t)payload[4] << 8)
        | (uint32_t)payload[5];

    measurement->humidity_rh = ((float)humidity_raw * 100.0f) / 1048576.0f;
    measurement->temperature_c = ((float)temperature_raw * 200.0f) / 1048576.0f - 50.0f;
    return HAL_OK;
}
