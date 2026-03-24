#include "relay_gpio.h"

void RelayGpio_InitPin(GPIO_TypeDef *port, uint16_t pin)
{
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_RESET);
}

void RelayGpio_Write(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state)
{
    HAL_GPIO_WritePin(port, pin, state);
}

void RelayGpio_On(GPIO_TypeDef *port, uint16_t pin)
{
    RelayGpio_Write(port, pin, GPIO_PIN_SET);
}

void RelayGpio_Off(GPIO_TypeDef *port, uint16_t pin)
{
    RelayGpio_Write(port, pin, GPIO_PIN_RESET);
}
