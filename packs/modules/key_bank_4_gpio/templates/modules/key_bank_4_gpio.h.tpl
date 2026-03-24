#ifndef __KEY_BANK_4_GPIO_H
#define __KEY_BANK_4_GPIO_H

#include "main.h"

typedef struct
{
    GPIO_TypeDef *ports[4];
    uint16_t pins[4];
    uint8_t active_low;
} KeyBank4Gpio;

void KeyBank4Gpio_Init(
    KeyBank4Gpio *bank,
    GPIO_TypeDef *const ports[4],
    const uint16_t pins[4],
    uint8_t active_low
);
uint8_t KeyBank4Gpio_ReadMask(const KeyBank4Gpio *bank);
GPIO_PinState KeyBank4Gpio_ReadKey(const KeyBank4Gpio *bank, uint8_t index);

#endif
