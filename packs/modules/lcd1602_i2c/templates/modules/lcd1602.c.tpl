#include "lcd1602.h"

#define LCD1602_RS 0x01U
#define LCD1602_RW 0x02U
#define LCD1602_EN 0x04U
#define LCD1602_BL 0x08U

static HAL_StatusTypeDef LCD1602_WriteExpander(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t value, uint32_t timeout)
{
    return HAL_I2C_Master_Transmit(hi2c, (uint16_t)(address7 << 1), &value, 1U, timeout);
}

static HAL_StatusTypeDef LCD1602_PulseEnable(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t value, uint32_t timeout)
{
    if (LCD1602_WriteExpander(hi2c, address7, (uint8_t)(value | LCD1602_EN), timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (LCD1602_WriteExpander(hi2c, address7, (uint8_t)(value & (uint8_t)~LCD1602_EN), timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    HAL_Delay(1);
    return HAL_OK;
}

static HAL_StatusTypeDef LCD1602_Send(I2C_HandleTypeDef *hi2c, uint16_t address7, uint8_t value, uint8_t rs, uint32_t timeout)
{
    uint8_t high = (uint8_t)((value & 0xF0U) | LCD1602_BL | (rs ? LCD1602_RS : 0U));
    uint8_t low = (uint8_t)(((value << 4) & 0xF0U) | LCD1602_BL | (rs ? LCD1602_RS : 0U));

    if (LCD1602_PulseEnable(hi2c, address7, high, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    return LCD1602_PulseEnable(hi2c, address7, low, timeout);
}

HAL_StatusTypeDef LCD1602_Init(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    HAL_Delay(50);
    if (LCD1602_Send(hi2c, address7, 0x33U, 0U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (LCD1602_Send(hi2c, address7, 0x32U, 0U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (LCD1602_Send(hi2c, address7, 0x28U, 0U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (LCD1602_Send(hi2c, address7, 0x0CU, 0U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    if (LCD1602_Send(hi2c, address7, 0x06U, 0U, timeout) != HAL_OK) {
        return HAL_ERROR;
    }
    return LCD1602_Clear(hi2c, address7, timeout);
}

HAL_StatusTypeDef LCD1602_Clear(I2C_HandleTypeDef *hi2c, uint16_t address7, uint32_t timeout)
{
    HAL_StatusTypeDef status = LCD1602_Send(hi2c, address7, 0x01U, 0U, timeout);
    HAL_Delay(2);
    return status;
}

HAL_StatusTypeDef LCD1602_SetCursor(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    uint8_t row,
    uint8_t column,
    uint32_t timeout
)
{
    static const uint8_t offsets[2] = {0x00U, 0x40U};
    if (row > 1U || column > 15U) {
        return HAL_ERROR;
    }
    return LCD1602_Send(hi2c, address7, (uint8_t)(0x80U | offsets[row] | column), 0U, timeout);
}

HAL_StatusTypeDef LCD1602_WriteString(
    I2C_HandleTypeDef *hi2c,
    uint16_t address7,
    const char *text,
    uint32_t timeout
)
{
    if (hi2c == NULL || text == NULL) {
        return HAL_ERROR;
    }
    while (*text != '\0') {
        if (LCD1602_Send(hi2c, address7, (uint8_t)(*text), 1U, timeout) != HAL_OK) {
            return HAL_ERROR;
        }
        ++text;
    }
    return HAL_OK;
}
