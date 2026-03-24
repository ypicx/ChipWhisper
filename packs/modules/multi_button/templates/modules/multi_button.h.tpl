#ifndef __MULTI_BUTTON_H
#define __MULTI_BUTTON_H

#include "main.h"

typedef enum
{
    MULTI_BUTTON_EVENT_NONE = 0,
    MULTI_BUTTON_EVENT_SINGLE_CLICK = 1,
    MULTI_BUTTON_EVENT_DOUBLE_CLICK = 2,
    MULTI_BUTTON_EVENT_LONG_PRESS = 3
} MultiButtonEvent;

typedef struct
{
    const char *name;
    GPIO_TypeDef *port;
    uint16_t pin;
    uint8_t active_low;
    uint8_t stable_pressed;
    uint8_t sampled_pressed;
    uint8_t long_press_reported;
    uint8_t click_count;
    uint32_t debounce_ms;
    uint32_t long_press_ms;
    uint32_t double_click_ms;
    uint32_t last_sample_change_ms;
    uint32_t press_started_ms;
    uint32_t click_deadline_ms;
} MultiButton;

void MultiButton_Init(
    MultiButton *button,
    const char *name,
    GPIO_TypeDef *port,
    uint16_t pin,
    uint8_t active_low
);
void MultiButton_SetTiming(
    MultiButton *button,
    uint32_t debounce_ms,
    uint32_t long_press_ms,
    uint32_t double_click_ms
);
void MultiButton_Process(MultiButton *button, uint32_t now_ms);
const char *MultiButton_EventName(MultiButtonEvent event);
uint8_t MultiButton_Matches(const MultiButton *button, const char *name);
void MultiButton_OnEvent(const MultiButton *button, MultiButtonEvent event);

#endif
