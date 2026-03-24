#ifndef __DC_MOTOR_PWM_H
#define __DC_MOTOR_PWM_H

#include "main.h"

typedef struct
{
    TIM_HandleTypeDef *htim;
    uint32_t channel;
    uint16_t period_counts;
} DcMotorPwm;

HAL_StatusTypeDef DcMotorPwm_Attach(DcMotorPwm *motor, TIM_HandleTypeDef *htim, uint32_t channel, uint16_t period_counts);
HAL_StatusTypeDef DcMotorPwm_SetDutyPercent(DcMotorPwm *motor, uint8_t duty_percent);
HAL_StatusTypeDef DcMotorPwm_Stop(DcMotorPwm *motor);

#endif
