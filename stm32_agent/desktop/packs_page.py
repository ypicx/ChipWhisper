from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..extension_packs import (
    doctor_packs,
    get_default_packs_dir,
    import_module_files,
    init_packs_dir,
    scaffold_module_pack,
)
from .widgets import (
    REPO_ROOT,
    BackgroundTask,
    Card,
    CodeEditor,
    _json_text,
    _run_task_with_lifetime,
    _timestamp,
)

class PacksPage(QWidget):
    packs_changed = Signal()

    def __init__(self):
        super().__init__()
        self.thread_pool = QThreadPool.globalInstance()
        self._active_tasks: set[BackgroundTask] = set()
        self.selected_vendor_files: List[str] = []

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        title = QLabel("模块扩展包")
        title.setObjectName("SectionTitle")
        hint = QLabel("把官方 .h / .c 示例文件导入 pack，并参与后续的规划和 Keil 工程生成。")
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        root_row = QHBoxLayout()
        self.packs_root_edit = QLineEdit()
        self.packs_root_edit.setReadOnly(True)
        self.packs_root_edit.setText(str(get_default_packs_dir()))
        refresh_root_button = QPushButton("刷新")
        refresh_root_button.clicked.connect(self.refresh_pack_summary)
        init_button = QPushButton("初始化 Packs")
        init_button.clicked.connect(self.init_pack_root)
        root_row.addWidget(self.packs_root_edit, 1)
        root_row.addWidget(refresh_root_button)
        root_row.addWidget(init_button)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.addWidget(QLabel("模块 Key"), 0, 0)
        self.module_key_edit = QLineEdit()
        self.module_key_edit.setPlaceholderText("例如：as608_uart")
        form.addWidget(self.module_key_edit, 0, 1, 1, 3)

        create_button = QPushButton("新建模块包")
        create_button.setObjectName("PrimaryButton")
        create_button.clicked.connect(self.create_module_pack)
        form.addWidget(create_button, 0, 4)

        files_title = QLabel("厂商源码文件")
        files_title.setObjectName("SectionTitle")
        files_hint = QLabel("选择模块官方提供的 .h / .c 文件。导入后会复制到 packs/modules/<key>/templates/modules/。")
        files_hint.setObjectName("SectionHint")
        files_hint.setWordWrap(True)

        files_row = QHBoxLayout()
        select_files_button = QPushButton("选择 .h/.c 文件")
        select_files_button.clicked.connect(self.select_vendor_files)
        clear_files_button = QPushButton("清空列表")
        clear_files_button.clicked.connect(self.clear_vendor_files)
        import_button = QPushButton("导入到模块包")
        import_button.setObjectName("PrimaryButton")
        import_button.clicked.connect(self.import_selected_vendor_files)
        doctor_button = QPushButton("诊断 Packs")
        doctor_button.clicked.connect(self.refresh_pack_summary)
        files_row.addWidget(select_files_button)
        files_row.addWidget(clear_files_button)
        files_row.addWidget(import_button)
        files_row.addWidget(doctor_button)
        files_row.addStretch(1)

        self.vendor_files_view = CodeEditor(read_only=True)
        self.vendor_files_view.setMaximumHeight(140)
        self.vendor_files_view.setPlainText("当前还没有选择厂商源码文件。")

        self.pack_result_editor = CodeEditor(read_only=True)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(root_row)
        layout.addLayout(form)
        layout.addWidget(files_title)
        layout.addWidget(files_hint)
        layout.addLayout(files_row)
        layout.addWidget(self.vendor_files_view)
        layout.addWidget(self.pack_result_editor, 1)

        root_layout.addWidget(card, 1)
        self.refresh_pack_summary()

    def init_pack_root(self) -> None:
        written = init_packs_dir()
        self.packs_root_edit.setText(str(written))
        self.pack_result_editor.setPlainText(_json_text({"packs_dir": str(written), "status": "initialized"}))
        self.packs_changed.emit()
        self.refresh_pack_summary()

    def create_module_pack(self) -> None:
        module_key = self.module_key_edit.text().strip()
        if not module_key:
            QMessageBox.warning(self, "缺少模块 Key", "请先输入模块 key，例如 as608_uart。")
            return
        try:
            path = scaffold_module_pack(module_key)
        except Exception as exc:  # pragma: no cover - GUI runtime path
            QMessageBox.critical(self, "创建模块包失败", str(exc))
            self.pack_result_editor.setPlainText(traceback.format_exc())
            return
        self.pack_result_editor.setPlainText(
            _json_text({"module_key": module_key, "module_pack_dir": str(path), "status": "created"})
        )
        self.packs_changed.emit()
        self.refresh_pack_summary()

    def select_vendor_files(self) -> None:
        current_dir = str(Path(self.selected_vendor_files[0]).parent) if self.selected_vendor_files else str(REPO_ROOT)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择厂商 .h / .c 文件",
            current_dir,
            "C Source/Header (*.c *.h)",
        )
        if not file_paths:
            return
        self.selected_vendor_files = file_paths
        self._refresh_vendor_files_view()

    def clear_vendor_files(self) -> None:
        self.selected_vendor_files = []
        self._refresh_vendor_files_view()

    def import_selected_vendor_files(self) -> None:
        module_key = self.module_key_edit.text().strip()
        if not module_key:
            QMessageBox.warning(self, "缺少模块 Key", "请先输入模块 key，再导入厂商源码。")
            return
        if not self.selected_vendor_files:
            QMessageBox.warning(self, "缺少源码文件", "请先选择至少一个 .h 或 .c 文件。")
            return
        self.pack_result_editor.setPlainText("正在导入厂商源码文件...")
        task = BackgroundTask(lambda: import_module_files(module_key, self.selected_vendor_files))
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            self._on_import_vendor_files_finished,
            self._on_import_vendor_files_failed,
        )

    def _on_import_vendor_files_finished(self, result) -> None:
        self.pack_result_editor.setPlainText(_json_text(result.to_dict()))
        self.packs_changed.emit()
        self.refresh_pack_summary()

    def _on_import_vendor_files_failed(self, details: str) -> None:  # pragma: no cover - GUI runtime path
        self.pack_result_editor.setPlainText(details)
        QMessageBox.critical(self, "导入厂商源码失败", details)

    def refresh_pack_summary(self) -> None:
        self.packs_root_edit.setText(str(get_default_packs_dir()))
        task = BackgroundTask(doctor_packs)
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            self._on_doctor_packs_finished,
            lambda text: self.pack_result_editor.setPlainText(text),
        )

    def _on_doctor_packs_finished(self, result) -> None:
        self.pack_result_editor.setPlainText(_json_text(result.to_dict()))

    def _refresh_vendor_files_view(self) -> None:
        if not self.selected_vendor_files:
            self.vendor_files_view.setPlainText("当前还没有选择厂商源码文件。")
            return
        self.vendor_files_view.setPlainText("\n".join(self.selected_vendor_files))


