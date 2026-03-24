from __future__ import annotations

import re
from typing import Callable, Dict, Iterable, List, Tuple

from .catalog import ChipDefinition
from .family_support import get_family_support
from .planner import PlanResult


I2C_REMAP_MACROS = {
    "I2C1_REMAP": "__HAL_AFIO_REMAP_I2C1_ENABLE();",
}

UART_REMAP_MACROS = {
    "USART1_REMAP": "__HAL_AFIO_REMAP_USART1_ENABLE();",
}

def _pin_parts(pin: str) -> Tuple[str, str]:
    match = re.fullmatch(r"P([A-Z])(\d+)", pin)
    if not match:
        return "GPIOA", "GPIO_PIN_0"
    port = f"GPIO{match.group(1)}"
    number = f"GPIO_PIN_{match.group(2)}"
    return port, number

def _pin_number(pin: str) -> int:
    return int(re.fullmatch(r"P[A-Z](\d+)", pin).group(1))


def _render_with_family_backend(
    family: str,
    renderers: Dict[str, Callable[..., List[str]]],
    *args: object,
) -> List[str]:
    support = get_family_support(family)
    renderer = renderers.get(support.family)
    if renderer is None:
        available = ", ".join(sorted(renderers)) or "none"
        raise KeyError(
            f"No HAL renderer backend registered for family {support.family}. "
            f"Available backends: {available}"
        )
    return renderer(*args)


def _render_system_clock_config(chip: ChipDefinition, plan: PlanResult | None = None) -> List[str]:
    clock_plan = _clock_plan_from_plan(plan)
    configured = clock_plan.get("system_clock_config", [])
    if isinstance(configured, list):
        lines = [str(item) for item in configured if str(item).strip() or item == ""]
        if lines:
            return lines
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_system_clock_config_f1,
            "STM32G4": _render_system_clock_config_g4,
        },
    )


def _render_system_clock_config_f1() -> List[str]:
    return [
        "    RCC_OscInitTypeDef RCC_OscInitStruct = {0};",
        "    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};",
        "",
        "    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;",
        "    RCC_OscInitStruct.HSIState = RCC_HSI_ON;",
        "    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;",
        "    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;",
        "    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {",
        "        Error_Handler();",
        "    }",
        "",
        "    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK",
        "                                 | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;",
        "    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;",
        "    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;",
        "    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;",
        "    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;",
        "    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK) {",
        "        Error_Handler();",
        "    }",
    ]


def _render_system_clock_config_g4() -> List[str]:
    return [
        "    RCC_OscInitTypeDef RCC_OscInitStruct = {0};",
        "    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};",
        "",
        "    if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK) {",
        "        Error_Handler();",
        "    }",
        "",
        "    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;",
        "    RCC_OscInitStruct.HSIState = RCC_HSI_ON;",
        "    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;",
        "    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;",
        "    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;",
        "    RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV2;",
        "    RCC_OscInitStruct.PLL.PLLN = 20;",
        "    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;",
        "    RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;",
        "    RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;",
        "    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {",
        "        Error_Handler();",
        "    }",
        "",
        "    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1;",
        "    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;",
        "    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;",
        "    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;",
        "    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_3) != HAL_OK) {",
        "        Error_Handler();",
        "    }",
    ]


def _clock_plan_from_plan(plan: PlanResult | None) -> Dict[str, object]:
    if plan is None:
        return {}
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    constraints = project_ir.get("constraints", {}) if isinstance(project_ir, dict) else {}
    clock_plan = constraints.get("clock_plan", {}) if isinstance(constraints, dict) else {}
    return clock_plan if isinstance(clock_plan, dict) else {}

def _render_mx_gpio_init_body(direct_gpios: List[Dict[str, str]]) -> List[str]:
    lines = [
        "void MX_GPIO_Init(void)",
        "{",
    ]
    if direct_gpios:
        lines.extend(
            [
                "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
                "",
            ]
        )
    else:
        lines.append("")

    clock_lines = []
    for port in sorted({item["port"] for item in direct_gpios}, key=_port_sort_key):
        clock_lines.append(f"    {_gpio_clock_enable(port)}")
    if not clock_lines:
        clock_lines.append("    /* No direct GPIO-only signals were requested by the planner. */")
    lines.extend(clock_lines)
    lines.append("")

    for item in direct_gpios:
        if item["mode"] in {"GPIO_MODE_OUTPUT_PP", "GPIO_MODE_OUTPUT_OD"}:
            lines.append(f"    HAL_GPIO_WritePin({item['port']}, {item['pin_macro']}, GPIO_PIN_RESET);")
    if direct_gpios:
        lines.append("")

    for item in direct_gpios:
        lines.append(f"    /* {item['module']}.{item['signal']} -> {item['pin']} */")
        lines.append(f"    GPIO_InitStruct.Pin = {item['pin_macro']};")
        lines.append(f"    GPIO_InitStruct.Mode = {item['mode']};")
        lines.append(f"    GPIO_InitStruct.Pull = {item['pull']};")
        if item["speed"]:
            lines.append(f"    GPIO_InitStruct.Speed = {item['speed']};")
        lines.append(f"    HAL_GPIO_Init({item['port']}, &GPIO_InitStruct);")
        lines.append("")

    lines.append("}")
    lines.append("")
    return lines

def _render_i2c_init_f1(bus: Dict[str, object]) -> List[str]:
    instance = str(bus["instance"])
    handle = str(bus["handle"])
    return [
        f"void MX_{instance}_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.ClockSpeed = 100000;",
        f"    {handle}.Init.DutyCycle = I2C_DUTYCYCLE_2;",
        f"    {handle}.Init.OwnAddress1 = 0;",
        f"    {handle}.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;",
        f"    {handle}.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;",
        f"    {handle}.Init.OwnAddress2 = 0;",
        f"    {handle}.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;",
        f"    {handle}.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;",
        f"    if (HAL_I2C_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]

def _render_i2c_init_v2(bus: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_i2c_init_f1,
            "STM32G4": _render_i2c_init_g4,
        },
        bus,
    )


