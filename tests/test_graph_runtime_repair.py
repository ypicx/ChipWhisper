from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stm32_agent.graph.nodes import GraphRuntime, route_after_evaluate
from stm32_agent.graph.repair import BuildErrorSnippet, _build_repair_prompt, attempt_llm_build_repair
from stm32_agent.llm_config import LlmProfile


class GraphRuntimeRepairTests(unittest.TestCase):
    def test_route_after_evaluate_retries_repair_when_runtime_validation_failed(self) -> None:
        runtime = GraphRuntime(
            profile=_dummy_profile(),
            repo_root=Path("."),
            enable_runtime_validation=True,
            max_repairs=2,
        )

        next_node = route_after_evaluate(
            {
                "runtime_validation_passed": False,
                "repair_count": 0,
            },
            runtime,
        )

        self.assertEqual(next_node, "repair")

    def test_runtime_repair_can_patch_app_main_after_failed_validation(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            app_src = project_dir / "App" / "Src"
            app_src.mkdir(parents=True, exist_ok=True)
            app_main = app_src / "app_main.c"
            app_main.write_text(
                "\n".join(
                    [
                        '#include "app_main.h"',
                        "",
                        "void App_Loop(void)",
                        "{",
                        '    DebugUart_WriteLine(&huart2, "boot ok", 100);',
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            state = {
                "project_dir": str(project_dir),
                "runtime_validation_passed": False,
                "user_input": "Emit boot ok and heartbeat over UART.",
                "request_payload": {"app_logic_goal": "Print boot ok once, then heartbeat repeatedly."},
                "evaluation_result": {
                    "passed": False,
                    "summary": "Renode UART validation missed one or more expected substrings.",
                    "reasons": ["heartbeat"],
                },
                "simulate_result": {
                    "ready": True,
                    "ran": False,
                    "validation_passed": False,
                    "expected_uart_contains": ["boot ok", "heartbeat"],
                    "missing_uart_contains": ["heartbeat"],
                    "uart_output": {"usart2": "boot ok\n"},
                    "warnings": [],
                    "errors": ["Renode UART validation did not observe expected text: heartbeat"],
                },
                "build_logs": [],
            }

            result = attempt_llm_build_repair(
                state,
                _dummy_profile(),
                completion_fn=lambda _profile, _messages: (
                    "{"
                    '"repair_strategy":"retry_build",'
                    '"summary":"add heartbeat output",'
                    '"patches":[{'
                    '"path":"App/Src/app_main.c",'
                    '"search":"DebugUart_WriteLine(&huart2, \\"boot ok\\", 100);",'
                    '"replace":"DebugUart_WriteLine(&huart2, \\"boot ok\\", 100);\\n    DebugUart_WriteLine(&huart2, \\"heartbeat\\", 100);",'
                    '"reason":"runtime validation expected a heartbeat log after boot"'
                    "}]}"
                ),
            )

            self.assertEqual(result["repair_strategy"], "retry_build")
            self.assertIn("build/simulate cycle", result["warnings"][0])
            updated = app_main.read_text(encoding="utf-8")
            self.assertIn('"heartbeat"', updated)

    def test_compile_repair_prompt_prefers_search_replace(self) -> None:
        prompt = _build_repair_prompt(
            [
                BuildErrorSnippet(
                    source_path="App/Src/app_main.c",
                    line=12,
                    level="error",
                    message="undeclared identifier",
                    snippet="  12: DebugUart_WriteLine(&huart2, msg, 100);",
                )
            ]
        )

        self.assertIn("Prefer a unified_diff patch", prompt)
        self.assertIn("prefer exact search/replace patches", prompt)
        self.assertIn('"search": "original code fragment"', prompt)
        self.assertIn('"unified_diff": "--- a/App/Src/app_main.c', prompt)

    def test_compile_repair_can_apply_unified_diff_patch(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            app_src = project_dir / "App" / "Src"
            app_src.mkdir(parents=True, exist_ok=True)
            app_main = app_src / "app_main.c"
            app_main.write_text(
                "\n".join(
                    [
                        '#include "app_main.h"',
                        "",
                        "void App_Loop(void)",
                        "{",
                        '    DebugUart_WriteLine(&huart2, "boot ok", 100);',
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            state = {
                "project_dir": str(project_dir),
                "build_logs": [
                    'App/Src/app_main.c(5): error: use of undeclared identifier "heartbeat"',
                ],
            }

            result = attempt_llm_build_repair(
                state,
                _dummy_profile(),
                completion_fn=lambda _profile, _messages: (
                    "{"
                    '"repair_strategy":"retry_build",'
                    '"summary":"apply unified diff",'
                    '"unified_diff":"--- a/App/Src/app_main.c\\n+++ b/App/Src/app_main.c\\n@@ -2,5 +2,6 @@\\n \\n void App_Loop(void)\\n {\\n     DebugUart_WriteLine(&huart2, \\"boot ok\\", 100);\\n+    DebugUart_WriteLine(&huart2, \\"heartbeat\\", 100);\\n }"'
                    "}"
                ),
            )

            self.assertEqual(result["repair_strategy"], "retry_build")
            updated = app_main.read_text(encoding="utf-8")
            self.assertIn('"heartbeat"', updated)

    def test_search_patch_takes_priority_over_incorrect_line_numbers(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            app_src = project_dir / "App" / "Src"
            app_src.mkdir(parents=True, exist_ok=True)
            app_main = app_src / "app_main.c"
            app_main.write_text(
                "\n".join(
                    [
                        '#include "app_main.h"',
                        "",
                        "void App_Loop(void)",
                        "{",
                        '    DebugUart_WriteLine(&huart2, "boot ok", 100);',
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            state = {
                "project_dir": str(project_dir),
                "build_logs": [
                    'App/Src/app_main.c(5): error: use of undeclared identifier "heartbeat"',
                ],
            }

            result = attempt_llm_build_repair(
                state,
                _dummy_profile(),
                completion_fn=lambda _profile, _messages: (
                    "{"
                    '"repair_strategy":"retry_build",'
                    '"summary":"prefer search patch",'
                    '"patches":[{'
                    '"path":"App/Src/app_main.c",'
                    '"start_line":999,'
                    '"end_line":999,'
                    '"search":"DebugUart_WriteLine(&huart2, \\"boot ok\\", 100);",'
                    '"replace":"DebugUart_WriteLine(&huart2, \\"boot ok\\", 100);\\n    DebugUart_WriteLine(&huart2, \\"heartbeat\\", 100);",'
                    '"reason":"anchor on the exact existing line instead of trusting line offsets"'
                    "}]}"
                ),
            )

            self.assertEqual(result["repair_strategy"], "retry_build")
            updated = app_main.read_text(encoding="utf-8")
            self.assertIn('"heartbeat"', updated)


def _dummy_profile() -> LlmProfile:
    return LlmProfile(
        profile_id="test",
        name="Test",
        provider_type="openai_compatible",
        base_url="http://localhost",
        api_key="test",
        model="test-model",
        system_prompt="",
        temperature=0.0,
        enabled=True,
    )


if __name__ == "__main__":
    unittest.main()
