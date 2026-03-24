/**
 * @file active_buzzer.c
 * @brief Active buzzer driver with non-blocking beep and alarm patterns.
 */

#include "active_buzzer.h"

typedef enum {
    BUZZER_STATE_IDLE,
    BUZZER_STATE_BEEP_ON,
    BUZZER_STATE_ALARM_ON,
    BUZZER_STATE_ALARM_OFF,
} BuzzerState;

static BuzzerState s_state = BUZZER_STATE_IDLE;
static uint32_t s_tick_start = 0;
static uint32_t s_on_ms = 0;
static uint32_t s_off_ms = 0;
static uint8_t  s_remain_count = 0;
static uint8_t  s_continuous = 0;

static void Buzzer_HW_On(void)
{
#if BUZZER_ACTIVE_LOW
    HAL_GPIO_WritePin(BUZZER_PORT, BUZZER_PIN, GPIO_PIN_RESET);
#else
    HAL_GPIO_WritePin(BUZZER_PORT, BUZZER_PIN, GPIO_PIN_SET);
#endif
}

static void Buzzer_HW_Off(void)
{
#if BUZZER_ACTIVE_LOW
    HAL_GPIO_WritePin(BUZZER_PORT, BUZZER_PIN, GPIO_PIN_SET);
#else
    HAL_GPIO_WritePin(BUZZER_PORT, BUZZER_PIN, GPIO_PIN_RESET);
#endif
}

void Buzzer_Init(void)
{
    Buzzer_HW_Off();
    s_state = BUZZER_STATE_IDLE;
}

void Buzzer_On(void)
{
    Buzzer_HW_On();
    s_state = BUZZER_STATE_IDLE;  /* manual control, no tick needed */
}

void Buzzer_Off(void)
{
    Buzzer_HW_Off();
    s_state = BUZZER_STATE_IDLE;
    s_remain_count = 0;
    s_continuous = 0;
}

void Buzzer_Beep(uint32_t ms)
{
    Buzzer_HW_On();
    s_on_ms = ms;
    s_tick_start = HAL_GetTick();
    s_state = BUZZER_STATE_BEEP_ON;
    s_remain_count = 0;
    s_continuous = 0;
}

void Buzzer_Alarm(uint8_t count, uint32_t on_ms, uint32_t off_ms)
{
    s_on_ms = on_ms;
    s_off_ms = off_ms;
    s_continuous = (count == 0) ? 1 : 0;
    s_remain_count = count;
    s_tick_start = HAL_GetTick();
    Buzzer_HW_On();
    s_state = BUZZER_STATE_ALARM_ON;
}

void Buzzer_Tick(void)
{
    uint32_t now = HAL_GetTick();
    uint32_t elapsed = now - s_tick_start;

    switch (s_state)
    {
    case BUZZER_STATE_BEEP_ON:
        if (elapsed >= s_on_ms)
        {
            Buzzer_HW_Off();
            s_state = BUZZER_STATE_IDLE;
        }
        break;

    case BUZZER_STATE_ALARM_ON:
        if (elapsed >= s_on_ms)
        {
            Buzzer_HW_Off();
            if (!s_continuous) s_remain_count--;
            if (s_remain_count == 0 && !s_continuous)
            {
                s_state = BUZZER_STATE_IDLE;
            }
            else
            {
                s_tick_start = now;
                s_state = BUZZER_STATE_ALARM_OFF;
            }
        }
        break;

    case BUZZER_STATE_ALARM_OFF:
        if (elapsed >= s_off_ms)
        {
            Buzzer_HW_On();
            s_tick_start = now;
            s_state = BUZZER_STATE_ALARM_ON;
        }
        break;

    default:
        break;
    }
}

uint8_t Buzzer_IsActive(void)
{
    return (s_state != BUZZER_STATE_IDLE) ? 1 : 0;
}
