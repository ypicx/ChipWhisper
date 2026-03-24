from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from stm32_agent.desktop.project_explorer import ProjectExplorerWidget


class ProjectExplorerWidgetEncodingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_load_text_file_uses_encoding_fallback_for_gbk_content(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "vendor_driver.c"
            file_path.write_bytes("中文注释".encode("gbk"))

            widget = ProjectExplorerWidget(compact=True)
            widget._load_text_file(file_path)

            self.assertEqual(widget.preview_editor.toPlainText(), "中文注释")
            self.assertEqual(widget.current_file_encoding, "gb18030")
            widget.deleteLater()

    def test_save_current_file_preserves_detected_legacy_encoding(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "vendor_driver.c"
            file_path.write_bytes("初始内容".encode("gbk"))

            widget = ProjectExplorerWidget(compact=True)
            widget._load_text_file(file_path)
            widget.edit_button.setChecked(True)
            widget.preview_editor.setPlainText("修改后内容")

            self.assertTrue(widget.save_current_file())
            self.assertEqual(file_path.read_text(encoding="gb18030"), "修改后内容")
            widget.deleteLater()


if __name__ == "__main__":
    unittest.main()
