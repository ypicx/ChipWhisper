/**
 * @file ir_receiver.c
 * @brief NEC infrared protocol decoder for VS1838B receiver
 *
 * NEC Protocol timing:
 *   Leader:  9ms LOW + 4.5ms HIGH
 *   Repeat:  9ms LOW + 2.25ms HIGH + 562us LOW
 *   Bit 0:   562us LOW + 562us HIGH
 *   Bit 1:   562us LOW + 1687us HIGH
 *   Frame:   addr[7:0] + addr_inv[7:0] + cmd[7:0] + cmd_inv[7:0]
 *
 * Uses EXTI falling edge interrupt + microsecond timer for timing measurement.
 * Reference: NEC IR transmission protocol specification.
 */

#include "ir_receiver.h"

/* State machine states */
typedef enum {
    IR_IDLE,
    IR_LEADER_LOW,
    IR_LEADER_HIGH,
    IR_DATA_LOW,
    IR_DATA_HIGH,
} IR_State;

static volatile IR_State  s_state = IR_IDLE;
static volatile uint32_t  s_code = 0;
static volatile uint8_t   s_bit_count = 0;
static volatile uint8_t   s_data_ready = 0;
static volatile uint8_t   s_repeat = 0;
static volatile uint32_t  s_last_edge_us = 0;
static volatile uint32_t  s_temp_code = 0;

/* Simple microsecond counter using SysTick (approximate) */
static uint32_t IR_GetMicros(void)
{
    /* Use HAL_GetTick() * 1000 + (SysTick reload - SysTick counter) / ticks_per_us */
    uint32_t ms = HAL_GetTick();
    uint32_t ticks = SysTick->LOAD - SysTick->VAL;
    uint32_t us_per_tick = (SystemCoreClock / 1000000UL);
    if (us_per_tick == 0) us_per_tick = 1;
    return ms * 1000UL + ticks / us_per_tick;
}

void IR_Init(void)
{
    s_state = IR_IDLE;
    s_code = 0;
    s_data_ready = 0;
    s_repeat = 0;
    s_bit_count = 0;
    /* GPIO EXTI should be configured in CubeMX as falling edge interrupt */
}

uint8_t IR_DataReady(void)
{
    return s_data_ready;
}

uint32_t IR_GetCode(void)
{
    return s_code;
}

uint8_t IR_GetCommand(void)
{
    return (uint8_t)(s_code & 0xFF);
}

uint8_t IR_GetAddress(void)
{
    return (uint8_t)((s_code >> 16) & 0xFF);
}

uint8_t IR_IsRepeat(void)
{
    return s_repeat;
}

void IR_ClearFlag(void)
{
    s_data_ready = 0;
    s_repeat = 0;
}

/**
 * @brief Call this from HAL_GPIO_EXTI_Callback() when IR pin triggers.
 *
 * Measures time between edges to decode NEC protocol.
 * Both falling and rising edges are needed; if only falling edge EXTI is
 * configured, this uses time between consecutive falling edges.
 */
void IR_EXTI_Callback(void)
{
    uint32_t now_us = IR_GetMicros();
    uint32_t elapsed = now_us - s_last_edge_us;
    s_last_edge_us = now_us;

    /* Filter out noise (< 300us) */
    if (elapsed < 300)
        return;

    /* Detect leader pulse: 9ms + 4.5ms = ~13.5ms between first two falling edges */
    if (elapsed > 12000 && elapsed < 15000)
    {
        /* Leader detected, start receiving data */
        s_temp_code = 0;
        s_bit_count = 0;
        s_state = IR_DATA_HIGH;
        return;
    }

    /* Detect repeat: 9ms + 2.25ms = ~11.25ms */
    if (elapsed > 10000 && elapsed < 12000)
    {
        s_repeat = 1;
        s_data_ready = 1;
        return;
    }

    if (s_state == IR_DATA_HIGH)
    {
        /* Bit timing: 562us+562us = ~1125us for bit 0
         *             562us+1687us = ~2250us for bit 1 */
        if (elapsed > 800 && elapsed < 1500)
        {
            /* Bit 0 */
            s_temp_code >>= 1;
            /* MSB stays 0 */
            s_bit_count++;
        }
        else if (elapsed > 1800 && elapsed < 2800)
        {
            /* Bit 1 */
            s_temp_code >>= 1;
            s_temp_code |= 0x80000000UL;
            s_bit_count++;
        }
        else
        {
            /* Invalid timing, reset */
            s_state = IR_IDLE;
            return;
        }

        if (s_bit_count >= 32)
        {
            s_code = s_temp_code;
            s_data_ready = 1;
            s_repeat = 0;
            s_state = IR_IDLE;
        }
    }
}
