from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stm32_agent.catalog import (
    BoardProfile,
    ChipDefinition,
    InterfaceOption,
    ModuleSpec,
    STM32F103C8T6,
    STM32F103RBT6,
    STM32G431RBT6,
)
from stm32_agent.cubemx_chip_import import build_chip_manifest_from_cubemx_xml
from stm32_agent.extension_packs import load_catalog
from stm32_agent.graph.retrieval import _catalog_chunks
from stm32_agent.keil_generator import scaffold_from_request
from stm32_agent.planner import ModuleRequest, Planner, plan_request


class PlannerAndCodegenRegressionTests(unittest.TestCase):
    def _clone_packs_tree(self, tmp_dir: str) -> Path:
        source_root = Path(__file__).resolve().parents[1] / "packs"
        packs_root = Path(tmp_dir) / "packs"
        shutil.copytree(source_root, packs_root)
        return packs_root

    def _write_module_pack(
        self,
        packs_root: Path,
        key: str,
        hal_components: list[str],
        resource_requests: list[str],
        extra_manifest: dict[str, object] | None = None,
    ) -> None:
        module_root = packs_root / "modules" / key
        module_root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": "1.0",
            "kind": "module",
            "key": key,
            "display_name": key,
            "summary": f"Test-only module {key}.",
            "hal_components": hal_components,
            "template_files": [],
            "resource_requests": resource_requests,
            "irqs": [],
            "dma_requests": [],
            "c_top_template": [],
            "c_init_template": [],
            "c_loop_template": [],
            "notes": [],
            "sources": ["unit-test"],
        }
        if extra_manifest:
            manifest.update(extra_manifest)
        (module_root / "module.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _write_chip_pack(
        self,
        packs_root: Path,
        filename: str,
        manifest: dict[str, object],
    ) -> None:
        chip_root = packs_root / "chips"
        chip_root.mkdir(parents=True, exist_ok=True)
        (chip_root / filename).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_project_ir_keeps_module_simulation_metadata(self) -> None:
        result = plan_request(
            {
                "chip": "STM32F103C8T6",
                "modules": [
                    {"kind": "led", "name": "status_led"},
                    {"kind": "button", "name": "user_key"},
                ],
            }
        )

        self.assertTrue(result.feasible, msg=result.errors)
        module_map = {item["name"]: item for item in result.project_ir["modules"]}
        self.assertEqual(
            module_map["status_led"]["simulation"]["renode"]["attach"][0]["kind"],
            "led",
        )
        self.assertEqual(
            module_map["user_key"]["simulation"]["renode"]["attach"][0]["kind"],
            "button",
        )

    def test_project_ir_keeps_structured_runtime_expectations_from_app_logic_ir(self) -> None:
        result = plan_request(
            {
                "chip": "STM32F103C8T6",
                "modules": [
                    {"kind": "uart_debug", "name": "debug_port", "options": {"instance": "USART1"}},
                ],
                "app_logic_ir": {
                    "acceptance": {
                        "uart_contains": ["boot ok", "ready"],
                        "uart_not_contains": ["panic"],
                    }
                },
            }
        )

        self.assertTrue(result.feasible, msg=result.errors)
        expectations = result.project_ir["build"]["runtime_expectations"]
        self.assertEqual(expectations["uart_contains"], ["boot ok", "ready"])
        self.assertEqual(expectations["uart_not_contains"], ["panic"])

    def test_explicit_chip_only_requires_manual_gpio_pin_connections(self) -> None:
        result = plan_request(
            {
                "chip": "STM32F103C8T6",
                "board": "chip_only",
                "modules": [
                    {"kind": "led", "name": "status_led"},
                ],
            }
        )

        self.assertFalse(result.feasible)
        self.assertTrue(
            any("board=chip_only" in error and "exact pin" in error for error in result.errors),
            msg=result.errors,
        )

    def test_omitting_board_keeps_auto_pin_assignment_behavior(self) -> None:
        result = plan_request(
            {
                "chip": "STM32F103C8T6",
                "modules": [
                    {"kind": "led", "name": "status_led"},
                ],
            }
        )

        self.assertTrue(result.feasible, msg=result.errors)
        self.assertEqual(result.board, "auto")
        self.assertTrue(any(item.module == "status_led" for item in result.assignments))

    def test_interrupt_modules_cannot_share_an_exti_line(self) -> None:
        chip = ChipDefinition(
            name="TESTCHIP",
            device_name="TESTCHIP",
            vendor="TestVendor",
            family="STM32F1",
            cpu_type="Cortex-M3",
            package="LQFP48",
            flash_kb=64,
            ram_kb=20,
            irom_start=0x08000000,
            iram_start=0x20000000,
            c_define="TESTCHIP",
            reserved_pins=(),
            gpio_preference=("PA0", "PB0"),
            adc_pins=(),
            interfaces={},
            definition_path="test:chip",
        )
        module = ModuleSpec(
            key="irq_sensor",
            display_name="IRQ Sensor",
            summary="Test-only interrupt source.",
            hal_components=("GPIO",),
            template_files=(),
            resource_requests=("gpio_in:int",),
            definition_path="test:module",
        )
        planner = Planner(
            chip=chip,
            module_registry={"irq_sensor": module},
            keep_swd=False,
        )

        result = planner.plan(
            [
                ModuleRequest(kind="irq_sensor", name="sensor_a"),
                ModuleRequest(kind="irq_sensor", name="sensor_b"),
            ]
        )

        self.assertFalse(result.feasible)
        self.assertTrue(
            any("free EXTI line" in error for error in result.errors),
            msg=result.errors,
        )

    def test_shared_i2c_dma_requests_are_grouped_per_bus(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "ssd1306_i2c", "name": "oled"},
                {"kind": "at24c02_i2c", "name": "eeprom"},
            ],
        }

        plan = plan_request(payload)

        self.assertTrue(plan.feasible, msg=plan.errors)
        peripherals = plan.project_ir["peripherals"]
        bus = peripherals["buses"][0]
        bus_name = str(bus["bus"])
        dma_items = [
            item
            for item in peripherals["dma"]
            if str(item.get("instance", "")).upper() == bus_name.upper()
        ]

        self.assertEqual({item["request"] for item in dma_items}, {f"{bus_name}_RX", f"{bus_name}_TX"})
        for item in dma_items:
            self.assertEqual(set(item.get("modules", [])), {"oled", "eeprom"})
            self.assertEqual(item.get("shared_scope"), "bus")

    def test_board_clock_profile_reaches_plan_and_codegen(self) -> None:
        payload = {
            "board": "blue_pill_f103c8",
            "modules": [
                {"kind": "led", "name": "status_led"},
            ],
        }

        plan = plan_request(payload)

        self.assertTrue(plan.feasible, msg=plan.errors)
        clock_plan = plan.project_ir["constraints"]["clock_plan"]
        self.assertEqual(clock_plan["source"], "board")
        self.assertEqual(clock_plan["cpu_clock_hz"], 72_000_000)

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "blue_pill_clock")
            self.assertTrue(result.feasible, msg=result.errors)
            main_text = (
                Path(result.project_dir) / "Core" / "Src" / "main.c"
            ).read_text(encoding="utf-8")

        self.assertIn("RCC_OSCILLATORTYPE_HSE", main_text)
        self.assertIn("RCC_PLL_MUL9", main_text)

    def test_generated_dma_pwm_and_exti_lifecycle_code(self) -> None:
        dma_and_pwm_payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "uart_debug", "name": "debug_port"},
                {"kind": "passive_buzzer", "name": "tone"},
            ],
        }
        exti_payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "mpu6050_i2c", "name": "imu", "options": {"use_int": True}},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            dma_result = scaffold_from_request(dma_and_pwm_payload, Path(tmp_dir) / "dma_pwm")
            self.assertTrue(dma_result.feasible, msg=dma_result.errors)
            peripherals_text = (
                Path(dma_result.project_dir) / "Core" / "Src" / "peripherals.c"
            ).read_text(encoding="utf-8")

            exti_result = scaffold_from_request(exti_payload, Path(tmp_dir) / "exti_irq")
            self.assertTrue(exti_result.feasible, msg=exti_result.errors)
            exti_peripherals_text = (
                Path(exti_result.project_dir) / "Core" / "Src" / "peripherals.c"
            ).read_text(encoding="utf-8")
            exti_it_text = (
                Path(exti_result.project_dir) / "Core" / "Src" / "stm32f1xx_it.c"
            ).read_text(encoding="utf-8")

        self.assertIn("void HAL_UART_MspDeInit(UART_HandleTypeDef* huart)", peripherals_text)
        self.assertIn("HAL_DMA_DeInit(huart->hdmarx);", peripherals_text)
        self.assertIn("HAL_DMA_DeInit(huart->hdmatx);", peripherals_text)
        self.assertIn("void HAL_TIM_PWM_MspDeInit(TIM_HandleTypeDef* htim_pwm)", peripherals_text)
        self.assertIn("HAL_GPIO_DeInit(", peripherals_text)

        self.assertIn("GPIO_MODE_IT_RISING_FALLING", exti_peripherals_text)
        self.assertIn("HAL_GPIO_EXTI_IRQHandler(", exti_it_text)
        self.assertIn("IRQHandler", exti_it_text)

    def test_multi_button_requires_soft_timer_dependency(self) -> None:
        plan = plan_request(
            {
                "chip": "STM32F103C8T6",
                "modules": [
                    {"kind": "multi_button", "name": "menu_key"},
                ],
            }
        )

        self.assertFalse(plan.feasible)
        self.assertTrue(
            any("soft_timer" in error for error in plan.errors),
            msg=plan.errors,
        )

    def test_software_middleware_packs_codegen_in_dependency_order(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "multi_button", "name": "menu_key"},
                {"kind": "soft_timer", "name": "scheduler"},
            ],
        }

        plan = plan_request(payload)
        self.assertTrue(plan.feasible, msg=plan.errors)
        module_map = {
            item["name"]: item
            for item in plan.project_ir["modules"]
        }
        self.assertEqual(module_map["menu_key"]["depends_on"], ["soft_timer"])
        self.assertEqual(module_map["scheduler"]["resource_requests"], [])

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "middleware_stack")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn('#include "soft_timer.h"', app_main_text)
        self.assertIn('#include "multi_button.h"', app_main_text)
        self.assertLess(app_main_text.index("SoftTimer_Init();"), app_main_text.index("MultiButton_Init("))
        self.assertLess(app_main_text.index("SoftTimer_Tick();"), app_main_text.index("MultiButton_Process("))
        self.assertIn('static MultiButton g_menu_key_module;', app_main_text)
        self.assertIn('MultiButton_Init(&g_menu_key_module, "menu_key"', app_main_text)

    def test_multi_button_option_tokens_render_with_defaults_and_bool_values(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "multi_button", "name": "user_key", "options": {
                    "active_low": False,
                    "debounce_ms": 40,
                    "long_press_ms": 1200,
                    "double_click_ms": 320,
                }},
                {"kind": "soft_timer", "name": "scheduler"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "button_tuning")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn('MultiButton_Init(&g_user_key_module, "user_key", USER_KEY_INPUT_PORT, USER_KEY_INPUT_PIN, 0);', app_main_text)
        self.assertIn("MultiButton_SetTiming(&g_user_key_module, 40, 1200, 320);", app_main_text)

    def test_soft_task_scheduler_pack_runs_between_timer_and_button(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "multi_button", "name": "menu_key"},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        plan = plan_request(payload)
        self.assertTrue(plan.feasible, msg=plan.errors)

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "scheduler_stack")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertLess(app_main_text.index("SoftTimer_Init();"), app_main_text.index("SoftTaskScheduler_Init();"))
        self.assertLess(app_main_text.index("SoftTaskScheduler_Init();"), app_main_text.index("MultiButton_Init("))
        self.assertLess(app_main_text.index("SoftTimer_Tick();"), app_main_text.index("SoftTaskScheduler_Tick(SoftTimer_GetMillis());"))
        self.assertLess(app_main_text.index("SoftTaskScheduler_Tick(SoftTimer_GetMillis());"), app_main_text.index("MultiButton_Process("))
        self.assertIn('#include "soft_task_scheduler.h"', app_main_text)

    def test_uart_frame_pack_uses_uart_handle_and_custom_options(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "uart_frame", "name": "console", "options": {
                    "instance": "USART2",
                    "delimiter_ascii": 13,
                    "idle_gap_ms": 55,
                }},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "uart_frame")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn('#include "uart_frame.h"', app_main_text)
        self.assertLess(app_main_text.index("SoftTimer_Init();"), app_main_text.index("UartFrame_Init("))
        self.assertLess(app_main_text.index("SoftTimer_Tick();"), app_main_text.index("UartFrame_Process("))
        self.assertIn('UartFrame_Init(&g_console_module, "console", &huart2);', app_main_text)
        self.assertIn("UartFrame_SetLineMode(&g_console_module, 13, 55);", app_main_text)

    def test_dependency_template_tokens_can_reference_dependent_module_context(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(
                packs_root,
                "dep_probe",
                [],
                [],
                extra_manifest={
                    "depends_on": ["uart_frame"],
                    "c_init_template": [
                        "    /* probe [[dep_uart_frame_module_name]] [[dep_uart_frame_module_identifier]] &[[dep_uart_frame_uart_handle]] */"
                    ],
                },
            )
            payload = {
                "chip": "STM32F103C8T6",
                "modules": [
                    {"kind": "dep_probe", "name": "probe"},
                    {"kind": "uart_frame", "name": "console", "options": {"instance": "USART1"}},
                    {"kind": "soft_timer", "name": "clock"},
                ],
            }

            result = scaffold_from_request(payload, Path(tmp_dir) / "dep_probe", packs_dir=packs_root)
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn("/* probe console g_console_module &huart1 */", app_main_text)

    def test_menu_view_pack_registers_scheduled_render_and_custom_navigation(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "menu_view", "name": "main_menu", "options": {
                    "refresh_ms": 90,
                    "visible_rows": 3,
                    "item_count": 6,
                    "initial_page": 2,
                    "up_button": "btn_up",
                    "down_button": "btn_down",
                    "enter_button": "btn_ok",
                    "back_button": "btn_back",
                }},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "menu_view",)
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn('#include "menu_view.h"', app_main_text)
        self.assertLess(app_main_text.index("SoftTimer_Init();"), app_main_text.index("SoftTaskScheduler_Init();"))
        self.assertLess(app_main_text.index("SoftTaskScheduler_Init();"), app_main_text.index("MenuView_Init("))
        self.assertIn('MenuView_Init(&g_main_menu_module, "main_menu", 3, 90);', app_main_text)
        self.assertIn("MenuView_SetPage(&g_main_menu_module, 2, 6);", app_main_text)
        self.assertIn('MenuView_BindNavigation(&g_main_menu_module, "btn_up", "btn_down", "btn_ok", "btn_back");', app_main_text)
        self.assertIn('(void)SoftTaskScheduler_Add("main_menu:render", 90, MenuView_TaskCallback, &g_main_menu_module);', app_main_text)

    def test_menu_view_pack_uses_default_navigation_names(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "menu_view", "name": "ui"},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "menu_defaults")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn('MenuView_BindNavigation(&g_ui_module, "key_up", "key_down", "key_ok", "key_back");', app_main_text)
        self.assertIn("MenuView_SetPage(&g_ui_module, 0, 4);", app_main_text)

    def test_menu_view_multi_button_bridge_injects_global_button_callback(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "menu_view", "name": "ui"},
                {"kind": "multi_button", "name": "key_ok"},
                {"kind": "menu_view_multi_button_bridge", "name": "ui_buttons"},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "menu_button_bridge")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")
            bridge_source_text = (
                Path(result.project_dir) / "Modules" / "Src" / "menu_view_multi_button_bridge.c"
            ).read_text(encoding="utf-8")

        self.assertIn('#include "menu_view_multi_button_bridge.h"', app_main_text)
        self.assertIn("void MultiButton_OnEvent(const MultiButton *button, MultiButtonEvent event)", app_main_text)
        self.assertIn("MenuView_DispatchNamedInput(button->name, (uint32_t)event);", app_main_text)
        self.assertIn("MenuViewMultiButton_AfterDispatch(button, event);", app_main_text)
        self.assertIn("__weak void MenuViewMultiButton_AfterDispatch(const MultiButton *button, MultiButtonEvent event)", bridge_source_text)

    def test_menu_view_lcd1602_adapter_injects_render_callback(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "menu_view", "name": "ui"},
                {"kind": "lcd1602_i2c", "name": "ui_lcd"},
                {"kind": "menu_view_lcd1602_adapter", "name": "ui_render"},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "menu_lcd1602")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")
            adapter_source_text = (
                Path(result.project_dir) / "Modules" / "Src" / "menu_view_lcd1602_adapter.c"
            ).read_text(encoding="utf-8")

        self.assertIn('#include "menu_view_lcd1602_adapter.h"', app_main_text)
        self.assertIn("void MenuView_OnRender(const MenuView *view)", app_main_text)
        self.assertIn("MenuViewLcd1602_FormatLine(view, 0U, line0, sizeof(line0));", app_main_text)
        self.assertIn("LCD1602_SetCursor(&hi2c1, UI_LCD_I2C_ADDRESS, 0U, 0U, 100);", app_main_text)
        self.assertIn("__weak void MenuViewLcd1602_FormatLine(const MenuView *view, uint8_t row, char *buffer, uint16_t buffer_size)", adapter_source_text)

    def test_menu_view_ct117e_adapter_injects_graphical_render_callback(self) -> None:
        payload = {
            "board": "ct117e_m4_g431",
            "modules": [
                {"kind": "menu_view", "name": "ui"},
                {"kind": "ct117e_lcd_parallel", "name": "board_lcd"},
                {"kind": "menu_view_ct117e_adapter", "name": "ui_render"},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "menu_ct117e")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")
            adapter_source_text = (
                Path(result.project_dir) / "Modules" / "Src" / "menu_view_ct117e_adapter.c"
            ).read_text(encoding="utf-8")

        self.assertIn('#include "menu_view_ct117e_adapter.h"', app_main_text)
        self.assertIn("MenuViewCt117e_FormatLine(view, row, line, sizeof(line));", app_main_text)
        self.assertIn("CT117ELcd_WriteString5x7(", app_main_text)
        self.assertIn("&g_board_lcd_module", app_main_text)
        self.assertIn("__weak void MenuViewCt117e_FormatLine(const MenuView *view, uint8_t row, char *buffer, uint16_t buffer_size)", adapter_source_text)

    def test_persistent_settings_pack_registers_commit_task_and_buffer(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "persistent_settings", "name": "settings"},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "persistent_defaults")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn('#include "persistent_settings.h"', app_main_text)
        self.assertIn("static PersistentSettings g_settings_module;", app_main_text)
        self.assertIn("static uint8_t g_settings_module_data[32];", app_main_text)
        self.assertIn('PersistentSettings_Init(&g_settings_module, "settings", g_settings_module_data, (uint16_t)sizeof(g_settings_module_data), (uint16_t)1, 1500);', app_main_text)
        self.assertIn("PersistentSettings_Load(&g_settings_module);", app_main_text)
        self.assertIn('(void)SoftTaskScheduler_Add("settings:commit", 100, PersistentSettings_TaskCallback, &g_settings_module);', app_main_text)

    def test_persistent_settings_pack_renders_custom_commit_options(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "persistent_settings", "name": "params", "options": {
                    "bytes": 48,
                    "version": 7,
                    "commit_delay_ms": 2500,
                    "task_period_ms": 80,
                }},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "persistent_custom")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn("static uint8_t g_params_module_data[48];", app_main_text)
        self.assertIn('PersistentSettings_Init(&g_params_module, "params", g_params_module_data, (uint16_t)sizeof(g_params_module_data), (uint16_t)7, 2500);', app_main_text)
        self.assertIn('(void)SoftTaskScheduler_Add("params:commit", 80, PersistentSettings_TaskCallback, &g_params_module);', app_main_text)

    def test_persistent_settings_at24c32_backend_injects_callbacks(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "persistent_settings", "name": "settings"},
                {"kind": "at24c32_i2c", "name": "settings_eeprom"},
                {"kind": "persistent_settings_at24c32", "name": "settings_backend", "options": {
                    "base_address": 16,
                    "timeout_ms": 120,
                }},
                {"kind": "soft_task_scheduler", "name": "tasks"},
                {"kind": "soft_timer", "name": "clock"},
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "persistent_eeprom_backend")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn("static HAL_StatusTypeDef PersistentSettingsAt24C32_ReadPayload", app_main_text)
        self.assertIn("void PersistentSettings_OnDefaults(PersistentSettings *settings, uint8_t *data, uint16_t length)", app_main_text)
        self.assertIn('PersistentSettings_Matches(settings, "settings")', app_main_text)
        self.assertIn("AT24C32_ReadBuffer(&hi2c1, SETTINGS_EEPROM_I2C_ADDRESS, memory_address, buffer, length, 120);", app_main_text)
        self.assertIn("AT24C32_WritePage(&hi2c1, SETTINGS_EEPROM_I2C_ADDRESS", app_main_text)
        self.assertIn("return PersistentSettingsAt24C32_ReadPayload((uint16_t)(16 + 2U), data, length);", app_main_text)
        self.assertIn("return PersistentSettingsAt24C32_WritePayload((uint16_t)(16 + 2U), data, length);", app_main_text)

    def test_g4_adc_codegen_supports_mixed_adc_instances(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(packs_root, "analog_probe", ["GPIO", "ADC"], ["adc_in"])
            payload = {
                "chip": "STM32G431RBT6",
                "modules": [
                    {"kind": "analog_probe", "name": "sense_a", "options": {"pin": "PB11"}},
                    {"kind": "analog_probe", "name": "sense_b", "options": {"pin": "PA4"}},
                ],
            }

            plan = plan_request(payload, packs_dir=packs_root)
            self.assertTrue(plan.feasible, msg=plan.errors)
            adc_units = {
                item["instance"]: {
                    channel["pin"]: channel["channel"]
                    for channel in item["channels"]
                }
                for item in plan.project_ir["peripherals"]["adc"]
            }
            self.assertEqual(adc_units["ADC1"]["PB11"], "ADC_CHANNEL_14")
            self.assertEqual(adc_units["ADC2"]["PA4"], "ADC_CHANNEL_17")

            result = scaffold_from_request(payload, Path(tmp_dir) / "g4_adc", packs_dir=packs_root)
            self.assertTrue(result.feasible, msg=result.errors)
            peripherals_text = (
                Path(result.project_dir) / "Core" / "Src" / "peripherals.c"
            ).read_text(encoding="utf-8")
            app_config_text = (
                Path(result.project_dir) / "Core" / "Inc" / "app_config.h"
            ).read_text(encoding="utf-8")

        self.assertIn("ADC_HandleTypeDef hadc1;", peripherals_text)
        self.assertIn("ADC_HandleTypeDef hadc2;", peripherals_text)
        self.assertIn("__HAL_RCC_ADC12_CLK_ENABLE();", peripherals_text)
        self.assertIn("void MX_ADC1_Init(void)", peripherals_text)
        self.assertIn("void MX_ADC2_Init(void)", peripherals_text)
        self.assertIn("GPIO_MODE_ANALOG", peripherals_text)
        self.assertIn("#define SENSE_A_IN_ADC_INSTANCE ADC1", app_config_text)
        self.assertIn("#define SENSE_B_IN_ADC_INSTANCE ADC2", app_config_text)

    def test_f103_adc_codegen_emits_ranked_channels(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(packs_root, "analog_probe", ["GPIO", "ADC"], ["adc_in"])
            payload = {
                "chip": "STM32F103RBT6",
                "modules": [
                    {"kind": "analog_probe", "name": "pot_a", "options": {"pin": "PA0"}},
                    {"kind": "analog_probe", "name": "pot_b", "options": {"pin": "PC0"}},
                ],
            }

            result = scaffold_from_request(payload, Path(tmp_dir) / "f103_adc", packs_dir=packs_root)
            self.assertTrue(result.feasible, msg=result.errors)
            peripherals_text = (
                Path(result.project_dir) / "Core" / "Src" / "peripherals.c"
            ).read_text(encoding="utf-8")

        self.assertIn("ADC_REGULAR_RANK_1", peripherals_text)
        self.assertIn("ADC_REGULAR_RANK_2", peripherals_text)
        self.assertIn("sConfig.Channel = ADC_CHANNEL_0;", peripherals_text)
        self.assertIn("sConfig.Channel = ADC_CHANNEL_10;", peripherals_text)

    def test_timer_input_capture_conflicts_with_pwm_on_same_timer(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(packs_root, "freq_capture", ["GPIO", "TIM"], ["timer_ic"])
            self._write_module_pack(packs_root, "tone_pwm", ["GPIO", "TIM"], ["pwm_out"])
            plan = plan_request(
                {
                    "chip": "STM32F103C8T6",
                    "modules": [
                        {"kind": "freq_capture", "name": "meter", "options": {"pin": "PA0"}},
                        {"kind": "tone_pwm", "name": "tone", "options": {"instance": "TIM2_CH2"}},
                    ],
                },
                packs_dir=packs_root,
            )

        self.assertFalse(plan.feasible)
        self.assertTrue(any("TIM2_CH2" in error or "PWM channel" in error for error in plan.errors), msg=plan.errors)

    def test_timer_input_capture_codegen_emits_irq_and_msp(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(packs_root, "freq_capture", ["GPIO", "TIM"], ["timer_ic"])
            payload = {
                "chip": "STM32F103C8T6",
                "modules": [
                    {"kind": "freq_capture", "name": "meter", "options": {"pin": "PA0"}},
                ],
            }

            result = scaffold_from_request(payload, Path(tmp_dir) / "timer_ic", packs_dir=packs_root)
            self.assertTrue(result.feasible, msg=result.errors)
            peripherals_text = (
                Path(result.project_dir) / "Core" / "Src" / "peripherals.c"
            ).read_text(encoding="utf-8")
            irq_text = (
                Path(result.project_dir) / "Core" / "Src" / "stm32f1xx_it.c"
            ).read_text(encoding="utf-8")
            app_config_text = (
                Path(result.project_dir) / "Core" / "Inc" / "app_config.h"
            ).read_text(encoding="utf-8")

        self.assertIn("void MX_TIM2_IC_Init(void)", peripherals_text)
        self.assertIn("HAL_TIM_IC_ConfigChannel(&htim2, &sConfigIC, TIM_CHANNEL_1)", peripherals_text)
        self.assertIn("HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_1)", peripherals_text)
        self.assertIn("void HAL_TIM_IC_MspInit(TIM_HandleTypeDef* htim_ic)", peripherals_text)
        self.assertIn("GPIO_MODE_AF_INPUT", peripherals_text)
        self.assertIn("HAL_NVIC_EnableIRQ(TIM2_IRQn);", peripherals_text)
        self.assertIn("void TIM2_IRQHandler(void)", irq_text)
        self.assertIn("HAL_TIM_IRQHandler(&htim2);", irq_text)
        self.assertIn("#define METER_CAPTURE_TIM_INSTANCE TIM2", app_config_text)
        self.assertIn("#define METER_CAPTURE_TIM_CHANNEL TIM_CHANNEL_1", app_config_text)

    def test_spi_bus_and_spi_devices_share_one_controller(self) -> None:
        chip = ChipDefinition(
            name="TESTSPI",
            device_name="TESTSPI",
            vendor="TestVendor",
            family="STM32F1",
            cpu_type="Cortex-M3",
            package="LQFP48",
            flash_kb=64,
            ram_kb=20,
            irom_start=0x08000000,
            iram_start=0x20000000,
            c_define="TESTSPI",
            reserved_pins=(),
            gpio_preference=("PA4", "PA5", "PA6", "PA7", "PB12", "PB13", "PB14", "PB15"),
            adc_pins=(),
            interfaces={
                "spi": (
                    InterfaceOption(
                        option_id="SPI1_DEFAULT",
                        kind="spi",
                        instance="SPI1",
                        signals={"nss": "PA4", "sck": "PA5", "miso": "PA6", "mosi": "PA7"},
                        shareable=True,
                    ),
                    InterfaceOption(
                        option_id="SPI2_DEFAULT",
                        kind="spi",
                        instance="SPI2",
                        signals={"nss": "PB12", "sck": "PB13", "miso": "PB14", "mosi": "PB15"},
                        shareable=True,
                    ),
                ),
            },
            definition_path="test:chip",
        )
        backbone = ModuleSpec(
            key="spi_backbone",
            display_name="SPI Backbone",
            summary="Owns an SPI bus.",
            hal_components=("GPIO", "SPI"),
            template_files=(),
            resource_requests=("spi_bus",),
            definition_path="test:module",
        )
        sensor = ModuleSpec(
            key="spi_sensor",
            display_name="SPI Sensor",
            summary="Uses a shared SPI device bus.",
            hal_components=("GPIO", "SPI"),
            template_files=(),
            resource_requests=("spi_device",),
            definition_path="test:module",
        )
        planner = Planner(
            chip=chip,
            module_registry={"spi_backbone": backbone, "spi_sensor": sensor},
            keep_swd=False,
        )

        result = planner.plan(
            [
                ModuleRequest(kind="spi_backbone", name="main_bus", options={"instance": "SPI1"}),
                ModuleRequest(kind="spi_sensor", name="flash", options={"bus": "SPI1"}),
                ModuleRequest(kind="spi_sensor", name="display", options={"bus": "SPI1"}),
            ]
        )

        self.assertTrue(result.feasible, msg=result.errors)
        spi_buses = [item for item in result.project_ir["peripherals"]["buses"] if item["kind"] == "spi"]
        self.assertEqual(len(spi_buses), 1)
        self.assertEqual(spi_buses[0]["bus"], "SPI1")
        self.assertEqual(
            {device["module"] for device in spi_buses[0]["devices"]},
            {"main_bus", "flash", "display"},
        )
        module_map = {item["name"]: item for item in result.project_ir["modules"]}
        self.assertEqual(module_map["main_bus"]["interfaces"]["spi"], "SPI1")
        self.assertEqual(module_map["flash"]["interfaces"]["spi"], "SPI1")
        self.assertEqual(module_map["display"]["interfaces"]["spi"], "SPI1")

    def test_encoder_reserves_timer_and_blocks_pwm_on_same_timer(self) -> None:
        chip = ChipDefinition(
            name="TESTENC",
            device_name="TESTENC",
            vendor="TestVendor",
            family="STM32F1",
            cpu_type="Cortex-M3",
            package="LQFP48",
            flash_kb=64,
            ram_kb=20,
            irom_start=0x08000000,
            iram_start=0x20000000,
            c_define="TESTENC",
            reserved_pins=(),
            gpio_preference=("PA0", "PA1", "PA2", "PA6", "PA7"),
            adc_pins=(),
            interfaces={
                "pwm": (
                    InterfaceOption("TIM2_CH1_PA0", "pwm", "TIM2_CH1", {"out": "PA0"}),
                    InterfaceOption("TIM2_CH2_PA1", "pwm", "TIM2_CH2", {"out": "PA1"}),
                    InterfaceOption("TIM2_CH3_PA2", "pwm", "TIM2_CH3", {"out": "PA2"}),
                    InterfaceOption("TIM3_CH1_PA6", "pwm", "TIM3_CH1", {"out": "PA6"}),
                    InterfaceOption("TIM3_CH2_PA7", "pwm", "TIM3_CH2", {"out": "PA7"}),
                ),
            },
            definition_path="test:chip",
        )
        encoder = ModuleSpec(
            key="quadrature_encoder",
            display_name="Quadrature Encoder",
            summary="Uses timer encoder mode.",
            hal_components=("GPIO", "TIM"),
            template_files=(),
            resource_requests=("encoder",),
            definition_path="test:module",
        )
        pwm = ModuleSpec(
            key="pwm_output",
            display_name="PWM Output",
            summary="Uses a timer PWM output.",
            hal_components=("GPIO", "TIM"),
            template_files=(),
            resource_requests=("pwm_out",),
            definition_path="test:module",
        )
        planner = Planner(
            chip=chip,
            module_registry={"quadrature_encoder": encoder, "pwm_output": pwm},
            keep_swd=False,
        )

        encoder_only = planner.plan([ModuleRequest(kind="quadrature_encoder", name="a_wheel", options={"instance": "TIM2"})])
        self.assertTrue(encoder_only.feasible, msg=encoder_only.errors)
        self.assertEqual(encoder_only.project_ir["peripherals"]["encoder"][0]["timer"], "TIM2")
        self.assertEqual(encoder_only.project_ir["peripherals"]["encoder"][0]["pins"]["a"], "PA0")
        self.assertEqual(encoder_only.project_ir["peripherals"]["encoder"][0]["pins"]["b"], "PA1")

        planner = Planner(
            chip=chip,
            module_registry={"quadrature_encoder": encoder, "pwm_output": pwm},
            keep_swd=False,
        )
        conflict = planner.plan(
            [
                ModuleRequest(kind="quadrature_encoder", name="a_wheel", options={"instance": "TIM2"}),
                ModuleRequest(kind="pwm_output", name="z_motor_pwm", options={"instance": "TIM2_CH3"}),
            ]
        )

        self.assertFalse(conflict.feasible)
        self.assertTrue(any("TIM2_CH3" in error or "PWM" in error for error in conflict.errors), msg=conflict.errors)

    def test_timer_output_compare_conflicts_with_capture_on_same_timer(self) -> None:
        chip = ChipDefinition(
            name="TESTOC",
            device_name="TESTOC",
            vendor="TestVendor",
            family="STM32F1",
            cpu_type="Cortex-M3",
            package="LQFP48",
            flash_kb=64,
            ram_kb=20,
            irom_start=0x08000000,
            iram_start=0x20000000,
            c_define="TESTOC",
            reserved_pins=(),
            gpio_preference=("PA6", "PA7"),
            adc_pins=(),
            interfaces={
                "pwm": (
                    InterfaceOption("TIM3_CH1_PA6", "pwm", "TIM3_CH1", {"out": "PA6"}),
                    InterfaceOption("TIM3_CH2_PA7", "pwm", "TIM3_CH2", {"out": "PA7"}),
                ),
            },
            definition_path="test:chip",
        )
        timer_oc = ModuleSpec(
            key="compare_output",
            display_name="Compare Output",
            summary="Uses timer output compare.",
            hal_components=("GPIO", "TIM"),
            template_files=(),
            resource_requests=("timer_oc",),
            definition_path="test:module",
        )
        timer_ic = ModuleSpec(
            key="capture_input",
            display_name="Capture Input",
            summary="Uses timer input capture.",
            hal_components=("GPIO", "TIM"),
            template_files=(),
            resource_requests=("timer_ic",),
            definition_path="test:module",
        )
        planner = Planner(
            chip=chip,
            module_registry={"compare_output": timer_oc, "capture_input": timer_ic},
            keep_swd=False,
        )

        result = planner.plan(
            [
                ModuleRequest(kind="compare_output", name="a_compare", options={"instance": "TIM3_CH1"}),
                ModuleRequest(kind="capture_input", name="b_capture", options={"instance": "TIM3_CH2"}),
            ]
        )

        self.assertFalse(result.feasible)
        self.assertTrue(any("TIM3_CH2" in error or "capture" in error for error in result.errors), msg=result.errors)

    def test_dac_can_and_usb_resources_appear_in_project_ir(self) -> None:
        chip = ChipDefinition(
            name="TESTMIXED",
            device_name="TESTMIXED",
            vendor="TestVendor",
            family="STM32G4",
            cpu_type="Cortex-M4",
            package="LQFP64",
            flash_kb=128,
            ram_kb=32,
            irom_start=0x08000000,
            iram_start=0x20000000,
            c_define="TESTMIXED",
            reserved_pins=(),
            gpio_preference=("PA4", "PB8", "PB9", "PA11", "PA12"),
            adc_pins=(),
            interfaces={
                "dac": (
                    InterfaceOption("DAC1_CH1_PA4", "dac", "DAC1_CH1", {"out": "PA4"}),
                ),
                "can": (
                    InterfaceOption("CAN1_PB8PB9", "can", "CAN1", {"rx": "PB8", "tx": "PB9"}),
                ),
                "usb": (
                    InterfaceOption("USB_FS_DEVICE", "usb", "USB_FS", {"dm": "PA11", "dp": "PA12"}),
                ),
            },
            definition_path="test:chip",
        )
        module_registry = {
            "wave_out": ModuleSpec(
                key="wave_out",
                display_name="Wave Out",
                summary="Uses DAC output.",
                hal_components=("GPIO", "DAC"),
                template_files=(),
                resource_requests=("dac_out",),
                definition_path="test:module",
            ),
            "can_link": ModuleSpec(
                key="can_link",
                display_name="CAN Link",
                summary="Uses CAN peripheral.",
                hal_components=("GPIO", "CAN"),
                template_files=(),
                resource_requests=("can_port",),
                definition_path="test:module",
            ),
            "usb_target": ModuleSpec(
                key="usb_target",
                display_name="USB Target",
                summary="Uses USB device peripheral.",
                hal_components=("GPIO",),
                template_files=(),
                resource_requests=("usb_device",),
                definition_path="test:module",
            ),
        }
        planner = Planner(chip=chip, module_registry=module_registry, keep_swd=False)

        result = planner.plan(
            [
                ModuleRequest(kind="wave_out", name="tone_out"),
                ModuleRequest(kind="can_link", name="bus"),
                ModuleRequest(kind="usb_target", name="usb"),
            ]
        )

        self.assertTrue(result.feasible, msg=result.errors)
        peripherals = result.project_ir["peripherals"]
        self.assertEqual(peripherals["dac"][0]["dac"], "DAC1")
        self.assertEqual(peripherals["dac"][0]["channels"][0]["channel_macro"], "DAC_CHANNEL_1")
        self.assertEqual(peripherals["can"][0]["instance"], "CAN1")
        self.assertEqual(peripherals["can"][0]["pins"]["rx"], "PB8")
        self.assertEqual(peripherals["usb"][0]["instance"], "USB_FS")
        self.assertEqual(peripherals["usb"][0]["pins"]["dm"], "PA11")

    def test_advanced_timer_reservation_blocks_pwm_on_same_instance(self) -> None:
        chip = ChipDefinition(
            name="TESTADV",
            device_name="TESTADV",
            vendor="TestVendor",
            family="STM32F1",
            cpu_type="Cortex-M3",
            package="LQFP48",
            flash_kb=64,
            ram_kb=20,
            irom_start=0x08000000,
            iram_start=0x20000000,
            c_define="TESTADV",
            reserved_pins=(),
            gpio_preference=("PA8", "PA9", "PA0"),
            adc_pins=(),
            interfaces={
                "pwm": (
                    InterfaceOption("TIM1_CH1_PA8", "pwm", "TIM1_CH1", {"out": "PA8"}),
                    InterfaceOption("TIM1_CH2_PA9", "pwm", "TIM1_CH2", {"out": "PA9"}),
                    InterfaceOption("TIM2_CH1_PA0", "pwm", "TIM2_CH1", {"out": "PA0"}),
                ),
            },
            definition_path="test:chip",
        )
        advanced = ModuleSpec(
            key="motor_timer",
            display_name="Advanced Timer",
            summary="Reserves a whole advanced timer.",
            hal_components=("TIM",),
            template_files=(),
            resource_requests=("advanced_timer",),
            definition_path="test:module",
        )
        pwm = ModuleSpec(
            key="pwm_output",
            display_name="PWM Output",
            summary="Uses a PWM channel.",
            hal_components=("GPIO", "TIM"),
            template_files=(),
            resource_requests=("pwm_out",),
            definition_path="test:module",
        )
        planner = Planner(
            chip=chip,
            module_registry={"motor_timer": advanced, "pwm_output": pwm},
            keep_swd=False,
        )

        advanced_only = planner.plan([ModuleRequest(kind="motor_timer", name="motor_core")])
        self.assertTrue(advanced_only.feasible, msg=advanced_only.errors)
        self.assertEqual(advanced_only.project_ir["peripherals"]["advanced_timer"][0]["timer"], "TIM1")

        planner = Planner(
            chip=chip,
            module_registry={"motor_timer": advanced, "pwm_output": pwm},
            keep_swd=False,
        )
        conflict = planner.plan(
            [
                ModuleRequest(kind="motor_timer", name="motor_core"),
                ModuleRequest(kind="pwm_output", name="phase_a", options={"instance": "TIM1_CH1"}),
            ]
        )

        self.assertFalse(conflict.feasible)
        self.assertTrue(any("TIM1_CH1" in error or "PWM" in error for error in conflict.errors), msg=conflict.errors)

    def test_spi_timer_oc_and_encoder_codegen_emit_hal_skeletons(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(packs_root, "spi_flash", ["GPIO", "SPI"], ["spi_device"])
            self._write_module_pack(packs_root, "compare_output", ["GPIO", "TIM"], ["timer_oc"])
            self._write_module_pack(packs_root, "quadrature_encoder", ["GPIO", "TIM"], ["encoder"])
            payload = {
                "chip": "STM32F103C8T6",
                "modules": [
                    {"kind": "spi_flash", "name": "flash", "options": {"bus": "SPI2"}},
                    {"kind": "compare_output", "name": "compare_a", "options": {"instance": "TIM2_CH3"}},
                    {"kind": "quadrature_encoder", "name": "wheel", "options": {"instance": "TIM3"}},
                ],
            }

            result = scaffold_from_request(payload, Path(tmp_dir) / "mixed_timers_and_spi", packs_dir=packs_root)
            self.assertTrue(result.feasible, msg=result.errors)
            peripherals_text = (
                Path(result.project_dir) / "Core" / "Src" / "peripherals.c"
            ).read_text(encoding="utf-8")
            peripherals_header = (
                Path(result.project_dir) / "Core" / "Inc" / "peripherals.h"
            ).read_text(encoding="utf-8")
            app_config_text = (
                Path(result.project_dir) / "Core" / "Inc" / "app_config.h"
            ).read_text(encoding="utf-8")

        self.assertIn("SPI_HandleTypeDef hspi2;", peripherals_text)
        self.assertIn("void MX_SPI2_Init(void)", peripherals_text)
        self.assertIn("HAL_SPI_Init(&hspi2)", peripherals_text)
        self.assertIn("void HAL_SPI_MspInit(SPI_HandleTypeDef* hspi)", peripherals_text)
        self.assertIn("void MX_TIM2_OC_Init(void)", peripherals_text)
        self.assertIn("HAL_TIM_OC_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_3)", peripherals_text)
        self.assertIn("void HAL_TIM_OC_MspInit(TIM_HandleTypeDef* htim_oc)", peripherals_text)
        self.assertIn("void MX_TIM3_Encoder_Init(void)", peripherals_text)
        self.assertIn("HAL_TIM_Encoder_Init(&htim3, &sConfig)", peripherals_text)
        self.assertIn("void HAL_TIM_Encoder_MspInit(TIM_HandleTypeDef* htim_encoder)", peripherals_text)
        self.assertIn("extern SPI_HandleTypeDef hspi2;", peripherals_header)
        self.assertIn("void MX_TIM2_OC_Init(void);", peripherals_header)
        self.assertIn("void MX_TIM3_Encoder_Init(void);", peripherals_header)
        self.assertIn("#define FLASH_SPI_INSTANCE SPI2", app_config_text)
        self.assertIn("#define COMPARE_A_OUT_TIM_INSTANCE TIM2", app_config_text)
        self.assertIn("#define WHEEL_ENCODER_TIM_INSTANCE TIM3", app_config_text)

    def test_dac_can_and_usb_codegen_emit_hal_skeletons(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_chip_pack(
                packs_root,
                "testperiphf1.json",
                {
                    "schema_version": "1.0",
                    "kind": "chip",
                    "name": "TESTPERIPHF1",
                    "device_name": "STM32F103RB",
                    "vendor": "TestVendor",
                    "family": "STM32F1",
                    "cpu_type": "Cortex-M3",
                    "package": "LQFP64",
                    "flash_kb": 128,
                    "ram_kb": 20,
                    "irom_start": "0x08000000",
                    "iram_start": "0x20000000",
                    "c_define": "STM32F103xB",
                    "reserved_pins": [],
                    "gpio_preference": ["PA4", "PB8", "PB9", "PA11", "PA12"],
                    "adc_pins": [],
                    "adc_channels": {},
                    "interfaces": {
                        "dac": [
                            {"option_id": "DAC1_CH1_PA4", "kind": "dac", "instance": "DAC1_CH1", "signals": {"out": "PA4"}}
                        ],
                        "can": [
                            {"option_id": "CAN1_PB8PB9", "kind": "can", "instance": "CAN1", "signals": {"rx": "PB8", "tx": "PB9"}}
                        ],
                        "usb": [
                            {"option_id": "USB_FS", "kind": "usb", "instance": "USB_FS", "signals": {"dm": "PA11", "dp": "PA12"}}
                        ],
                    },
                    "dma_channels": [],
                    "dma_request_map": {},
                    "sources": ["unit-test"],
                },
            )
            self._write_module_pack(packs_root, "wave_out", ["GPIO", "DAC"], ["dac_out"])
            self._write_module_pack(packs_root, "can_link", ["GPIO", "CAN"], ["can_port"])
            self._write_module_pack(packs_root, "usb_target", ["GPIO", "PCD"], ["usb_device"])
            payload = {
                "chip": "TESTPERIPHF1",
                "modules": [
                    {"kind": "wave_out", "name": "tone_out"},
                    {"kind": "can_link", "name": "bus"},
                    {"kind": "usb_target", "name": "usb"},
                ],
            }

            result = scaffold_from_request(payload, Path(tmp_dir) / "dac_can_usb", packs_dir=packs_root)
            self.assertTrue(result.feasible, msg=result.errors)
            peripherals_text = (
                Path(result.project_dir) / "Core" / "Src" / "peripherals.c"
            ).read_text(encoding="utf-8")
            irq_text = (
                Path(result.project_dir) / "Core" / "Src" / "stm32f1xx_it.c"
            ).read_text(encoding="utf-8")
            main_text = (
                Path(result.project_dir) / "Core" / "Src" / "main.c"
            ).read_text(encoding="utf-8")
            hal_conf_text = (
                Path(result.project_dir) / "Core" / "Inc" / "stm32f1xx_hal_conf.h"
            ).read_text(encoding="utf-8")

        self.assertIn("DAC_HandleTypeDef hdac1;", peripherals_text)
        self.assertIn("void MX_DAC1_Init(void)", peripherals_text)
        self.assertIn("HAL_DAC_ConfigChannel(&hdac1, &sConfig, DAC_CHANNEL_1)", peripherals_text)
        self.assertIn("void HAL_DAC_MspInit(DAC_HandleTypeDef* hdac)", peripherals_text)
        self.assertIn("CAN_HandleTypeDef hcan1;", peripherals_text)
        self.assertIn("void MX_CAN1_Init(void)", peripherals_text)
        self.assertIn("HAL_CAN_Init(&hcan1)", peripherals_text)
        self.assertIn("void HAL_CAN_MspInit(CAN_HandleTypeDef* hcan)", peripherals_text)
        self.assertIn("PCD_HandleTypeDef hpcd_usb_fs;", peripherals_text)
        self.assertIn("void MX_USB_FS_Init(void)", peripherals_text)
        self.assertIn("HAL_PCD_Init(&hpcd_usb_fs)", peripherals_text)
        self.assertIn("void HAL_PCD_MspInit(PCD_HandleTypeDef* hpcd)", peripherals_text)
        self.assertIn("MX_DAC1_Init();", main_text)
        self.assertIn("MX_CAN1_Init();", main_text)
        self.assertIn("MX_USB_FS_Init();", main_text)
        self.assertIn("MX_NVIC_Init();", main_text)
        self.assertIn("void USB_LP_CAN1_RX0_IRQHandler(void)", irq_text)
        self.assertIn("HAL_PCD_IRQHandler(&hpcd_usb_fs);", irq_text)
        self.assertIn("HAL_DAC_MODULE_ENABLED", hal_conf_text)
        self.assertIn("HAL_CAN_MODULE_ENABLED", hal_conf_text)
        self.assertIn("HAL_PCD_MODULE_ENABLED", hal_conf_text)
        self.assertIn('stm32f1xx_hal_dac.h', hal_conf_text)
        self.assertIn('stm32f1xx_hal_can.h', hal_conf_text)
        self.assertIn('stm32f1xx_hal_pcd.h', hal_conf_text)

    def test_real_f103_pack_can_and_usb_can_coexist_via_remap(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(packs_root, "can_link", ["GPIO", "CAN"], ["can_port"])
            self._write_module_pack(packs_root, "usb_target", ["GPIO", "PCD"], ["usb_device"])

            plan = plan_request(
                {
                    "chip": "STM32F103C8T6",
                    "modules": [
                        {"kind": "can_link", "name": "bus"},
                        {"kind": "usb_target", "name": "usb"},
                    ],
                },
                packs_dir=packs_root,
            )

        self.assertTrue(plan.feasible, msg=plan.errors)
        module_map = {item["name"]: item for item in plan.project_ir["modules"]}
        self.assertEqual(module_map["bus"]["interfaces"]["can"], "CAN1")
        self.assertEqual(module_map["usb"]["interfaces"]["usb"], "USB_FS")
        signals = {(item.module, item.pin) for item in plan.assignments}
        self.assertIn(("bus", "PB8"), signals)
        self.assertIn(("bus", "PB9"), signals)
        self.assertIn(("usb", "PA11"), signals)
        self.assertIn(("usb", "PA12"), signals)

    def test_real_g431_pack_dac_can_and_usb_plan_together(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(packs_root, "wave_out", ["GPIO", "DAC"], ["dac_out"])
            self._write_module_pack(packs_root, "can_link", ["GPIO", "CAN"], ["can_port"])
            self._write_module_pack(packs_root, "usb_target", ["GPIO", "PCD"], ["usb_device"])

            plan = plan_request(
                {
                    "chip": "STM32G431RBT6",
                    "modules": [
                        {"kind": "wave_out", "name": "tone"},
                        {"kind": "can_link", "name": "bus"},
                        {"kind": "usb_target", "name": "usb"},
                    ],
                },
                packs_dir=packs_root,
            )

        self.assertTrue(plan.feasible, msg=plan.errors)
        module_map = {item["name"]: item for item in plan.project_ir["modules"]}
        self.assertEqual(module_map["tone"]["interfaces"]["dac"], "DAC1")
        self.assertEqual(module_map["bus"]["interfaces"]["can"], "FDCAN1")
        self.assertEqual(module_map["usb"]["interfaces"]["usb"], "USB_FS")
        signals = {(item.module, item.pin) for item in plan.assignments}
        self.assertIn(("tone", "PA4"), signals)
        self.assertIn(("bus", "PB8"), signals)
        self.assertIn(("bus", "PB9"), signals)
        self.assertIn(("usb", "PA11"), signals)
        self.assertIn(("usb", "PA12"), signals)

    def test_resource_kind_board_preferences_can_steer_generic_spi_and_can_resources(self) -> None:
        chip = ChipDefinition(
            name="TESTBOARDPREF",
            device_name="TESTBOARDPREF",
            vendor="TestVendor",
            family="STM32F1",
            cpu_type="Cortex-M3",
            package="LQFP64",
            flash_kb=128,
            ram_kb=20,
            irom_start=0x08000000,
            iram_start=0x20000000,
            c_define="TESTBOARDPREF",
            reserved_pins=(),
            gpio_preference=("PA4", "PA5", "PA6", "PA7", "PB8", "PB9", "PB12", "PB13", "PB14", "PB15"),
            adc_pins=(),
            interfaces={
                "spi": (
                    InterfaceOption(
                        "SPI1_DEFAULT",
                        "spi",
                        "SPI1",
                        {"nss": "PA4", "sck": "PA5", "miso": "PA6", "mosi": "PA7"},
                        shareable=True,
                    ),
                    InterfaceOption(
                        "SPI2_DEFAULT",
                        "spi",
                        "SPI2",
                        {"nss": "PB12", "sck": "PB13", "miso": "PB14", "mosi": "PB15"},
                        shareable=True,
                    ),
                ),
                "can": (
                    InterfaceOption("CAN1_DEFAULT", "can", "CAN1", {"rx": "PA11", "tx": "PA12"}),
                    InterfaceOption("CAN1_REMAP", "can", "CAN1", {"rx": "PB8", "tx": "PB9"}),
                ),
            },
            definition_path="test:chip",
        )
        board_profile = BoardProfile(
            key="test_board_pref",
            display_name="Test Board Pref",
            summary="Board-level generic peripheral preferences.",
            chip=chip.name,
            preferred_signals={
                "spi_device.nss": ("PB12",),
                "spi_device.sck": ("PB13",),
                "spi_device.miso": ("PB14",),
                "spi_device.mosi": ("PB15",),
                "can_port.rx": ("PB8",),
                "can_port.tx": ("PB9",),
            },
            definition_path="test:board",
        )
        module_registry = {
            "spi_flash": ModuleSpec(
                key="spi_flash",
                display_name="SPI Flash",
                summary="Uses a shared SPI bus.",
                hal_components=("GPIO", "SPI"),
                template_files=(),
                resource_requests=("spi_device",),
                definition_path="test:module",
            ),
            "can_link": ModuleSpec(
                key="can_link",
                display_name="CAN Link",
                summary="Uses a CAN peripheral.",
                hal_components=("GPIO", "CAN"),
                template_files=(),
                resource_requests=("can_port",),
                definition_path="test:module",
            ),
        }

        planner = Planner(
            chip=chip,
            module_registry=module_registry,
            board="test_board_pref",
            board_profile=board_profile,
            keep_swd=False,
        )
        result = planner.plan(
            [
                ModuleRequest(kind="spi_flash", name="flash"),
                ModuleRequest(kind="can_link", name="bus"),
            ]
        )

        self.assertTrue(result.feasible, msg=result.errors)
        module_map = {item["name"]: item for item in result.project_ir["modules"]}
        self.assertEqual(module_map["flash"]["interfaces"]["spi"], "SPI2")
        self.assertEqual(module_map["bus"]["interfaces"]["can"], "CAN1")
        signals = {(item.module, item.pin) for item in result.assignments}
        self.assertIn(("flash", "PB12"), signals)
        self.assertIn(("flash", "PB13"), signals)
        self.assertIn(("flash", "PB14"), signals)
        self.assertIn(("flash", "PB15"), signals)
        self.assertIn(("bus", "PB8"), signals)
        self.assertIn(("bus", "PB9"), signals)

    def test_real_blue_pill_board_prefers_can_remap_for_generic_can_port(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            self._write_module_pack(packs_root, "can_link", ["GPIO", "CAN"], ["can_port"])

            plan = plan_request(
                {
                    "board": "blue_pill_f103c8",
                    "modules": [
                        {"kind": "can_link", "name": "bus"},
                    ],
                },
                packs_dir=packs_root,
            )

        self.assertTrue(plan.feasible, msg=plan.errors)
        signals = {(item.module, item.pin) for item in plan.assignments}
        self.assertIn(("bus", "PB8"), signals)
        self.assertIn(("bus", "PB9"), signals)
        self.assertNotIn(("bus", "PA11"), signals)
        self.assertNotIn(("bus", "PA12"), signals)

    def test_catalog_reference_constants_include_new_can_usb_and_dac_interfaces(self) -> None:
        self.assertEqual(
            {option.option_id for option in STM32F103C8T6.interfaces["can"]},
            {"CAN1_DEFAULT", "CAN1_REMAP"},
        )
        self.assertEqual(
            {option.option_id for option in STM32F103RBT6.interfaces["usb"]},
            {"USB_FS_DEFAULT"},
        )
        self.assertEqual(
            {option.option_id for option in STM32G431RBT6.interfaces["dac"]},
            {"DAC1_CH1_PA4", "DAC1_CH2_PA5"},
        )
        self.assertEqual(
            {option.option_id for option in STM32G431RBT6.interfaces["can"]},
            {"FDCAN1_DEFAULT", "FDCAN1_PB8_PB9"},
        )
        self.assertEqual(
            {option.option_id for option in STM32G431RBT6.interfaces["usb"]},
            {"USB_FS_DEFAULT"},
        )

    def test_board_retrieval_chunks_render_capability_display_names(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_root = self._clone_packs_tree(tmp_dir)
            registry = load_catalog(packs_root)
            board_chunks = [
                chunk for chunk in _catalog_chunks(registry)
                if chunk.get("metadata", {}).get("doc_type") == "board_def"
            ]

        blue_pill_chunk = next(
            chunk for chunk in board_chunks
            if chunk.get("metadata", {}).get("board_name") == "blue_pill_f103c8"
        )
        nucleo_chunk = next(
            chunk for chunk in board_chunks
            if chunk.get("metadata", {}).get("board_name") == "nucleo_f103rb"
        )

        self.assertIn("On-board LED", str(blue_pill_chunk.get("content", "")))
        self.assertIn("USB FS device pins", str(blue_pill_chunk.get("content", "")))
        self.assertIn("ST-LINK Virtual COM Port", str(nucleo_chunk.get("content", "")))
        self.assertIn("Arduino SPI header routing", str(nucleo_chunk.get("content", "")))

    def test_cubemx_import_parses_can_usb_and_dac_interfaces(self) -> None:
        xml_text = """<?xml version="1.0" encoding="UTF-8"?>
<Mcu RefName="STM32TEST123" Family="STM32G4" Package="LQFP48">
  <Core>Cortex-M4</Core>
  <Flash>128</Flash>
  <Ram>32</Ram>
  <Pin Name="PA4">
    <Signal Name="DAC1_OUT1" />
  </Pin>
  <Pin Name="PA11">
    <Signal Name="FDCAN1_RX" />
    <Signal Name="USB_DM" />
  </Pin>
  <Pin Name="PA12">
    <Signal Name="FDCAN1_TX" />
    <Signal Name="USB_DP" />
  </Pin>
  <Pin Name="PB8">
    <Signal Name="FDCAN1_RX" />
  </Pin>
  <Pin Name="PB9">
    <Signal Name="FDCAN1_TX" />
  </Pin>
</Mcu>
"""
        with TemporaryDirectory() as tmp_dir:
            xml_path = Path(tmp_dir) / "stm32test123.xml"
            xml_path.write_text(xml_text, encoding="utf-8")
            manifest, warnings = build_chip_manifest_from_cubemx_xml(xml_path, chip_name="STM32TEST123")

        self.assertEqual(manifest["name"], "STM32TEST123")
        self.assertIn("dac", manifest["interfaces"])
        self.assertIn("can", manifest["interfaces"])
        self.assertIn("usb", manifest["interfaces"])
        self.assertEqual(manifest["interfaces"]["dac"][0]["instance"], "DAC1_CH1")
        can_options = {item["option_id"]: item for item in manifest["interfaces"]["can"]}
        self.assertIn("FDCAN1_PA11_PA12", can_options)
        self.assertIn("FDCAN1_PB8_PB9", can_options)
        usb_option = manifest["interfaces"]["usb"][0]
        self.assertEqual(usb_option["instance"], "USB_FS")
        self.assertEqual(usb_option["signals"]["dm"], "PA11")
        self.assertEqual(usb_option["signals"]["dp"], "PA12")
        self.assertIsInstance(warnings, list)


if __name__ == "__main__":
    unittest.main()
