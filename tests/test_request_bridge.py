from __future__ import annotations

import unittest

from stm32_agent.desktop.request_bridge import _build_system_prompt, build_chat_system_prompt, draft_request_json
from stm32_agent.extension_packs import load_catalog
from stm32_agent.llm_config import LlmProfile


class RequestBridgePromptTests(unittest.TestCase):
    def test_system_prompt_uses_grounded_module_subset_when_retrieval_exists(self) -> None:
        registry = load_catalog()
        retrieved_context = """
[1] catalog:module:at24c32_i2c | module_def | at24c32_i2c
模块: AT24C32 EEPROM (at24c32_i2c)
摘要: I2C EEPROM
"""

        prompt = _build_system_prompt(
            registry,
            user_prompt="做一个 AT24C32 参数保存工程",
            retrieved_context=retrieved_context,
        )

        self.assertIn("Relevant module kinds", prompt)
        self.assertIn("at24c32_i2c", prompt)
        self.assertNotIn("as608_uart", prompt)

    def test_chat_system_prompt_uses_grounded_module_names_and_context(self) -> None:
        retrieved_context = """
[1] catalog:module:at24c32_i2c | module_def | at24c32_i2c
模块: AT24C32 EEPROM (at24c32_i2c)
摘要: I2C EEPROM
"""

        prompt = build_chat_system_prompt(
            base_system_prompt="You are helpful.",
            user_prompt="我想做一个带 AT24C32 的参数保存小项目",
            retrieved_context=retrieved_context,
        )

        self.assertIn("Supported module kinds:", prompt)
        self.assertIn("- at24c32_i2c", prompt)
        self.assertNotIn("- as608_uart", prompt)
        self.assertIn("Relevant local knowledge snippets for this turn:", prompt)

    def test_draft_request_json_includes_thread_context_in_user_prompt(self) -> None:
        captured_messages = []

        def _fake_completion(_profile, messages):
            captured_messages.extend(messages)
            return (
                '{"chip":"STM32F103C8T6","board":"chip_only","keep_swd":true,'
                '"reserved_pins":[],"avoid_pins":[],"modules":[],'
                '"app_logic_goal":"","app_logic":{"AppTop":"","AppInit":"","AppLoop":"","AppCallbacks":""},'
                '"requirements":[],"assumptions":[],"open_questions":[]}'
            )

        profile = LlmProfile(
            profile_id="test-profile",
            name="test",
            provider_type="openai",
            base_url="http://localhost",
            api_key="test",
            model="test-model",
            system_prompt="",
            temperature=0.0,
        )

        result = draft_request_json(
            profile,
            "在当前工程上再加一个 EEPROM 保存参数",
            thread_context="Existing desktop project thread summary:\n当前工程: demo\n目标芯片: stm32f103c8t6",
            completion_fn=_fake_completion,
        )

        self.assertTrue(result.ok)
        self.assertEqual(captured_messages[1]["role"], "user")
        self.assertIn("follow-up inside an existing desktop project thread", str(captured_messages[1]["content"]))
        self.assertIn("当前工程: demo", str(captured_messages[1]["content"]))


if __name__ == "__main__":
    unittest.main()
