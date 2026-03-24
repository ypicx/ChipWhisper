from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .widgets import CodeEditor

class ProposalDiffReviewDialog(QDialog):
    def __init__(
        self,
        summary_lines: List[str],
        file_changes: List[dict[str, object]],
        confirm_label: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("确认即将变更")
        self.resize(980, 680)
        self._file_changes = [dict(item) for item in file_changes if isinstance(item, dict)]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("确认前预览")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.summary_view = QTextBrowser()
        self.summary_view.setObjectName("SidebarViewer")
        self.summary_view.setPlainText("\n".join(summary_lines))
        self.summary_view.setMinimumHeight(150)
        layout.addWidget(self.summary_view)

        self.diff_splitter = QSplitter(Qt.Horizontal)
        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(280)
        self.file_list.currentRowChanged.connect(self._update_diff_view)
        self.diff_view = CodeEditor(read_only=True)
        self.diff_view.setPlainText("选择左侧文件查看变更差异。")
        self.diff_splitter.addWidget(self.file_list)
        self.diff_splitter.addWidget(self.diff_view)
        self.diff_splitter.setStretchFactor(0, 0)
        self.diff_splitter.setStretchFactor(1, 1)
        self.diff_splitter.setSizes([300, 680])
        layout.addWidget(self.diff_splitter, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        cancel_button = QPushButton("返回修改")
        cancel_button.setObjectName("GhostButton")
        cancel_button.clicked.connect(self.reject)
        self.confirm_button = QPushButton(confirm_label)
        self.confirm_button.setObjectName("PrimaryButton")
        self.confirm_button.clicked.connect(self.accept)
        actions.addStretch(1)
        actions.addWidget(cancel_button)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)

        if self._file_changes:
            for item in self._file_changes:
                list_item = QListWidgetItem(self._format_file_label(item))
                tooltip = str(item.get("relative_path", "") or item.get("path", "")).strip()
                summary = str(item.get("change_summary", "") or "").strip()
                if summary:
                    tooltip = f"{tooltip}\n{summary}" if tooltip else summary
                list_item.setToolTip(tooltip)
                self.file_list.addItem(list_item)
            self.file_list.setCurrentRow(0)
        else:
            placeholder = QListWidgetItem("当前没有可展示的文件 diff")
            self.file_list.addItem(placeholder)
            self.file_list.setEnabled(False)
            self.diff_view.setPlainText("当前预览仅包含摘要信息，还没有可展示的文件差异。")

    @staticmethod
    def _format_file_label(item: dict[str, object]) -> str:
        status_map = {
            "create": "create",
            "update": "update",
            "unchanged": "same",
        }
        status = status_map.get(str(item.get("status", "")).strip(), "file")
        relative_path = str(item.get("relative_path", "") or item.get("path", "")).strip() or "(unknown file)"
        summary = str(item.get("change_summary", "") or "").strip()
        return f"[{status}] {relative_path}\n{summary}" if summary else f"[{status}] {relative_path}"

    def _update_diff_view(self, row: int) -> None:
        if row < 0 or row >= len(self._file_changes):
            self.diff_view.setPlainText("选择左侧文件查看变更差异。")
            return
        item = self._file_changes[row]
        diff_preview = str(item.get("diff_preview", "") or "").strip()
        if diff_preview:
            self.diff_view.setPlainText(diff_preview)
            return
        relative_path = str(item.get("relative_path", "") or item.get("path", "")).strip() or "(unknown file)"
        status = str(item.get("status", "") or "file").strip()
        summary = str(item.get("change_summary", "") or "").strip()
        lines = [f"{status}: {relative_path}"]
        if summary:
            lines.extend(["", summary])
        self.diff_view.setPlainText("\n".join(lines))

