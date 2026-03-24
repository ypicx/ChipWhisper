#include "ds1302_gpio.h"

static void DS1302_Delay(void)
{
    volatile uint32_t index;
    for (index = 0U; index < 36U; ++index) {
        __NOP();
    }
}

static void DS1302_SetIoOutput(DS1302_Gpio *rtc)
{
    GPIO_InitTypeDef init = {0};

    init.Pin = rtc->io_pin;
    init.Mode = GPIO_MODE_OUTPUT_OD;
    init.Pull = GPIO_NOPULL;
    init.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(rtc->io_port, &init);
}

static void DS1302_SetIoInput(DS1302_Gpio *rtc)
{
    GPIO_InitTypeDef init = {0};

    init.Pin = rtc->io_pin;
    init.Mode = GPIO_MODE_INPUT;
    init.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(rtc->io_port, &init);
}

static void DS1302_WriteByte(DS1302_Gpio *rtc, uint8_t value)
{
    uint8_t index;

    DS1302_SetIoOutput(rtc);
    for (index = 0U; index < 8U; ++index) {
        HAL_GPIO_WritePin(rtc->clk_port, rtc->clk_pin, GPIO_PIN_RESET);
        HAL_GPIO_WritePin(rtc->io_port, rtc->io_pin, (value & 0x01U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
        DS1302_Delay();
        HAL_GPIO_WritePin(rtc->clk_port, rtc->clk_pin, GPIO_PIN_SET);
        DS1302_Delay();
        value >>= 1;
    }
}

static uint8_t DS1302_ReadByte(DS1302_Gpio *rtc)
{
    uint8_t index;
    uint8_t value = 0U;

    DS1302_SetIoInput(rtc);
    for (index = 0U; index < 8U; ++index) {
        HAL_GPIO_WritePin(rtc->clk_port, rtc->clk_pin, GPIO_PIN_RESET);
        DS1302_Delay();
        if (HAL_GPIO_ReadPin(rtc->io_port, rtc->io_pin) == GPIO_PIN_SET) {
            value |= (uint8_t)(1U << index);
        }
        HAL_GPIO_WritePin(rtc->clk_port, rtc->clk_pin, GPIO_PIN_SET);
        DS1302_Delay();
    }
    return value;
}

void DS1302_Init(
    DS1302_Gpio *rtc,
    GPIO_TypeDef *ce_port,
    uint16_t ce_pin,
    GPIO_TypeDef *clk_port,
    uint16_t clk_pin,
    GPIO_TypeDef *io_port,
    uint16_t io_pin
)
{
    if (rtc == NULL) {
        return;
    }

    rtc->ce_port = ce_port;
    rtc->ce_pin = ce_pin;
    rtc->clk_port = clk_port;
    rtc->clk_pin = clk_pin;
    rtc->io_port = io_port;
    rtc->io_pin = io_pin;

    HAL_GPIO_WritePin(rtc->ce_port, rtc->ce_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(rtc->clk_port, rtc->clk_pin, GPIO_PIN_RESET);
    DS1302_SetIoOutput(rtc);
    HAL_GPIO_WritePin(rtc->io_port, rtc->io_pin, GPIO_PIN_RESET);
}

HAL_StatusTypeDef DS1302_WriteRegister(DS1302_Gpio *rtc, uint8_t address, uint8_t value)
{
    if (rtc == NULL) {
        return HAL_ERROR;
    }

    HAL_GPIO_WritePin(rtc->ce_port, rtc->ce_pin, GPIO_PIN_SET);
    DS1302_Delay();
    DS1302_WriteByte(rtc, (uint8_t)(address & 0xFEU));
    DS1302_WriteByte(rtc, value);
    HAL_GPIO_WritePin(rtc->ce_port, rtc->ce_pin, GPIO_PIN_RESET);
    return HAL_OK;
}

HAL_StatusTypeDef DS1302_ReadRegister(DS1302_Gpio *rtc, uint8_t address, uint8_t *value)
{
    if (rtc == NULL || value == NULL) {
        return HAL_ERROR;
    }

    HAL_GPIO_WritePin(rtc->ce_port, rtc->ce_pin, GPIO_PIN_SET);
    DS1302_Delay();
    DS1302_WriteByte(rtc, (uint8_t)(address | 0x01U));
    *value = DS1302_ReadByte(rtc);
    HAL_GPIO_WritePin(rtc->ce_port, rtc->ce_pin, GPIO_PIN_RESET);
    return HAL_OK;
}

HAL_StatusTypeDef DS1302_ReadTime(DS1302_Gpio *rtc, DS1302_Time *time_value)
{
    uint8_t raw = 0U;

    if (rtc == NULL || time_value == NULL) {
        return HAL_ERROR;
    }

    if (DS1302_ReadRegister(rtc, 0x81U, &raw) != HAL_OK) {
        return HAL_ERROR;
    }
    time_value->second = DS1302_BcdToDec((uint8_t)(raw & 0x7FU));

    if (DS1302_ReadRegister(rtc, 0x83U, &raw) != HAL_OK) {
        return HAL_ERROR;
    }
    time_value->minute = DS1302_BcdToDec((uint8_t)(raw & 0x7FU));

    if (DS1302_ReadRegister(rtc, 0x85U, &raw) != HAL_OK) {
        return HAL_ERROR;
    }
    time_value->hour = DS1302_BcdToDec((uint8_t)(raw & 0x3FU));

    if (DS1302_ReadRegister(rtc, 0x87U, &raw) != HAL_OK) {
        return HAL_ERROR;
    }
    time_value->day = DS1302_BcdToDec((uint8_t)(raw & 0x3FU));

    if (DS1302_ReadRegister(rtc, 0x89U, &raw) != HAL_OK) {
        return HAL_ERROR;
    }
    time_value->month = DS1302_BcdToDec((uint8_t)(raw & 0x1FU));

    if (DS1302_ReadRegister(rtc, 0x8BU, &raw) != HAL_OK) {
        return HAL_ERROR;
    }
    time_value->weekday = DS1302_BcdToDec((uint8_t)(raw & 0x07U));

    if (DS1302_ReadRegister(rtc, 0x8DU, &raw) != HAL_OK) {
        return HAL_ERROR;
    }
    time_value->year = DS1302_BcdToDec(raw);

    return HAL_OK;
}

uint8_t DS1302_BcdToDec(uint8_t value)
{
    return (uint8_t)(((value >> 4) * 10U) + (value & 0x0FU));
}

uint8_t DS1302_DecToBcd(uint8_t value)
{
    return (uint8_t)(((value / 10U) << 4) | (value % 10U));
}
