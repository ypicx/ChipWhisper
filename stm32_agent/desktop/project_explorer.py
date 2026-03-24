from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import QDir, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .attachments import ATTACHMENT_FILE_FILTER
from .widgets import (
    REPO_ROOT,
    Card,
    CodeEditor,
    StatusChip,
    _decode_text_with_fallback,
)

class ProjectExplorerWidget(QWidget):
    root_changed = Signal(str)
    file_saved = Signal(str)

    def __init__(
        self,
        title: str = "项目树",
        hint: str = "查看生成的工程目录、文件树和源码内容。",
        compact: bool = False,
    ):
        super().__init__()
        self.compact = compact
        self.current_root = ""
        self.current_file_path = ""
        self.current_file_encoding = "utf-8"
        self.current_file_is_binary = False
        self.current_file_is_truncated = False
        self.preview_dirty = False
        self._loading_preview = False
        self._selection_guard = False
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.model.setRootPath("")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        card = Card()
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14 if compact else 18, 12 if compact else 16, 14 if compact else 18, 12 if compact else 16)
        layout.setSpacing(10 if compact else 14)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("SectionHint")
        hint_label.setWordWrap(True)
        title_label.setToolTip(hint)
        hint_label.setToolTip(hint)
        self.hint_label = hint_label

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择工程目录")
        browse_button = QPushButton("浏览")
        browse_button.clicked.connect(self._browse_root)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh_root)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_button)
        path_row.addWidget(refresh_button)

        splitter = QSplitter(Qt.Vertical if compact else Qt.Horizontal)
        self.splitter = splitter
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setModel(self.model)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setAnimated(True)
        self.tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        for section in (1, 2, 3):
            self.tree.hideColumn(section)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(10)
        preview_header = QHBoxLayout()
        preview_header.setSpacing(8)
        self.preview_title = QLabel("文件预览")
        self.preview_title.setObjectName("SectionTitle")
        self.preview_status = StatusChip("只读", "neutral")
        self.edit_button = QPushButton("编辑")
        self.edit_button.setCheckable(True)
        self.edit_button.setEnabled(False)
        self.edit_button.toggled.connect(self._set_edit_mode)
        self.save_button = QPushButton("保存")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_current_file)
        self.revert_button = QPushButton("撤销")
        self.revert_button.setEnabled(False)
        self.revert_button.clicked.connect(self.revert_current_file)
        preview_header.addWidget(self.preview_title)
        preview_header.addStretch(1)
        preview_header.addWidget(self.preview_status)
        preview_header.addWidget(self.edit_button)
        preview_header.addWidget(self.save_button)
        preview_header.addWidget(self.revert_button)
        self.preview_hint = QLabel("选择左侧文件后，在这里查看源码内容。")
        self.preview_hint.setObjectName("SectionHint")
        self.preview_hint.setWordWrap(True)
        self.preview_editor = CodeEditor(read_only=True)
        self.preview_editor.textChanged.connect(self._on_preview_text_changed)
        preview_layout.addLayout(preview_header)
        if not compact:
            preview_layout.addWidget(self.preview_hint)
        preview_layout.addWidget(self.preview_editor, 1)

        splitter.addWidget(self.tree)
        splitter.addWidget(preview_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setHandleWidth(8)
        splitter.setSizes([260, 340] if compact else [340, 640])

        layout.addWidget(title_label)
        if not compact:
            layout.addWidget(hint_label)
        layout.addLayout(path_row)
        layout.addWidget(splitter, 1)

    def set_root_path(self, path: str) -> None:
        normalized = str(Path(path).resolve()) if path else ""
        if normalized != self.current_root and not self._confirm_close_current_file():
            return
        if not normalized or not Path(normalized).exists():
            self.current_root = ""
            self.path_edit.clear()
            self._clear_preview("目录不存在，或尚未选择项目目录。")
            self.preview_hint.setText("目录不存在，或尚未选择项目目录。")
            return
        self.current_root = normalized
        self.path_edit.setText(normalized)
        root_index = self.model.setRootPath(normalized)
        self.tree.setRootIndex(root_index)
        self._clear_preview("选择左侧文件后，在这里查看源码内容。")
        self.preview_hint.setText("选择左侧文件后，在这里查看源码内容。")
        self.root_changed.emit(normalized)

    def refresh_root(self) -> None:
        self.set_root_path(self.path_edit.text().strip())

    def _browse_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择项目目录", self.current_root or str(REPO_ROOT))
        if directory:
            self.set_root_path(directory)

    def _on_selection_changed(self) -> None:  # pragma: no cover - GUI interaction
        if self._selection_guard:
            return
        index = self.tree.currentIndex()
        if not index.isValid():
            return
        file_path = Path(self.model.filePath(index))
        if str(file_path.resolve()) == self.current_file_path:
            return
        if not self._confirm_close_current_file():
            self._restore_current_selection()
            return
        if file_path.is_dir():
            self.current_file_path = ""
            self.preview_title.setText(file_path.name)
            self.preview_hint.setText(f"目录: {file_path}")
            self.preview_status.set_status("目录", "neutral")
            self.edit_button.setChecked(False)
            self.edit_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.revert_button.setEnabled(False)
            try:
                children = list(file_path.iterdir())
            except OSError as exc:
                self.preview_editor.setPlainText(f"无法读取目录: {exc}")
                return
            self.preview_editor.setPlainText("\n".join(sorted(item.name for item in children)))
            return

        self._load_text_file(file_path)

    def save_current_file(self) -> bool:
        if not self.current_file_path or self.current_file_is_binary or self.current_file_is_truncated:
            return False
        file_path = Path(self.current_file_path)
        try:
            file_path.write_text(
                self.preview_editor.toPlainText(),
                encoding=self.current_file_encoding or "utf-8",
            )
        except (OSError, UnicodeError) as exc:
            QMessageBox.critical(self, "保存失败", f"无法保存文件:\n{file_path}\n\n{exc}")
            return False
        self.preview_dirty = False
        self._update_preview_actions()
        self.preview_status.set_status("已保存", "success")
        self.preview_hint.setText(str(file_path))
        self.file_saved.emit(str(file_path))
        return True

    def revert_current_file(self) -> None:
        if not self.current_file_path:
            return
        file_path = Path(self.current_file_path)
        if not file_path.exists():
            QMessageBox.warning(self, "文件不存在", f"当前文件不存在:\n{file_path}")
            return
        self._load_text_file(file_path, keep_edit_mode=self.edit_button.isChecked())

    def _set_edit_mode(self, enabled: bool) -> None:
        if enabled and (self.current_file_is_binary or self.current_file_is_truncated or not self.current_file_path):
            self.edit_button.setChecked(False)
            return
        self.preview_editor.setReadOnly(not enabled)
        self.edit_button.setText("完成" if enabled else "编辑")
        if enabled and self.current_file_path:
            self.preview_status.set_status("编辑中", "warning" if self.preview_dirty else "success")
        elif self.current_file_path:
            self.preview_status.set_status("只读", "neutral")
        self._update_preview_actions()

    def _on_preview_text_changed(self) -> None:
        if self._loading_preview or not self.current_file_path or self.preview_editor.isReadOnly():
            return
        self.preview_dirty = True
        self.preview_status.set_status("未保存", "warning")
        self._update_preview_actions()

    def _load_text_file(self, file_path: Path, keep_edit_mode: bool = False) -> None:
        self.preview_title.setText(file_path.name)
        self.preview_hint.setText(str(file_path))
        self.current_file_path = str(file_path.resolve())
        self.current_file_encoding = "utf-8"
        self.current_file_is_binary = False
        self.current_file_is_truncated = False
        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            self._set_preview_text(f"无法读取文件: {exc}")
            self.preview_status.set_status("读取失败", "error")
            self.edit_button.setChecked(False)
            self.edit_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.revert_button.setEnabled(False)
            return
        if b"\x00" in raw[:2048]:
            self.current_file_is_binary = True
            self._set_preview_text("二进制文件，当前不支持在界面中编辑。")
            self.preview_status.set_status("二进制", "warning")
            self.edit_button.setChecked(False)
            self.edit_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.revert_button.setEnabled(False)
            return
        text, encoding = _decode_text_with_fallback(raw)
        self.current_file_encoding = encoding
        if len(text) > 300_000:
            self.current_file_is_truncated = True
            text = text[:300_000] + "\n\n... 文件过大，当前只显示截断预览，不能直接编辑 ..."
            self.preview_status.set_status("文件过大", "warning")
            self.edit_button.setChecked(False)
            self.edit_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.revert_button.setEnabled(False)
            self._set_preview_text(text)
            return
        self.preview_dirty = False
        self._set_preview_text(text)
        self.edit_button.setEnabled(True)
        self.edit_button.setChecked(bool(keep_edit_mode))
        if not keep_edit_mode:
            self.preview_editor.setReadOnly(True)
            self.preview_status.set_status("只读", "neutral")
        self._update_preview_actions()

    def _set_preview_text(self, text: str) -> None:
        self._loading_preview = True
        self.preview_editor.setPlainText(text)
        self._loading_preview = False

    def _clear_preview(self, hint_text: str) -> None:
        self.current_file_path = ""
        self.current_file_encoding = "utf-8"
        self.current_file_is_binary = False
        self.current_file_is_truncated = False
        self.preview_dirty = False
        self._loading_preview = True
        self.preview_title.setText("文件预览")
        self.preview_editor.clear()
        self._loading_preview = False
        self.preview_hint.setText(hint_text)
        self.preview_status.set_status("只读", "neutral")
        self.edit_button.setChecked(False)
        self.edit_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.revert_button.setEnabled(False)

    def _update_preview_actions(self) -> None:
        editable = bool(self.current_file_path) and not self.current_file_is_binary and not self.current_file_is_truncated
        self.edit_button.setEnabled(editable)
        self.save_button.setEnabled(editable and self.edit_button.isChecked() and self.preview_dirty)
        self.revert_button.setEnabled(editable and self.preview_dirty)

    def _confirm_close_current_file(self) -> bool:
        if not self.preview_dirty or not self.current_file_path:
            return True
        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("文件尚未保存")
        message_box.setText("当前文件有未保存的修改。")
        message_box.setInformativeText("要先保存再切换文件吗？")
        message_box.setStandardButtons(
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
        )
        message_box.setDefaultButton(QMessageBox.Save)
        choice = message_box.exec()
        if choice == QMessageBox.Save:
            return self.save_current_file()
        if choice == QMessageBox.Discard:
            self.preview_dirty = False
            self._update_preview_actions()
            return True
        return False

    def _restore_current_selection(self) -> None:
        if not self.current_file_path:
            return
        index = self.model.index(self.current_file_path)
        if not index.isValid():
            return
        self._selection_guard = True
        self.tree.setCurrentIndex(index)
        self._selection_guard = False


class AttachmentPickerWidget(QWidget):
    paths_changed = Signal()

    def __init__(self, title: str, hint: str, collapsed: bool = False):
        super().__init__()
        self._paths: List[str] = []
        self.collapsed = bool(collapsed)
        self._show_hint = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SectionTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("SectionHint")
        hint_label.setWordWrap(True)
        self.title_label.setToolTip(hint)
        hint_label.setToolTip(hint)
        self.hint_label = hint_label
        self.count_label = QLabel("未添加文件")
        self.count_label.setObjectName("MetricCaption")
        self.toggle_button = QToolButton()
        self.toggle_button.setObjectName("PanelToggleButton")
        self.toggle_button.setAutoRaise(True)
        self.toggle_button.setFixedSize(34, 34)
        self.toggle_button.clicked.connect(self._toggle_collapsed)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.count_label)
        header_layout.addWidget(self.toggle_button)

        actions = QHBoxLayout()
        self.add_button = QPushButton("添加文件")
        self.add_button.clicked.connect(self.add_files)
        self.clear_button = QPushButton("清空文件")
        self.clear_button.clicked.connect(self.clear_files)
        actions.addWidget(self.add_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setMaximumHeight(76)

        layout.addWidget(self.header_widget)
        self.details_widget = QWidget()
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        details_layout.addWidget(hint_label)
        details_layout.addLayout(actions)
        details_layout.addWidget(self.file_list)
        layout.addWidget(self.details_widget)
        self._refresh()

    def _set_collapsed(self, collapsed: bool) -> None:
        self.collapsed = bool(collapsed)
        self.details_widget.setVisible(not self.collapsed)
        self.toggle_button.setText("⌄" if self.collapsed else "⌃")
        self.toggle_button.setToolTip("展开附件" if self.collapsed else "收起附件")

    def _toggle_collapsed(self) -> None:
        self._set_collapsed(not self.collapsed)

    def set_header_visible(self, visible: bool) -> None:
        self.header_widget.setVisible(bool(visible))

    def set_hint_visible(self, visible: bool) -> None:
        self._show_hint = bool(visible)
        self.hint_label.setVisible(self._show_hint and not self._paths)

    def add_files(self) -> None:
        current_dir = str(REPO_ROOT)
        if self._paths:
            current_dir = str(Path(self._paths[-1]).parent)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择需求附件",
            current_dir,
            ATTACHMENT_FILE_FILTER,
        )
        if file_paths:
            self.set_paths([*self._paths, *file_paths])

    def clear_files(self) -> None:
        self._paths = []
        self._refresh()

    def paths(self) -> List[str]:
        return list(self._paths)

    def set_paths(self, paths: List[str]) -> None:
        seen: set[str] = set()
        normalized: List[str] = []
        for item in paths:
            path = str(item).strip()
            if not path or path in seen:
                continue
            seen.add(path)
            normalized.append(path)
        self._paths = normalized
        if self._paths:
            self._set_collapsed(False)
        self._refresh()

    def _refresh(self) -> None:
        self.file_list.clear()
        for item in self._paths:
            path = Path(item)
            list_item = QListWidgetItem(f"{path.name}    {path.parent}")
            list_item.setData(Qt.UserRole, item)
            self.file_list.addItem(list_item)
        if self._paths:
            self.count_label.setText(f"{len(self._paths)} 个文件")
        else:
            self.count_label.setText("未添加文件")
        self.clear_button.setEnabled(bool(self._paths))
        self.file_list.setVisible(bool(self._paths))
        self.hint_label.setVisible(self._show_hint and not self._paths)
        self._set_collapsed(self.collapsed and not self._paths)
        self.paths_changed.emit()

