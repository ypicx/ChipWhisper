#ifndef __MENU_VIEW_LCD1602_ADAPTER_H
#define __MENU_VIEW_LCD1602_ADAPTER_H

#include "lcd1602.h"
#include "menu_view.h"

void MenuViewLcd1602_FormatLine(const MenuView *view, uint8_t row, char *buffer, uint16_t buffer_size);

#endif
