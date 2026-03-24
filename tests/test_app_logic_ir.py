from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stm32_agent.app_logic_ir import render_app_logic_from_ir
from stm32_agent.keil_generator import scaffold_from_request


class AppLogicIrTests(unittest.TestCase):
    def test_render_app_logic_ir_generates_periodic_tasks_and_state_machine(self) -> None:
        sections = render_app_logic_from_ir(
            {},
            {
                "types": [
                    {
                        "kind": "enum",
                        "name": "AppState",
                        "values": ["APP_STATE_BOOT", "APP_STATE_RUN"],
                    }
                ],
                "globals": [
                    {
                        "name": "g_app_state",
                        "type": "AppState",
                        "init": "APP_STATE_BOOT",
                    }
                ],
                "init": [
                    '(void)DebugUart_WriteLine(&huart1, "boot ok", 100);',
                ],
                "loop": {
                    "tasks": [
                        {
                            "name": "heartbeat",
                            "every_ms": 1000,
                            "run": ['(void)DebugUart_WriteLine(&huart1, "heartbeat", 100);'],
                        }
                    ],
                    "state_machine": {
                        "state_var": "g_app_state",
                        "states": [
                            {
                                "name": "APP_STATE_BOOT",
                                "run": ["g_app_state = APP_STATE_RUN;"],
                            },
                            {
                                "name": "APP_STATE_RUN",
                                "run": ["/* steady state */"],
                            },
                        ],
                    },
                },
            },
        )

        self.assertIn("typedef enum", sections["AppTop"])
        self.assertIn("static uint32_t g_app_task_heartbeat_last_run_ms = 0U;", sections["AppTop"])
        self.assertIn("static AppState g_app_state = APP_STATE_BOOT;", sections["AppTop"])
        self.assertIn('DebugUart_WriteLine(&huart1, "boot ok", 100);', sections["AppInit"])
        self.assertIn("switch (g_app_state)", sections["AppLoop"])
        self.assertIn("case APP_STATE_BOOT:", sections["AppLoop"])
        self.assertIn("g_app_state = APP_STATE_RUN;", sections["AppLoop"])
        self.assertIn("g_app_task_heartbeat_last_run_ms", sections["AppLoop"])
        self.assertIn('DebugUart_WriteLine(&huart1, "heartbeat", 100);', sections["AppLoop"])

    def test_render_app_logic_ir_supports_guarded_transitions(self) -> None:
        sections = render_app_logic_from_ir(
            {},
            {
                "globals": [
                    {
                        "name": "g_app_state",
                        "type": "uint8_t",
                        "init": "0U",
                    }
                ],
                "loop": {
                    "state_machine": {
                        "state_var": "g_app_state",
                        "states": [
                            {
                                "name": "0U",
                                "run": ["/* boot work */"],
                                "transitions": [
                                    {
                                        "guard": "Boot_IsReady()",
                                        "actions": ['(void)DebugUart_WriteLine(&huart1, "boot -> run", 100);'],
                                        "target": "1U",
                                    }
                                ],
                            },
                            {
                                "name": "1U",
                                "run": ["/* running */"],
                            },
                        ],
                    },
                },
            },
        )

        self.assertIn("if (Boot_IsReady()) {", sections["AppLoop"])
        self.assertIn('DebugUart_WriteLine(&huart1, "boot -> run", 100);', sections["AppLoop"])
        self.assertIn("g_app_state = 1U;", sections["AppLoop"])
        self.assertIn("break;", sections["AppLoop"])

    def test_render_app_logic_ir_supports_event_and_timeout_transitions(self) -> None:
        sections = render_app_logic_from_ir(
            {},
            {
                "globals": [
                    {
                        "name": "g_app_state",
                        "type": "AppState",
                        "init": "APP_STATE_WAIT",
                    }
                ],
                "loop": {
                    "state_machine": {
                        "state_var": "g_app_state",
                        "states": [
                            {
                                "name": "APP_STATE_WAIT",
                                "transitions": [
                                    {
                                        "event": "Button_StartPressed()",
                                        "after_ms": 500,
                                        "guard": "Sensor_IsReady()",
                                        "actions": ['(void)DebugUart_WriteLine(&huart1, "wait -> run", 100);'],
                                        "target": "APP_STATE_RUN",
                                    }
                                ],
                            },
                            {
                                "name": "APP_STATE_RUN",
                                "run": ["/* running */"],
                            },
                        ],
                    },
                },
            },
        )

        self.assertIn("static uint32_t g_app_state_entered_ms = 0U;", sections["AppTop"])
        self.assertIn("g_app_state_entered_ms = HAL_GetTick();", sections["AppInit"])
        self.assertIn("(HAL_GetTick() - g_app_state_entered_ms) >= 500U", sections["AppLoop"])
        self.assertIn("Button_StartPressed()", sections["AppLoop"])
        self.assertIn("Sensor_IsReady()", sections["AppLoop"])
        self.assertIn("g_app_state = APP_STATE_RUN;", sections["AppLoop"])
        self.assertIn("g_app_state_entered_ms = HAL_GetTick();", sections["AppLoop"])

    def test_render_app_logic_ir_supports_named_events_with_clear_actions(self) -> None:
        sections = render_app_logic_from_ir(
            {},
            {
                "globals": [
                    {
                        "name": "g_app_state",
                        "type": "uint8_t",
                        "init": "0U",
                    },
                    {
                        "name": "g_start_requested",
                        "type": "uint8_t",
                        "init": "0U",
                    },
                ],
                "loop": {
                    "events": [
                        {
                            "name": "start_request",
                            "condition": "g_start_requested != 0U",
                            "clear_actions": ["g_start_requested = 0U;"],
                        }
                    ],
                    "state_machine": {
                        "state_var": "g_app_state",
                        "states": [
                            {
                                "name": "0U",
                                "transitions": [
                                    {
                                        "event": "start_request",
                                        "actions": ['(void)DebugUart_WriteLine(&huart1, "start accepted", 100);'],
                                        "target": "1U",
                                    }
                                ],
                            },
                            {
                                "name": "1U",
                                "run": ["/* run */"],
                            },
                        ],
                    },
                },
            },
        )

        self.assertIn("g_start_requested != 0U", sections["AppLoop"])
        self.assertIn("g_start_requested = 0U;", sections["AppLoop"])
        self.assertIn('DebugUart_WriteLine(&huart1, "start accepted", 100);', sections["AppLoop"])
        self.assertIn("g_app_state = 1U;", sections["AppLoop"])

    def test_scaffold_from_request_uses_app_logic_ir_when_sections_are_empty(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {
                    "kind": "uart_debug",
                    "name": "debug_port",
                    "options": {"instance": "USART1"},
                }
            ],
            "app_logic": {
                "AppTop": "",
                "AppInit": "",
                "AppLoop": "",
                "AppCallbacks": "",
            },
            "app_logic_ir": {
                "types": [
                    {
                        "kind": "enum",
                        "name": "AppState",
                        "values": ["APP_STATE_BOOT", "APP_STATE_RUN"],
                    }
                ],
                "globals": [
                    {
                        "name": "g_app_state",
                        "type": "AppState",
                        "init": "APP_STATE_BOOT",
                    }
                ],
                "init": [
                    '(void)DebugUart_WriteLine(&huart1, "boot ok", 100);',
                ],
                "loop": {
                    "tasks": [
                        {
                            "name": "heartbeat",
                            "every_ms": 1000,
                            "run": ['(void)DebugUart_WriteLine(&huart1, "heartbeat", 100);'],
                        }
                    ],
                    "state_machine": {
                        "state_var": "g_app_state",
                        "states": [
                            {
                                "name": "APP_STATE_BOOT",
                                "run": ["/* boot state */"],
                                "transitions": [
                                    {
                                        "guard": "Boot_IsReady()",
                                        "actions": ['(void)DebugUart_WriteLine(&huart1, "boot -> run", 100);'],
                                        "target": "APP_STATE_RUN",
                                    }
                                ],
                            },
                            {
                                "name": "APP_STATE_RUN",
                                "run": ["/* steady state */"],
                            },
                        ],
                    },
                },
            },
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "ir_project")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn("typedef enum", app_main_text)
        self.assertIn("g_app_task_heartbeat_last_run_ms", app_main_text)
        self.assertIn('DebugUart_WriteLine(&huart1, "boot ok", 100);', app_main_text)
        self.assertIn('DebugUart_WriteLine(&huart1, "heartbeat", 100);', app_main_text)
        self.assertIn("switch (g_app_state)", app_main_text)
        self.assertIn("case APP_STATE_BOOT:", app_main_text)
        self.assertIn("if (Boot_IsReady()) {", app_main_text)
        self.assertIn('DebugUart_WriteLine(&huart1, "boot -> run", 100);', app_main_text)
        self.assertIn("g_app_state = APP_STATE_RUN;", app_main_text)

    def test_scaffold_from_request_renders_timeout_triggered_state_machine(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {
                    "kind": "uart_debug",
                    "name": "debug_port",
                    "options": {"instance": "USART1"},
                }
            ],
            "app_logic_ir": {
                "globals": [
                    {
                        "name": "g_app_state",
                        "type": "uint8_t",
                        "init": "0U",
                    }
                ],
                "loop": {
                    "state_machine": {
                        "state_var": "g_app_state",
                        "states": [
                            {
                                "name": "0U",
                                "transitions": [
                                    {
                                        "event": "Boot_IsReady()",
                                        "after_ms": 300,
                                        "actions": ['(void)DebugUart_WriteLine(&huart1, "boot timeout ok", 100);'],
                                        "target": "1U",
                                    }
                                ],
                            },
                            {
                                "name": "1U",
                                "run": ["/* run */"],
                            },
                        ],
                    },
                },
            },
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "ir_timeout_project")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn("static uint32_t g_app_state_entered_ms = 0U;", app_main_text)
        self.assertIn("g_app_state_entered_ms = HAL_GetTick();", app_main_text)
        self.assertIn("(HAL_GetTick() - g_app_state_entered_ms) >= 300U", app_main_text)
        self.assertIn("Boot_IsReady()", app_main_text)
        self.assertIn('DebugUart_WriteLine(&huart1, "boot timeout ok", 100);', app_main_text)

    def test_render_app_logic_ir_supports_retry_and_failure_branches(self) -> None:
        sections = render_app_logic_from_ir(
            {},
            {
                "globals": [
                    {
                        "name": "g_app_state",
                        "type": "uint8_t",
                        "init": "0U",
                    }
                ],
                "loop": {
                    "state_machine": {
                        "state_var": "g_app_state",
                        "states": [
                            {
                                "name": "0U",
                                "transitions": [
                                    {
                                        "after_ms": 200,
                                        "max_retries": 3,
                                        "retry_target": "0U",
                                        "retry_actions": ["Comm_Restart();"],
                                        "failure_target": "2U",
                                        "failure_actions": ['(void)DebugUart_WriteLine(&huart1, "comm failed", 100);'],
                                    }
                                ],
                            },
                            {
                                "name": "2U",
                                "run": ["/* error */"],
                            },
                        ],
                    },
                },
            },
        )

        self.assertIn("static uint32_t g_app_state_retry_count = 0U;", sections["AppTop"])
        self.assertIn("g_app_state_retry_count = 0U;", sections["AppInit"])
        self.assertIn("if (g_app_state_retry_count < 3U) {", sections["AppLoop"])
        self.assertIn("g_app_state_retry_count++;", sections["AppLoop"])
        self.assertIn("Comm_Restart();", sections["AppLoop"])
        self.assertIn("g_app_state_retry_count = 0U;", sections["AppLoop"])
        self.assertIn("g_app_state = 2U;", sections["AppLoop"])
        self.assertIn('DebugUart_WriteLine(&huart1, "comm failed", 100);', sections["AppLoop"])

    def test_scaffold_from_request_renders_retry_and_failure_state_machine(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {
                    "kind": "uart_debug",
                    "name": "debug_port",
                    "options": {"instance": "USART1"},
                }
            ],
            "app_logic_ir": {
                "globals": [
                    {
                        "name": "g_app_state",
                        "type": "uint8_t",
                        "init": "0U",
                    }
                ],
                "loop": {
                    "state_machine": {
                        "state_var": "g_app_state",
                        "states": [
                            {
                                "name": "0U",
                                "transitions": [
                                    {
                                        "after_ms": 200,
                                        "max_retries": 2,
                                        "retry_target": "0U",
                                        "retry_actions": ["Comm_Restart();"],
                                        "failure_target": "2U",
                                        "failure_actions": ['(void)DebugUart_WriteLine(&huart1, "comm failed", 100);'],
                                    }
                                ],
                            },
                            {
                                "name": "2U",
                                "run": ["/* error */"],
                            },
                        ],
                    },
                },
            },
        }

        with TemporaryDirectory() as tmp_dir:
            result = scaffold_from_request(payload, Path(tmp_dir) / "ir_retry_project")
            self.assertTrue(result.feasible, msg=result.errors)
            app_main_text = (
                Path(result.project_dir) / "App" / "Src" / "app_main.c"
            ).read_text(encoding="utf-8")

        self.assertIn("static uint32_t g_app_state_retry_count = 0U;", app_main_text)
        self.assertIn("if (g_app_state_retry_count < 2U) {", app_main_text)
        self.assertIn("Comm_Restart();", app_main_text)
        self.assertIn("g_app_state = 2U;", app_main_text)
        self.assertIn('DebugUart_WriteLine(&huart1, "comm failed", 100);', app_main_text)


if __name__ == "__main__":
    unittest.main()
