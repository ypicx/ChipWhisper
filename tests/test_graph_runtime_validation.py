from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stm32_agent.graph.nodes import (
    _derive_runtime_uart_expectations,
    _ensure_runtime_expectations,
    evaluate_runtime_validation,
)


class GraphRuntimeValidationTests(unittest.TestCase):
    def test_derive_runtime_uart_expectations_from_debug_uart_calls(self) -> None:
        payload = {
            "app_logic": {
                "AppInit": '(void)DebugUart_WriteLine(&huart2, "boot ok", 100);',
                "AppLoop": 'DebugUart_WriteLine(&huart2, "heartbeat", 100);',
                "AppCallbacks": 'DebugUart_WriteLine(&huart2, "boot ok", 100);',
            }
        }

        expectations = _derive_runtime_uart_expectations(payload, {})

        self.assertEqual(expectations, ["boot ok", "heartbeat"])

    def test_ensure_runtime_expectations_writes_expect_file_when_missing(self) -> None:
        payload = {
            "app_logic": {
                "AppInit": '(void)DebugUart_WriteLine(&huart2, "init done", 100);',
                "AppLoop": 'DebugUart_WriteLine(&huart2, "ready", 100);',
            }
        }
        with TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)

            warnings = _ensure_runtime_expectations(project_dir, payload, {})

            expect_path = project_dir / "renode_expect.json"
            self.assertTrue(expect_path.exists())
            self.assertTrue(warnings)
            content = json.loads(expect_path.read_text(encoding="utf-8"))
            self.assertEqual(content["uart_contains"], ["init done", "ready"])
            self.assertEqual(content["uart_sequence"], ["init done", "ready"])

    def test_ensure_runtime_expectations_can_derive_led_probe_log_expectations(self) -> None:
        project_ir = {
            "modules": [
                {
                    "name": "status_led",
                    "simulation": {
                        "renode": {
                            "attach": [
                                {
                                    "kind": "led",
                                    "name": "status_led",
                                    "probes": [
                                        {"at": 1.0, "label": "status_led_after_boot", "expect": True}
                                    ],
                                }
                            ]
                        }
                    },
                }
            ]
        }
        with TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)

            warnings = _ensure_runtime_expectations(project_dir, {}, project_ir)

            expect_path = project_dir / "renode_expect.json"
            self.assertTrue(expect_path.exists())
            self.assertTrue(warnings)
            content = json.loads(expect_path.read_text(encoding="utf-8"))
            self.assertEqual(content["log_contains"], ["[SIM][LED] status_led_after_boot=1"])

    def test_evaluate_runtime_validation_prefers_explicit_expectations(self) -> None:
        evaluation = evaluate_runtime_validation(
            {
                "ready": True,
                "ran": True,
                "validation_passed": True,
                "matched_uart_contains": ["boot ok", "heartbeat"],
                "uart_output": {"usart2": "boot ok\nheartbeat\n"},
            }
        )

        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["mode"], "expected_uart")

    def test_evaluate_runtime_validation_reports_missing_expected_text_even_if_run_marked_failed(self) -> None:
        evaluation = evaluate_runtime_validation(
            {
                "ready": True,
                "ran": False,
                "validation_passed": False,
                "missing_uart_contains": ["heartbeat"],
                "errors": ["Renode UART validation did not observe expected text: heartbeat"],
            }
        )

        self.assertFalse(evaluation["passed"])
        self.assertEqual(evaluation["mode"], "expected_uart")
        self.assertIn("heartbeat", evaluation["reasons"][0])

    def test_evaluate_runtime_validation_summarizes_extended_runtime_rules(self) -> None:
        evaluation = evaluate_runtime_validation(
            {
                "ready": True,
                "ran": True,
                "validation_passed": True,
                "validation_details": {
                    "checks": {
                        "uart_contains": {
                            "expected": ["boot ok"],
                            "matched": ["boot ok"],
                            "missing": [],
                            "passed": True,
                        },
                        "uart_any_contains": {
                            "expected": ["heartbeat", "tick"],
                            "matched": ["heartbeat"],
                            "passed": True,
                        },
                        "uart_sequence": {
                            "expected": ["boot ok", "heartbeat"],
                            "matched": ["boot ok", "heartbeat"],
                            "missing": [],
                            "passed": True,
                        },
                        "log_contains": {
                            "expected": ["[SIM][LED] status_led_after_boot=1"],
                            "matched": ["[SIM][LED] status_led_after_boot=1"],
                            "missing": [],
                            "passed": True,
                        },
                    }
                },
            }
        )

        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["mode"], "expected_rules")
        self.assertTrue(any("Matched UART sequence" in item for item in evaluation["reasons"]))
        self.assertTrue(any("Matched monitor log text" in item for item in evaluation["reasons"]))

    def test_evaluate_runtime_validation_reports_extended_runtime_rule_failures(self) -> None:
        evaluation = evaluate_runtime_validation(
            {
                "ready": True,
                "ran": False,
                "validation_passed": False,
                "validation_details": {
                    "checks": {
                        "uart_not_contains": {
                            "expected": ["panic"],
                            "matched": ["panic"],
                            "passed": False,
                        },
                        "exit_code": {
                            "expected": 0,
                            "actual": 1,
                            "passed": False,
                        },
                        "log_not_contains": {
                            "expected": ["panic"],
                            "matched": ["panic"],
                            "passed": False,
                        },
                    }
                },
            }
        )

        self.assertFalse(evaluation["passed"])
        self.assertEqual(evaluation["mode"], "expected_rules")
        self.assertTrue(any("forbidden UART text" in item for item in evaluation["reasons"]))
        self.assertTrue(any("forbidden monitor log text" in item for item in evaluation["reasons"]))
        self.assertTrue(any("exit code" in item.lower() for item in evaluation["reasons"]))

    def test_evaluate_runtime_validation_can_fall_back_to_observed_uart(self) -> None:
        evaluation = evaluate_runtime_validation(
            {
                "ready": True,
                "ran": True,
                "validation_passed": None,
                "uart_analyzers": ["usart2"],
                "uart_output": {"usart2": "boot ok\nheartbeat\n"},
            }
        )

        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["mode"], "uart_observed")
        self.assertTrue(evaluation["warnings"])

    def test_evaluate_runtime_validation_keeps_timeout_as_warning_when_rules_pass(self) -> None:
        evaluation = evaluate_runtime_validation(
            {
                "ready": True,
                "ran": True,
                "timed_out": True,
                "validation_passed": True,
                "validation_details": {
                    "checks": {
                        "uart_contains": {
                            "expected": ["boot ok"],
                            "matched": ["boot ok"],
                            "missing": [],
                            "passed": True,
                        }
                    }
                },
            }
        )

        self.assertTrue(evaluation["passed"])
        self.assertTrue(any("validation time window" in item for item in evaluation["warnings"]))


if __name__ == "__main__":
    unittest.main()
