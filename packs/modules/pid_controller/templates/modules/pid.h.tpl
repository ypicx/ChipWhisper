#ifndef __PID_H
#define __PID_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float kp;
    float ki;
    float kd;
    float output_min;
    float output_max;
    float integral;
    float prev_error;
    unsigned char initialized;
} PID_Controller;

/**
 * @brief Initialize PID controller with gains and output limits.
 * @param pid      Pointer to PID controller instance
 * @param kp       Proportional gain
 * @param ki       Integral gain
 * @param kd       Derivative gain
 * @param out_min  Minimum output value (anti-windup clamp)
 * @param out_max  Maximum output value (anti-windup clamp)
 */
void PID_Init(PID_Controller *pid, float kp, float ki, float kd, float out_min, float out_max);

/**
 * @brief Compute one PID iteration.
 * @param pid       Pointer to PID controller instance
 * @param setpoint  Desired target value
 * @param measured  Current measured value
 * @return Clamped output value in [out_min, out_max]
 */
float PID_Compute(PID_Controller *pid, float setpoint, float measured);

/**
 * @brief Reset integral accumulator and derivative state.
 */
void PID_Reset(PID_Controller *pid);

/**
 * @brief Update PID tuning parameters at runtime.
 */
void PID_SetTunings(PID_Controller *pid, float kp, float ki, float kd);

/**
 * @brief Update output limits at runtime.
 */
void PID_SetOutputLimits(PID_Controller *pid, float out_min, float out_max);

#ifdef __cplusplus
}
#endif

#endif /* __PID_H */
