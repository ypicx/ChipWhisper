#ifndef __MENU_VIEW_H
#define __MENU_VIEW_H

#include "main.h"

typedef enum
{
    MENU_VIEW_INPUT_NONE = 0,
    MENU_VIEW_INPUT_SINGLE_CLICK = 1,
    MENU_VIEW_INPUT_DOUBLE_CLICK = 2,
    MENU_VIEW_INPUT_LONG_PRESS = 3
} MenuViewInputEvent;

typedef enum
{
    MENU_VIEW_COMMAND_NONE = 0,
    MENU_VIEW_COMMAND_ENTER = 1,
    MENU_VIEW_COMMAND_BACK = 2,
    MENU_VIEW_COMMAND_VALUE_INC = 3,
    MENU_VIEW_COMMAND_VALUE_DEC = 4
} MenuViewCommand;

typedef struct
{
    const char *name;
    uint8_t page_id;
    uint8_t item_count;
    uint8_t selected_index;
    uint8_t visible_rows;
    uint8_t dirty;
    uint32_t refresh_ms;
    uint32_t last_render_ms;
    const char *up_button_name;
    const char *down_button_name;
    const char *enter_button_name;
    const char *back_button_name;
} MenuView;

void MenuView_Init(MenuView *view, const char *name, uint8_t visible_rows, uint32_t refresh_ms);
void MenuView_SetPage(MenuView *view, uint8_t page_id, uint8_t item_count);
void MenuView_SetSelection(MenuView *view, uint8_t selected_index);
void MenuView_Move(MenuView *view, int8_t delta);
void MenuView_RequestRender(MenuView *view);
void MenuView_BindNavigation(
    MenuView *view,
    const char *up_button_name,
    const char *down_button_name,
    const char *enter_button_name,
    const char *back_button_name
);
void MenuView_Process(MenuView *view, uint32_t now_ms);
void MenuView_TaskCallback(void *user_data);
void MenuView_DispatchNamedInput(const char *input_name, uint32_t input_event);
uint8_t MenuView_Matches(const MenuView *view, const char *name);
void MenuView_OnRender(const MenuView *view);
void MenuView_OnCommand(MenuView *view, MenuViewCommand command);

#endif
