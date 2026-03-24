#ifndef __DS1302_GPIO_H
#define __DS1302_GPIO_H

#include "main.h"

typedef struct
{
    GPIO_TypeDef *ce_port;
    uint16_t ce_pin;
    GPIO_TypeDef *clk_port;
    uint16_t clk_pin;
    GPIO_TypeDef *io_port;
    uint16_t io_pin;
} DS1302_Gpio;

typedef struct
{
    uint8_t year;
    uint8_t month;
    uint8_t day;
    uint8_t weekday;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
} DS1302_Time;

void DS1302_Init(
    DS1302_Gpio *rtc,
    GPIO_TypeDef *ce_port,
    uint16_t ce_pin,
    GPIO_TypeDef *clk_port,
    uint16_t clk_pin,
    GPIO_TypeDef *io_port,
    uint16_t io_pin
);
HAL_StatusTypeDef DS1302_WriteRegister(DS1302_Gpio *rtc, uint8_t address, uint8_t value);
HAL_StatusTypeDef DS1302_ReadRegister(DS1302_Gpio *rtc, uint8_t address, uint8_t *value);
HAL_StatusTypeDef DS1302_ReadTime(DS1302_Gpio *rtc, DS1302_Time *time_value);
uint8_t DS1302_BcdToDec(uint8_t value);
uint8_t DS1302_DecToBcd(uint8_t value);

#endif
