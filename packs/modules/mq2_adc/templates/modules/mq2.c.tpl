/**
 * @file mq2.c
 * @brief MQ-2 gas/smoke sensor driver for STM32 HAL
 *
 * Reference: MQ-2 semiconductor sensor datasheet
 * - Heater voltage: 5V ± 0.1V
 * - Load resistance RL: 10kΩ ~ 47kΩ (breakout board default 10kΩ)
 * - Clean air Rs/Ro ≈ 9.83
 * - Sensitive to LPG, propane, methane, alcohol, hydrogen, smoke
 *
 * PPM approximation uses simplified power-law: PPM = a * (Rs/Ro)^b
 * For smoke: a ≈ 3616.4, b ≈ -2.675 (from datasheet log-log curve)
 */

#include "mq2.h"
#include <math.h>

extern ADC_HandleTypeDef MQ2_ADC_HANDLE;

static float s_ro = 10.0f;  /* sensor resistance in clean air (kΩ) */

/* Read ADC with simple averaging (4 samples) */
static uint16_t MQ2_ReadADC_Avg(void)
{
    uint32_t sum = 0;
    uint8_t i;

    for (i = 0; i < 4; i++)
    {
        HAL_ADC_Start(&MQ2_ADC_HANDLE);
        HAL_ADC_PollForConversion(&MQ2_ADC_HANDLE, 10);
        sum += HAL_ADC_GetValue(&MQ2_ADC_HANDLE);
        HAL_ADC_Stop(&MQ2_ADC_HANDLE);
    }

    return (uint16_t)(sum / 4);
}

/* Calculate sensor resistance Rs from ADC reading */
static float MQ2_CalcRs(uint16_t adc_raw)
{
    if (adc_raw == 0) adc_raw = 1;
    /* Voltage divider: Vout = VCC * RL / (Rs + RL)
     * Rs = RL * (VCC/Vout - 1) = RL * (4095/adc - 1)  for 12-bit ADC */
    return MQ2_RL_KOHM * (4095.0f / (float)adc_raw - 1.0f);
}

void MQ2_Init(void)
{
    /* ADC channel should already be configured by CubeMX */
    s_ro = 10.0f;  /* default, call MQ2_Calibrate() after warm-up */
}

float MQ2_Calibrate(void)
{
    uint32_t sum = 0;
    uint8_t i;
    float rs_avg;

    /* Take 50 samples for stable calibration */
    for (i = 0; i < 50; i++)
    {
        sum += MQ2_ReadADC_Avg();
        HAL_Delay(20);
    }

    rs_avg = MQ2_CalcRs((uint16_t)(sum / 50));
    s_ro = rs_avg / MQ2_RO_CLEAN_AIR_FACTOR;

    if (s_ro < 0.1f) s_ro = 0.1f;  /* safety clamp */
    return s_ro;
}

uint16_t MQ2_ReadRaw(void)
{
    return MQ2_ReadADC_Avg();
}

float MQ2_ReadVoltage(void)
{
    return (float)MQ2_ReadADC_Avg() * 3.3f / 4095.0f;
}

float MQ2_GetRsRoRatio(void)
{
    float rs = MQ2_CalcRs(MQ2_ReadADC_Avg());
    return rs / s_ro;
}

float MQ2_ReadPPM(void)
{
    float ratio = MQ2_GetRsRoRatio();

    /* Simplified power-law for smoke from MQ-2 datasheet curve:
     * log(PPM) = log(a) + b * log(Rs/Ro)
     * For smoke: a ≈ 3616.4, b ≈ -2.675
     * PPM = 3616.4 * (Rs/Ro) ^ (-2.675) */
    if (ratio < 0.01f) ratio = 0.01f;

    float ppm = 3616.4f * powf(ratio, -2.675f);

    if (ppm < 0.0f) ppm = 0.0f;
    if (ppm > 10000.0f) ppm = 10000.0f;
    return ppm;
}
