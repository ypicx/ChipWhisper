from __future__ import annotations

import unittest

from stm32_agent.catalog import STM32F103C8T6
from stm32_agent.keil_generator_docs import (
    render_drivers_readme_v2,
    render_generated_readme_v2,
    render_project_report,
)
from stm32_agent.planner import BusAssignment, PinAssignment, PlanResult


class KeilGeneratorDocsTests(unittest.TestCase):
    def test_render_generated_readme_v2_uses_template(self) -> None:
        rendered = render_generated_readme_v2("demo_project", STM32F103C8T6)

        self.assertIn("# demo_project", rendered)
        self.assertIn("STM32CubeF1", rendered)
        self.assertIn("MDK-ARM/demo_project.uvprojx", rendered)

    def test_render_drivers_readme_v2_uses_template(self) -> None:
        rendered = render_drivers_readme_v2(STM32F103C8T6)

        self.assertIn("STM32CubeF1", rendered)
        self.assertIn("Drivers/CMSIS/Device/ST/STM32F1xx/Include", rendered)
        self.assertIn("Drivers/STM32F1xx_HAL_Driver/Src", rendered)

    def test_render_project_report_renders_context_sections(self) -> None:
        plan = PlanResult(
            feasible=True,
            chip=STM32F103C8T6.name,
            board="blue_pill_f103c8",
            summary="ok",
            warnings=["Check power rails."],
            errors=[],
            assignments=[
                PinAssignment(
                    module="status_led",
                    signal="control",
                    pin="PC13",
                    reason="On-board LED default pin.",
                )
            ],
            buses=[
                BusAssignment(
                    bus="I2C1",
                    kind="i2c",
                    option_id="I2C1_default",
                    pins={"scl": "PB6", "sda": "PB7"},
                    devices=[{"module": "config_store", "address": "0x50"}],
                    notes=["Shared bus for settings storage."],
                )
            ],
            hal_components=["GPIO", "I2C"],
            template_files=[],
            next_steps=[],
            project_ir={
                "target": {
                    "chip": "STM32F103C8T6",
                    "family": "STM32F1",
                    "package": "LQFP48",
                    "board": "blue_pill_f103c8",
                    "board_capabilities": [
                        {
                            "key": "usb_fs",
                            "display_name": "USB FS",
                            "summary": "USB full-speed routed to the USB connector.",
                        }
                    ],
                    "board_notes": ["PA12 is shared with the on-board USB connector."],
                },
                "modules": [
                    {
                        "name": "status_led",
                        "kind": "led",
                        "summary": "Status indicator.",
                    }
                ],
            },
        )

        rendered = render_project_report(plan, "demo_project", STM32F103C8T6)

        self.assertIn("# demo_project Project Report", rendered)
        self.assertIn("USB full-speed routed to the USB connector.", rendered)
        self.assertIn("`status_led` (`led`) Status indicator.", rendered)
        self.assertIn("| `status_led` | `control` | `PC13` | On-board LED default pin. |", rendered)
        self.assertIn("| `I2C1` | `SCL=PB6, SDA=PB7` | config_store(0x50) | Shared bus for settings storage. |", rendered)
        self.assertIn("Check power rails.", rendered)


if __name__ == "__main__":
    unittest.main()
