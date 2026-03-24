#include "menu_view_lcd1602_adapter.h"

#include <stdio.h>
#include <string.h>

static void MenuViewLcd1602_FillPadded(char *buffer, uint16_t buffer_size, const char *text)
{
    uint16_t index;
    uint16_t usable = 0U;

    if (buffer == NULL || buffer_size == 0U) {
        return;
    }

    usable = (uint16_t)(buffer_size - 1U);
    for (index = 0U; index < usable; ++index) {
        buffer[index] = ' ';
    }
    buffer[usable] = '\0';

    if (text == NULL) {
        return;
    }

    for (index = 0U; index < usable && text[index] != '\0'; ++index) {
        buffer[index] = text[index];
    }
}

__weak void MenuViewLcd1602_FormatLine(const MenuView *view, uint8_t row, char *buffer, uint16_t buffer_size)
{
    char scratch[24];

    if (buffer == NULL || buffer_size == 0U) {
        return;
    }

    if (view == NULL) {
        MenuViewLcd1602_FillPadded(buffer, buffer_size, "");
        return;
    }

    if (row == 0U) {
        (void)snprintf(
            scratch,
            sizeof(scratch),
            "Pg%u Sel%u/%u",
            (unsigned int)view->page_id,
            (unsigned int)(view->item_count == 0U ? 0U : (view->selected_index + 1U)),
            (unsigned int)view->item_count
        );
    } else {
        (void)snprintf(
            scratch,
            sizeof(scratch),
            "Rows%u Dirty%u",
            (unsigned int)view->visible_rows,
            (unsigned int)view->dirty
        );
    }
    MenuViewLcd1602_FillPadded(buffer, buffer_size, scratch);
}
