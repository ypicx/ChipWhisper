#include "tm1637.h"

static void TM1637_SetLine(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state)
{
    HAL_GPIO_WritePin(port, pin, state);
}

static void TM1637_Start(GPIO_TypeDef *clk_port, uint16_t clk_pin, GPIO_TypeDef *dio_port, uint16_t dio_pin)
{
    TM1637_SetLine(clk_port, clk_pin, GPIO_PIN_SET);
    TM1637_SetLine(dio_port, dio_pin, GPIO_PIN_SET);
    TM1637_SetLine(dio_port, dio_pin, GPIO_PIN_RESET);
}

static void TM1637_Stop(GPIO_TypeDef *clk_port, uint16_t clk_pin, GPIO_TypeDef *dio_port, uint16_t dio_pin)
{
    TM1637_SetLine(clk_port, clk_pin, GPIO_PIN_RESET);
    TM1637_SetLine(dio_port, dio_pin, GPIO_PIN_RESET);
    TM1637_SetLine(clk_port, clk_pin, GPIO_PIN_SET);
    TM1637_SetLine(dio_port, dio_pin, GPIO_PIN_SET);
}

static void TM1637_WriteByte(GPIO_TypeDef *clk_port, uint16_t clk_pin, GPIO_TypeDef *dio_port, uint16_t dio_pin, uint8_t value)
{
    uint8_t bit_index;

    for (bit_index = 0U; bit_index < 8U; ++bit_index) {
        TM1637_SetLine(clk_port, clk_pin, GPIO_PIN_RESET);
        TM1637_SetLine(dio_port, dio_pin, ((value & 0x01U) != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
        value >>= 1;
        TM1637_SetLine(clk_port, clk_pin, GPIO_PIN_SET);
    }
    TM1637_SetLine(clk_port, clk_pin, GPIO_PIN_RESET);
    TM1637_SetLine(clk_port, clk_pin, GPIO_PIN_SET);
}

void TM1637_InitPins(GPIO_TypeDef *clk_port, uint16_t clk_pin, GPIO_TypeDef *dio_port, uint16_t dio_pin)
{
    TM1637_SetLine(clk_port, clk_pin, GPIO_PIN_SET);
    TM1637_SetLine(dio_port, dio_pin, GPIO_PIN_SET);
}

HAL_StatusTypeDef TM1637_DisplayRaw(
    GPIO_TypeDef *clk_port,
    uint16_t clk_pin,
    GPIO_TypeDef *dio_port,
    uint16_t dio_pin,
    const uint8_t digits[4],
    uint8_t brightness
)
{
    uint8_t index;

    if (clk_port == NULL || dio_port == NULL || digits == NULL || brightness > 7U) {
        return HAL_ERROR;
    }
    TM1637_Start(clk_port, clk_pin, dio_port, dio_pin);
    TM1637_WriteByte(clk_port, clk_pin, dio_port, dio_pin, 0x40U);
    TM1637_Stop(clk_port, clk_pin, dio_port, dio_pin);

    TM1637_Start(clk_port, clk_pin, dio_port, dio_pin);
    TM1637_WriteByte(clk_port, clk_pin, dio_port, dio_pin, 0xC0U);
    for (index = 0U; index < 4U; ++index) {
        TM1637_WriteByte(clk_port, clk_pin, dio_port, dio_pin, digits[index]);
    }
    TM1637_Stop(clk_port, clk_pin, dio_port, dio_pin);

    TM1637_Start(clk_port, clk_pin, dio_port, dio_pin);
    TM1637_WriteByte(clk_port, clk_pin, dio_port, dio_pin, (uint8_t)(0x88U | brightness));
    TM1637_Stop(clk_port, clk_pin, dio_port, dio_pin);
    return HAL_OK;
}
