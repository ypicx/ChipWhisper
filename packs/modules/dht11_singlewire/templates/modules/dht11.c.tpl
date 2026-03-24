#include "dht11.h"

static void DHT11_ReconfigurePin(GPIO_TypeDef *port, uint16_t pin, uint32_t mode)
{
    GPIO_InitTypeDef gpio_init = {0};

    if (port == NULL) {
        return;
    }

    gpio_init.Pin = pin;
    gpio_init.Mode = mode;
    gpio_init.Pull = GPIO_NOPULL;
    gpio_init.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(port, &gpio_init);
}

void DHT11_DriveLow(GPIO_TypeDef *port, uint16_t pin)
{
    DHT11_ReconfigurePin(port, pin, GPIO_MODE_OUTPUT_OD);
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_RESET);
}

void DHT11_ReleaseBus(GPIO_TypeDef *port, uint16_t pin)
{
    DHT11_ReconfigurePin(port, pin, GPIO_MODE_OUTPUT_OD);
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_SET);
}

GPIO_PinState DHT11_ReadLine(GPIO_TypeDef *port, uint16_t pin)
{
    DHT11_ReconfigurePin(port, pin, GPIO_MODE_INPUT);
    return HAL_GPIO_ReadPin(port, pin);
}

HAL_StatusTypeDef DHT11_StartFrame(GPIO_TypeDef *port, uint16_t pin)
{
    if (port == NULL) {
        return HAL_ERROR;
    }

    DHT11_DriveLow(port, pin);
    HAL_Delay(20);
    DHT11_ReleaseBus(port, pin);
    return HAL_OK;
}
