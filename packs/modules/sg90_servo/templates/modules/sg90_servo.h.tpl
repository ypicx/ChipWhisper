#ifndef __SG90_SERVO_H
#define __SG90_SERVO_H

#include "main.h"

typedef struct
{
    TIM_HandleTypeDef *htim;
    uint32_t channel;
    uint16_t min_pulse_us;
    uint16_t max_pulse_us;
    uint16_t max_angle_deg;
} Sg90Servo;

HAL_StatusTypeDef Sg90Servo_Attach(Sg90Servo *servo, TIM_HandleTypeDef *htim, uint32_t channel);
HAL_StatusTypeDef Sg90Servo_SetPulseUs(Sg90Servo *servo, uint16_t pulse_us);
HAL_StatusTypeDef Sg90Servo_SetAngle(Sg90Servo *servo, uint16_t angle_deg);

#endif
