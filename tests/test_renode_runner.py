from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from stm32_agent.renode_runner import (
    derive_runtime_expectation_payload,
    doctor_renode_project,
    RenodeExecutionCapture,
    RenodeSocketTerminal,
    render_renode_script,
    run_renode_project,
)


class RenodeRunnerTests(unittest.TestCase):
    def _write_project(self, tmp_dir: str, chip: str = "STM32F103C8T6") -> tuple[Path, Path]:
        project_dir = Path(tmp_dir) / "demo_project"
        mdk_dir = project_dir / "MDK-ARM"
        objects_dir = mdk_dir / "Objects"
        main_source = project_dir / "Core" / "Src"
        objects_dir.mkdir(parents=True, exist_ok=True)
        main_source.mkdir(parents=True, exist_ok=True)

        (mdk_dir / "demo.uvprojx").write_text("<Project />\n", encoding="utf-8")
        (objects_dir / "demo.axf").write_text("fake axf\n", encoding="utf-8")
        (objects_dir / "demo.map").write_text(
            "    main                                     0x080014AF   Thumb Code    30  main.o(i.main)\n",
            encoding="utf-8",
        )
        (main_source / "main.c").write_text(
            "\n".join(
                [
                    "int main(void)",
                    "{",
                    "    HAL_Init();",
                    "    SystemClock_Config();",
                    "    MX_GPIO_Init();",
                    "    return 0;",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (project_dir / "project_ir.json").write_text(
            json.dumps(
                {
                    "target": {
                        "chip": chip,
                        "family": "STM32F1" if chip.startswith("STM32F103") else "STM32G4",
                        "board": "test_board",
                    },
                    "constraints": {
                        "clock_plan": {
                            "system_clock_config": (
                                [
                                    "RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;",
                                    "RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;",
                                ]
                                if chip.startswith("STM32F103")
                                else []
                            )
                        }
                    },
                    "modules": [
                        {
                            "name": "uart_console",
                            "interfaces": {
                                "uart": "USART1",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        renode_exe = Path(tmp_dir) / "renode.exe"
        renode_exe.write_text("fake renode exe\n", encoding="utf-8")
        return project_dir, renode_exe

    def test_doctor_accepts_stm32f103_project(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")

            result = doctor_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.5)

        self.assertTrue(result.ready, msg=result.errors)
        self.assertEqual(result.platform_key, "stm32f103")
        self.assertEqual(result.platform_path, "platforms/cpus/stm32f103.repl")
        self.assertEqual(result.uart_analyzers, ["usart1"])
        self.assertTrue(result.script_path.endswith("demo.resc"))

    def test_doctor_rejects_unsupported_target(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32G431RBT6")

            result = doctor_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.5)

        self.assertFalse(result.ready)
        self.assertTrue(any("currently available only" in error for error in result.errors), msg=result.errors)

    def test_derive_runtime_expectation_payload_merges_structured_acceptance(self) -> None:
        payload = derive_runtime_expectation_payload(
            project_ir={
                "build": {
                    "app_logic_ir": {
                        "acceptance": {
                            "uart_contains": ["boot ok"],
                            "uart_sequence": ["boot ok", "ready"],
                            "uart_not_contains": ["panic"],
                            "log_not_contains": ["[SIM][LED] status_led_after_boot=0"],
                        }
                    }
                }
            }
        )

        self.assertEqual(payload["uart_contains"], ["boot ok"])
        self.assertEqual(payload["uart_sequence"], ["boot ok", "ready"])
        self.assertEqual(payload["uart_not_contains"], ["panic"])
        self.assertEqual(payload["log_not_contains"], ["[SIM][LED] status_led_after_boot=0"])

    def test_render_script_includes_platform_binary_and_run_window(self) -> None:
        script = render_renode_script(
            binary_path=Path(r"D:\demo\firmware.axf"),
            platform_path="platforms/cpus/stm32f103.repl",
            uart_analyzers=["usart1"],
            run_seconds=0.25,
        )

        self.assertIn("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl", script)
        self.assertIn("showAnalyzer usart1", script)
        self.assertIn('sysbus LoadELF "D:/demo/firmware.axf"', script)
        self.assertIn('emulation RunFor "0.25"', script)
        self.assertTrue(script.rstrip().endswith("quit"))

    def test_render_script_can_use_socket_terminals_for_uart_capture(self) -> None:
        script = render_renode_script(
            binary_path=Path(r"D:\demo\firmware.axf"),
            platform_path="platforms/cpus/stm32f103.repl",
            uart_analyzers=["usart1"],
            run_seconds=0.5,
            uart_terminals=[RenodeSocketTerminal(name="uart_capture_1", uart_name="usart1", port=3456)],
        )

        self.assertIn('emulation CreateServerSocketTerminal 3456 "uart_capture_1" false', script)
        self.assertIn("connector Connect sysbus.usart1 uart_capture_1", script)
        self.assertNotIn("showAnalyzer usart1", script)

    def test_run_renode_project_adds_f103_clock_skip_patch_for_generated_projects(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n",
                uart_output={"usart1": "boot ok\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.1)

            script_text = Path(result.script_path).read_text(encoding="utf-8")
            self.assertIn("sysbus WriteDoubleWord 0x080014B2 0xBF00BF00", script_text)
            self.assertTrue(result.applied_patches)
            self.assertTrue(any("skips SystemClock_Config" in item for item in result.applied_patches))

    def test_run_renode_project_writes_script_and_log(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Log started\nMachine booted\n",
                uart_output={"usart1": "boot ok\nheartbeat\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed) as mocked_run:
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.1)

            self.assertTrue(result.ran, msg=result.errors)
            self.assertTrue(Path(result.script_path).exists())
            self.assertTrue(Path(result.log_path).exists())
            self.assertIn("Machine booted", Path(result.log_path).read_text(encoding="utf-8"))
            self.assertTrue(Path(result.uart_capture_path).exists())
            self.assertIn("boot ok", Path(result.uart_capture_path).read_text(encoding="utf-8"))
            mocked_run.assert_called_once()

    def test_run_renode_project_auto_generates_uart_expectations_from_project_ir_app_logic(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            project_ir_path = project_dir / "project_ir.json"
            payload = json.loads(project_ir_path.read_text(encoding="utf-8"))
            payload["build"] = {
                "app_logic": {
                    "AppInit": '(void)DebugUart_WriteLine(&huart1, "boot ok", 100);',
                    "AppLoop": 'DebugUart_WriteLine(&huart1, "heartbeat", 100);',
                }
            }
            project_ir_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n",
                uart_output={"usart1": "boot ok\nheartbeat\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.1)

            expect_path = project_dir / "renode_expect.json"
            self.assertTrue(expect_path.exists())
            expect_payload = json.loads(expect_path.read_text(encoding="utf-8"))
            self.assertEqual(expect_payload["uart_contains"], ["boot ok", "heartbeat"])
            self.assertEqual(expect_payload["uart_sequence"], ["boot ok", "heartbeat"])
            self.assertTrue(result.ran, msg=result.errors)
            self.assertTrue(result.validation_passed)
            self.assertEqual(result.expectations["uart_contains"], ["boot ok", "heartbeat"])
            self.assertTrue(any("Generated ordered Renode UART expectations" in item for item in result.warnings))

    def test_run_renode_project_can_fail_on_missing_expected_uart_text(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            (project_dir / "renode_expect.json").write_text(
                json.dumps({"uart_contains": ["boot ok", "heartbeat"]}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n",
                uart_output={"usart1": "boot ok\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.1)

            self.assertFalse(result.ran)
            self.assertEqual(result.expected_uart_contains, ["boot ok", "heartbeat"])
            self.assertEqual(result.matched_uart_contains, ["boot ok"])
            self.assertEqual(result.missing_uart_contains, ["heartbeat"])
            self.assertFalse(result.validation_passed)

    def test_run_renode_project_supports_extended_runtime_expectations(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            (project_dir / "renode_expect.json").write_text(
                json.dumps(
                    {
                        "uart_contains": ["boot ok"],
                        "uart_any_contains": ["heartbeat", "tick"],
                        "uart_not_contains": ["panic"],
                        "uart_sequence": ["boot ok", "heartbeat"],
                        "exit_code": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n",
                uart_output={"usart1": "boot ok\nheartbeat\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.1)

            self.assertTrue(result.ran)
            self.assertTrue(result.validation_passed)
            self.assertEqual(result.expectations["uart_any_contains"], ["heartbeat", "tick"])
            self.assertTrue(result.validation_details["checks"]["uart_any_contains"]["passed"])
            self.assertTrue(result.validation_details["checks"]["uart_not_contains"]["passed"])
            self.assertTrue(result.validation_details["checks"]["uart_sequence"]["passed"])
            self.assertTrue(result.validation_details["checks"]["exit_code"]["passed"])

    def test_run_renode_project_reports_forbidden_and_sequence_failures(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            (project_dir / "renode_expect.json").write_text(
                json.dumps(
                    {
                        "uart_not_contains": ["panic"],
                        "uart_sequence": ["boot ok", "heartbeat", "done"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n",
                uart_output={"usart1": "boot ok\npanic\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.1)

            self.assertFalse(result.ran)
            self.assertFalse(result.validation_passed)
            self.assertEqual(result.validation_details["checks"]["uart_not_contains"]["matched"], ["panic"])
            self.assertEqual(result.validation_details["checks"]["uart_sequence"]["missing"], ["heartbeat", "done"])
            self.assertTrue(any("forbidden text" in item.lower() for item in result.errors))

    def test_run_renode_project_can_pass_validation_even_if_process_times_out(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            (project_dir / "renode_expect.json").write_text(
                json.dumps(
                    {
                        "uart_contains": ["boot ok", "heartbeat"],
                        "uart_sequence": ["boot ok", "heartbeat"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            completed = RenodeExecutionCapture(
                exit_code=-9,
                output_text="Machine booted\n",
                uart_output={"usart1": "boot ok\nheartbeat\n"},
                warnings=["Renode did not exit within the expected timeout window and was terminated after collecting output."],
                errors=[],
                timed_out=True,
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.1)

            self.assertTrue(result.ran, msg=result.errors)
            self.assertTrue(result.validation_passed)
            self.assertTrue(result.timed_out)
            self.assertTrue(any("validation time window" in item for item in result.warnings))

    def test_run_renode_project_renders_button_and_led_simulation_from_project_ir(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            (project_dir / "project_ir.json").write_text(
                json.dumps(
                    {
                        "target": {
                            "chip": "STM32F103C8T6",
                            "family": "STM32F1",
                            "board": "test_board",
                        },
                        "constraints": {
                            "clock_plan": {
                                "system_clock_config": [
                                    "RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;",
                                    "RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;",
                                ]
                            }
                        },
                        "modules": [
                            {
                                "name": "status_led",
                                "kind": "led",
                                "simulation": {
                                    "renode": {
                                        "attach": [
                                            {
                                                "kind": "led",
                                                "signal": "control",
                                                "name": "status_led",
                                                "probes": [{"at": 1.5, "label": "status_led_after_boot", "expect": True}],
                                            }
                                        ]
                                    }
                                },
                            },
                            {
                                "name": "user_key",
                                "kind": "button",
                                "simulation": {
                                    "renode": {
                                        "attach": [
                                            {
                                                "kind": "button",
                                                "signal": "input",
                                                "name": "user_button",
                                                "actions": [{"at": 1.0, "action": "press_and_release"}],
                                            }
                                        ]
                                    }
                                },
                            },
                        ],
                        "peripherals": {
                            "signals": [
                                {"module": "status_led", "signal": "control", "pin": "PC13"},
                                {"module": "user_key", "signal": "input", "pin": "PB0"},
                            ]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n[SIM][LED] status_led_after_boot=1\n",
                uart_output={"usart2": "boot ok\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=2.0)

            script_text = Path(result.script_path).read_text(encoding="utf-8")
            self.assertIn('machine LoadPlatformDescriptionFromString "status_led: Miscellaneous.LED @ gpioPortC 13"', script_text)
            self.assertIn('machine LoadPlatformDescriptionFromString "user_button: Miscellaneous.Button @ gpioPortB 0 { -> gpioPortB@0 }"', script_text)
            self.assertIn("sysbus.gpioPortB.user_button PressAndRelease", script_text)
            self.assertIn("[SIM][LED] status_led_after_boot=", script_text)
            self.assertTrue(any("attached LED status_led" in item for item in result.attached_simulation))
            self.assertTrue(any("scheduled press_and_release" in item for item in result.scheduled_interactions))
            self.assertTrue(any("scheduled LED probe status_led_after_boot" in item for item in result.scheduled_interactions))
            self.assertTrue(result.validation_passed)
            self.assertEqual(result.expectations["log_contains"], ["[SIM][LED] status_led_after_boot=1"])

    def test_run_renode_project_renders_i2c_mock_from_project_ir(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            (project_dir / "project_ir.json").write_text(
                json.dumps(
                    {
                        "target": {
                            "chip": "STM32F103C8T6",
                            "family": "STM32F1",
                            "board": "test_board",
                        },
                        "modules": [
                            {
                                "name": "storage",
                                "kind": "at24c32_i2c",
                                "interfaces": {"i2c": "I2C1"},
                                "simulation": {
                                    "renode": {
                                        "attach": [
                                            {
                                                "kind": "i2c_mock",
                                                "interface": "i2c",
                                                "model": "echo",
                                                "name": "eeprom_mock",
                                            }
                                        ]
                                    }
                                },
                            }
                        ],
                        "peripherals": {
                            "buses": [
                                {
                                    "bus": "I2C1",
                                    "kind": "i2c",
                                    "devices": [
                                        {"module": "storage", "address": "0x50"}
                                    ],
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n",
                uart_output={"usart2": "boot ok\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.5)

            script_text = Path(result.script_path).read_text(encoding="utf-8")
            self.assertIn('machine LoadPlatformDescriptionFromString "eeprom_mock: Mocks.EchoI2CDevice @ i2c1 0x50"', script_text)
            self.assertTrue(any("attached echo I2C mock eeprom_mock" in item for item in result.attached_simulation))

    def test_run_renode_project_renders_memory_backed_at24_mock_from_project_ir(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            (project_dir / "project_ir.json").write_text(
                json.dumps(
                    {
                        "target": {
                            "chip": "STM32F103C8T6",
                            "family": "STM32F1",
                            "board": "test_board",
                        },
                        "modules": [
                            {
                                "name": "storage",
                                "kind": "at24c32_i2c",
                                "interfaces": {"i2c": "I2C1"},
                                "simulation": {
                                    "renode": {
                                        "attach": [
                                            {
                                                "kind": "i2c_mock",
                                                "interface": "i2c",
                                                "model": "at24c32",
                                                "name": "eeprom_mock",
                                            }
                                        ]
                                    }
                                },
                            }
                        ],
                        "peripherals": {
                            "buses": [
                                {
                                    "bus": "I2C1",
                                    "kind": "i2c",
                                    "devices": [
                                        {"module": "storage", "address": "0x50"}
                                    ],
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n",
                uart_output={"usart2": "boot ok\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.5)

            script_text = Path(result.script_path).read_text(encoding="utf-8")
            self.assertIn('machine LoadPlatformDescriptionFromString "eeprom_mock: Mocks.DummyI2CSlave @ i2c1 0x50"', script_text)
            self.assertIn("class At24CxxI2CPeripheral:", script_text)
            self.assertIn('setup_at24_i2c_peripheral "sysbus.i2c1.eeprom_mock" 2 4096 255', script_text)
            self.assertTrue(any("memory-backed AT24C32 I2C mock eeprom_mock" in item for item in result.attached_simulation))

    def test_run_renode_project_supports_log_expectations(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir, renode_exe = self._write_project(tmp_dir, chip="STM32F103C8T6")
            (project_dir / "renode_expect.json").write_text(
                json.dumps(
                    {
                        "log_contains": ["[SIM][LED] status_led_after_boot=1"],
                        "log_not_contains": ["[SIM][LED] status_led_after_boot=0"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            completed = RenodeExecutionCapture(
                exit_code=0,
                output_text="Machine booted\n[SIM][LED] status_led_after_boot=1\n",
                uart_output={"usart1": "boot ok\n"},
                warnings=[],
                errors=[],
            )

            with patch("stm32_agent.renode_runner._run_renode_command", return_value=completed):
                result = run_renode_project(project_dir, renode_path=renode_exe, run_seconds=0.1)

            self.assertTrue(result.ran, msg=result.errors)
            self.assertTrue(result.validation_passed)
            self.assertTrue(result.validation_details["checks"]["log_contains"]["passed"])
            self.assertTrue(result.validation_details["checks"]["log_not_contains"]["passed"])


if __name__ == "__main__":
    unittest.main()
