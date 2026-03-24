#ifndef __CT117E_LCD_PARALLEL_H
#define __CT117E_LCD_PARALLEL_H

#include "main.h"

#define CT117E_LCD_WIDTH 240U
#define CT117E_LCD_HEIGHT 320U

#define CT117E_LCD_COLOR_WHITE 0xFFFFU
#define CT117E_LCD_COLOR_BLACK 0x0000U
#define CT117E_LCD_COLOR_BLUE 0x001FU
#define CT117E_LCD_COLOR_RED 0xF800U
#define CT117E_LCD_COLOR_GREEN 0x07E0U
#define CT117E_LCD_COLOR_YELLOW 0xFFE0U
#define CT117E_LCD_COLOR_CYAN 0x7FFFU
#define CT117E_LCD_COLOR_MAGENTA 0xF81FU

typedef struct
{
    GPIO_TypeDef *data_ports[16];
    uint16_t data_pins[16];
    GPIO_TypeDef *cs_port;
    uint16_t cs_pin;
    GPIO_TypeDef *rs_port;
    uint16_t rs_pin;
    GPIO_TypeDef *wr_port;
    uint16_t wr_pin;
    GPIO_TypeDef *rd_port;
    uint16_t rd_pin;
} CT117ELcdBus;

HAL_StatusTypeDef CT117ELcd_Init(const CT117ELcdBus *bus);
void CT117ELcd_Clear(const CT117ELcdBus *bus, uint16_t color);
void CT117ELcd_FillColorBars(const CT117ELcdBus *bus, uint8_t phase);
void CT117ELcd_DrawPixel(const CT117ELcdBus *bus, uint16_t x, uint16_t y, uint16_t color);
void CT117ELcd_WriteChar5x7(
    const CT117ELcdBus *bus,
    uint16_t x,
    uint16_t y,
    char ch,
    uint16_t foreground,
    uint16_t background
);
void CT117ELcd_WriteString5x7(
    const CT117ELcdBus *bus,
    uint16_t x,
    uint16_t y,
    const char *text,
    uint16_t foreground,
    uint16_t background
);

#endif
