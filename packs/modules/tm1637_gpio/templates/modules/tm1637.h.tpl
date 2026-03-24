#ifndef __TM1637_H
#define __TM1637_H

#include "main.h"

void TM1637_InitPins(GPIO_TypeDef *clk_port, uint16_t clk_pin, GPIO_TypeDef *dio_port, uint16_t dio_pin);
HAL_StatusTypeDef TM1637_DisplayRaw(
    GPIO_TypeDef *clk_port,
    uint16_t clk_pin,
    GPIO_TypeDef *dio_port,
    uint16_t dio_pin,
    const uint8_t digits[4],
    uint8_t brightness
);

#endif
