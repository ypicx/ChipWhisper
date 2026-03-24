#ifndef __HC_SR04_H
#define __HC_SR04_H

#include "main.h"

void HCSR04_InitPins(GPIO_TypeDef *trig_port, uint16_t trig_pin);
void HCSR04_SetTrigger(GPIO_TypeDef *trig_port, uint16_t trig_pin, GPIO_PinState state);
GPIO_PinState HCSR04_ReadEcho(GPIO_TypeDef *echo_port, uint16_t echo_pin);

#endif
