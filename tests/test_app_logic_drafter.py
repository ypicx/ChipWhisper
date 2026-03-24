from __future__ import annotations

import unittest

from stm32_agent.app_logic_drafter import (
    _extract_tagged_app_logic,
    _extract_tagged_generated_files,
    draft_app_logic_for_plan,
    has_nonempty_generated_files,
    merge_generated_app_logic,
)
from stm32_agent.llm_config import LlmProfile
from stm32_agent.planner import plan_request


class AppLogicDrafterTests(unittest.TestCase):
    def test_extract_tagged_app_logic_strips_markdown_fences(self) -> None:
        raw = """
<AppInit>
```c
HAL_GPIO_TogglePin(GPIOC, GPIO_PIN_13);
```
</AppInit>
<AppLoop>
```cpp
DebugUart_WriteLine(&huart2, "tick", 100);
```
</AppLoop>
"""
        sections = _extract_tagged_app_logic(raw)

        self.assertEqual(sections["AppInit"], "HAL_GPIO_TogglePin(GPIOC, GPIO_PIN_13);")
        self.assertEqual(sections["AppLoop"], 'DebugUart_WriteLine(&huart2, "tick", 100);')

    def test_extract_tagged_generated_files_normalizes_paths(self) -> None:
        raw = """
<File path="App/Src/tasks/helper_task.c">
```c
void HelperTask_Run(void)
{
}
```
</File>
<File path="modules/inc/drivers/helper_task.h">
void HelperTask_Run(void);
</File>
"""
        files = _extract_tagged_generated_files(raw)

        self.assertIn("app/tasks/helper_task.c", files)
        self.assertIn("modules/drivers/helper_task.h", files)
        self.assertIn("void HelperTask_Run(void)", files["app/tasks/helper_task.c"])

    def test_merge_generated_app_logic_preserves_manual_generated_files(self) -> None:
        merged = merge_generated_app_logic(
            {
                "generated_files": {
                    "App/Inc/helper_task.h": "void HelperTask_Run(void);\n",
                }
            },
            {"AppLoop": "HelperTask_Run();"},
            {"App/Src/helper_task.c": "void HelperTask_Run(void) {}\n"},
        )

        self.assertEqual(merged["app_logic"]["AppLoop"], "HelperTask_Run();")
        self.assertTrue(has_nonempty_generated_files(merged["generated_files"]))
        self.assertIn("app/helper_task.h", merged["generated_files"])
        self.assertIn("app/helper_task.c", merged["generated_files"])

    def test_draft_prompt_keeps_constraints_and_context_grounded(self) -> None:
        captured_messages = []
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "uart_debug", "name": "debug_port"},
            ],
            "requirements": [
                "Boot once and print a startup banner.",
                "Keep reporting system status over UART.",
            ],
            "assumptions": [
                "System status can be summarized as a short text line.",
            ],
            "open_questions": [
                "Should heartbeat be emitted every second or only on state change?",
            ],
            "app_logic_goal": "Print boot ok once, then keep reporting health status without blocking the main loop.",
        }
        plan = plan_request(payload)
        self.assertTrue(plan.feasible, msg=plan.errors)

        def _fake_completion(_profile, messages):
            captured_messages.extend(messages)
            return "<AppLoop>HAL_Delay(1);</AppLoop>"

        result = draft_app_logic_for_plan(
            _dummy_profile(),
            "做一个带串口状态输出的小系统",
            payload,
            plan,
            retrieved_context="Relevant snippet: uart_debug exposes DebugUart_WriteLine.",
            thread_context="Existing thread summary: current project already uses USART1 for logs.",
            plan_warnings=["Prefer the planned UART handle instead of hard-coded ports."],
            completion_fn=_fake_completion,
        )

        self.assertTrue(result.ok, msg=result.errors)
        prompt = str(captured_messages[1]["content"])
        self.assertIn("Assumptions to preserve:", prompt)
        self.assertIn("System status can be summarized as a short text line.", prompt)
        self.assertIn("Open questions that remain unresolved:", prompt)
        self.assertIn("Should heartbeat be emitted every second", prompt)
        self.assertIn("Grounded local knowledge snippets:", prompt)
        self.assertIn("DebugUart_WriteLine", prompt)
        self.assertIn("Existing project/thread context:", prompt)
        self.assertIn("current project already uses USART1", prompt)
        self.assertIn("Planner warnings / constraints to respect:", prompt)
        self.assertIn("Prefer the planned UART handle", prompt)
        self.assertIn("loop.events[] may declare named event conditions", str(captured_messages[0]["content"]))
        self.assertIn("transitions[] may contain guard, actions, and target fields", str(captured_messages[0]["content"]))
        self.assertIn("acceptance.uart_contains", str(captured_messages[0]["content"]))
        self.assertIn("loop.events[]", prompt)
        self.assertIn("guard/actions/target", prompt)
        self.assertIn("acceptance fields", prompt)

    def test_draft_can_extract_app_logic_ir_block(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [
                {"kind": "uart_debug", "name": "debug_port"},
            ],
            "app_logic_goal": "Boot once, then print heartbeat periodically.",
        }
        plan = plan_request(payload)
        self.assertTrue(plan.feasible, msg=plan.errors)

        result = draft_app_logic_for_plan(
            _dummy_profile(),
            "做一个带心跳日志的串口工程",
            payload,
            plan,
            completion_fn=lambda _profile, _messages: """
<AppLogicIR>
{
  "globals": [{"name": "g_started", "type": "uint8_t", "init": "0U"}],
  "loop": {
    "tasks": [
      {"name": "heartbeat", "every_ms": 1000, "run": ["(void)DebugUart_WriteLine(&huart1, \\"heartbeat\\", 100);"]}
    ],
    "state_machine": {
      "state_var": "g_state",
      "states": [
        {
          "name": "0U",
          "transitions": [
            {"guard": "Boot_IsReady()", "actions": ["g_state = 1U;"], "target": "1U"}
          ]
        }
      ]
    }
  }
}
</AppLogicIR>
""",
        )

        self.assertTrue(result.ok, msg=result.errors)
        self.assertIn("globals", result.app_logic_ir)
        self.assertIn("loop", result.app_logic_ir)
        loop = result.app_logic_ir["loop"]
        self.assertIn("state_machine", loop)


def _dummy_profile() -> LlmProfile:
    return LlmProfile(
        profile_id="test-profile",
        name="Test",
        provider_type="openai",
        base_url="http://localhost",
        api_key="test",
        model="test-model",
        system_prompt="",
        temperature=0.0,
    )


if __name__ == "__main__":
    unittest.main()
