#ifndef __KEYPAD_4X4_H
#define __KEYPAD_4X4_H

#include "main.h"

typedef struct
{
    GPIO_TypeDef *row_ports[4];
    uint16_t row_pins[4];
    GPIO_TypeDef *col_ports[4];
    uint16_t col_pins[4];
    uint32_t debounce_ms;
    char last_raw;
    char last_reported;
    uint32_t last_change_tick;
} Keypad4x4;

void Keypad4x4_Init(
    Keypad4x4 *keypad,
    GPIO_TypeDef *row_ports[4],
    const uint16_t row_pins[4],
    GPIO_TypeDef *col_ports[4],
    const uint16_t col_pins[4],
    uint32_t debounce_ms
);
char Keypad4x4_PollEvent(Keypad4x4 *keypad);
void Keypad4x4_ClearState(Keypad4x4 *keypad);

#endif
