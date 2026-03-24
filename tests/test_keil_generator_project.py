from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stm32_agent.keil_generator_app import APP_LOGIC_PLACEHOLDERS
from stm32_agent.keil_generator_context import CodegenContext
from stm32_agent.keil_generator_project import (
    assemble_project_files_to_write,
    collect_custom_template_roots,
)
from stm32_agent.planner import PlanResult


def _empty_context() -> CodegenContext:
    return CodegenContext(
        chip=None,
        support=object(),
        hal_sources=[],
        app_headers=[],
        app_sources=[],
        module_headers=[],
        module_sources=[],
        i2c_buses=[],
        spi_buses=[],
        uart_ports=[],
        adc_inputs=[],
        dac_units=[],
        can_ports=[],
        usb_devices=[],
        pwm_timers=[],
        timer_oc_timers=[],
        timer_ic_timers=[],
        encoder_timers=[],
        dma_allocations=[],
        irqs=[],
        direct_gpios=[],
    )


class KeilGeneratorProjectTests(unittest.TestCase):
    def test_collect_custom_template_roots_deduplicates_entries(self) -> None:
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
            project_ir={
                "modules": [
                    {
                        "name": "custom_app",
                        "template_root": "packs/modules/custom/templates",
                        "template_files": ["app/custom.h", "app/custom.h"],
                    }
                ]
            },
        )

        roots = collect_custom_template_roots(plan)

        self.assertEqual(["packs/modules/custom/templates"], roots["app/custom.h"])

    def test_assemble_project_files_to_write_uses_template_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            template_root = root / "template_root"
            (template_root / "app").mkdir(parents=True, exist_ok=True)
            (template_root / "app" / "custom.h.tpl").write_text("// custom override\n", encoding="utf-8")

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
                project_ir={
                    "modules": [
                        {
                            "name": "custom_app",
                            "template_root": str(template_root),
                            "template_files": ["app/custom.h"],
                        }
                    ]
                },
            )
            context = _empty_context()
            context.app_headers.append("custom.h")

            files = assemble_project_files_to_write(
                plan,
                root,
                context,
                rendered_files={"README.generated.md": "# demo\n"},
            )

            self.assertEqual("// custom override\n", files[root / "App" / "Inc" / "custom.h"])

    def test_assemble_project_files_to_write_preserves_existing_user_code_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            app_src = root / "App" / "Src"
            app_src.mkdir(parents=True, exist_ok=True)
            existing = app_src / "app_main.c"
            existing.write_text(
                "\n".join(
                    [
                        "/* USER CODE BEGIN AppLoop */",
                        "existing_logic();",
                        "/* USER CODE END AppLoop */",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

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

            generated = "\n".join(
                [
                    "/* USER CODE BEGIN AppLoop */",
                    APP_LOGIC_PLACEHOLDERS["AppLoop"],
                    "/* USER CODE END AppLoop */",
                ]
            )

            files = assemble_project_files_to_write(
                plan,
                root,
                _empty_context(),
                rendered_files={"App/Src/app_main.c": generated},
            )

            self.assertIn("existing_logic();", files[existing])

    def test_assemble_project_files_to_write_keeps_generated_file_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
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
                template_files=["app/tasks/helper_task.h", "app/tasks/helper_task.c"],
                next_steps=[],
                project_ir={
                    "build": {
                        "generated_files": {
                            "app/tasks/helper_task.h": "void HelperTask_Run(void);\n",
                            "app/tasks/helper_task.c": '#include "tasks/helper_task.h"\n',
                        }
                    }
                },
            )

            files = assemble_project_files_to_write(
                plan,
                root,
                _empty_context(),
                rendered_files={"README.generated.md": "# demo\n"},
            )

            self.assertIn(root / "App" / "Inc" / "tasks" / "helper_task.h", files)
            self.assertIn(root / "App" / "Src" / "tasks" / "helper_task.c", files)


if __name__ == "__main__":
    unittest.main()
