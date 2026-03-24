from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .project_explorer import ProjectExplorerWidget
from .widgets import Card, CodeEditor, _json_text

class ProjectsPage(QWidget):
    def __init__(self):
        super().__init__()
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(18)

        self.explorer = ProjectExplorerWidget(
            title="工程总览",
            hint="支持查看生成目录、源码文件、build.log 和 project_ir.json。",
        )

        self.explorer.hint_label.setVisible(False)
        side_card = Card()
        side_layout = QVBoxLayout(side_card)
        side_layout.setContentsMargins(18, 16, 18, 16)
        side_layout.setSpacing(12)
        title = QLabel("工程摘要")
        title.setObjectName("SectionTitle")
        hint = QLabel("当工程目录下存在 `project_ir.json` 时，这里会显示目标芯片、模块数量和结构化信息。")
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)
        title.setToolTip(hint.text())
        hint.setVisible(False)
        self.project_title_label = QLabel("未加载工程")
        self.project_title_label.setObjectName("MetricValue")
        self.project_meta_label = QLabel("选择工程目录后显示。")
        self.project_meta_label.setObjectName("MetricCaption")
        self.project_ir_view = CodeEditor(read_only=True)
        side_layout.addWidget(title)
        side_layout.addWidget(hint)
        side_layout.addWidget(self.project_title_label)
        side_layout.addWidget(self.project_meta_label)
        side_layout.addWidget(self.project_ir_view, 1)

        root_layout.addWidget(self.explorer, 3)
        root_layout.addWidget(side_card, 2)

        self.explorer.root_changed.connect(self._load_project_summary)

    def set_project_root(self, project_dir: str) -> None:
        self.explorer.set_root_path(project_dir)
        self._load_project_summary(project_dir)

    def _load_project_summary(self, project_dir: str) -> None:
        if not project_dir:
            return
        root = Path(project_dir)
        self.project_title_label.setText(root.name)
        ir_path = root / "project_ir.json"
        if not ir_path.exists():
            self.project_meta_label.setText("当前目录下没有 project_ir.json。")
            self.project_ir_view.clear()
            return
        try:
            payload = json.loads(ir_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.project_meta_label.setText(f"无法读取 project_ir.json: {exc}")
            return
        target = payload.get("target", {})
        modules = payload.get("modules", [])
        self.project_meta_label.setText(
            f"{target.get('chip', '--')} · {target.get('family', '--')} · {len(modules)} 个模块"
        )
        self.project_ir_view.setPlainText(_json_text(payload))


