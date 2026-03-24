#ifndef __SOFT_TASK_SCHEDULER_H
#define __SOFT_TASK_SCHEDULER_H

#include "main.h"

typedef void (*SoftTaskCallback)(void *user_data);

typedef struct
{
    uint8_t in_use;
    const char *name;
    uint32_t period_ms;
    uint32_t next_run_ms;
    SoftTaskCallback callback;
    void *user_data;
} SoftTaskSlot;

void SoftTaskScheduler_Init(void);
HAL_StatusTypeDef SoftTaskScheduler_Add(
    const char *name,
    uint32_t period_ms,
    SoftTaskCallback callback,
    void *user_data
);
void SoftTaskScheduler_Remove(const char *name);
void SoftTaskScheduler_Clear(void);
void SoftTaskScheduler_Tick(uint32_t now_ms);
uint8_t SoftTaskScheduler_HasTask(const char *name);

#endif
