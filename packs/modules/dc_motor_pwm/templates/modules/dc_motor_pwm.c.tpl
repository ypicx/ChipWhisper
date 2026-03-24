#include "dc_motor_pwm.h"

HAL_StatusTypeDef DcMotorPwm_Attach(DcMotorPwm *motor, TIM_HandleTypeDef *htim, uint32_t channel, uint16_t period_counts)
{
    HAL_StatusTypeDef status;

    if (motor == NULL || htim == NULL || period_counts == 0U) {
        return HAL_ERROR;
    }

    motor->htim = htim;
    motor->channel = channel;
    motor->period_counts = period_counts;

    status = HAL_TIM_PWM_Start(htim, channel);
    if (status != HAL_OK) {
        return status;
    }

    return DcMotorPwm_Stop(motor);
}

HAL_StatusTypeDef DcMotorPwm_SetDutyPercent(DcMotorPwm *motor, uint8_t duty_percent)
{
    uint32_t compare;

    if (motor == NULL || motor->htim == NULL) {
        return HAL_ERROR;
    }

    if (duty_percent > 100U) {
        duty_percent = 100U;
    }

    compare = ((uint32_t)motor->period_counts * duty_percent) / 100U;
    __HAL_TIM_SET_COMPARE(motor->htim, motor->channel, compare);
    return HAL_OK;
}

HAL_StatusTypeDef DcMotorPwm_Stop(DcMotorPwm *motor)
{
    return DcMotorPwm_SetDutyPercent(motor, 0U);
}
