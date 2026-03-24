from __future__ import annotations

import unittest

from stm32_agent.desktop.chat_agent import detect_agent_action


class ChatAgentIntentTests(unittest.TestCase):
    def test_detect_agent_action_recognizes_chinese_build_and_scaffold_keywords(self) -> None:
        self.assertEqual(detect_agent_action("帮我编译一下当前工程"), "build")
        self.assertEqual(detect_agent_action("帮我做一个 STM32 流水灯工程"), "scaffold")
        self.assertEqual(detect_agent_action("帮我检查一下工程"), "doctor")


if __name__ == "__main__":
    unittest.main()
