/**
 * @file stepper_28byj48.c
 * @brief 28BYJ-48 stepper motor driver via ULN2003
 *
 * Half-step drive sequence for smooth operation.
 * Reference: 28BYJ-48 datasheet, ULN2003 application notes.
 *
 * Half-step sequence (8 phases):
 *   Step  IN1  IN2  IN3  IN4
 *    0     1    0    0    0
 *    1     1    1    0    0
 *    2     0    1    0    0
 *    3     0    1    1    0
 *    4     0    0    1    0
 *    5     0    0    1    1
 *    6     0    0    0    1
 *    7     1    0    0    1
 *
 * 4096 half-steps = 360 degrees (with 1:64 gear ratio).
 */

#include "stepper_28byj48.h"

/* 8-phase half-step lookup table */
static const uint8_t s_halfstep_seq[8][4] = {
    {1, 0, 0, 0},  /* phase 0 */
    {1, 1, 0, 0},  /* phase 1 */
    {0, 1, 0, 0},  /* phase 2 */
    {0, 1, 1, 0},  /* phase 3 */
    {0, 0, 1, 0},  /* phase 4 */
    {0, 0, 1, 1},  /* phase 5 */
    {0, 0, 0, 1},  /* phase 6 */
    {1, 0, 0, 1},  /* phase 7 */
};

static uint16_t s_step_delay_ms = 2;  /* ms between half-steps */
static int8_t   s_phase_index   = 0;

/* Write one phase to the GPIO pins */
static void Stepper_WritePhase(uint8_t phase)
{
    HAL_GPIO_WritePin(STEPPER_IN1_PORT, STEPPER_IN1_PIN,
                      s_halfstep_seq[phase][0] ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(STEPPER_IN2_PORT, STEPPER_IN2_PIN,
                      s_halfstep_seq[phase][1] ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(STEPPER_IN3_PORT, STEPPER_IN3_PIN,
                      s_halfstep_seq[phase][2] ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(STEPPER_IN4_PORT, STEPPER_IN4_PIN,
                      s_halfstep_seq[phase][3] ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void Stepper_Init(void)
{
    /* GPIO should already be configured as outputs by CubeMX/peripherals.c */
    Stepper_Stop();
    s_phase_index = 0;
}

void Stepper_SetSpeed(uint8_t rpm)
{
    if (rpm == 0) rpm = 1;
    if (rpm > 15) rpm = 15;  /* 28BYJ-48 max ~15 RPM */

    /* delay_ms = 60000 / (steps_per_rev * rpm)
     * For 4096 steps/rev: delay_ms = 60000 / (4096 * rpm) */
    uint32_t delay = 60000UL / ((uint32_t)STEPPER_STEPS_PER_REV * rpm);
    if (delay < 1) delay = 1;
    if (delay > 20) delay = 20;
    s_step_delay_ms = (uint16_t)delay;
}

void Stepper_Step(uint32_t steps, uint8_t dir)
{
    uint32_t i;
    for (i = 0; i < steps; i++)
    {
        if (dir == STEPPER_CW)
        {
            s_phase_index++;
            if (s_phase_index > 7) s_phase_index = 0;
        }
        else
        {
            s_phase_index--;
            if (s_phase_index < 0) s_phase_index = 7;
        }
        Stepper_WritePhase((uint8_t)s_phase_index);
        HAL_Delay(s_step_delay_ms);
    }
}

void Stepper_RotateDegrees(float angle_deg, uint8_t dir)
{
    uint32_t steps = (uint32_t)(angle_deg * (float)STEPPER_STEPS_PER_REV / 360.0f + 0.5f);
    if (steps > 0)
    {
        Stepper_Step(steps, dir);
    }
}

void Stepper_Stop(void)
{
    HAL_GPIO_WritePin(STEPPER_IN1_PORT, STEPPER_IN1_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(STEPPER_IN2_PORT, STEPPER_IN2_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(STEPPER_IN3_PORT, STEPPER_IN3_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(STEPPER_IN4_PORT, STEPPER_IN4_PIN, GPIO_PIN_RESET);
}
