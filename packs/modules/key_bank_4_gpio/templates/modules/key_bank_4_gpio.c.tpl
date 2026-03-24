#include "key_bank_4_gpio.h"

void KeyBank4Gpio_Init(
    KeyBank4Gpio *bank,
    GPIO_TypeDef *const ports[4],
    const uint16_t pins[4],
    uint8_t active_low
)
{
    uint8_t index;

    if (bank == NULL) {
        return;
    }

    for (index = 0; index < 4U; ++index) {
        bank->ports[index] = ports[index];
        bank->pins[index] = pins[index];
    }
    bank->active_low = active_low ? 1U : 0U;
}

uint8_t KeyBank4Gpio_ReadMask(const KeyBank4Gpio *bank)
{
    uint8_t index;
    uint8_t mask = 0U;

    if (bank == NULL) {
        return 0U;
    }

    for (index = 0; index < 4U; ++index) {
        GPIO_PinState state = HAL_GPIO_ReadPin(bank->ports[index], bank->pins[index]);
        uint8_t pressed = (state == GPIO_PIN_SET) ? 1U : 0U;
        if (bank->active_low != 0U) {
            pressed = pressed ? 0U : 1U;
        }
        if (pressed != 0U) {
            mask |= (uint8_t)(1U << index);
        }
    }

    return mask;
}

GPIO_PinState KeyBank4Gpio_ReadKey(const KeyBank4Gpio *bank, uint8_t index)
{
    if (bank == NULL || index >= 4U) {
        return GPIO_PIN_RESET;
    }
    return ((KeyBank4Gpio_ReadMask(bank) >> index) & 0x01U) ? GPIO_PIN_SET : GPIO_PIN_RESET;
}
