#include "keypad_4x4.h"

static const char kKeypadMap[4][4] = {
    {'1', '2', '3', 'A'},
    {'4', '5', '6', 'B'},
    {'7', '8', '9', 'C'},
    {'*', '0', '#', 'D'},
};

static void Keypad4x4_SetAllRows(Keypad4x4 *keypad, GPIO_PinState state)
{
    uint8_t index;

    for (index = 0U; index < 4U; ++index) {
        HAL_GPIO_WritePin(keypad->row_ports[index], keypad->row_pins[index], state);
    }
}

static char Keypad4x4_ScanRaw(Keypad4x4 *keypad)
{
    uint8_t row;
    uint8_t col;
    volatile uint32_t settle_delay;

    if (keypad == NULL) {
        return '\0';
    }

    Keypad4x4_SetAllRows(keypad, GPIO_PIN_SET);

    for (row = 0U; row < 4U; ++row) {
        HAL_GPIO_WritePin(keypad->row_ports[row], keypad->row_pins[row], GPIO_PIN_RESET);
        for (settle_delay = 0U; settle_delay < 128U; ++settle_delay) {
            __NOP();
        }

        for (col = 0U; col < 4U; ++col) {
            if (HAL_GPIO_ReadPin(keypad->col_ports[col], keypad->col_pins[col]) == GPIO_PIN_RESET) {
                HAL_GPIO_WritePin(keypad->row_ports[row], keypad->row_pins[row], GPIO_PIN_SET);
                return kKeypadMap[row][col];
            }
        }

        HAL_GPIO_WritePin(keypad->row_ports[row], keypad->row_pins[row], GPIO_PIN_SET);
    }

    return '\0';
}

void Keypad4x4_Init(
    Keypad4x4 *keypad,
    GPIO_TypeDef *row_ports[4],
    const uint16_t row_pins[4],
    GPIO_TypeDef *col_ports[4],
    const uint16_t col_pins[4],
    uint32_t debounce_ms
)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    uint8_t index;

    if (keypad == NULL) {
        return;
    }

    for (index = 0U; index < 4U; ++index) {
        keypad->row_ports[index] = row_ports[index];
        keypad->row_pins[index] = row_pins[index];
        keypad->col_ports[index] = col_ports[index];
        keypad->col_pins[index] = col_pins[index];
    }

    keypad->debounce_ms = debounce_ms;
    keypad->last_raw = '\0';
    keypad->last_reported = '\0';
    keypad->last_change_tick = HAL_GetTick();

    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    for (index = 0U; index < 4U; ++index) {
        GPIO_InitStruct.Pin = keypad->row_pins[index];
        HAL_GPIO_Init(keypad->row_ports[index], &GPIO_InitStruct);
    }

    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    for (index = 0U; index < 4U; ++index) {
        GPIO_InitStruct.Pin = keypad->col_pins[index];
        HAL_GPIO_Init(keypad->col_ports[index], &GPIO_InitStruct);
    }

    Keypad4x4_SetAllRows(keypad, GPIO_PIN_SET);
}

char Keypad4x4_PollEvent(Keypad4x4 *keypad)
{
    char raw;
    uint32_t now;

    if (keypad == NULL) {
        return '\0';
    }

    raw = Keypad4x4_ScanRaw(keypad);
    now = HAL_GetTick();

    if (raw != keypad->last_raw) {
        keypad->last_raw = raw;
        keypad->last_change_tick = now;
        return '\0';
    }

    if ((now - keypad->last_change_tick) < keypad->debounce_ms) {
        return '\0';
    }

    if (raw == '\0') {
        keypad->last_reported = '\0';
        return '\0';
    }

    if (raw == keypad->last_reported) {
        return '\0';
    }

    keypad->last_reported = raw;
    return raw;
}

void Keypad4x4_ClearState(Keypad4x4 *keypad)
{
    if (keypad == NULL) {
        return;
    }

    keypad->last_raw = '\0';
    keypad->last_reported = '\0';
    keypad->last_change_tick = HAL_GetTick();
    Keypad4x4_SetAllRows(keypad, GPIO_PIN_SET);
}
