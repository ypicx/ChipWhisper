#include "moving_avg.h"

void MovingAvg_Init(MovingAvg_Filter *f, float *buffer, uint16_t size)
{
    uint16_t i;
    if (f == (void *)0 || buffer == (void *)0 || size == 0U) return;
    f->buffer = buffer;
    f->size = size;
    f->index = 0U;
    f->count = 0U;
    f->sum = 0.0f;
    for (i = 0U; i < size; i++) {
        buffer[i] = 0.0f;
    }
}

float MovingAvg_Update(MovingAvg_Filter *f, float sample)
{
    if (f == (void *)0 || f->buffer == (void *)0 || f->size == 0U) return 0.0f;

    /* Subtract oldest value if buffer is full */
    if (f->count >= f->size) {
        f->sum -= f->buffer[f->index];
    } else {
        f->count++;
    }

    /* Store new sample */
    f->buffer[f->index] = sample;
    f->sum += sample;

    /* Advance circular index */
    f->index++;
    if (f->index >= f->size) {
        f->index = 0U;
    }

    return f->sum / (float)f->count;
}

float MovingAvg_GetAverage(const MovingAvg_Filter *f)
{
    if (f == (void *)0 || f->count == 0U) return 0.0f;
    return f->sum / (float)f->count;
}

void MovingAvg_Reset(MovingAvg_Filter *f)
{
    uint16_t i;
    if (f == (void *)0) return;
    f->index = 0U;
    f->count = 0U;
    f->sum = 0.0f;
    if (f->buffer != (void *)0) {
        for (i = 0U; i < f->size; i++) {
            f->buffer[i] = 0.0f;
        }
    }
}
