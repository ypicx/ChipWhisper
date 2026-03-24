from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from stm32_agent.desktop.dialogs import ProposalDiffReviewDialog


class ProposalDiffReviewDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_loads_selected_diff_preview(self) -> None:
        dialog = ProposalDiffReviewDialog(
            summary_lines=["确认后将执行这些变更：", "- 更新 app_main.c"],
            file_changes=[
                {
                    "status": "update",
                    "relative_path": "App/Src/app_main.c",
                    "change_summary": "预计改动 4 行（新增 1，减少 0）。",
                    "diff_preview": "--- a/App/Src/app_main.c\n+++ b/App/Src/app_main.c\n@@ -1,2 +1,3 @@\n void App_Loop(void)\n {\n+    DebugUart_WriteLine(&huart2, \"heartbeat\", 100);\n }\n",
                },
                {
                    "status": "create",
                    "relative_path": "Modules/led.c",
                    "change_summary": "新建文件，预计写入 12 行。",
                    "diff_preview": "--- /dev/null\n+++ b/Modules/led.c\n@@ -0,0 +1,2 @@\n+void Led_Init(void) {}\n+void Led_On(void) {}\n",
                },
            ],
            confirm_label="确认并生成",
        )

        self.assertEqual(dialog.file_list.count(), 2)
        self.assertIn("App/Src/app_main.c", dialog.file_list.item(0).text())
        self.assertIn("heartbeat", dialog.diff_view.toPlainText())

        dialog.file_list.setCurrentRow(1)
        self.assertIn("Modules/led.c", dialog.diff_view.toPlainText())
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
