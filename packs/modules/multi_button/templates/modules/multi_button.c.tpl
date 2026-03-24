#include "multi_button.h"

#include <string.h>

static uint8_t MultiButton_TimeReached(uint32_t now_ms, uint32_t timestamp_ms)
{
    return ((int32_t)(now_ms - timestamp_ms) >= 0) ? 1U : 0U;
}

static uint8_t MultiButton_ReadPressed(const MultiButton *button)
{
    GPIO_PinState state;

    if (button == NULL || button->port == NULL) {
        return 0U;
    }

    state = HAL_GPIO_ReadPin(button->port, button->pin);
    if (button->active_low) {
        return (state == GPIO_PIN_RESET) ? 1U : 0U;
    }
    return (state == GPIO_PIN_SET) ? 1U : 0U;
}

static void MultiButton_Emit(MultiButton *button, MultiButtonEvent event)
{
    if (button == NULL || event == MULTI_BUTTON_EVENT_NONE) {
        return;
    }
    MultiButton_OnEvent(button, event);
}

void MultiButton_Init(
    MultiButton *button,
    const char *name,
    GPIO_TypeDef *port,
    uint16_t pin,
    uint8_t active_low
)
{
    if (button == NULL) {
        return;
    }

    button->name = name;
    button->port = port;
    button->pin = pin;
    button->active_low = active_low ? 1U : 0U;
    button->debounce_ms = 25U;
    button->long_press_ms = 800U;
    button->double_click_ms = 250U;
    button->sampled_pressed = MultiButton_ReadPressed(button);
    button->stable_pressed = button->sampled_pressed;
    button->long_press_reported = 0U;
    button->click_count = 0U;
    button->last_sample_change_ms = HAL_GetTick();
    button->press_started_ms = button->stable_pressed ? button->last_sample_change_ms : 0U;
    button->click_deadline_ms = 0U;
}

void MultiButton_SetTiming(
    MultiButton *button,
    uint32_t debounce_ms,
    uint32_t long_press_ms,
    uint32_t double_click_ms
)
{
    if (button == NULL) {
        return;
    }

    button->debounce_ms = debounce_ms;
    button->long_press_ms = long_press_ms;
    button->double_click_ms = double_click_ms;
}

void MultiButton_Process(MultiButton *button, uint32_t now_ms)
{
    uint8_t pressed;

    if (button == NULL) {
        return;
    }

    pressed = MultiButton_ReadPressed(button);
    if (pressed != button->sampled_pressed) {
        button->sampled_pressed = pressed;
        button->last_sample_change_ms = now_ms;
    }

    if (pressed != button->stable_pressed
        && (uint32_t)(now_ms - button->last_sample_change_ms) >= button->debounce_ms) {
        button->stable_pressed = pressed;
        if (pressed) {
            button->press_started_ms = now_ms;
            button->long_press_reported = 0U;
        } else {
            if (button->long_press_reported == 0U) {
                button->click_count = (uint8_t)(button->click_count + 1U);
                button->click_deadline_ms = now_ms + button->double_click_ms;
            } else {
                button->click_count = 0U;
            }
        }
    }

    if (button->stable_pressed
        && button->long_press_reported == 0U
        && (uint32_t)(now_ms - button->press_started_ms) >= button->long_press_ms) {
        button->long_press_reported = 1U;
        button->click_count = 0U;
        MultiButton_Emit(button, MULTI_BUTTON_EVENT_LONG_PRESS);
    }

    if (button->stable_pressed == 0U
        && button->click_count > 0U
        && MultiButton_TimeReached(now_ms, button->click_deadline_ms)) {
        if (button->click_count >= 2U) {
            MultiButton_Emit(button, MULTI_BUTTON_EVENT_DOUBLE_CLICK);
        } else {
            MultiButton_Emit(button, MULTI_BUTTON_EVENT_SINGLE_CLICK);
        }
        button->click_count = 0U;
    }
}

const char *MultiButton_EventName(MultiButtonEvent event)
{
    switch (event) {
    case MULTI_BUTTON_EVENT_SINGLE_CLICK:
        return "single_click";
    case MULTI_BUTTON_EVENT_DOUBLE_CLICK:
        return "double_click";
    case MULTI_BUTTON_EVENT_LONG_PRESS:
        return "long_press";
    default:
        return "none";
    }
}

uint8_t MultiButton_Matches(const MultiButton *button, const char *name)
{
    if (button == NULL || button->name == NULL || name == NULL) {
        return 0U;
    }
    return (strcmp(button->name, name) == 0) ? 1U : 0U;
}

__weak void MultiButton_OnEvent(const MultiButton *button, MultiButtonEvent event)
{
    (void)button;
    (void)event;
}
