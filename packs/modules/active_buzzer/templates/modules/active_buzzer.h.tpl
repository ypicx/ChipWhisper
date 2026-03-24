#ifndef __ACTIVE_BUZZER_H
#define __ACTIVE_BUZZER_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* Pin configuration - override in app_config.h */
#ifndef BUZZER_PORT
#define BUZZER_PORT  GPIOC
#endif
#ifndef BUZZER_PIN
#define BUZZER_PIN   GPIO_PIN_15
#endif
/* Set to 1 if buzzer is active LOW (e.g. CT117E PNP driver) */
#ifndef BUZZER_ACTIVE_LOW
#define BUZZER_ACTIVE_LOW  0
#endif

/**
 * @brief Initialize buzzer GPIO.
 */
void Buzzer_Init(void);

/**
 * @brief Turn buzzer ON.
 */
void Buzzer_On(void);

/**
 * @brief Turn buzzer OFF.
 */
void Buzzer_Off(void);

/**
 * @brief Single beep for given duration (non-blocking, use Buzzer_Tick).
 * @param ms  Beep duration in milliseconds
 */
void Buzzer_Beep(uint32_t ms);

/**
 * @brief Alarm pattern: repeated beeps (non-blocking, use Buzzer_Tick).
 * @param count   Number of beeps (0 = continuous until Buzzer_Off)
 * @param on_ms   ON duration per beep
 * @param off_ms  OFF duration between beeps
 */
void Buzzer_Alarm(uint8_t count, uint32_t on_ms, uint32_t off_ms);

/**
 * @brief Call in main loop (every ~10ms) to update non-blocking beep/alarm.
 */
void Buzzer_Tick(void);

/**
 * @brief Check if alarm/beep pattern is still active.
 * @return 1 if active, 0 if idle
 */
uint8_t Buzzer_IsActive(void);

#ifdef __cplusplus
}
#endif

#endif /* __ACTIVE_BUZZER_H */
