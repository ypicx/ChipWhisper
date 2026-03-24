#ifndef __IR_RECEIVER_H
#define __IR_RECEIVER_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* Pin configuration */
#ifndef IR_PORT
#define IR_PORT  GPIOA
#endif
#ifndef IR_PIN
#define IR_PIN   GPIO_PIN_0
#endif

/* Common NEC remote key codes (21-key mini remote) */
#define IR_KEY_POWER  0x45
#define IR_KEY_MODE   0x46
#define IR_KEY_MUTE   0x47
#define IR_KEY_PLAY   0x44
#define IR_KEY_PREV   0x40
#define IR_KEY_NEXT   0x43
#define IR_KEY_EQ     0x07
#define IR_KEY_MINUS  0x15
#define IR_KEY_PLUS   0x09
#define IR_KEY_0      0x16
#define IR_KEY_RPT    0x19
#define IR_KEY_USD    0x0D
#define IR_KEY_1      0x0C
#define IR_KEY_2      0x18
#define IR_KEY_3      0x5E
#define IR_KEY_4      0x08
#define IR_KEY_5      0x1C
#define IR_KEY_6      0x5A
#define IR_KEY_7      0x42
#define IR_KEY_8      0x52
#define IR_KEY_9      0x4A

/**
 * @brief Initialize IR receiver (configure EXTI on falling edge).
 */
void IR_Init(void);

/**
 * @brief Check if a complete NEC frame has been received.
 * @return 1 if data ready
 */
uint8_t IR_DataReady(void);

/**
 * @brief Get full 32-bit NEC code: addr_inv|addr|cmd_inv|cmd
 */
uint32_t IR_GetCode(void);

/**
 * @brief Get 8-bit command byte from last received frame.
 */
uint8_t IR_GetCommand(void);

/**
 * @brief Get 8-bit address byte from last received frame.
 */
uint8_t IR_GetAddress(void);

/**
 * @brief Check if last code was a repeat (button held).
 */
uint8_t IR_IsRepeat(void);

/**
 * @brief Clear received data flag.
 */
void IR_ClearFlag(void);

/**
 * @brief Call from EXTI ISR callback for the IR pin.
 */
void IR_EXTI_Callback(void);

#ifdef __cplusplus
}
#endif

#endif /* __IR_RECEIVER_H */
