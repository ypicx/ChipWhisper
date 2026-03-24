from __future__ import annotations

import unittest

from stm32_agent.keil_generator_peripherals import (
    render_peripherals_c_v2,
    render_peripherals_h_v2,
)


class KeilGeneratorPeripheralsTests(unittest.TestCase):
    def test_render_peripherals_h_v2_uses_template_and_renders_sections(self) -> None:
        rendered = render_peripherals_h_v2(
            handle_declarations=["extern UART_HandleTypeDef huart2;"],
            function_declarations=[
                "void MX_GPIO_Init(void);",
                "void MX_USART2_UART_Init(void);",
            ],
        )

        self.assertIn("#ifndef __PERIPHERALS_H", rendered)
        self.assertIn('#include "main.h"', rendered)
        self.assertIn("extern UART_HandleTypeDef huart2;", rendered)
        self.assertIn("void MX_USART2_UART_Init(void);", rendered)

    def test_render_peripherals_h_v2_handles_empty_handle_section(self) -> None:
        rendered = render_peripherals_h_v2(
            handle_declarations=[],
            function_declarations=["void MX_GPIO_Init(void);"],
        )

        self.assertNotIn("extern ", rendered)
        self.assertIn("void MX_GPIO_Init(void);", rendered)
        self.assertTrue(rendered.endswith("#endif\n"))

    def test_render_peripherals_c_v2_uses_template_and_preserves_block_order(self) -> None:
        rendered = render_peripherals_c_v2(
            handle_definitions=["UART_HandleTypeDef huart2;"],
            user_code_top="/* USER CODE BEGIN PeripheralsTop */\n/* USER CODE END PeripheralsTop */",
            gpio_init_block="void MX_GPIO_Init(void)\n{\n}\n",
            init_blocks=["void MX_USART2_UART_Init(void)\n{\n}\n"],
            msp_blocks=["void HAL_UART_MspInit(UART_HandleTypeDef* huart)\n{\n}\n"],
            user_code_bottom="/* USER CODE BEGIN PeripheralsBottom */\n/* USER CODE END PeripheralsBottom */\n",
        )

        self.assertIn('#include "peripherals.h"', rendered)
        self.assertIn("UART_HandleTypeDef huart2;", rendered)
        self.assertIn("/* USER CODE BEGIN PeripheralsTop */", rendered)
        self.assertIn("/* USER CODE BEGIN PeripheralsBottom */", rendered)
        self.assertLess(rendered.index("void MX_GPIO_Init(void)"), rendered.index("void MX_USART2_UART_Init(void)"))
        self.assertLess(
            rendered.index("void MX_USART2_UART_Init(void)"),
            rendered.index("void HAL_UART_MspInit(UART_HandleTypeDef* huart)"),
        )


if __name__ == "__main__":
    unittest.main()
