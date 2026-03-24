#ifndef __MENU_VIEW_CT117E_ADAPTER_H
#define __MENU_VIEW_CT117E_ADAPTER_H

#include "ct117e_lcd_parallel.h"
#include "menu_view.h"

void MenuViewCt117e_FormatLine(const MenuView *view, uint8_t row, char *buffer, uint16_t buffer_size);

#endif
