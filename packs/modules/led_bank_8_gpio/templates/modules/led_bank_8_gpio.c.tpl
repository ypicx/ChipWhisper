#include "led_bank_8_gpio.h"

void LedBank8Gpio_Init(
    LedBank8Gpio *bank,
    GPIO_TypeDef *const ports[8],
    const uint16_t pins[8],
    uint8_t active_low
)
{
    uint8_t index;

    if (bank == NULL) {
        return;
    }

    for (index = 0; index < 8U; ++index) {
        bank->ports[index] = ports[index];
        bank->pins[index] = pins[index];
    }
    bank->active_low = active_low ? 1U : 0U;
    LedBank8Gpio_AllOff(bank);
}

void LedBank8Gpio_WriteMask(LedBank8Gpio *bank, uint8_t mask)
{
    uint8_t index;

    if (bank == NULL) {
        return;
    }

    for (index = 0; index < 8U; ++index) {
        GPIO_PinState state = ((mask >> index) & 0x01U) ? GPIO_PIN_SET : GPIO_PIN_RESET;
        if (bank->active_low != 0U) {
            state = (state == GPIO_PIN_SET) ? GPIO_PIN_RESET : GPIO_PIN_SET;
        }
        HAL_GPIO_WritePin(bank->ports[index], bank->pins[index], state);
    }
}

void LedBank8Gpio_AllOff(LedBank8Gpio *bank)
{
    LedBank8Gpio_WriteMask(bank, 0x00U);
}
