#include "menu_view.h"

#include <string.h>

#define MENU_VIEW_MAX_VIEWS 4U

static MenuView *g_menu_views[MENU_VIEW_MAX_VIEWS];

static uint8_t MenuView_TimeReached(uint32_t now_ms, uint32_t timestamp_ms)
{
    return ((int32_t)(now_ms - timestamp_ms) >= 0) ? 1U : 0U;
}

static void MenuView_Register(MenuView *view)
{
    uint32_t index;

    if (view == NULL) {
        return;
    }

    for (index = 0U; index < MENU_VIEW_MAX_VIEWS; ++index) {
        if (g_menu_views[index] == view) {
            return;
        }
    }

    for (index = 0U; index < MENU_VIEW_MAX_VIEWS; ++index) {
        if (g_menu_views[index] == NULL) {
            g_menu_views[index] = view;
            return;
        }
    }
}

static uint8_t MenuView_NameEquals(const char *left, const char *right)
{
    if (left == NULL || right == NULL) {
        return 0U;
    }
    return (strcmp(left, right) == 0) ? 1U : 0U;
}

static void MenuView_EmitCommand(MenuView *view, MenuViewCommand command)
{
    if (view == NULL || command == MENU_VIEW_COMMAND_NONE) {
        return;
    }
    MenuView_OnCommand(view, command);
    MenuView_RequestRender(view);
}

void MenuView_Init(MenuView *view, const char *name, uint8_t visible_rows, uint32_t refresh_ms)
{
    if (view == NULL) {
        return;
    }

    view->name = name;
    view->page_id = 0U;
    view->item_count = 0U;
    view->selected_index = 0U;
    view->visible_rows = visible_rows ? visible_rows : 4U;
    view->dirty = 1U;
    view->refresh_ms = refresh_ms;
    view->last_render_ms = 0U;
    view->up_button_name = NULL;
    view->down_button_name = NULL;
    view->enter_button_name = NULL;
    view->back_button_name = NULL;
    MenuView_Register(view);
}

void MenuView_SetPage(MenuView *view, uint8_t page_id, uint8_t item_count)
{
    if (view == NULL) {
        return;
    }

    view->page_id = page_id;
    view->item_count = item_count;
    if (view->item_count == 0U) {
        view->selected_index = 0U;
    } else if (view->selected_index >= view->item_count) {
        view->selected_index = (uint8_t)(view->item_count - 1U);
    }
    MenuView_RequestRender(view);
}

void MenuView_SetSelection(MenuView *view, uint8_t selected_index)
{
    if (view == NULL) {
        return;
    }

    if (view->item_count == 0U) {
        view->selected_index = 0U;
    } else if (selected_index >= view->item_count) {
        view->selected_index = (uint8_t)(view->item_count - 1U);
    } else {
        view->selected_index = selected_index;
    }
    MenuView_RequestRender(view);
}

void MenuView_Move(MenuView *view, int8_t delta)
{
    int16_t next_index;

    if (view == NULL || view->item_count == 0U || delta == 0) {
        return;
    }

    next_index = (int16_t)view->selected_index + delta;
    if (next_index < 0) {
        next_index = (int16_t)view->item_count - 1;
    }
    if (next_index >= (int16_t)view->item_count) {
        next_index = 0;
    }
    view->selected_index = (uint8_t)next_index;
    MenuView_RequestRender(view);
}

void MenuView_RequestRender(MenuView *view)
{
    if (view == NULL) {
        return;
    }
    view->dirty = 1U;
}

void MenuView_BindNavigation(
    MenuView *view,
    const char *up_button_name,
    const char *down_button_name,
    const char *enter_button_name,
    const char *back_button_name
)
{
    if (view == NULL) {
        return;
    }

    view->up_button_name = up_button_name;
    view->down_button_name = down_button_name;
    view->enter_button_name = enter_button_name;
    view->back_button_name = back_button_name;
}

void MenuView_Process(MenuView *view, uint32_t now_ms)
{
    if (view == NULL) {
        return;
    }

    if (view->dirty == 0U && view->refresh_ms > 0U
        && !MenuView_TimeReached(now_ms, view->last_render_ms + view->refresh_ms)) {
        return;
    }

    view->dirty = 0U;
    view->last_render_ms = now_ms;
    MenuView_OnRender(view);
}

void MenuView_TaskCallback(void *user_data)
{
    MenuView *view = (MenuView *)user_data;
    MenuView_Process(view, HAL_GetTick());
}

void MenuView_DispatchNamedInput(const char *input_name, uint32_t input_event)
{
    uint32_t index;

    for (index = 0U; index < MENU_VIEW_MAX_VIEWS; ++index) {
        MenuView *view = g_menu_views[index];
        if (view == NULL || input_name == NULL) {
            continue;
        }

        if (MenuView_NameEquals(input_name, view->up_button_name)) {
            if (input_event == MENU_VIEW_INPUT_SINGLE_CLICK) {
                MenuView_Move(view, -1);
            } else if (input_event == MENU_VIEW_INPUT_LONG_PRESS) {
                MenuView_EmitCommand(view, MENU_VIEW_COMMAND_VALUE_DEC);
            }
            continue;
        }
        if (MenuView_NameEquals(input_name, view->down_button_name)) {
            if (input_event == MENU_VIEW_INPUT_SINGLE_CLICK) {
                MenuView_Move(view, 1);
            } else if (input_event == MENU_VIEW_INPUT_LONG_PRESS) {
                MenuView_EmitCommand(view, MENU_VIEW_COMMAND_VALUE_INC);
            }
            continue;
        }
        if (MenuView_NameEquals(input_name, view->enter_button_name)) {
            if (input_event == MENU_VIEW_INPUT_SINGLE_CLICK || input_event == MENU_VIEW_INPUT_DOUBLE_CLICK) {
                MenuView_EmitCommand(view, MENU_VIEW_COMMAND_ENTER);
            }
            continue;
        }
        if (MenuView_NameEquals(input_name, view->back_button_name)) {
            if (input_event == MENU_VIEW_INPUT_SINGLE_CLICK || input_event == MENU_VIEW_INPUT_LONG_PRESS) {
                MenuView_EmitCommand(view, MENU_VIEW_COMMAND_BACK);
            }
        }
    }
}

uint8_t MenuView_Matches(const MenuView *view, const char *name)
{
    if (view == NULL || view->name == NULL || name == NULL) {
        return 0U;
    }
    return (strcmp(view->name, name) == 0) ? 1U : 0U;
}

__weak void MenuView_OnRender(const MenuView *view)
{
    (void)view;
}

__weak void MenuView_OnCommand(MenuView *view, MenuViewCommand command)
{
    (void)view;
    (void)command;
}
