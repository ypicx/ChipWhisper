#ifndef __LED_BANK_8_GPIO_H
#define __LED_BANK_8_GPIO_H

#include "main.h"

typedef struct
{
    GPIO_TypeDef *ports[8];
    uint16_t pins[8];
    uint8_t active_low;
} LedBank8Gpio;

void LedBank8Gpio_Init(
    LedBank8Gpio *bank,
    GPIO_TypeDef *const ports[8],
    const uint16_t pins[8],
    uint8_t active_low
);
void LedBank8Gpio_WriteMask(LedBank8Gpio *bank, uint8_t mask);
void LedBank8Gpio_AllOff(LedBank8Gpio *bank);

#endif
