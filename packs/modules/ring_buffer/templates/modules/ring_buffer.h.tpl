#ifndef __RING_BUFFER_H
#define __RING_BUFFER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t *buf;
    uint16_t size;
    volatile uint16_t head;
    volatile uint16_t tail;
} RingBuf;

/**
 * @brief Initialize ring buffer with caller-provided storage.
 * @param rb     Pointer to ring buffer instance
 * @param buf    Caller-provided byte storage
 * @param size   Buffer capacity in bytes
 */
void RingBuf_Init(RingBuf *rb, uint8_t *buf, uint16_t size);

/**
 * @brief Put one byte into the ring buffer.
 * @return 0 on success, -1 if buffer is full
 */
int RingBuf_Put(RingBuf *rb, uint8_t byte);

/**
 * @brief Get one byte from the ring buffer.
 * @param rb    Pointer to ring buffer instance
 * @param out   Pointer to store retrieved byte
 * @return 0 on success, -1 if buffer is empty
 */
int RingBuf_Get(RingBuf *rb, uint8_t *out);

/**
 * @brief Return number of bytes available to read.
 */
uint16_t RingBuf_Available(const RingBuf *rb);

/**
 * @brief Return remaining free space in bytes.
 */
uint16_t RingBuf_Free(const RingBuf *rb);

/**
 * @brief Discard all data in the buffer.
 */
void RingBuf_Flush(RingBuf *rb);

#ifdef __cplusplus
}
#endif

#endif /* __RING_BUFFER_H */
