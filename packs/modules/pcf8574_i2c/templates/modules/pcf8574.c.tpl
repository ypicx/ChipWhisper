#include "pcf8574.h"

HAL_StatusTypeDef PCF8574_WritePort(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t value, uint32_t timeout)
{
    if (hi2c == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), &value, 1U, timeout);
}

HAL_StatusTypeDef PCF8574_ReadPort(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t *value, uint32_t timeout)
{
    if (hi2c == NULL || value == NULL) {
        return HAL_ERROR;
    }
    return HAL_I2C_Master_Receive(hi2c, (uint16_t)(address7 << 1), value, 1U, timeout);
}

HAL_StatusTypeDef PCF8574_WritePin(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t pin_index,
    GPIO_PinState state,
    uint32_t timeout
)
{
    uint8_t current_value = 0xFFU;
    HAL_StatusTypeDef status;

    if (pin_index > 7U) {
        return HAL_ERROR;
    }

    status = PCF8574_ReadPort(hi2c, address7, &current_value, timeout);
    if (status != HAL_OK) {
        return status;
    }

    if (state == GPIO_PIN_SET) {
        current_value = (uint8_t)(current_value | (uint8_t)(1U << pin_index));
    } else {
        current_value = (uint8_t)(current_value & (uint8_t)~(1U << pin_index));
    }
    return PCF8574_WritePort(hi2c, address7, current_value, timeout);
}
