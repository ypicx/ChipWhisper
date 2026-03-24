#ifndef __MCP4017_H
#define __MCP4017_H

#include "main.h"

HAL_StatusTypeDef MCP4017_SetWiper(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t value, uint32_t timeout);
HAL_StatusTypeDef MCP4017_ReadWiper(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t *value, uint32_t timeout);

#endif
