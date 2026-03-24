#ifndef __SN74HC595_H
#define __SN74HC595_H

#include "main.h"

void ShiftRegister595_InitPins(
    GPIO_TypeDef *data_port,
    uint16_t data_pin,
    GPIO_TypeDef *clock_port,
    uint16_t clock_pin,
    GPIO_TypeDef *latch_port,
    uint16_t latch_pin
);
HAL_StatusTypeDef ShiftRegister595_WriteByte(
    GPIO_TypeDef *data_port,
    uint16_t data_pin,
    GPIO_TypeDef *clock_port,
    uint16_t clock_pin,
    GPIO_TypeDef *latch_port,
    uint16_t latch_pin,
    uint8_t value
);

#endif
