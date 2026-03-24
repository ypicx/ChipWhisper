#ifndef __MOVING_AVG_H
#define __MOVING_AVG_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float *buffer;
    uint16_t size;
    uint16_t index;
    uint16_t count;
    float sum;
} MovingAvg_Filter;

/**
 * @brief Initialize the moving average filter.
 * @param f          Pointer to filter instance
 * @param buffer     Caller-provided float buffer of at least @p size elements
 * @param size       Window size (number of samples)
 */
void MovingAvg_Init(MovingAvg_Filter *f, float *buffer, uint16_t size);

/**
 * @brief Feed a new sample and return the updated average.
 * @param f      Pointer to filter instance
 * @param sample New sample value
 * @return Current moving average
 */
float MovingAvg_Update(MovingAvg_Filter *f, float sample);

/**
 * @brief Get current average without adding a new sample.
 */
float MovingAvg_GetAverage(const MovingAvg_Filter *f);

/**
 * @brief Reset filter state, clearing all accumulated samples.
 */
void MovingAvg_Reset(MovingAvg_Filter *f);

#ifdef __cplusplus
}
#endif

#endif /* __MOVING_AVG_H */
