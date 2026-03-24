#ifndef __SOFT_TIMER_H
#define __SOFT_TIMER_H

#include "main.h"

typedef struct
{
    uint32_t period_ms;
    uint32_t deadline_ms;
    uint8_t armed;
} SoftTimer;

void SoftTimer_Init(void);
void SoftTimer_Tick(void);
uint32_t SoftTimer_GetMillis(void);
void SoftTimer_Start(SoftTimer *timer, uint32_t period_ms);
void SoftTimer_Stop(SoftTimer *timer);
uint8_t SoftTimer_IsArmed(const SoftTimer *timer);
uint8_t SoftTimer_Expired(SoftTimer *timer, uint32_t now_ms);
uint8_t SoftTimer_Every(SoftTimer *timer, uint32_t now_ms, uint32_t period_ms);

#endif
