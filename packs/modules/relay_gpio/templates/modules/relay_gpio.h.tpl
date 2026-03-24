#ifndef __RELAY_GPIO_H
#define __RELAY_GPIO_H

#include "main.h"

void RelayGpio_InitPin(GPIO_TypeDef *port, uint16_t pin);
void RelayGpio_Write(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state);
void RelayGpio_On(GPIO_TypeDef *port, uint16_t pin);
void RelayGpio_Off(GPIO_TypeDef *port, uint16_t pin);

#endif
