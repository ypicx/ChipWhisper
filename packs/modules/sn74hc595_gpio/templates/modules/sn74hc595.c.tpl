#include "sn74hc595.h"

static void ShiftRegister595_Pulse(GPIO_TypeDef *port, uint16_t pin)
{
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_RESET);
}

void ShiftRegister595_InitPins(
    GPIO_TypeDef *data_port,
    uint16_t data_pin,
    GPIO_TypeDef *clock_port,
    uint16_t clock_pin,
    GPIO_TypeDef *latch_port,
    uint16_t latch_pin
)
{
    HAL_GPIO_WritePin(data_port, data_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(clock_port, clock_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(latch_port, latch_pin, GPIO_PIN_RESET);
}

HAL_StatusTypeDef ShiftRegister595_WriteByte(
    GPIO_TypeDef *data_port,
    uint16_t data_pin,
    GPIO_TypeDef *clock_port,
    uint16_t clock_pin,
    GPIO_TypeDef *latch_port,
    uint16_t latch_pin,
    uint8_t value
)
{
    uint8_t bit_index;

    if (data_port == NULL || clock_port == NULL || latch_port == NULL) {
        return HAL_ERROR;
    }

    for (bit_index = 0U; bit_index < 8U; ++bit_index) {
        GPIO_PinState state = ((value & 0x80U) != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET;
        HAL_GPIO_WritePin(data_port, data_pin, state);
        ShiftRegister595_Pulse(clock_port, clock_pin);
        value <<= 1;
    }

    ShiftRegister595_Pulse(latch_port, latch_pin);
    return HAL_OK;
}
