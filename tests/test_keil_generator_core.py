from __future__ import annotations

import unittest

from stm32_agent.keil_generator_core import (
    render_hal_msp_c_v2,
    render_it_c_v2,
    render_it_h_v2,
    render_main_c_v2,
    render_main_h_v2,
)


class KeilGeneratorCoreTests(unittest.TestCase):
    def test_render_main_h_v2_uses_template_and_extra_headers(self) -> None:
        rendered = render_main_h_v2(
            main_hal_header="stm32g4xx_hal.h",
            extra_headers=["stm32g4xx_ll_pwr.h"],
        )

        self.assertIn('#include "stm32g4xx_hal.h"', rendered)
        self.assertIn('#include "stm32g4xx_ll_pwr.h"', rendered)
        self.assertIn('#include "app_config.h"', rendered)
        self.assertIn("void Error_Handler(void);", rendered)

    def test_render_it_h_v2_uses_template_and_handler_list(self) -> None:
        rendered = render_it_h_v2(
            guard="STM32F1XX_IT_H",
            handler_declarations=[
                "void SysTick_Handler(void);",
                "void DMA1_Channel5_IRQHandler(void);",
                "void USART1_IRQHandler(void);",
            ],
        )

        self.assertIn("#ifndef __STM32F1XX_IT_H", rendered)
        self.assertIn("void DMA1_Channel5_IRQHandler(void);", rendered)
        self.assertIn("void USART1_IRQHandler(void);", rendered)
        self.assertTrue(rendered.endswith("#endif\n"))

    def test_render_main_c_v2_uses_template_and_preserves_init_flow(self) -> None:
        rendered = render_main_c_v2(
            include_lines=[
                '#include "main.h"',
                '#include "peripherals.h"',
                '#include "app_main.h"',
            ],
            main_init_block="    /* USER CODE BEGIN MainInit */\n    /* USER CODE END MainInit */",
            init_calls=[
                "    MX_GPIO_Init();",
                "    MX_USART2_UART_Init();",
            ],
            system_clock_block="    RCC_OscInitTypeDef RCC_OscInitStruct = {0};",
            planned_modules=[
                {
                    "name": "status_led",
                    "kind": "led",
                    "summary": "Status indicator.",
                }
            ],
        )

        self.assertIn('#include "app_main.h"', rendered)
        self.assertIn("/* USER CODE BEGIN MainInit */", rendered)
        self.assertIn("void Error_Handler(void)", rendered)
        self.assertIn(" * - status_led (led): Status indicator.", rendered)
        self.assertLess(rendered.index("MX_GPIO_Init"), rendered.index("MX_USART2_UART_Init"))
        self.assertLess(rendered.index("MX_USART2_UART_Init"), rendered.index("App_Init();"))

    def test_render_it_c_v2_uses_template_and_renders_handlers(self) -> None:
        rendered = render_it_c_v2(
            include_lines=[
                '#include "main.h"',
                '#include "peripherals.h"',
                '#include "stm32f1xx_it.h"',
            ],
            interrupt_blocks=[
                "void DMA1_Channel5_IRQHandler(void)\n{\n    HAL_DMA_IRQHandler(&hdma_usart1_rx);\n}",
                "void USART1_IRQHandler(void)\n{\n    HAL_UART_IRQHandler(&huart1);\n}",
            ],
        )

        self.assertIn('#include "stm32f1xx_it.h"', rendered)
        self.assertIn("void SysTick_Handler(void)", rendered)
        self.assertIn("HAL_DMA_IRQHandler(&hdma_usart1_rx);", rendered)
        self.assertIn("HAL_UART_IRQHandler(&huart1);", rendered)
        self.assertLess(rendered.index("void SysTick_Handler"), rendered.index("void DMA1_Channel5_IRQHandler"))
        self.assertLess(rendered.index("void DMA1_Channel5_IRQHandler"), rendered.index("void USART1_IRQHandler"))

    def test_render_hal_msp_c_v2_uses_template_and_global_lines(self) -> None:
        rendered = render_hal_msp_c_v2(
            global_msp_init_lines=[
                "__HAL_RCC_AFIO_CLK_ENABLE();",
                "__HAL_RCC_PWR_CLK_ENABLE();",
            ]
        )

        self.assertIn('#include "main.h"', rendered)
        self.assertIn("__HAL_RCC_AFIO_CLK_ENABLE();", rendered)
        self.assertIn("__HAL_RCC_PWR_CLK_ENABLE();", rendered)
        self.assertIn("/* USER CODE BEGIN MspInit_Post */", rendered)


if __name__ == "__main__":
    unittest.main()
