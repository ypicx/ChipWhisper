#include "hc_sr04.h"

void HCSR04_InitPins(GPIO_TypeDef *trig_port, uint16_t trig_pin)
{
    HAL_GPIO_WritePin(trig_port, trig_pin, GPIO_PIN_RESET);
}

void HCSR04_SetTrigger(GPIO_TypeDef *trig_port, uint16_t trig_pin, GPIO_PinState state)
{
    HAL_GPIO_WritePin(trig_port, trig_pin, state);
}

GPIO_PinState HCSR04_ReadEcho(GPIO_TypeDef *echo_port, uint16_t echo_pin)
{
    return HAL_GPIO_ReadPin(echo_port, echo_pin);
}
