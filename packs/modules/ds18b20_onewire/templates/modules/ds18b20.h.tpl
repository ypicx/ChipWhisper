#ifndef __DS18B20_H
#define __DS18B20_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* Pin configuration - override in app_config.h */
#ifndef DS18B20_PORT
#define DS18B20_PORT  GPIOA
#endif
#ifndef DS18B20_PIN
#define DS18B20_PIN   GPIO_PIN_0
#endif

/* Timer handle for microsecond delays - must be configured as 1MHz counter */
#ifndef DS18B20_TIMER
#define DS18B20_TIMER  htim6
#endif

/* Error return value */
#define DS18B20_ERR_TEMP  (-999.0f)

/**
 * @brief Initialize DS18B20 and verify sensor presence.
 * @return 0 on success, -1 if no sensor detected
 */
int8_t DS18B20_Init(void);

/**
 * @brief Check if sensor is present on the bus.
 * @return 1 if present, 0 if not
 */
uint8_t DS18B20_IsPresent(void);

/**
 * @brief Start temperature conversion (takes ~750ms at 12-bit).
 */
void DS18B20_StartConversion(void);

/**
 * @brief Read temperature after conversion is complete.
 * @return Temperature in Celsius, or DS18B20_ERR_TEMP on error
 */
float DS18B20_ReadTemperature(void);

/**
 * @brief Combined: start conversion, wait, read and return temperature.
 * @note  Blocking call (~750ms). Use separate Start/Read for non-blocking.
 * @return Temperature in Celsius, or DS18B20_ERR_TEMP on error
 */
float DS18B20_GetTemperature(void);

/**
 * @brief Read 64-bit ROM code (for multi-sensor bus identification).
 * @param rom_code  Output buffer, 8 bytes
 * @return 0 on success, -1 on error
 */
int8_t DS18B20_ReadROM(uint8_t *rom_code);

#ifdef __cplusplus
}
#endif

#endif /* __DS18B20_H */
