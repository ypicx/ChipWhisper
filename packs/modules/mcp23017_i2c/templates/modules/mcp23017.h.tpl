#ifndef __MCP23017_H
#define __MCP23017_H

#include "main.h"

HAL_StatusTypeDef MCP23017_SetDirection(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t iodir_a,
    uint8_t iodir_b,
    uint32_t timeout
);
HAL_StatusTypeDef MCP23017_WriteGpio(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t value_a,
    uint8_t value_b,
    uint32_t timeout
);
HAL_StatusTypeDef MCP23017_ReadGpio(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t *value_a,
    uint8_t *value_b,
    uint32_t timeout
);

#endif
