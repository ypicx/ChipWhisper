#include "sg90_servo.h"

HAL_StatusTypeDef Sg90Servo_Attach(Sg90Servo *servo, TIM_HandleTypeDef *htim, uint32_t channel)
{
    HAL_StatusTypeDef status;

    if (servo == NULL || htim == NULL) {
        return HAL_ERROR;
    }

    servo->htim = htim;
    servo->channel = channel;
    servo->min_pulse_us = 500U;
    servo->max_pulse_us = 2400U;
    servo->max_angle_deg = 180U;

    status = HAL_TIM_PWM_Start(htim, channel);
    if (status != HAL_OK) {
        return status;
    }

    return Sg90Servo_SetAngle(servo, 90U);
}

HAL_StatusTypeDef Sg90Servo_SetPulseUs(Sg90Servo *servo, uint16_t pulse_us)
{
    if (servo == NULL || servo->htim == NULL) {
        return HAL_ERROR;
    }

    if (pulse_us < servo->min_pulse_us) {
        pulse_us = servo->min_pulse_us;
    }
    if (pulse_us > servo->max_pulse_us) {
        pulse_us = servo->max_pulse_us;
    }

    __HAL_TIM_SET_COMPARE(servo->htim, servo->channel, pulse_us);
    return HAL_OK;
}

HAL_StatusTypeDef Sg90Servo_SetAngle(Sg90Servo *servo, uint16_t angle_deg)
{
    uint32_t pulse_range;
    uint32_t pulse_us;

    if (servo == NULL || servo->max_angle_deg == 0U) {
        return HAL_ERROR;
    }

    if (angle_deg > servo->max_angle_deg) {
        angle_deg = servo->max_angle_deg;
    }

    pulse_range = (uint32_t)(servo->max_pulse_us - servo->min_pulse_us);
    pulse_us = (uint32_t)servo->min_pulse_us + ((uint32_t)angle_deg * pulse_range) / servo->max_angle_deg;
    return Sg90Servo_SetPulseUs(servo, (uint16_t)pulse_us);
}
