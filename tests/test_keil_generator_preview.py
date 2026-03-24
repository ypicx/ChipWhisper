from __future__ import annotations

import unittest

from stm32_agent.keil_generator import _build_project_file_diff_preview, _summarize_project_file_change


class KeilGeneratorPreviewTests(unittest.TestCase):
    def test_build_project_file_diff_preview_renders_unified_diff_for_updates(self) -> None:
        preview = _build_project_file_diff_preview(
            "App/Src/app_main.c",
            "update",
            "void App_Loop(void)\n{\n}\n",
            'void App_Loop(void)\n{\n    DebugUart_WriteLine(&huart2, "heartbeat", 100);\n}\n',
        )

        self.assertIn("--- a/App/Src/app_main.c", preview)
        self.assertIn("+++ b/App/Src/app_main.c", preview)
        self.assertIn('+    DebugUart_WriteLine(&huart2, "heartbeat", 100);', preview)

    def test_summarize_project_file_change_reports_create_and_unchanged_states(self) -> None:
        self.assertIn("新建文件", _summarize_project_file_change("create", "", "line1\nline2\n"))
        self.assertIn("内容未变化", _summarize_project_file_change("unchanged", "line1\n", "line1\n"))


if __name__ == "__main__":
    unittest.main()
