#include "pid.h"

static float PID_Clamp(float value, float min_val, float max_val)
{
    if (value < min_val) return min_val;
    if (value > max_val) return max_val;
    return value;
}

void PID_Init(PID_Controller *pid, float kp, float ki, float kd, float out_min, float out_max)
{
    if (pid == (void *)0) return;
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->output_min = out_min;
    pid->output_max = out_max;
    pid->integral = 0.0f;
    pid->prev_error = 0.0f;
    pid->initialized = 0U;
}

float PID_Compute(PID_Controller *pid, float setpoint, float measured)
{
    float error;
    float p_term;
    float i_term;
    float d_term;
    float output;

    if (pid == (void *)0) return 0.0f;

    error = setpoint - measured;

    /* Proportional */
    p_term = pid->kp * error;

    /* Integral with anti-windup */
    pid->integral += pid->ki * error;
    pid->integral = PID_Clamp(pid->integral, pid->output_min, pid->output_max);
    i_term = pid->integral;

    /* Derivative (skip on first call to avoid spike) */
    if (pid->initialized) {
        d_term = pid->kd * (error - pid->prev_error);
    } else {
        d_term = 0.0f;
        pid->initialized = 1U;
    }

    pid->prev_error = error;

    /* Sum and clamp */
    output = p_term + i_term + d_term;
    return PID_Clamp(output, pid->output_min, pid->output_max);
}

void PID_Reset(PID_Controller *pid)
{
    if (pid == (void *)0) return;
    pid->integral = 0.0f;
    pid->prev_error = 0.0f;
    pid->initialized = 0U;
}

void PID_SetTunings(PID_Controller *pid, float kp, float ki, float kd)
{
    if (pid == (void *)0) return;
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
}

void PID_SetOutputLimits(PID_Controller *pid, float out_min, float out_max)
{
    if (pid == (void *)0) return;
    pid->output_min = out_min;
    pid->output_max = out_max;
    /* Re-clamp existing integral */
    pid->integral = PID_Clamp(pid->integral, out_min, out_max);
}
