from __future__ import annotations

import unittest

from stm32_agent.catalog import STM32F103C8T6
from stm32_agent.keil_generator import _render_peripherals_h
from stm32_agent.keil_generator_context import _build_codegen_context
from stm32_agent.planner import BusAssignment, PinAssignment, PlanResult


class KeilGeneratorContextTests(unittest.TestCase):
    def test_build_codegen_context_collects_units_and_resources_once(self) -> None:
        plan = PlanResult(
            feasible=True,
            chip=STM32F103C8T6.name,
            board="blue_pill_f103c8",
            summary="ok",
            warnings=[],
            errors=[],
            assignments=[
                PinAssignment(module="debug", signal="USART1.tx", pin="PA9", reason="UART TX"),
                PinAssignment(module="debug", signal="USART1.rx", pin="PA10", reason="UART RX"),
            ],
            buses=[
                BusAssignment(
                    bus="I2C1",
                    kind="i2c",
                    option_id="I2C1_default",
                    pins={"scl": "PB6", "sda": "PB7"},
                )
            ],
            hal_components=["GPIO", "USART", "I2C"],
            template_files=[
                "app/debug_uart.h",
                "app/debug_uart.c",
                "modules/demo_module.h",
                "modules/demo_module.c",
            ],
            next_steps=[],
            project_ir={
                "target": {"family": "STM32F1"},
                "peripherals": {
                    "timer_ic": [
                        {
                            "timer": "TIM2",
                            "handle": "htim2",
                            "irq": "TIM2_IRQn",
                            "channels": [
                                {
                                    "module": "meter",
                                    "signal": "capture",
                                    "channel_macro": "TIM_CHANNEL_1",
                                }
                            ],
                        }
                    ],
                    "exti": [
                        {
                            "module": "button",
                            "signal": "interrupt",
                            "pin": "PA0",
                            "irq": "EXTI0_IRQn",
                        }
                    ],
                },
            },
        )

        context = _build_codegen_context(plan, STM32F103C8T6)

        self.assertEqual(["debug_uart.h"], context.app_headers)
        self.assertEqual(["debug_uart.c"], context.app_sources)
        self.assertEqual(["demo_module.h"], context.module_headers)
        self.assertEqual(["demo_module.c"], context.module_sources)
        self.assertEqual("I2C1", context.i2c_buses[0]["instance"])
        self.assertEqual("USART1", context.uart_ports[0]["instance"])
        self.assertIn("USART1_IRQn", context.irqs)
        self.assertIn("EXTI0_IRQn", context.irqs)
        self.assertIn("TIM2_IRQn", context.irqs)

    def test_render_peripherals_h_can_infer_context_without_chip(self) -> None:
        plan = PlanResult(
            feasible=True,
            chip=STM32F103C8T6.name,
            board="blue_pill_f103c8",
            summary="ok",
            warnings=[],
            errors=[],
            assignments=[
                PinAssignment(module="debug", signal="USART1.tx", pin="PA9", reason="UART TX"),
                PinAssignment(module="debug", signal="USART1.rx", pin="PA10", reason="UART RX"),
            ],
            buses=[],
            hal_components=["GPIO", "USART"],
            template_files=[],
            next_steps=[],
            project_ir={"target": {"family": "STM32F1"}},
        )

        rendered = _render_peripherals_h(plan)

        self.assertIn("extern UART_HandleTypeDef huart1;", rendered)
        self.assertIn("void MX_USART1_UART_Init(void);", rendered)


if __name__ == "__main__":
    unittest.main()
