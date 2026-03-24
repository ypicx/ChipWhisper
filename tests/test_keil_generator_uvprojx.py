from __future__ import annotations

import unittest

from stm32_agent.catalog import STM32F103C8T6
from stm32_agent.keil_generator_uvprojx import render_uvprojx_v2
from stm32_agent.planner import PlanResult


class KeilGeneratorUvprojxTests(unittest.TestCase):
    def test_render_uvprojx_v2_uses_template_and_renders_groups(self) -> None:
        plan = PlanResult(
            feasible=True,
            chip=STM32F103C8T6.name,
            board="blue_pill_f103c8",
            summary="ok",
            warnings=[],
            errors=[],
            assignments=[],
            buses=[],
            hal_components=["GPIO", "USART"],
            template_files=[],
            next_steps=[],
            project_ir={
                "constraints": {
                    "clock_plan": {
                        "cpu_clock_hz": 72000000,
                    }
                }
            },
        )

        rendered = render_uvprojx_v2(
            plan=plan,
            project_name="demo_project",
            chip=STM32F103C8T6,
            hal_sources=["stm32f1xx_hal_gpio.c", "stm32f1xx_hal_uart.c"],
            app_sources=["debug_uart.c"],
            module_sources=["foo.c"],
        )

        self.assertIn("<TargetName>demo_project</TargetName>", rendered)
        self.assertIn("<Device>STM32F103C8</Device>", rendered)
        self.assertIn('CLOCK(72000000) CPUTYPE("Cortex-M3")', rendered)
        self.assertIn("<Define>USE_HAL_DRIVER,STM32F103xB</Define>", rendered)
        self.assertIn("<GroupName>Modules/Src</GroupName>", rendered)
        self.assertIn("<FileName>foo.c</FileName>", rendered)
        self.assertIn("<FilePath>../Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_uart.c</FilePath>", rendered)
        self.assertIn("<IncludePath>../Core/Inc;../App/Inc;../Modules/Inc;", rendered)

    def test_render_uvprojx_v2_omits_modules_group_when_empty(self) -> None:
        plan = PlanResult(
            feasible=True,
            chip=STM32F103C8T6.name,
            board="blue_pill_f103c8",
            summary="ok",
            warnings=[],
            errors=[],
            assignments=[],
            buses=[],
            hal_components=["GPIO"],
            template_files=[],
            next_steps=[],
            project_ir={},
        )

        rendered = render_uvprojx_v2(
            plan=plan,
            project_name="demo_project",
            chip=STM32F103C8T6,
            hal_sources=[],
            app_sources=[],
            module_sources=[],
        )

        self.assertNotIn("<GroupName>Modules/Src</GroupName>", rendered)
        self.assertIn("<GroupName>Startup</GroupName>", rendered)

    def test_render_uvprojx_v2_splits_nested_generated_sources_into_subgroups(self) -> None:
        plan = PlanResult(
            feasible=True,
            chip=STM32F103C8T6.name,
            board="blue_pill_f103c8",
            summary="ok",
            warnings=[],
            errors=[],
            assignments=[],
            buses=[],
            hal_components=["GPIO"],
            template_files=[],
            next_steps=[],
            project_ir={},
        )

        rendered = render_uvprojx_v2(
            plan=plan,
            project_name="demo_project",
            chip=STM32F103C8T6,
            hal_sources=[],
            app_sources=["tasks/helper_task.c"],
            module_sources=["drivers/sensor_bus.c"],
        )

        self.assertIn("<GroupName>App/Src/tasks</GroupName>", rendered)
        self.assertIn("<GroupName>Modules/Src/drivers</GroupName>", rendered)
        self.assertIn("<FilePath>../App/Src/tasks/helper_task.c</FilePath>", rendered)
        self.assertIn("<FilePath>../Modules/Src/drivers/sensor_bus.c</FilePath>", rendered)


if __name__ == "__main__":
    unittest.main()
