#include "ring_buffer.h"

void RingBuf_Init(RingBuf *rb, uint8_t *buf, uint16_t size)
{
    if (rb == (void *)0 || buf == (void *)0) return;
    rb->buf = buf;
    rb->size = size;
    rb->head = 0U;
    rb->tail = 0U;
}

int RingBuf_Put(RingBuf *rb, uint8_t byte)
{
    uint16_t next;
    if (rb == (void *)0) return -1;
    next = (uint16_t)((rb->head + 1U) % rb->size);
    if (next == rb->tail) {
        return -1;  /* Buffer full */
    }
    rb->buf[rb->head] = byte;
    rb->head = next;
    return 0;
}

int RingBuf_Get(RingBuf *rb, uint8_t *out)
{
    if (rb == (void *)0 || out == (void *)0) return -1;
    if (rb->head == rb->tail) {
        return -1;  /* Buffer empty */
    }
    *out = rb->buf[rb->tail];
    rb->tail = (uint16_t)((rb->tail + 1U) % rb->size);
    return 0;
}

uint16_t RingBuf_Available(const RingBuf *rb)
{
    if (rb == (void *)0) return 0U;
    return (uint16_t)((rb->size + rb->head - rb->tail) % rb->size);
}

uint16_t RingBuf_Free(const RingBuf *rb)
{
    if (rb == (void *)0) return 0U;
    return (uint16_t)(rb->size - 1U - RingBuf_Available(rb));
}

void RingBuf_Flush(RingBuf *rb)
{
    if (rb == (void *)0) return;
    rb->head = 0U;
    rb->tail = 0U;
}
