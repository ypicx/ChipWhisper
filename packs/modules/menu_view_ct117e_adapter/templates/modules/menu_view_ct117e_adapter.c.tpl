#include "menu_view_ct117e_adapter.h"

#include <stdio.h>

static void MenuViewCt117e_FillPadded(char *buffer, uint16_t buffer_size, const char *text)
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

__weak void MenuViewCt117e_FormatLine(const MenuView *view, uint8_t row, char *buffer, uint16_t buffer_size)
{
    char scratch[32];

    if (buffer == NULL || buffer_size == 0U) {
        return;
    }

    if (view == NULL) {
        MenuViewCt117e_FillPadded(buffer, buffer_size, "");
        return;
    }

    switch (row) {
    case 0U:
        (void)snprintf(
            scratch,
            sizeof(scratch),
            "Page %u  Sel %u/%u",
            (unsigned int)view->page_id,
            (unsigned int)(view->item_count == 0U ? 0U : (view->selected_index + 1U)),
            (unsigned int)view->item_count
        );
        break;
    case 1U:
        (void)snprintf(
            scratch,
            sizeof(scratch),
            "Rows %u  Dirty %u",
            (unsigned int)view->visible_rows,
            (unsigned int)view->dirty
        );
        break;
    case 2U:
        (void)snprintf(
            scratch,
            sizeof(scratch),
            "Click: move select"
        );
        break;
    default:
        (void)snprintf(
            scratch,
            sizeof(scratch),
            "Hold: value  Back"
        );
        break;
    }

    MenuViewCt117e_FillPadded(buffer, buffer_size, scratch);
}
