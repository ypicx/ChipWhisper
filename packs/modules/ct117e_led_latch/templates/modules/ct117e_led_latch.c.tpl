#include "ct117e_led_latch.h"

static GPIO_TypeDef *const kCt117eLedPorts[8] = {
    GPIOC, GPIOC, GPIOC, GPIOC,
    GPIOC, GPIOC, GPIOC, GPIOC,
};

static const uint16_t kCt117eLedPins[8] = {
    GPIO_PIN_8,
    GPIO_PIN_9,
    GPIO_PIN_10,
    GPIO_PIN_11,
    GPIO_PIN_12,
    GPIO_PIN_13,
    GPIO_PIN_14,
    GPIO_PIN_15,
};

static void CT117ELed_InitDataBus(void)
{
    GPIO_InitTypeDef gpio_init = {0};

    __HAL_RCC_GPIOC_CLK_ENABLE();

    gpio_init.Pin = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10 | GPIO_PIN_11 |
                    GPIO_PIN_12 | GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15;
    gpio_init.Mode = GPIO_MODE_OUTPUT_PP;
    gpio_init.Pull = GPIO_NOPULL;
    gpio_init.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOC, &gpio_init);
}

static void CT117ELed_PulseLatch(CT117ELedLatch *bank)
{
    HAL_GPIO_WritePin(bank->latch_port, bank->latch_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(bank->latch_port, bank->latch_pin, GPIO_PIN_RESET);
}

void CT117ELedLatch_Init(
    CT117ELedLatch *bank,
    GPIO_TypeDef *latch_port,
    uint16_t latch_pin,
    uint8_t active_low
)
{
    GPIO_InitTypeDef gpio_init = {0};

    if (bank == NULL || latch_port == NULL) {
        return;
    }

    __HAL_RCC_GPIOD_CLK_ENABLE();
    CT117ELed_InitDataBus();

    gpio_init.Pin = latch_pin;
    gpio_init.Mode = GPIO_MODE_OUTPUT_PP;
    gpio_init.Pull = GPIO_NOPULL;
    gpio_init.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(latch_port, &gpio_init);

    bank->latch_port = latch_port;
    bank->latch_pin = latch_pin;
    bank->active_low = active_low ? 1U : 0U;

    HAL_GPIO_WritePin(bank->latch_port, bank->latch_pin, GPIO_PIN_RESET);
    CT117ELedLatch_AllOff(bank);
}

void CT117ELedLatch_WriteMask(CT117ELedLatch *bank, uint8_t mask)
{
    uint8_t index;
    uint8_t output_mask;

    if (bank == NULL) {
        return;
    }

    output_mask = (bank->active_low != 0U) ? (uint8_t)(~mask) : mask;
    for (index = 0U; index < 8U; ++index) {
        GPIO_PinState state = ((output_mask >> index) & 0x01U) ? GPIO_PIN_SET : GPIO_PIN_RESET;
        HAL_GPIO_WritePin(kCt117eLedPorts[index], kCt117eLedPins[index], state);
    }

    CT117ELed_PulseLatch(bank);
}

void CT117ELedLatch_AllOff(CT117ELedLatch *bank)
{
    CT117ELedLatch_WriteMask(bank, 0x00U);
}
