#include "soft_timer.h"

static volatile uint32_t g_soft_timer_now_ms = 0U;

static uint8_t SoftTimer_TimeReached(uint32_t now_ms, uint32_t deadline_ms)
{
    return ((int32_t)(now_ms - deadline_ms) >= 0) ? 1U : 0U;
}

void SoftTimer_Init(void)
{
    g_soft_timer_now_ms = HAL_GetTick();
}

void SoftTimer_Tick(void)
{
    g_soft_timer_now_ms = HAL_GetTick();
}

uint32_t SoftTimer_GetMillis(void)
{
    return g_soft_timer_now_ms;
}

void SoftTimer_Start(SoftTimer *timer, uint32_t period_ms)
{
    if (timer == NULL) {
        return;
    }

    timer->period_ms = period_ms;
    timer->deadline_ms = g_soft_timer_now_ms + period_ms;
    timer->armed = 1U;
}

void SoftTimer_Stop(SoftTimer *timer)
{
    if (timer == NULL) {
        return;
    }

    timer->armed = 0U;
}

uint8_t SoftTimer_IsArmed(const SoftTimer *timer)
{
    if (timer == NULL) {
        return 0U;
    }
    return timer->armed;
}

uint8_t SoftTimer_Expired(SoftTimer *timer, uint32_t now_ms)
{
    if (timer == NULL || timer->armed == 0U) {
        return 0U;
    }
    if (!SoftTimer_TimeReached(now_ms, timer->deadline_ms)) {
        return 0U;
    }

    timer->deadline_ms = now_ms + timer->period_ms;
    return 1U;
}

uint8_t SoftTimer_Every(SoftTimer *timer, uint32_t now_ms, uint32_t period_ms)
{
    if (timer == NULL) {
        return 0U;
    }
    if (timer->armed == 0U || timer->period_ms != period_ms) {
        timer->period_ms = period_ms;
        timer->deadline_ms = now_ms + period_ms;
        timer->armed = 1U;
        return 0U;
    }
    return SoftTimer_Expired(timer, now_ms);
}
