#include "soft_task_scheduler.h"

#include <string.h>

#define SOFT_TASK_SCHEDULER_MAX_TASKS 8U

static SoftTaskSlot g_soft_task_slots[SOFT_TASK_SCHEDULER_MAX_TASKS];

static uint8_t SoftTaskScheduler_TimeReached(uint32_t now_ms, uint32_t timestamp_ms)
{
    return ((int32_t)(now_ms - timestamp_ms) >= 0) ? 1U : 0U;
}

void SoftTaskScheduler_Init(void)
{
    SoftTaskScheduler_Clear();
}

HAL_StatusTypeDef SoftTaskScheduler_Add(
    const char *name,
    uint32_t period_ms,
    SoftTaskCallback callback,
    void *user_data
)
{
    uint32_t now_ms = HAL_GetTick();
    uint32_t index;

    if (callback == NULL || period_ms == 0U) {
        return HAL_ERROR;
    }

    for (index = 0U; index < SOFT_TASK_SCHEDULER_MAX_TASKS; ++index) {
        SoftTaskSlot *slot = &g_soft_task_slots[index];
        if (slot->in_use == 0U) {
            slot->in_use = 1U;
            slot->name = name;
            slot->period_ms = period_ms;
            slot->next_run_ms = now_ms + period_ms;
            slot->callback = callback;
            slot->user_data = user_data;
            return HAL_OK;
        }
    }

    return HAL_BUSY;
}

void SoftTaskScheduler_Remove(const char *name)
{
    uint32_t index;

    if (name == NULL) {
        return;
    }

    for (index = 0U; index < SOFT_TASK_SCHEDULER_MAX_TASKS; ++index) {
        SoftTaskSlot *slot = &g_soft_task_slots[index];
        if (slot->in_use && slot->name != NULL && strcmp(slot->name, name) == 0) {
            slot->in_use = 0U;
            slot->name = NULL;
            slot->period_ms = 0U;
            slot->next_run_ms = 0U;
            slot->callback = NULL;
            slot->user_data = NULL;
        }
    }
}

void SoftTaskScheduler_Clear(void)
{
    memset(g_soft_task_slots, 0, sizeof(g_soft_task_slots));
}

void SoftTaskScheduler_Tick(uint32_t now_ms)
{
    uint32_t index;

    for (index = 0U; index < SOFT_TASK_SCHEDULER_MAX_TASKS; ++index) {
        SoftTaskSlot *slot = &g_soft_task_slots[index];
        if (slot->in_use == 0U || slot->callback == NULL) {
            continue;
        }
        if (!SoftTaskScheduler_TimeReached(now_ms, slot->next_run_ms)) {
            continue;
        }
        slot->next_run_ms = now_ms + slot->period_ms;
        slot->callback(slot->user_data);
    }
}

uint8_t SoftTaskScheduler_HasTask(const char *name)
{
    uint32_t index;

    if (name == NULL) {
        return 0U;
    }

    for (index = 0U; index < SOFT_TASK_SCHEDULER_MAX_TASKS; ++index) {
        const SoftTaskSlot *slot = &g_soft_task_slots[index];
        if (slot->in_use && slot->name != NULL && strcmp(slot->name, name) == 0) {
            return 1U;
        }
    }

    return 0U;
}