def _render_i2c_init_g4(bus: Dict[str, object]) -> List[str]:
    instance = str(bus["instance"])
    handle = str(bus["handle"])
    return [
        f"void MX_{instance}_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.Timing = 0x00303D5B;",
        f"    {handle}.Init.OwnAddress1 = 0;",
        f"    {handle}.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;",
        f"    {handle}.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;",
        f"    {handle}.Init.OwnAddress2 = 0;",
        f"    {handle}.Init.OwnAddress2Masks = I2C_OA2_NOMASK;",
        f"    {handle}.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;",
        f"    {handle}.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;",
        f"    if (HAL_I2C_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        f"    if (HAL_I2CEx_ConfigAnalogFilter(&{handle}, I2C_ANALOGFILTER_ENABLE) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        f"    if (HAL_I2CEx_ConfigDigitalFilter(&{handle}, 0) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]

def _render_uart_init_f1(uart: Dict[str, object]) -> List[str]:
    instance = str(uart["instance"])
    handle = str(uart["handle"])
    return [
        f"void MX_{instance}_UART_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.BaudRate = 115200;",
        f"    {handle}.Init.WordLength = UART_WORDLENGTH_8B;",
        f"    {handle}.Init.StopBits = UART_STOPBITS_1;",
        f"    {handle}.Init.Parity = UART_PARITY_NONE;",
        f"    {handle}.Init.Mode = UART_MODE_TX_RX;",
        f"    {handle}.Init.HwFlowCtl = UART_HWCONTROL_NONE;",
        f"    {handle}.Init.OverSampling = UART_OVERSAMPLING_16;",
        f"    if (HAL_UART_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]

def _render_uart_init_v2(uart: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_uart_init_f1,
            "STM32G4": _render_uart_init_g4,
        },
        uart,
    )


def _render_uart_init_g4(uart: Dict[str, object]) -> List[str]:
    instance = str(uart["instance"])
    handle = str(uart["handle"])
    return [
        f"void MX_{instance}_UART_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.BaudRate = 115200;",
        f"    {handle}.Init.WordLength = UART_WORDLENGTH_8B;",
        f"    {handle}.Init.StopBits = UART_STOPBITS_1;",
        f"    {handle}.Init.Parity = UART_PARITY_NONE;",
        f"    {handle}.Init.Mode = UART_MODE_TX_RX;",
        f"    {handle}.Init.HwFlowCtl = UART_HWCONTROL_NONE;",
        f"    {handle}.Init.OverSampling = UART_OVERSAMPLING_16;",
        f"    {handle}.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;",
        f"    {handle}.Init.ClockPrescaler = UART_PRESCALER_DIV1;",
        f"    {handle}.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;",
        f"    if (HAL_UART_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        f"    if (HAL_UARTEx_SetTxFifoThreshold(&{handle}, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        f"    if (HAL_UARTEx_SetRxFifoThreshold(&{handle}, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        f"    if (HAL_UARTEx_DisableFifoMode(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]


def _render_spi_init_v2(spi: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_spi_init_f1,
            "STM32G4": _render_spi_init_g4,
        },
        spi,
    )


def _render_spi_init_g4(spi: Dict[str, object]) -> List[str]:
    instance = str(spi["instance"])
    handle = str(spi["handle"])
    return [
        f"void MX_{instance}_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.Mode = SPI_MODE_MASTER;",
        f"    {handle}.Init.Direction = SPI_DIRECTION_2LINES;",
        f"    {handle}.Init.DataSize = SPI_DATASIZE_8BIT;",
        f"    {handle}.Init.CLKPolarity = SPI_POLARITY_LOW;",
        f"    {handle}.Init.CLKPhase = SPI_PHASE_1EDGE;",
        f"    {handle}.Init.NSS = SPI_NSS_SOFT;",
        f"    {handle}.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_16;",
        f"    {handle}.Init.FirstBit = SPI_FIRSTBIT_MSB;",
        f"    {handle}.Init.TIMode = SPI_TIMODE_DISABLE;",
        f"    {handle}.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;",
        f"    {handle}.Init.CRCPolynomial = 7;",
        f"    {handle}.Init.CRCLength = SPI_CRC_LENGTH_DATASIZE;",
        f"    {handle}.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;",
        f"    if (HAL_SPI_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]


def _render_spi_init_f1(spi: Dict[str, object]) -> List[str]:
    instance = str(spi["instance"])
    handle = str(spi["handle"])
    return [
        f"void MX_{instance}_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.Mode = SPI_MODE_MASTER;",
        f"    {handle}.Init.Direction = SPI_DIRECTION_2LINES;",
        f"    {handle}.Init.DataSize = SPI_DATASIZE_8BIT;",
        f"    {handle}.Init.CLKPolarity = SPI_POLARITY_LOW;",
        f"    {handle}.Init.CLKPhase = SPI_PHASE_1EDGE;",
        f"    {handle}.Init.NSS = SPI_NSS_SOFT;",
        f"    {handle}.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_16;",
        f"    {handle}.Init.FirstBit = SPI_FIRSTBIT_MSB;",
        f"    {handle}.Init.TIMode = SPI_TIMODE_DISABLE;",
        f"    {handle}.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;",
        f"    {handle}.Init.CRCPolynomial = 7;",
        f"    if (HAL_SPI_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]


def _render_adc_init_v2(adc: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_adc_init_f1,
            "STM32G4": _render_adc_init_g4,
        },
        adc,
    )


def _render_adc_init_g4(adc: Dict[str, object]) -> List[str]:
    instance = str(adc["instance"])
    handle = str(adc["handle"])
    channels = list(adc.get("channels", []))
    if not channels:
        return []
    scan_mode = "ADC_SCAN_ENABLE" if len(channels) > 1 else "ADC_SCAN_DISABLE"
    eoc_selection = "ADC_EOC_SEQ_CONV" if len(channels) > 1 else "ADC_EOC_SINGLE_CONV"
    lines = [
        f"void MX_{instance}_Init(void)",
        "{",
        "    ADC_ChannelConfTypeDef sConfig = {0};",
        "",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;",
        f"    {handle}.Init.Resolution = ADC_RESOLUTION_12B;",
        f"    {handle}.Init.DataAlign = ADC_DATAALIGN_RIGHT;",
        f"    {handle}.Init.GainCompensation = 0;",
        f"    {handle}.Init.ScanConvMode = {scan_mode};",
        f"    {handle}.Init.EOCSelection = {eoc_selection};",
        f"    {handle}.Init.LowPowerAutoWait = DISABLE;",
        f"    {handle}.Init.ContinuousConvMode = DISABLE;",
        f"    {handle}.Init.NbrOfConversion = {len(channels)};",
        f"    {handle}.Init.DiscontinuousConvMode = DISABLE;",
        f"    {handle}.Init.ExternalTrigConv = ADC_SOFTWARE_START;",
        f"    {handle}.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;",
        f"    {handle}.Init.DMAContinuousRequests = DISABLE;",
        f"    {handle}.Init.Overrun = ADC_OVR_DATA_PRESERVED;",
        f"    {handle}.Init.OversamplingMode = DISABLE;",
        f"    if (HAL_ADC_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "",
    ]
    for channel in channels:
        lines.extend(
            [
                f"    sConfig.Channel = {channel['channel']};",
                f"    sConfig.Rank = {channel['rank_macro']};",
                "    sConfig.SamplingTime = ADC_SAMPLETIME_640CYCLES_5;",
                "    sConfig.SingleDiff = ADC_SINGLE_ENDED;",
                "    sConfig.OffsetNumber = ADC_OFFSET_NONE;",
                "    sConfig.Offset = 0;",
                f"    if (HAL_ADC_ConfigChannel(&{handle}, &sConfig) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                "",
            ]
        )
    lines.extend(["}", ""])
    return lines


def _render_adc_init_f1(adc: Dict[str, object]) -> List[str]:
    instance = str(adc["instance"])
    handle = str(adc["handle"])
    channels = list(adc.get("channels", []))
    if not channels:
        return []
    scan_mode = "ADC_SCAN_ENABLE" if len(channels) > 1 else "ADC_SCAN_DISABLE"
    lines = [
        f"void MX_{instance}_Init(void)",
        "{",
        "    ADC_ChannelConfTypeDef sConfig = {0};",
        "",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.DataAlign = ADC_DATAALIGN_RIGHT;",
        f"    {handle}.Init.ScanConvMode = {scan_mode};",
        f"    {handle}.Init.ContinuousConvMode = DISABLE;",
        f"    {handle}.Init.NbrOfConversion = {len(channels)};",
        f"    {handle}.Init.DiscontinuousConvMode = DISABLE;",
        f"    {handle}.Init.NbrOfDiscConversion = 1;",
        f"    {handle}.Init.ExternalTrigConv = ADC_SOFTWARE_START;",
        f"    if (HAL_ADC_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "",
    ]
    for channel in channels:
        lines.extend(
            [
                f"    sConfig.Channel = {channel['channel']};",
                f"    sConfig.Rank = {channel['rank_macro']};",
                "    sConfig.SamplingTime = ADC_SAMPLETIME_41CYCLES_5;",
                f"    if (HAL_ADC_ConfigChannel(&{handle}, &sConfig) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                "",
            ]
        )
    lines.extend(["}", ""])
    return lines


def _render_tim_oc_init_v2(timer: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_tim_oc_init_f1,
            "STM32G4": _render_tim_oc_init_g4,
        },
        timer,
    )


def _render_tim_oc_init_g4(timer: Dict[str, object]) -> List[str]:
    timer_name = str(timer["timer"])
    handle = str(timer["handle"])
    channels = list(timer.get("channels", []))
    lines = [
        f"void MX_{timer_name}_OC_Init(void)",
        "{",
        "    TIM_OC_InitTypeDef sConfigOC = {0};",
        "",
        f"    {handle}.Instance = {timer_name};",
        f"    {handle}.Init.Prescaler = 79;",
        f"    {handle}.Init.CounterMode = TIM_COUNTERMODE_UP;",
        f"    {handle}.Init.Period = 999;",
        f"    {handle}.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;",
        f"    {handle}.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;",
        f"    if (HAL_TIM_OC_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "",
        "    sConfigOC.OCMode = TIM_OCMODE_TOGGLE;",
        "    sConfigOC.Pulse = 0;",
        "    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;",
        "    sConfigOC.OCNPolarity = TIM_OCNPOLARITY_HIGH;",
        "    sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;",
        "    sConfigOC.OCIdleState = TIM_OCIDLESTATE_RESET;",
        "    sConfigOC.OCNIdleState = TIM_OCNIDLESTATE_RESET;",
    ]
    for channel in channels:
        lines.extend(
            [
                f"    if (HAL_TIM_OC_ConfigChannel(&{handle}, &sConfigOC, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                f"    if (HAL_TIM_OC_Start(&{handle}, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
            ]
        )
    lines.extend(["}", ""])
    return lines


def _render_tim_oc_init_f1(timer: Dict[str, object]) -> List[str]:
    timer_name = str(timer["timer"])
    handle = str(timer["handle"])
    channels = list(timer.get("channels", []))
    lines = [
        f"void MX_{timer_name}_OC_Init(void)",
        "{",
        "    TIM_OC_InitTypeDef sConfigOC = {0};",
        "",
        f"    {handle}.Instance = {timer_name};",
        f"    {handle}.Init.Prescaler = 71;",
        f"    {handle}.Init.CounterMode = TIM_COUNTERMODE_UP;",
        f"    {handle}.Init.Period = 999;",
        f"    {handle}.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;",
        f"    {handle}.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;",
        f"    if (HAL_TIM_OC_Init(&{handle}) != HAL_OK) {{",
            "        Error_Handler();",
            "    }",
            "",
            "    sConfigOC.OCMode = TIM_OCMODE_TOGGLE;",
            "    sConfigOC.Pulse = 0;",
            "    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;",
            "    sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;",
        ]
    for channel in channels:
        lines.extend(
            [
                f"    if (HAL_TIM_OC_ConfigChannel(&{handle}, &sConfigOC, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                f"    if (HAL_TIM_OC_Start(&{handle}, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
            ]
        )
    lines.extend(["}", ""])
    return lines


def _render_tim_encoder_init_v2(timer: Dict[str, object], chip: ChipDefinition) -> List[str]:
    timer_name = str(timer["timer"])
    handle = str(timer["handle"])
    lines = [
        f"void MX_{timer_name}_Encoder_Init(void)",
        "{",
        "    TIM_Encoder_InitTypeDef sConfig = {0};",
        "",
        f"    {handle}.Instance = {timer_name};",
        f"    {handle}.Init.Prescaler = 0;",
        f"    {handle}.Init.CounterMode = TIM_COUNTERMODE_UP;",
        f"    {handle}.Init.Period = 0xFFFF;",
        f"    {handle}.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;",
        f"    {handle}.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;",
        "    sConfig.EncoderMode = TIM_ENCODERMODE_TI12;",
        "    sConfig.IC1Polarity = TIM_ICPOLARITY_RISING;",
        "    sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;",
        "    sConfig.IC1Prescaler = TIM_ICPSC_DIV1;",
        "    sConfig.IC1Filter = 0;",
        "    sConfig.IC2Polarity = TIM_ICPOLARITY_RISING;",
        "    sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;",
        "    sConfig.IC2Prescaler = TIM_ICPSC_DIV1;",
        "    sConfig.IC2Filter = 0;",
        f"    if (HAL_TIM_Encoder_Init(&{handle}, &sConfig) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        f"    if (HAL_TIM_Encoder_Start(&{handle}, TIM_CHANNEL_ALL) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]
    return lines


def _render_dac_init_v2(dac: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_dac_init_f1,
            "STM32G4": _render_dac_init_g4,
        },
        dac,
    )


def _render_dac_init_g4(dac: Dict[str, object]) -> List[str]:
    dac_name = str(dac["dac"])
    handle = str(dac["handle"])
    channels = list(dac.get("channels", []))
    lines = [
        f"void MX_{dac_name}_Init(void)",
        "{",
        "    DAC_ChannelConfTypeDef sConfig = {0};",
        "",
        f"    {handle}.Instance = {dac_name};",
        f"    if (HAL_DAC_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "",
    ]
    for channel in channels:
        lines.extend(
            [
                "    sConfig.DAC_Trigger = DAC_TRIGGER_NONE;",
                "    sConfig.DAC_OutputBuffer = DAC_OUTPUTBUFFER_ENABLE;",
                "    sConfig.DAC_ConnectOnChipPeripheral = DAC_CHIPCONNECT_DISABLE;",
                "    sConfig.DAC_UserTrimming = DAC_TRIMMING_FACTORY;",
            ]
        )
        lines.extend(
            [
                f"    if (HAL_DAC_ConfigChannel(&{handle}, &sConfig, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                f"    if (HAL_DAC_Start(&{handle}, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                "",
            ]
        )
    lines.extend(["}", ""])
    return lines


def _render_dac_init_f1(dac: Dict[str, object]) -> List[str]:
    dac_name = str(dac["dac"])
    handle = str(dac["handle"])
    channels = list(dac.get("channels", []))
    lines = [
        f"void MX_{dac_name}_Init(void)",
        "{",
        "    DAC_ChannelConfTypeDef sConfig = {0};",
        "",
        f"    {handle}.Instance = {dac_name};",
        f"    if (HAL_DAC_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "",
    ]
    for channel in channels:
        lines.extend(
            [
                "    sConfig.DAC_Trigger = DAC_TRIGGER_NONE;",
                "    sConfig.DAC_OutputBuffer = DAC_OUTPUTBUFFER_ENABLE;",
            ]
        )
        lines.extend(
            [
                f"    if (HAL_DAC_ConfigChannel(&{handle}, &sConfig, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                f"    if (HAL_DAC_Start(&{handle}, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                "",
            ]
        )
    lines.extend(["}", ""])
    return lines


def _render_can_init_v2(can: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_can_init_f1,
            "STM32G4": _render_can_init_g4,
        },
        can,
    )


def _render_can_init_g4(can: Dict[str, object]) -> List[str]:
    instance = str(can["instance"])
    handle = str(can["handle"])
    return [
        f"void MX_{instance}_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.FrameFormat = FDCAN_FRAME_CLASSIC;",
        f"    {handle}.Init.Mode = FDCAN_MODE_NORMAL;",
        f"    {handle}.Init.AutoRetransmission = ENABLE;",
        f"    {handle}.Init.TransmitPause = DISABLE;",
        f"    {handle}.Init.ProtocolException = DISABLE;",
        f"    {handle}.Init.NominalPrescaler = 8;",
        f"    {handle}.Init.NominalSyncJumpWidth = 1;",
        f"    {handle}.Init.NominalTimeSeg1 = 13;",
        f"    {handle}.Init.NominalTimeSeg2 = 2;",
        f"    {handle}.Init.DataPrescaler = 8;",
        f"    {handle}.Init.DataSyncJumpWidth = 1;",
        f"    {handle}.Init.DataTimeSeg1 = 1;",
        f"    {handle}.Init.DataTimeSeg2 = 1;",
        f"    {handle}.Init.StdFiltersNbr = 0;",
        f"    {handle}.Init.ExtFiltersNbr = 0;",
        f"    {handle}.Init.TxFifoQueueMode = FDCAN_TX_FIFO_OPERATION;",
        f"    if (HAL_FDCAN_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]


def _render_can_init_f1(can: Dict[str, object]) -> List[str]:
    instance = str(can["instance"])
    handle = str(can["handle"])
    return [
        f"void MX_{instance}_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.Prescaler = 16;",
        f"    {handle}.Init.Mode = CAN_MODE_NORMAL;",
        f"    {handle}.Init.SyncJumpWidth = CAN_SJW_1TQ;",
        f"    {handle}.Init.TimeSeg1 = CAN_BS1_1TQ;",
        f"    {handle}.Init.TimeSeg2 = CAN_BS2_1TQ;",
        f"    {handle}.Init.TimeTriggeredMode = DISABLE;",
        f"    {handle}.Init.AutoBusOff = DISABLE;",
        f"    {handle}.Init.AutoWakeUp = DISABLE;",
        f"    {handle}.Init.AutoRetransmission = ENABLE;",
        f"    {handle}.Init.ReceiveFifoLocked = DISABLE;",
        f"    {handle}.Init.TransmitFifoPriority = DISABLE;",
        f"    if (HAL_CAN_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]


def _render_usb_pcd_init_v2(usb: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_usb_pcd_init_f1,
            "STM32G4": _render_usb_pcd_init_g4,
        },
        usb,
    )


def _render_usb_pcd_init_f1(usb: Dict[str, object]) -> List[str]:
    instance = str(usb["instance"])
    handle = str(usb["handle"])
    return [
        f"void MX_{instance}_Init(void)",
        "{",
        f"    {handle}.Instance = USB;",
        f"    {handle}.Init.dev_endpoints = 8;",
        f"    {handle}.Init.speed = PCD_SPEED_FULL;",
        f"    {handle}.Init.phy_itface = PCD_PHY_EMBEDDED;",
        f"    {handle}.Init.Sof_enable = DISABLE;",
        f"    {handle}.Init.low_power_enable = DISABLE;",
        f"    {handle}.Init.lpm_enable = DISABLE;",
        f"    {handle}.Init.battery_charging_enable = DISABLE;",
        f"    if (HAL_PCD_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]


def _render_usb_pcd_init_g4(usb: Dict[str, object]) -> List[str]:
    instance = str(usb["instance"])
    handle = str(usb["handle"])
    return [
        f"void MX_{instance}_Init(void)",
        "{",
        f"    {handle}.Instance = {instance};",
        f"    {handle}.Init.dev_endpoints = 8;",
        f"    {handle}.Init.speed = PCD_SPEED_FULL;",
        f"    {handle}.Init.phy_itface = PCD_PHY_EMBEDDED;",
        f"    {handle}.Init.Sof_enable = DISABLE;",
        f"    {handle}.Init.low_power_enable = DISABLE;",
        f"    {handle}.Init.lpm_enable = DISABLE;",
        f"    {handle}.Init.battery_charging_enable = DISABLE;",
        f"    if (HAL_PCD_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "}",
        "",
    ]


def _render_tim_ic_init_v2(timer: Dict[str, object], chip: ChipDefinition) -> List[str]:
    timer_name = str(timer["timer"])
    handle = str(timer["handle"])
    channels = list(timer.get("channels", []))
    lines = [
        f"void MX_{timer_name}_IC_Init(void)",
        "{",
        "    TIM_IC_InitTypeDef sConfigIC = {0};",
        "",
        f"    {handle}.Instance = {timer_name};",
        f"    {handle}.Init.Prescaler = 0;",
        f"    {handle}.Init.CounterMode = TIM_COUNTERMODE_UP;",
        f"    {handle}.Init.Period = 0xFFFF;",
        f"    {handle}.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;",
        f"    {handle}.Init.RepetitionCounter = 0;",
        f"    {handle}.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;",
        f"    if (HAL_TIM_IC_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "",
        "    sConfigIC.ICPolarity = TIM_ICPOLARITY_RISING;",
        "    sConfigIC.ICSelection = TIM_ICSELECTION_DIRECTTI;",
        "    sConfigIC.ICPrescaler = TIM_ICPSC_DIV1;",
        "    sConfigIC.ICFilter = 0;",
    ]
    for channel in channels:
        lines.extend(
            [
                f"    if (HAL_TIM_IC_ConfigChannel(&{handle}, &sConfigIC, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                f"    if (HAL_TIM_IC_Start_IT(&{handle}, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
                "",
            ]
        )
    lines.extend(["}", ""])
    return lines

def _render_tim_init(timer: Dict[str, object]) -> List[str]:
    timer_name = str(timer["timer"])
    handle = str(timer["handle"])
    pwm_profile = str(timer.get("pwm_profile", "default"))
    prescaler = 71
    period = 999
    default_pulse = 0
    if pwm_profile == "servo_50hz":
        period = 19999
        default_pulse = 1500
    elif pwm_profile == "motor_pwm":
        prescaler = 35
        period = 999
        default_pulse = 0
    lines = [
        f"void MX_{timer_name}_Init(void)",
        "{",
        "    TIM_OC_InitTypeDef sConfigOC = {0};",
        "",
        f"    {handle}.Instance = {timer_name};",
        f"    {handle}.Init.Prescaler = {prescaler};",
        f"    {handle}.Init.CounterMode = TIM_COUNTERMODE_UP;",
        f"    {handle}.Init.Period = {period};",
        f"    {handle}.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;",
        f"    {handle}.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;",
        f"    if (HAL_TIM_PWM_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "",
        "    sConfigOC.OCMode = TIM_OCMODE_PWM1;",
        f"    sConfigOC.Pulse = {default_pulse};",
        "    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;",
        "    sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;",
    ]
    for channel in timer["channels"]:
        lines.extend(
            [
                f"    if (HAL_TIM_PWM_ConfigChannel(&{handle}, &sConfigOC, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
            ]
        )
    lines.extend(
        [
            "}",
            "",
        ]
    )
    return lines

def _render_tim_init_v2(timer: Dict[str, object], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_tim_init_f1,
            "STM32G4": _render_tim_init_g4,
        },
        timer,
        chip,
    )


def _render_tim_init_f1(timer: Dict[str, object], _chip: ChipDefinition) -> List[str]:
    return _render_tim_init(timer)


def _render_tim_init_g4(timer: Dict[str, object], chip: ChipDefinition) -> List[str]:
    support = get_family_support(chip.family)
    timer_name = str(timer["timer"])
    handle = str(timer["handle"])
    pwm_profile = str(timer.get("pwm_profile", "default"))
    prescaler, period, default_pulse = _timer_profile_settings_v2(pwm_profile, support.family)

    lines = [
        f"void MX_{timer_name}_Init(void)",
        "{",
        "    TIM_OC_InitTypeDef sConfigOC = {0};",
        "",
        f"    {handle}.Instance = {timer_name};",
        f"    {handle}.Init.Prescaler = {prescaler};",
        f"    {handle}.Init.CounterMode = TIM_COUNTERMODE_UP;",
        f"    {handle}.Init.Period = {period};",
        f"    {handle}.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;",
        f"    {handle}.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;",
        f"    if (HAL_TIM_PWM_Init(&{handle}) != HAL_OK) {{",
        "        Error_Handler();",
        "    }",
        "",
        "    sConfigOC.OCMode = TIM_OCMODE_PWM1;",
        f"    sConfigOC.Pulse = {default_pulse};",
        "    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;",
        "    sConfigOC.OCNPolarity = TIM_OCNPOLARITY_HIGH;",
        "    sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;",
        "    sConfigOC.OCIdleState = TIM_OCIDLESTATE_RESET;",
        "    sConfigOC.OCNIdleState = TIM_OCNIDLESTATE_RESET;",
    ]
    for channel in timer["channels"]:
        lines.extend(
            [
                f"    if (HAL_TIM_PWM_ConfigChannel(&{handle}, &sConfigOC, {channel['channel_macro']}) != HAL_OK) {{",
                "        Error_Handler();",
                "    }",
            ]
        )
    lines.extend(
        [
            f"    HAL_TIM_MspPostInit(&{handle});",
            "}",
            "",
        ]
    )
    return lines

def _render_hal_i2c_msp_init(
    i2c_buses: List[Dict[str, object]],
    dma_allocations: List[Dict[str, object]] | None = None,
) -> List[str]:
    lines = [
        "void HAL_I2C_MspInit(I2C_HandleTypeDef* hi2c)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, bus in enumerate(i2c_buses):
        instance = str(bus["instance"])
        pins = dict(bus["pins"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (hi2c->Instance == {instance}) {{")
        for port in sorted({_pin_parts(pin)[0] for pin in pins.values()}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        remap_macro = I2C_REMAP_MACROS.get(str(bus["option_id"]))
        if remap_macro:
            lines.append(f"        {remap_macro}")
        pin_expr = " | ".join(_pin_parts(pin)[1] for pin in pins.values())
        port = _pin_parts(next(iter(pins.values())))[0]
        lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
        lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;")
        lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
        lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
        lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        lines.extend(_render_dma_setup_lines(_dma_allocations_for_parent(dma_allocations, "i2c", instance), "hi2c", chip_family="STM32F1"))
        lines.append("    }")
    lines.extend(["}", ""])
    lines.extend(_render_hal_i2c_msp_deinit(i2c_buses, dma_allocations=dma_allocations))
    return lines

def _render_hal_i2c_msp_init_v2(
    i2c_buses: List[Dict[str, object]],
    chip: ChipDefinition,
    dma_allocations: List[Dict[str, object]] | None = None,
) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_i2c_msp_init,
            "STM32G4": _render_hal_i2c_msp_init_g4,
        },
        i2c_buses,
        dma_allocations,
    )


def _render_hal_i2c_msp_init_g4(
    i2c_buses: List[Dict[str, object]],
    dma_allocations: List[Dict[str, object]] | None = None,
) -> List[str]:
    support = get_family_support("STM32G4")
    lines = [
        "void HAL_I2C_MspInit(I2C_HandleTypeDef* hi2c)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, bus in enumerate(i2c_buses):
        instance = str(bus["instance"])
        pins = dict(bus["pins"])
        prefix = "if" if index == 0 else "else if"
        port = _pin_parts(next(iter(pins.values())))[0]
        pin_expr = " | ".join(_pin_parts(pin)[1] for pin in pins.values())
        af_macro = _g4_i2c_af_macro(instance)
        lines.append(f"    {prefix} (hi2c->Instance == {instance}) {{")
        for gpio_port in sorted({_pin_parts(pin)[0] for pin in pins.values()}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(gpio_port)}")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
        lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;")
        lines.append("        GPIO_InitStruct.Pull = GPIO_PULLUP;")
        lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;")
        lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
        lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.extend(_render_dma_setup_lines(_dma_allocations_for_parent(dma_allocations, "i2c", instance), "hi2c", chip_family=support.family))
        lines.append("    }")
    lines.extend(["}", ""])
    lines.extend(_render_hal_i2c_msp_deinit(i2c_buses, dma_allocations=dma_allocations))
    return lines


def _render_hal_i2c_msp_deinit(
    i2c_buses: List[Dict[str, object]],
    dma_allocations: List[Dict[str, object]] | None = None,
) -> List[str]:
    lines = [
        "void HAL_I2C_MspDeInit(I2C_HandleTypeDef* hi2c)",
        "{",
    ]
    for index, bus in enumerate(i2c_buses):
        instance = str(bus["instance"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (hi2c->Instance == {instance}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(bus["pins"].values()):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.extend(_render_dma_cleanup_lines(_dma_allocations_for_parent(dma_allocations, "i2c", instance), "hi2c"))
        lines.append(f"        __HAL_RCC_{instance}_CLK_DISABLE();")
        lines.append("    }")
    lines.extend(["}", ""])
    return lines

def _render_hal_uart_msp_init(
    uart_ports: List[Dict[str, object]],
    dma_allocations: List[Dict[str, object]] | None = None,
) -> List[str]:
    lines = [
        "void HAL_UART_MspInit(UART_HandleTypeDef* huart)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, uart in enumerate(uart_ports):
        instance = str(uart["instance"])
        pins = dict(uart["pins"])
        tx_port, tx_pin = _pin_parts(pins["tx"])
        rx_port, rx_pin = _pin_parts(pins["rx"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (huart->Instance == {instance}) {{")
        for port in sorted({tx_port, rx_port}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        remap_macro = UART_REMAP_MACROS.get(str(uart["option_id"]))
        if remap_macro:
            lines.append(f"        {remap_macro}")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        lines.append(f"        GPIO_InitStruct.Pin = {tx_pin};")
        lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
        lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
        lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
        lines.append(f"        HAL_GPIO_Init({tx_port}, &GPIO_InitStruct);")
        lines.append("")
        lines.append(f"        GPIO_InitStruct.Pin = {rx_pin};")
        lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_INPUT;")
        lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
        lines.append(f"        HAL_GPIO_Init({rx_port}, &GPIO_InitStruct);")
        lines.extend(_render_dma_setup_lines(_dma_allocations_for_parent(dma_allocations, "uart", instance), "huart", chip_family="STM32F1"))
        lines.append("    }")
    lines.extend(["}", ""])
    lines.extend(_render_hal_uart_msp_deinit(uart_ports, dma_allocations=dma_allocations))
    return lines

def _render_hal_uart_msp_init_v2(
    uart_ports: List[Dict[str, object]],
    chip: ChipDefinition,
    dma_allocations: List[Dict[str, object]] | None = None,
) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_uart_msp_init,
            "STM32G4": _render_hal_uart_msp_init_g4,
        },
        uart_ports,
        dma_allocations,
    )


def _render_hal_uart_msp_init_g4(
    uart_ports: List[Dict[str, object]],
    dma_allocations: List[Dict[str, object]] | None = None,
) -> List[str]:
    support = get_family_support("STM32G4")
    lines = [
        "void HAL_UART_MspInit(UART_HandleTypeDef* huart)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, uart in enumerate(uart_ports):
        instance = str(uart["instance"])
        pins = dict(uart["pins"])
        tx_port, tx_pin = _pin_parts(pins["tx"])
        rx_port, rx_pin = _pin_parts(pins["rx"])
        prefix = "if" if index == 0 else "else if"
        af_macro = _g4_uart_af_macro(instance)
        lines.append(f"    {prefix} (huart->Instance == {instance}) {{")
        for port in sorted({tx_port, rx_port}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        lines.append(f"        GPIO_InitStruct.Pin = {tx_pin} | {rx_pin};")
        lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
        lines.append("        GPIO_InitStruct.Pull = GPIO_PULLUP;")
        lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;")
        lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
        lines.append(f"        HAL_GPIO_Init({tx_port}, &GPIO_InitStruct);")
        if tx_port != rx_port:
            lines.append(f"        HAL_GPIO_Init({rx_port}, &GPIO_InitStruct);")
        lines.extend(_render_dma_setup_lines(_dma_allocations_for_parent(dma_allocations, "uart", instance), "huart", chip_family=support.family))
        lines.append("    }")
    lines.extend(["}", ""])
    lines.extend(_render_hal_uart_msp_deinit(uart_ports, dma_allocations=dma_allocations))
    return lines


def _render_hal_uart_msp_deinit(
    uart_ports: List[Dict[str, object]],
    dma_allocations: List[Dict[str, object]] | None = None,
) -> List[str]:
    lines = [
        "void HAL_UART_MspDeInit(UART_HandleTypeDef* huart)",
        "{",
    ]
    for index, uart in enumerate(uart_ports):
        instance = str(uart["instance"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (huart->Instance == {instance}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(dict(uart["pins"]).values()):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.extend(_render_dma_cleanup_lines(_dma_allocations_for_parent(dma_allocations, "uart", instance), "huart"))
        lines.append(f"        HAL_NVIC_DisableIRQ({instance}_IRQn);")
        lines.append(f"        __HAL_RCC_{instance}_CLK_DISABLE();")
        lines.append("    }")
    lines.extend(["}", ""])
    return lines


def _render_hal_adc_msp_init_v2(adc_inputs: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_adc_msp_init_f1,
            "STM32G4": _render_hal_adc_msp_init_g4,
        },
        adc_inputs,
    )


def _render_hal_adc_msp_init_f1(adc_inputs: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_ADC_MspInit(ADC_HandleTypeDef* hadc)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "    RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};",
        "",
        "    PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC;",
        "    PeriphClkInit.AdcClockSelection = RCC_ADCPCLK2_DIV6;",
        "    if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK) {",
        "        Error_Handler();",
        "    }",
        "",
    ]
    for index, adc in enumerate(adc_inputs):
        instance = str(adc["instance"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (hadc->Instance == {instance}) {{")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in adc.get("channels", [])):
            lines.append(f"        {_gpio_clock_enable(port)}")
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_ANALOG;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not adc_inputs:
        lines.append("    (void)hadc;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_adc_msp_deinit(adc_inputs, chip_family="STM32F1"))
    return lines


def _render_hal_adc_msp_init_g4(adc_inputs: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_ADC_MspInit(ADC_HandleTypeDef* hadc)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "    RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};",
        "",
    ]
    for index, adc in enumerate(adc_inputs):
        instance = str(adc["instance"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (hadc->Instance == {instance}) {{")
        lines.append("        PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC12;")
        lines.append("        PeriphClkInit.Adc12ClockSelection = RCC_ADC12CLKSOURCE_SYSCLK;")
        lines.append("        if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK) {")
        lines.append("            Error_Handler();")
        lines.append("        }")
        lines.append("        __HAL_RCC_ADC12_CLK_ENABLE();")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in adc.get("channels", [])):
            lines.append(f"        {_gpio_clock_enable(port)}")
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_ANALOG;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not adc_inputs:
        lines.append("    (void)hadc;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_adc_msp_deinit(adc_inputs, chip_family="STM32G4"))
    return lines


def _render_hal_adc_msp_deinit(
    adc_inputs: List[Dict[str, object]],
    chip_family: str,
) -> List[str]:
    return _render_with_family_backend(
        chip_family,
        {
            "STM32F1": _render_hal_adc_msp_deinit_f1,
            "STM32G4": _render_hal_adc_msp_deinit_g4,
        },
        adc_inputs,
    )


def _render_hal_adc_msp_deinit_f1(adc_inputs: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_ADC_MspDeInit(ADC_HandleTypeDef* hadc)",
        "{",
    ]
    for index, adc in enumerate(adc_inputs):
        instance = str(adc["instance"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (hadc->Instance == {instance}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in adc.get("channels", [])):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append(f"        __HAL_RCC_{instance}_CLK_DISABLE();")
        lines.append("    }")
    if not adc_inputs:
        lines.append("    (void)hadc;")
    lines.extend(["}", ""])
    return lines


def _render_hal_adc_msp_deinit_g4(adc_inputs: List[Dict[str, object]]) -> List[str]:
    unique_instances = {
        str(adc.get("instance", "")).strip().upper()
        for adc in adc_inputs
        if str(adc.get("instance", "")).strip()
    }
    disable_shared_clock = len(unique_instances) <= 1
    lines = [
        "void HAL_ADC_MspDeInit(ADC_HandleTypeDef* hadc)",
        "{",
    ]
    for index, adc in enumerate(adc_inputs):
        instance = str(adc["instance"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (hadc->Instance == {instance}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in adc.get("channels", [])):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        if disable_shared_clock:
            lines.append("        __HAL_RCC_ADC12_CLK_DISABLE();")
        else:
            lines.append("        /* ADC12 clock is shared by multiple planned ADC instances. */")
        lines.append("    }")
    if not adc_inputs:
        lines.append("    (void)hadc;")
    lines.extend(["}", ""])
    return lines


def _render_hal_tim_ic_msp_init_v2(timer_ic_timers: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_tim_ic_msp_init_f1,
            "STM32G4": _render_hal_tim_ic_msp_init_g4,
        },
        timer_ic_timers,
    )


def _render_hal_tim_ic_msp_init_f1(timer_ic_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_IC_MspInit(TIM_HandleTypeDef* htim_ic)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, timer in enumerate(timer_ic_timers):
        timer_name = str(timer["timer"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (htim_ic->Instance == {timer_name}) {{")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_ENABLE();")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in timer.get("channels", [])):
            lines.append(f"        {_gpio_clock_enable(port)}")
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_INPUT;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not timer_ic_timers:
        lines.append("    (void)htim_ic;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_tim_ic_msp_deinit(timer_ic_timers))
    return lines


def _render_hal_tim_ic_msp_init_g4(timer_ic_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_IC_MspInit(TIM_HandleTypeDef* htim_ic)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, timer in enumerate(timer_ic_timers):
        timer_name = str(timer["timer"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (htim_ic->Instance == {timer_name}) {{")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_ENABLE();")
        for port in sorted({_pin_parts(channel['pin'])[0] for channel in timer.get('channels', [])}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        af_macro = _g4_tim_af_macro(timer_name)
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in timer.get("channels", [])):
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;")
            lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not timer_ic_timers:
        lines.append("    (void)htim_ic;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_tim_ic_msp_deinit(timer_ic_timers))
    return lines


def _render_hal_tim_ic_msp_deinit(timer_ic_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_IC_MspDeInit(TIM_HandleTypeDef* htim_ic)",
        "{",
    ]
    for index, timer in enumerate(timer_ic_timers):
        timer_name = str(timer["timer"])
        irq = str(timer.get("irq", "")).strip()
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (htim_ic->Instance == {timer_name}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in timer.get("channels", [])):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        if irq:
            lines.append(f"        HAL_NVIC_DisableIRQ({irq});")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_DISABLE();")
        lines.append("    }")
    if not timer_ic_timers:
        lines.append("    (void)htim_ic;")
    lines.extend(["}", ""])
    return lines

def _render_hal_tim_pwm_msp_init(pwm_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_PWM_MspInit(TIM_HandleTypeDef* htim_pwm)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, timer in enumerate(pwm_timers):
        timer_name = str(timer["timer"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (htim_pwm->Instance == {timer_name}) {{")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_ENABLE();")
        for port in sorted({_pin_parts(channel['pin'])[0] for channel in timer["channels"]}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        for channel in timer["channels"]:
            port, pin_macro = _pin_parts(channel["pin"])
            lines.append(f"        GPIO_InitStruct.Pin = {pin_macro};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
            lines.append("")
        if lines[-1] == "":
            lines.pop()
        lines.append("    }")
    lines.extend(["}", ""])
    lines.extend(_render_hal_tim_pwm_msp_deinit(pwm_timers))
    return lines

def _render_hal_tim_pwm_msp_init_v2(pwm_timers: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_tim_pwm_msp_init,
            "STM32G4": _render_hal_tim_pwm_msp_init_g4,
        },
        pwm_timers,
    )


def _render_hal_tim_pwm_msp_init_g4(pwm_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_PWM_MspInit(TIM_HandleTypeDef* htim_pwm)",
        "{",
    ]
    for index, timer in enumerate(pwm_timers):
        timer_name = str(timer["timer"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (htim_pwm->Instance == {timer_name}) {{")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_ENABLE();")
        lines.append("    }")
    if not pwm_timers:
        lines.append("    (void)htim_pwm;")
    lines.extend(["}", "", "void HAL_TIM_MspPostInit(TIM_HandleTypeDef* htim)", "{", "    GPIO_InitTypeDef GPIO_InitStruct = {0};", ""])
    for index, timer in enumerate(pwm_timers):
        timer_name = str(timer["timer"])
        af_macro = _g4_tim_af_macro(timer_name)
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (htim->Instance == {timer_name}) {{")
        for port in sorted({_pin_parts(channel['pin'])[0] for channel in timer['channels']}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        grouped_by_port: Dict[str, List[str]] = {}
        for channel in timer["channels"]:
            port, pin_macro = _pin_parts(channel["pin"])
            grouped_by_port.setdefault(port, []).append(pin_macro)
        for port in sorted(grouped_by_port, key=_port_sort_key):
            pin_expr = " | ".join(grouped_by_port[port])
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_PULLUP;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;")
            lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
            lines.append("")
        if lines[-1] == "":
            lines.pop()
        lines.append("    }")
    lines.extend(["}", ""])
    lines.extend(_render_hal_tim_pwm_msp_deinit(pwm_timers))
    return lines


def _render_hal_tim_pwm_msp_deinit(pwm_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_PWM_MspDeInit(TIM_HandleTypeDef* htim_pwm)",
        "{",
    ]
    for index, timer in enumerate(pwm_timers):
        timer_name = str(timer["timer"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (htim_pwm->Instance == {timer_name}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in timer["channels"]):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_DISABLE();")
        lines.append("    }")
    lines.extend(["}", ""])
    return lines


def _render_hal_tim_oc_msp_init_v2(timer_oc_timers: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_tim_oc_msp_init_f1,
            "STM32G4": _render_hal_tim_oc_msp_init_g4,
        },
        timer_oc_timers,
    )


def _render_hal_tim_oc_msp_init_g4(timer_oc_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_OC_MspInit(TIM_HandleTypeDef* htim_oc)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, timer in enumerate(timer_oc_timers):
        timer_name = str(timer["timer"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (htim_oc->Instance == {timer_name}) {{")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_ENABLE();")
        for port in sorted({_pin_parts(channel['pin'])[0] for channel in timer['channels']}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        af_macro = _g4_tim_af_macro(timer_name)
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in timer["channels"]):
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_PULLUP;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;")
            lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not timer_oc_timers:
        lines.append("    (void)htim_oc;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_tim_oc_msp_deinit(timer_oc_timers))
    return lines


def _render_hal_tim_oc_msp_init_f1(timer_oc_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_OC_MspInit(TIM_HandleTypeDef* htim_oc)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, timer in enumerate(timer_oc_timers):
        timer_name = str(timer["timer"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (htim_oc->Instance == {timer_name}) {{")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_ENABLE();")
        for port in sorted({_pin_parts(channel['pin'])[0] for channel in timer["channels"]}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in timer["channels"]):
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not timer_oc_timers:
        lines.append("    (void)htim_oc;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_tim_oc_msp_deinit(timer_oc_timers))
    return lines


def _render_hal_tim_oc_msp_deinit(timer_oc_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_OC_MspDeInit(TIM_HandleTypeDef* htim_oc)",
        "{",
    ]
    for index, timer in enumerate(timer_oc_timers):
        timer_name = str(timer["timer"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (htim_oc->Instance == {timer_name}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in timer["channels"]):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_DISABLE();")
        lines.append("    }")
    if not timer_oc_timers:
        lines.append("    (void)htim_oc;")
    lines.extend(["}", ""])
    return lines


def _render_hal_tim_encoder_msp_init_v2(encoder_timers: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_tim_encoder_msp_init_f1,
            "STM32G4": _render_hal_tim_encoder_msp_init_g4,
        },
        encoder_timers,
    )


def _render_hal_tim_encoder_msp_init_g4(encoder_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_Encoder_MspInit(TIM_HandleTypeDef* htim_encoder)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, timer in enumerate(encoder_timers):
        timer_name = str(timer["timer"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (htim_encoder->Instance == {timer_name}) {{")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_ENABLE();")
        for port in sorted({_pin_parts(pin)[0] for pin in dict(timer.get('pins', {})).values()}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        af_macro = _g4_tim_af_macro(timer_name)
        for port, pin_expr in _gpio_pin_exprs_by_port(dict(timer.get("pins", {})).values()):
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;")
            lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not encoder_timers:
        lines.append("    (void)htim_encoder;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_tim_encoder_msp_deinit(encoder_timers))
    return lines


def _render_hal_tim_encoder_msp_init_f1(encoder_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_Encoder_MspInit(TIM_HandleTypeDef* htim_encoder)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, timer in enumerate(encoder_timers):
        timer_name = str(timer["timer"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (htim_encoder->Instance == {timer_name}) {{")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_ENABLE();")
        for port in sorted({_pin_parts(pin)[0] for pin in dict(timer.get('pins', {})).values()}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        for port, pin_expr in _gpio_pin_exprs_by_port(dict(timer.get("pins", {})).values()):
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_INPUT;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not encoder_timers:
        lines.append("    (void)htim_encoder;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_tim_encoder_msp_deinit(encoder_timers))
    return lines


def _render_hal_tim_encoder_msp_deinit(encoder_timers: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_TIM_Encoder_MspDeInit(TIM_HandleTypeDef* htim_encoder)",
        "{",
    ]
    for index, timer in enumerate(encoder_timers):
        timer_name = str(timer["timer"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (htim_encoder->Instance == {timer_name}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(dict(timer.get("pins", {})).values()):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append(f"        __HAL_RCC_{timer_name}_CLK_DISABLE();")
        lines.append("    }")
    if not encoder_timers:
        lines.append("    (void)htim_encoder;")
    lines.extend(["}", ""])
    return lines


def _render_hal_spi_msp_init_v2(spi_buses: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_spi_msp_init_f1,
            "STM32G4": _render_hal_spi_msp_init_g4,
        },
        spi_buses,
    )


def _render_hal_spi_msp_init_f1(spi_buses: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_SPI_MspInit(SPI_HandleTypeDef* hspi)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, spi in enumerate(spi_buses):
        instance = str(spi["instance"])
        pins = dict(spi["pins"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (hspi->Instance == {instance}) {{")
        for port in sorted({_pin_parts(pin)[0] for pin in pins.values()}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        output_pins = [pins[role] for role in ("sck", "mosi", "nss") if role in pins]
        if output_pins:
            for port, pin_expr in _gpio_pin_exprs_by_port(output_pins):
                lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
                lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
                lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
                lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
                lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        if "miso" in pins:
            port, pin_macro = _pin_parts(pins["miso"])
            lines.append(f"        GPIO_InitStruct.Pin = {pin_macro};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_INPUT;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not spi_buses:
        lines.append("    (void)hspi;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_spi_msp_deinit(spi_buses))
    return lines


def _render_hal_spi_msp_init_g4(spi_buses: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_SPI_MspInit(SPI_HandleTypeDef* hspi)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, spi in enumerate(spi_buses):
        instance = str(spi["instance"])
        pins = dict(spi["pins"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (hspi->Instance == {instance}) {{")
        for port in sorted({_pin_parts(pin)[0] for pin in pins.values()}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        af_macro = _g4_spi_af_macro(instance)
        for role in ("sck", "miso", "mosi", "nss"):
            pin = pins.get(role)
            if not pin:
                continue
            port, pin_macro = _pin_parts(pin)
            lines.append(f"        GPIO_InitStruct.Pin = {pin_macro};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;")
            lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not spi_buses:
        lines.append("    (void)hspi;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_spi_msp_deinit(spi_buses))
    return lines


def _render_hal_spi_msp_deinit(spi_buses: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_SPI_MspDeInit(SPI_HandleTypeDef* hspi)",
        "{",
    ]
    for index, spi in enumerate(spi_buses):
        instance = str(spi["instance"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (hspi->Instance == {instance}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(dict(spi["pins"]).values()):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append(f"        __HAL_RCC_{instance}_CLK_DISABLE();")
        lines.append("    }")
    if not spi_buses:
        lines.append("    (void)hspi;")
    lines.extend(["}", ""])
    return lines


def _render_hal_dac_msp_init_v2(dac_units: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_dac_msp_init_f1,
            "STM32G4": _render_hal_dac_msp_init_g4,
        },
        dac_units,
    )


def _render_hal_dac_msp_init_f1(dac_units: List[Dict[str, object]]) -> List[str]:
    return _render_hal_dac_msp_init_common(dac_units)


def _render_hal_dac_msp_init_g4(dac_units: List[Dict[str, object]]) -> List[str]:
    return _render_hal_dac_msp_init_common(dac_units)


def _render_hal_dac_msp_init_common(dac_units: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_DAC_MspInit(DAC_HandleTypeDef* hdac)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, dac in enumerate(dac_units):
        dac_name = str(dac["dac"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (hdac->Instance == {dac_name}) {{")
        lines.append(f"        __HAL_RCC_{dac_name}_CLK_ENABLE();")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in dac.get("channels", [])):
            lines.append(f"        {_gpio_clock_enable(port)}")
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_ANALOG;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not dac_units:
        lines.append("    (void)hdac;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_dac_msp_deinit(dac_units))
    return lines


def _render_hal_dac_msp_deinit(dac_units: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_DAC_MspDeInit(DAC_HandleTypeDef* hdac)",
        "{",
    ]
    for index, dac in enumerate(dac_units):
        dac_name = str(dac["dac"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (hdac->Instance == {dac_name}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(channel["pin"] for channel in dac.get("channels", [])):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append(f"        __HAL_RCC_{dac_name}_CLK_DISABLE();")
        lines.append("    }")
    if not dac_units:
        lines.append("    (void)hdac;")
    lines.extend(["}", ""])
    return lines


def _render_hal_can_msp_init_v2(can_ports: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_can_msp_init_f1,
            "STM32G4": _render_hal_fdcan_msp_init_g4_v2,
        },
        can_ports,
        chip,
    )


def _render_hal_can_msp_init_f1(can_ports: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    lines = [
        "void HAL_CAN_MspInit(CAN_HandleTypeDef* hcan)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, can in enumerate(can_ports):
        instance = str(can["instance"])
        pins = dict(can["pins"])
        prefix = "if" if index == 0 else "else if"
        tx_port, tx_pin = _pin_parts(pins["tx"])
        rx_port, rx_pin = _pin_parts(pins["rx"])
        lines.append(f"    {prefix} (hcan->Instance == {instance}) {{")
        for port in sorted({tx_port, rx_port}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        lines.append(f"        GPIO_InitStruct.Pin = {tx_pin};")
        lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
        lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
        lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
        lines.append(f"        HAL_GPIO_Init({tx_port}, &GPIO_InitStruct);")
        lines.append(f"        GPIO_InitStruct.Pin = {rx_pin};")
        lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_INPUT;")
        lines.append(f"        HAL_GPIO_Init({rx_port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not can_ports:
        lines.append("    (void)hcan;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_can_msp_deinit(can_ports, chip.family))
    return lines


def _render_hal_fdcan_msp_init_g4(can_ports: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_FDCAN_MspInit(FDCAN_HandleTypeDef* hfdcan)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, can in enumerate(can_ports):
        instance = str(can["instance"])
        pins = dict(can["pins"])
        prefix = "if" if index == 0 else "else if"
        af_macro = _g4_can_af_macro(instance)
        for_port = sorted({_pin_parts(pin)[0] for pin in pins.values()}, key=_port_sort_key)
        lines.append(f"    {prefix} (hfdcan->Instance == {instance}) {{")
        for port in for_port:
            lines.append(f"        {_gpio_clock_enable(port)}")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        for port, pin_expr in _gpio_pin_exprs_by_port(pins.values()):
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;")
            lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not can_ports:
        lines.append("    (void)hfdcan;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_can_msp_deinit(can_ports, chip_family="STM32G4"))
    return lines


def _render_hal_fdcan_msp_init_g4_v2(
    can_ports: List[Dict[str, object]],
    _chip: ChipDefinition,
) -> List[str]:
    return _render_hal_fdcan_msp_init_g4(can_ports)


def _render_hal_can_msp_deinit(can_ports: List[Dict[str, object]], chip_family: str) -> List[str]:
    return _render_with_family_backend(
        chip_family,
        {
            "STM32F1": _render_hal_can_msp_deinit_f1,
            "STM32G4": _render_hal_can_msp_deinit_g4,
        },
        can_ports,
    )


def _render_hal_can_msp_deinit_f1(can_ports: List[Dict[str, object]]) -> List[str]:
    return _render_hal_can_msp_deinit_common(
        can_ports,
        signature="CAN_HandleTypeDef* hcan",
        handle_var="hcan",
        function_name="HAL_CAN_MspDeInit",
    )


def _render_hal_can_msp_deinit_g4(can_ports: List[Dict[str, object]]) -> List[str]:
    return _render_hal_can_msp_deinit_common(
        can_ports,
        signature="FDCAN_HandleTypeDef* hfdcan",
        handle_var="hfdcan",
        function_name="HAL_FDCAN_MspDeInit",
    )


def _render_hal_can_msp_deinit_common(
    can_ports: List[Dict[str, object]],
    signature: str,
    handle_var: str,
    function_name: str,
) -> List[str]:
    lines = [
        f"void {function_name}({signature})",
        "{",
    ]
    for index, can in enumerate(can_ports):
        instance = str(can["instance"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} ({handle_var}->Instance == {instance}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(dict(can["pins"]).values()):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append(f"        __HAL_RCC_{instance}_CLK_DISABLE();")
        lines.append("    }")
    if not can_ports:
        lines.append(f"    (void){handle_var};")
    lines.extend(["}", ""])
    return lines


def _render_hal_pcd_msp_init_v2(usb_devices: List[Dict[str, object]], chip: ChipDefinition) -> List[str]:
    return _render_with_family_backend(
        chip.family,
        {
            "STM32F1": _render_hal_pcd_msp_init_f1,
            "STM32G4": _render_hal_pcd_msp_init_g4,
        },
        usb_devices,
    )


def _render_hal_pcd_msp_init_f1(usb_devices: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_PCD_MspInit(PCD_HandleTypeDef* hpcd)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, usb in enumerate(usb_devices):
        instance = str(usb["instance"])
        pins = dict(usb["pins"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (hpcd->Instance == USB) {{")
        for port in sorted({_pin_parts(pin)[0] for pin in pins.values()}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        lines.append("        __HAL_RCC_USB_CLK_ENABLE();")
        for port, pin_expr in _gpio_pin_exprs_by_port(pins.values()):
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not usb_devices:
        lines.append("    (void)hpcd;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_pcd_msp_deinit(usb_devices, "STM32F1"))
    return lines


def _render_hal_pcd_msp_init_g4(usb_devices: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_PCD_MspInit(PCD_HandleTypeDef* hpcd)",
        "{",
        "    GPIO_InitTypeDef GPIO_InitStruct = {0};",
        "",
    ]
    for index, usb in enumerate(usb_devices):
        instance = str(usb["instance"])
        pins = dict(usb["pins"])
        prefix = "if" if index == 0 else "else if"
        lines.append(f"    {prefix} (hpcd->Instance == {instance}) {{")
        for port in sorted({_pin_parts(pin)[0] for pin in pins.values()}, key=_port_sort_key):
            lines.append(f"        {_gpio_clock_enable(port)}")
        lines.append(f"        __HAL_RCC_{instance}_CLK_ENABLE();")
        af_macro = _g4_usb_af_macro(instance)
        for port, pin_expr in _gpio_pin_exprs_by_port(pins.values()):
            lines.append(f"        GPIO_InitStruct.Pin = {pin_expr};")
            lines.append("        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;")
            lines.append("        GPIO_InitStruct.Pull = GPIO_NOPULL;")
            lines.append("        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;")
            lines.append(f"        GPIO_InitStruct.Alternate = {af_macro};")
            lines.append(f"        HAL_GPIO_Init({port}, &GPIO_InitStruct);")
        lines.append("    }")
    if not usb_devices:
        lines.append("    (void)hpcd;")
    lines.extend(["}", ""])
    lines.extend(_render_hal_pcd_msp_deinit(usb_devices, "STM32G4"))
    return lines


def _render_hal_pcd_msp_deinit(usb_devices: List[Dict[str, object]], chip_family: str) -> List[str]:
    return _render_with_family_backend(
        chip_family,
        {
            "STM32F1": _render_hal_pcd_msp_deinit_f1,
            "STM32G4": _render_hal_pcd_msp_deinit_g4,
        },
        usb_devices,
    )


def _render_hal_pcd_msp_deinit_f1(usb_devices: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_PCD_MspDeInit(PCD_HandleTypeDef* hpcd)",
        "{",
    ]
    for index, usb in enumerate(usb_devices):
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (hpcd->Instance == USB) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(dict(usb["pins"]).values()):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append("        __HAL_RCC_USB_CLK_DISABLE();")
        lines.append("    }")
    if not usb_devices:
        lines.append("    (void)hpcd;")
    lines.extend(["}", ""])
    return lines


def _render_hal_pcd_msp_deinit_g4(usb_devices: List[Dict[str, object]]) -> List[str]:
    lines = [
        "void HAL_PCD_MspDeInit(PCD_HandleTypeDef* hpcd)",
        "{",
    ]
    for index, usb in enumerate(usb_devices):
        instance = str(usb["instance"])
        prefix = "    if" if index == 0 else "    else if"
        lines.append(f"{prefix} (hpcd->Instance == {instance}) {{")
        for port, pin_expr in _gpio_pin_exprs_by_port(dict(usb["pins"]).values()):
            lines.append(f"        HAL_GPIO_DeInit({port}, {pin_expr});")
        lines.append(f"        __HAL_RCC_{instance}_CLK_DISABLE();")
        lines.append("    }")
    if not usb_devices:
        lines.append("    (void)hpcd;")
    lines.extend(["}", ""])
    return lines

def _timer_profile_settings_v2(pwm_profile: str, family: str) -> Tuple[int, int, int]:
    support = get_family_support(family)
    renderers = {
        "STM32F1": _timer_profile_settings_f1,
        "STM32G4": _timer_profile_settings_g4,
    }
    renderer = renderers.get(support.family)
    if renderer is None:
        available = ", ".join(sorted(renderers)) or "none"
        raise KeyError(
            f"No timer profile renderer backend registered for family {support.family}. "
            f"Available backends: {available}"
        )
    return renderer(pwm_profile)


def _timer_profile_settings_g4(pwm_profile: str) -> Tuple[int, int, int]:
    prescaler = 79
    period = 999
    default_pulse = 0
    if pwm_profile == "servo_50hz":
        period = 19999
        default_pulse = 1500
    return prescaler, period, default_pulse


def _timer_profile_settings_f1(pwm_profile: str) -> Tuple[int, int, int]:
    prescaler = 71
    period = 999
    default_pulse = 0
    if pwm_profile == "servo_50hz":
        period = 19999
        default_pulse = 1500
    elif pwm_profile == "motor_pwm":
        prescaler = 35
    return prescaler, period, default_pulse

def _g4_i2c_af_macro(instance: str) -> str:
    mapping = {
        "I2C1": "GPIO_AF4_I2C1",
    }
    return mapping.get(instance, f"GPIO_AF4_{instance}")

def _g4_uart_af_macro(instance: str) -> str:
    mapping = {
        "USART1": "GPIO_AF7_USART1",
        "USART2": "GPIO_AF7_USART2",
        "USART3": "GPIO_AF7_USART3",
    }
    return mapping.get(instance, f"GPIO_AF7_{instance}")

def _g4_tim_af_macro(timer_name: str) -> str:
    mapping = {
        "TIM1": "GPIO_AF6_TIM1",
        "TIM2": "GPIO_AF1_TIM2",
        "TIM3": "GPIO_AF2_TIM3",
        "TIM4": "GPIO_AF2_TIM4",
    }
    return mapping.get(timer_name, f"GPIO_AF1_{timer_name}")


def _g4_spi_af_macro(instance: str) -> str:
    mapping = {
        "SPI1": "GPIO_AF5_SPI1",
        "SPI2": "GPIO_AF5_SPI2",
        "SPI3": "GPIO_AF6_SPI3",
    }
    return mapping.get(instance, f"GPIO_AF5_{instance}")


def _g4_can_af_macro(instance: str) -> str:
    mapping = {
        "CAN1": "GPIO_AF9_FDCAN1",
        "FDCAN1": "GPIO_AF9_FDCAN1",
        "FDCAN2": "GPIO_AF9_FDCAN2",
    }
    return mapping.get(instance, "GPIO_AF9_FDCAN1")


def _g4_usb_af_macro(instance: str) -> str:
    mapping = {
        "USB_FS": "GPIO_AF14_USB",
        "USB_OTG_FS": "GPIO_AF10_OTG_FS",
    }
    return mapping.get(instance, "GPIO_AF14_USB")


def _dma_allocations_for_parent(
    dma_allocations: List[Dict[str, object]] | None,
    peripheral_kind: str,
    instance: str,
) -> List[Dict[str, object]]:
    if not dma_allocations:
        return []
    matched = [
        item
        for item in dma_allocations
        if str(item.get("peripheral_kind", "")).strip().lower() == peripheral_kind
        and str(item.get("instance", "")).strip().upper() == instance
    ]
    return sorted(matched, key=lambda item: (str(item.get("direction", "")), str(item.get("channel", ""))))


def _render_dma_setup_lines(
    dma_allocations: List[Dict[str, object]],
    parent_handle_var: str,
    chip_family: str,
) -> List[str]:
    if not dma_allocations:
        return []

    lines: List[str] = [""]
    support = get_family_support(chip_family)
    lines.extend([f"        {line}" for line in support.dma_setup_clock_lines])

    enabled_controllers: List[str] = []
    for allocation in dma_allocations:
        controller = _dma_controller_name(str(allocation.get("channel", "")))
        if controller and controller not in enabled_controllers:
            enabled_controllers.append(controller)
            lines.append(f"        __HAL_RCC_{controller}_CLK_ENABLE();")

    for allocation in dma_allocations:
        handle = str(allocation.get("handle", "")).strip()
        channel = str(allocation.get("channel", "")).strip()
        direction = str(allocation.get("direction", "")).strip().lower()
        link_field = str(allocation.get("link_field", "")).strip()
        request_macro = str(allocation.get("request_macro", "")).strip()
        if not handle or not channel or direction not in {"rx", "tx"} or not link_field:
            continue
        lines.extend(
            [
                "",
                f"        {handle}.Instance = {channel};",
            ]
        )
        if support.dma_uses_request_field and request_macro:
            lines.append(f"        {handle}.Init.Request = {request_macro};")
        lines.extend(
            [
                f"        {handle}.Init.Direction = {_dma_direction_macro(direction)};",
                f"        {handle}.Init.PeriphInc = DMA_PINC_DISABLE;",
                f"        {handle}.Init.MemInc = DMA_MINC_ENABLE;",
                f"        {handle}.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;",
                f"        {handle}.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;",
                f"        {handle}.Init.Mode = DMA_NORMAL;",
                f"        {handle}.Init.Priority = {_dma_priority_macro(direction)};",
                f"        if (HAL_DMA_Init(&{handle}) != HAL_OK) {{",
                "            Error_Handler();",
                "        }",
                f"        __HAL_LINKDMA({parent_handle_var}, {link_field}, {handle});",
            ]
        )

    return lines


def _render_dma_cleanup_lines(
    dma_allocations: List[Dict[str, object]],
    parent_handle_var: str,
) -> List[str]:
    if not dma_allocations:
        return []

    lines: List[str] = [""]
    disabled_irqs: List[str] = []
    for allocation in dma_allocations:
        link_field = str(allocation.get("link_field", "")).strip()
        irq = str(allocation.get("irq", "")).strip()
        if not link_field:
            continue
        lines.extend(
            [
                f"        if ({parent_handle_var}->{link_field} != NULL) {{",
                f"            HAL_DMA_DeInit({parent_handle_var}->{link_field});",
                "        }",
            ]
        )
        if irq and irq not in disabled_irqs:
            disabled_irqs.append(irq)
            lines.append(f"        HAL_NVIC_DisableIRQ({irq});")

    return lines


def _gpio_pin_exprs_by_port(pins: Iterable[str]) -> List[Tuple[str, str]]:
    grouped: Dict[str, List[str]] = {}
    for raw_pin in pins:
        pin = str(raw_pin).strip().upper()
        if not pin:
            continue
        port, pin_expr = _pin_parts(pin)
        grouped.setdefault(port, [])
        if pin_expr not in grouped[port]:
            grouped[port].append(pin_expr)

    results: List[Tuple[str, str]] = []
    for port in sorted(grouped, key=_port_sort_key):
        ordered = sorted(grouped[port], key=lambda item: int(item.replace("GPIO_PIN_", "")))
        results.append((port, " | ".join(ordered)))
    return results


def _dma_controller_name(channel: str) -> str:
    normalized = str(channel).strip().upper()
    if "_" not in normalized:
        return ""
    return normalized.split("_", 1)[0]


def _dma_direction_macro(direction: str) -> str:
    return "DMA_PERIPH_TO_MEMORY" if str(direction).strip().lower() == "rx" else "DMA_MEMORY_TO_PERIPH"


def _dma_priority_macro(direction: str) -> str:
    return "DMA_PRIORITY_MEDIUM" if str(direction).strip().lower() == "rx" else "DMA_PRIORITY_LOW"

def _gpio_clock_enable(port: str) -> str:
    return f"__HAL_RCC_{port}_CLK_ENABLE();"

def _port_sort_key(port: str) -> Tuple[str, int]:
    return (port[4], 0)

def _uart_handle_name(instance: str) -> str:
    return f"h{instance.lower().replace('usart', 'uart')}"
