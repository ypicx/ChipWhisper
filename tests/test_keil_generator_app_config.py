from __future__ import annotations

import unittest

from stm32_agent.keil_generator_app_config import render_app_config_v2
from stm32_agent.planner import BusAssignment, PinAssignment, PlanResult


class KeilGeneratorAppConfigTests(unittest.TestCase):
    def test_render_app_config_v2_uses_template_and_renders_multiple_resource_macros(self) -> None:
        plan = PlanResult(
            feasible=True,
            chip="STM32F103C8T6",
            board="blue_pill_f103c8",
            summary="ok",
            warnings=[],
            errors=[],
            assignments=[
                PinAssignment(module="debug_port", signal="tx", pin="PA9", reason="UART TX"),
            ],
            buses=[
                BusAssignment(
                    bus="I2C1",
                    kind="i2c",
                    option_id="I2C1_default",
                    pins={"scl": "PB6", "sda": "PB7"},
                    devices=[{"module": "config_store", "address": "0x50"}],
                )
            ],
            hal_components=[],
            template_files=[],
            next_steps=[],
            project_ir={
                "peripherals": {
                    "buses": [
                        {
                            "kind": "spi",
                            "bus": "SPI1",
                            "devices": [{"module": "display"}],
                        }
                    ],
                    "adc": [
                        {
                            "instance": "ADC1",
                            "channels": [
                                {
                                    "module": "sense_a",
                                    "signal": "in",
                                    "channel": "ADC_CHANNEL_0",
                                    "rank_macro": "ADC_REGULAR_RANK_1",
                                }
                            ],
                        }
                    ],
                    "timer_ic": [
                        {
                            "timer": "TIM2",
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
                    "encoder": [
                        {
                            "module": "wheel",
                            "signal": "encoder",
                            "timer": "TIM3",
                        }
                    ],
                    "dac": [
                        {
                            "dac": "DAC1",
                            "channels": [
                                {
                                    "module": "wave",
                                    "signal": "out",
                                    "channel_macro": "DAC_CHANNEL_1",
                                }
                            ],
                        }
                    ],
                    "can": [
                        {
                            "module": "busmon",
                            "instance": "CAN1",
                        }
                    ],
                    "usb": [
                        {
                            "module": "usb_link",
                            "instance": "USB_FS",
                        }
                    ],
                }
            },
        )

        rendered = render_app_config_v2(plan)

        self.assertIn("#define DEBUG_PORT_TX_PORT GPIOA", rendered)
        self.assertIn("#define CONFIG_STORE_I2C_INSTANCE I2C1", rendered)
        self.assertIn("#define CONFIG_STORE_I2C_ADDRESS 0x50", rendered)
        self.assertIn("#define DISPLAY_SPI_INSTANCE SPI1", rendered)
        self.assertIn("#define SENSE_A_IN_ADC_INSTANCE ADC1", rendered)
        self.assertIn("#define SENSE_A_IN_ADC_RANK ADC_REGULAR_RANK_1", rendered)
        self.assertIn("#define METER_CAPTURE_TIM_CHANNEL TIM_CHANNEL_1", rendered)
        self.assertIn("#define METER_CAPTURE_IRQ TIM2_IRQn", rendered)
        self.assertIn("#define WHEEL_ENCODER_TIM_CHANNEL_A TIM_CHANNEL_1", rendered)
        self.assertIn("#define WAVE_OUT_DAC_CHANNEL DAC_CHANNEL_1", rendered)
        self.assertIn("#define BUSMON_CAN_INSTANCE CAN1", rendered)
        self.assertIn("#define USB_LINK_USB_INSTANCE USB_FS", rendered)

    def test_render_app_config_v2_handles_empty_plan(self) -> None:
        plan = PlanResult(
            feasible=True,
            chip="STM32F103C8T6",
            board="blue_pill_f103c8",
            summary="ok",
            warnings=[],
            errors=[],
            assignments=[],
            buses=[],
            hal_components=[],
            template_files=[],
            next_steps=[],
            project_ir={},
        )

        rendered = render_app_config_v2(plan)

        self.assertIn("#ifndef __APP_CONFIG_H", rendered)
        self.assertIn("/* Auto-generated from planner assignments. */", rendered)
        self.assertTrue(rendered.endswith("#endif\n"))


if __name__ == "__main__":
    unittest.main()
