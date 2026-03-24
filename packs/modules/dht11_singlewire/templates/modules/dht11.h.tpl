#ifndef __DHT11_H
#define __DHT11_H

#include "main.h"

typedef struct
{
    uint8_t humidity_integer;
    uint8_t humidity_decimal;
    uint8_t temperature_integer;
    uint8_t temperature_decimal;
    uint8_t checksum;
} DHT11_Frame;

void DHT11_DriveLow(GPIO_TypeDef *port, uint16_t pin);
void DHT11_ReleaseBus(GPIO_TypeDef *port, uint16_t pin);
GPIO_PinState DHT11_ReadLine(GPIO_TypeDef *port, uint16_t pin);
HAL_StatusTypeDef DHT11_StartFrame(GPIO_TypeDef *port, uint16_t pin);

#endif
