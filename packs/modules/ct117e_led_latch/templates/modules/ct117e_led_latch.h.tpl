#ifndef __CT117E_LED_LATCH_H
#define __CT117E_LED_LATCH_H

#include "main.h"

typedef struct
{
    GPIO_TypeDef *latch_port;
    uint16_t latch_pin;
    uint8_t active_low;
} CT117ELedLatch;

void CT117ELedLatch_Init(
    CT117ELedLatch *bank,
    GPIO_TypeDef *latch_port,
    uint16_t latch_pin,
    uint8_t active_low
);
void CT117ELedLatch_WriteMask(CT117ELedLatch *bank, uint8_t mask);
void CT117ELedLatch_AllOff(CT117ELedLatch *bank);

#endif
