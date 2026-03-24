#ifndef __MQ2_H
#define __MQ2_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* ADC handle - override in app_config.h */
#ifndef MQ2_ADC_HANDLE
#define MQ2_ADC_HANDLE  hadc1
#endif

/* Clean air Rs/Ro ratio (from MQ-2 datasheet typical value) */
#define MQ2_RO_CLEAN_AIR_FACTOR  9.83f

/* Load resistance on the MQ-2 breakout board (kΩ) */
#ifndef MQ2_RL_KOHM
#define MQ2_RL_KOHM  10.0f
#endif

/**
 * @brief Initialize MQ-2 ADC channel. Call after ADC is configured.
 */
void MQ2_Init(void);

/**
 * @brief Calibrate sensor in clean air. Call after 20s warm-up.
 * @return Ro value (sensor resistance in clean air)
 */
float MQ2_Calibrate(void);

/**
 * @brief Read raw 12-bit ADC value.
 */
uint16_t MQ2_ReadRaw(void);

/**
 * @brief Read analog voltage (0.0 ~ 3.3V).
 */
float MQ2_ReadVoltage(void);

/**
 * @brief Read approximate smoke/gas concentration in PPM.
 * @note  Uses simplified Rs/Ro curve for LPG/smoke.
 *        For accurate readings, calibrate in clean air first.
 */
float MQ2_ReadPPM(void);

/**
 * @brief Get Rs/Ro ratio (useful for custom concentration curves).
 */
float MQ2_GetRsRoRatio(void);

#ifdef __cplusplus
}
#endif

#endif /* __MQ2_H */
