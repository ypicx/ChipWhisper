/**
 * @file ds18b20.c
 * @brief DS18B20 one-wire temperature sensor driver for STM32 HAL
 *
 * Protocol reference: Maxim DS18B20 datasheet (19-7487 Rev 6)
 * - Reset pulse: pull LOW >= 480us, release, wait 60-240us for presence
 * - Write 0: pull LOW >= 60us
 * - Write 1: pull LOW 1-15us, release for remainder of 60us slot
 * - Read: pull LOW 1-2us, release, sample at 15us mark
 * - Convert T command: 0x44, takes up to 750ms at 12-bit resolution
 * - Read Scratchpad: 0xBE, returns 9 bytes
 * - Temperature = (byte[1] << 8 | byte[0]) * 0.0625 for 12-bit
 *
 * Requires a hardware timer configured at 1MHz for microsecond delays.
 */

#include "ds18b20.h"

extern TIM_HandleTypeDef DS18B20_TIMER;

/* ---- Microsecond delay using hardware timer ---- */
static void delay_us(uint32_t us)
{
    __HAL_TIM_SET_COUNTER(&DS18B20_TIMER, 0);
    HAL_TIM_Base_Start(&DS18B20_TIMER);
    while (__HAL_TIM_GET_COUNTER(&DS18B20_TIMER) < us) {}
    HAL_TIM_Base_Stop(&DS18B20_TIMER);
}

/* ---- GPIO helpers: switch between output and input mode ---- */
static void OW_SetPinOutput(void)
{
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin   = DS18B20_PIN;
    gpio.Mode  = GPIO_MODE_OUTPUT_OD;  /* open-drain for one-wire */
    gpio.Pull  = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DS18B20_PORT, &gpio);
}

static void OW_SetPinInput(void)
{
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin  = DS18B20_PIN;
    gpio.Mode = GPIO_MODE_INPUT;
    gpio.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(DS18B20_PORT, &gpio);
}

/* ---- One-Wire protocol primitives ---- */
static uint8_t OW_Reset(void)
{
    uint8_t presence;

    OW_SetPinOutput();
    HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_RESET);
    delay_us(480);  /* reset pulse >= 480us */

    OW_SetPinInput();
    delay_us(70);   /* wait for presence pulse */
    presence = (HAL_GPIO_ReadPin(DS18B20_PORT, DS18B20_PIN) == GPIO_PIN_RESET) ? 1 : 0;
    delay_us(410);  /* complete the reset time slot */

    return presence;
}

static void OW_WriteBit(uint8_t bit)
{
    OW_SetPinOutput();
    HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_RESET);

    if (bit)
    {
        delay_us(6);   /* short low for write-1 */
        OW_SetPinInput();
        delay_us(64);
    }
    else
    {
        delay_us(60);  /* long low for write-0 */
        OW_SetPinInput();
        delay_us(10);
    }
}

static uint8_t OW_ReadBit(void)
{
    uint8_t bit;

    OW_SetPinOutput();
    HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_RESET);
    delay_us(2);

    OW_SetPinInput();
    delay_us(12);   /* sample near 15us from start */
    bit = (HAL_GPIO_ReadPin(DS18B20_PORT, DS18B20_PIN) == GPIO_PIN_SET) ? 1 : 0;
    delay_us(56);

    return bit;
}

static void OW_WriteByte(uint8_t byte)
{
    uint8_t i;
    for (i = 0; i < 8; i++)
    {
        OW_WriteBit(byte & 0x01);
        byte >>= 1;
    }
}

static uint8_t OW_ReadByte(void)
{
    uint8_t byte = 0;
    uint8_t i;
    for (i = 0; i < 8; i++)
    {
        byte >>= 1;
        if (OW_ReadBit())
            byte |= 0x80;
    }
    return byte;
}

/* ---- DS18B20 public API ---- */

int8_t DS18B20_Init(void)
{
    if (!OW_Reset())
        return -1;
    return 0;
}

uint8_t DS18B20_IsPresent(void)
{
    return OW_Reset();
}

void DS18B20_StartConversion(void)
{
    OW_Reset();
    OW_WriteByte(0xCC);  /* Skip ROM (single sensor) */
    OW_WriteByte(0x44);  /* Convert T */
}

float DS18B20_ReadTemperature(void)
{
    uint8_t scratchpad[9];
    int16_t raw;
    uint8_t i;

    if (!OW_Reset())
        return DS18B20_ERR_TEMP;

    OW_WriteByte(0xCC);  /* Skip ROM */
    OW_WriteByte(0xBE);  /* Read Scratchpad */

    for (i = 0; i < 9; i++)
        scratchpad[i] = OW_ReadByte();

    /* CRC check (byte 8) - simplified: just verify data is not all 0xFF */
    if (scratchpad[0] == 0xFF && scratchpad[1] == 0xFF)
        return DS18B20_ERR_TEMP;

    raw = (int16_t)(scratchpad[1] << 8) | scratchpad[0];

    /* 12-bit resolution: 0.0625 degrees per LSB */
    return (float)raw * 0.0625f;
}

float DS18B20_GetTemperature(void)
{
    DS18B20_StartConversion();
    HAL_Delay(750);  /* 12-bit conversion time */
    return DS18B20_ReadTemperature();
}

int8_t DS18B20_ReadROM(uint8_t *rom_code)
{
    uint8_t i;

    if (!OW_Reset())
        return -1;

    OW_WriteByte(0x33);  /* Read ROM command */

    for (i = 0; i < 8; i++)
        rom_code[i] = OW_ReadByte();

    return 0;
}
