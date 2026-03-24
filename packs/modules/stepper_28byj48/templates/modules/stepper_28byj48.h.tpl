#ifndef __STEPPER_28BYJ48_H
#define __STEPPER_28BYJ48_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* Direction constants */
#define STEPPER_CW   0
#define STEPPER_CCW  1

/* 28BYJ-48 with 1:64 gear ratio:
 * Full-step: 2048 steps/rev, Half-step: 4096 steps/rev */
#define STEPPER_STEPS_PER_REV  4096

/* Pin configuration - override in app_config.h if needed */
#ifndef STEPPER_IN1_PORT
#define STEPPER_IN1_PORT  GPIOA
#endif
#ifndef STEPPER_IN1_PIN
#define STEPPER_IN1_PIN   GPIO_PIN_0
#endif
#ifndef STEPPER_IN2_PORT
#define STEPPER_IN2_PORT  GPIOA
#endif
#ifndef STEPPER_IN2_PIN
#define STEPPER_IN2_PIN   GPIO_PIN_1
#endif
#ifndef STEPPER_IN3_PORT
#define STEPPER_IN3_PORT  GPIOA
#endif
#ifndef STEPPER_IN3_PIN
#define STEPPER_IN3_PIN   GPIO_PIN_2
#endif
#ifndef STEPPER_IN4_PORT
#define STEPPER_IN4_PORT  GPIOA
#endif
#ifndef STEPPER_IN4_PIN
#define STEPPER_IN4_PIN   GPIO_PIN_3
#endif

/**
 * @brief Initialize stepper GPIO pins as outputs.
 */
void Stepper_Init(void);

/**
 * @brief Set rotation speed in RPM (1~15 RPM typical for 28BYJ-48).
 * @param rpm  Desired speed in revolutions per minute
 */
void Stepper_SetSpeed(uint8_t rpm);

/**
 * @brief Move stepper a given number of half-steps.
 *        Blocking call; returns after all steps complete.
 * @param steps  Number of half-steps (4096 = one full revolution)
 * @param dir    STEPPER_CW or STEPPER_CCW
 */
void Stepper_Step(uint32_t steps, uint8_t dir);

/**
 * @brief Rotate by a given angle in degrees.
 * @param angle_deg  Angle to rotate (positive value)
 * @param dir        STEPPER_CW or STEPPER_CCW
 */
void Stepper_RotateDegrees(float angle_deg, uint8_t dir);

/**
 * @brief De-energize all coils (saves power, but loses holding torque).
 */
void Stepper_Stop(void);

#ifdef __cplusplus
}
#endif

#endif /* __STEPPER_28BYJ48_H */
