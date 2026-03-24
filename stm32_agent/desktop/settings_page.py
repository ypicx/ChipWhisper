from __future__ import annotations

import uuid
from typing import List

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..llm_config import (
    DEFAULT_SYSTEM_PROMPT,
    LlmProfile,
    load_llm_config,
    save_llm_config,
    write_llm_config_template,
)
from ..path_config import (
    CONFIG_KEYS,
    doctor_path_config,
    load_path_config,
    save_path_config,
    write_path_config_template,
)
from .llm_client import get_supported_provider_types, test_profile_connection
from .widgets import (
    REPO_ROOT,
    BackgroundTask,
    Card,
    CodeEditor,
    StatusChip,
    _json_text,
    _run_task_with_lifetime,
)

PATH_LABELS = {
    "keil_uv4_path": "Keil UV4.exe",
    "keil_fromelf_path": "Keil fromelf.exe",
    "stm32cubemx_install_path": "STM32CubeMX 安装目录",
    "stm32cube_repository_path": "STM32Cube Repository",
    "stm32cube_f1_package_path": "STM32Cube FW_F1 固件包",
    "renode_exe_path": "Renode executable",
    "stm32cube_g4_package_path": "STM32Cube FW_G4 固件包",
}

class SettingsPage(QWidget):
    paths_saved = Signal()
    profiles_changed = Signal()
    packs_changed = Signal()

    def __init__(self):
        super().__init__()
        self.thread_pool = QThreadPool.globalInstance()
        self._active_tasks: set[BackgroundTask] = set()
        self.profiles: List[LlmProfile] = []
        self.default_profile_id = ""

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        tabs = QTabWidget()
        root_layout.addWidget(tabs)

        env_page = QWidget()
        env_layout = QVBoxLayout(env_page)
        env_layout.setContentsMargins(0, 0, 0, 0)
        env_layout.setSpacing(16)

        env_card = Card()
        env_card_layout = QVBoxLayout(env_card)
        env_card_layout.setContentsMargins(18, 16, 18, 16)
        env_card_layout.setSpacing(12)
        env_title = QLabel("环境路径")
        env_title.setObjectName("SectionTitle")
        env_hint = QLabel("直接修改 Keil、CubeMX 和固件包路径，保存到本地配置文件。")
        env_hint.setObjectName("SectionHint")
        env_hint.setWordWrap(True)

        env_buttons = QHBoxLayout()
        self.reload_paths_button = QPushButton("重新加载")
        self.reload_paths_button.clicked.connect(self.reload_paths)
        self.save_paths_button = QPushButton("保存路径")
        self.save_paths_button.setObjectName("PrimaryButton")
        self.save_paths_button.clicked.connect(self.save_paths)
        self.init_paths_button = QPushButton("生成模板")
        self.init_paths_button.clicked.connect(self.init_path_config)
        self.doctor_paths_button = QPushButton("路径诊断")
        self.doctor_paths_button.clicked.connect(self.doctor_paths)
        for button in (
            self.reload_paths_button,
            self.save_paths_button,
            self.init_paths_button,
            self.doctor_paths_button,
        ):
            env_buttons.addWidget(button)
        env_buttons.addStretch(1)

        self.path_fields: dict[str, QLineEdit] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        for row, key in enumerate(CONFIG_KEYS):
            label = QLabel(PATH_LABELS.get(key, key))
            edit = QLineEdit()
            browse = QPushButton("浏览")
            browse.clicked.connect(lambda _=False, current_key=key: self._browse_path(current_key))
            self.path_fields[key] = edit
            grid.addWidget(label, row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(browse, row, 2)
        grid.setColumnStretch(1, 1)

        self.path_result_editor = CodeEditor(read_only=True)
        env_card_layout.addWidget(env_title)
        env_card_layout.addWidget(env_hint)
        env_card_layout.addLayout(env_buttons)
        env_card_layout.addLayout(grid)
        env_card_layout.addWidget(self.path_result_editor, 1)
        env_layout.addWidget(env_card, 1)

        llm_page = QWidget()
        llm_layout = QVBoxLayout(llm_page)
        llm_layout.setContentsMargins(0, 0, 0, 0)
        llm_layout.setSpacing(16)

        llm_card = Card()
        llm_card_layout = QVBoxLayout(llm_card)
        llm_card_layout.setContentsMargins(18, 16, 18, 16)
        llm_card_layout.setSpacing(14)
        llm_title = QLabel("模型与 API")
        llm_title.setObjectName("SectionTitle")
        llm_hint = QLabel("支持配置多组 API Profile，当前先以 OpenAI-compatible 和 Ollama 为主。")
        llm_hint.setObjectName("SectionHint")
        llm_hint.setWordWrap(True)

        llm_buttons = QHBoxLayout()
        self.reload_llm_button = QPushButton("重新加载")
        self.reload_llm_button.clicked.connect(self.reload_llm_profiles)
        self.save_llm_button = QPushButton("保存配置")
        self.save_llm_button.setObjectName("PrimaryButton")
        self.save_llm_button.clicked.connect(self.save_profiles)
        self.init_llm_button = QPushButton("生成模板")
        self.init_llm_button.clicked.connect(self.init_llm_config)
        self.test_profile_button = QPushButton("测试连接")
        self.test_profile_button.clicked.connect(self.test_selected_profile)
        for button in (
            self.reload_llm_button,
            self.save_llm_button,
            self.init_llm_button,
            self.test_profile_button,
        ):
            llm_buttons.addWidget(button)
        llm_buttons.addStretch(1)

        llm_splitter = QSplitter(Qt.Horizontal)

        profile_list_card = Card(elevated=True)
        profile_list_layout = QVBoxLayout(profile_list_card)
        profile_list_layout.setContentsMargins(16, 16, 16, 16)
        profile_list_layout.setSpacing(10)
        profile_list_title = QLabel("Profile 列表")
        profile_list_title.setObjectName("SectionTitle")
        self.profile_list = QListWidget()
        self.profile_list.currentRowChanged.connect(self._load_selected_profile)
        profile_actions = QHBoxLayout()
        add_profile_button = QPushButton("新增")
        add_profile_button.clicked.connect(self.add_profile)
        remove_profile_button = QPushButton("删除")
        remove_profile_button.setObjectName("DangerButton")
        remove_profile_button.clicked.connect(self.remove_profile)
        default_profile_button = QPushButton("设为默认")
        default_profile_button.clicked.connect(self.set_selected_as_default)
        profile_actions.addWidget(add_profile_button)
        profile_actions.addWidget(remove_profile_button)
        profile_actions.addWidget(default_profile_button)
        profile_list_layout.addWidget(profile_list_title)
        profile_list_layout.addWidget(self.profile_list, 1)
        profile_list_layout.addLayout(profile_actions)

        form_card = Card()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setSpacing(10)
        form_title = QLabel("Profile 详情")
        form_title.setObjectName("SectionTitle")
        self.default_chip = StatusChip("非默认", "neutral")

        form_header = QHBoxLayout()
        form_header.addWidget(form_title)
        form_header.addStretch(1)
        form_header.addWidget(self.default_chip)

        form = QFormLayout()
        form.setSpacing(10)
        self.profile_name_edit = QLineEdit()
        self.provider_type_combo = QComboBox()
        self.provider_type_combo.addItems(get_supported_provider_types())
        self.base_url_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.model_edit = QLineEdit()
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setSingleStep(0.05)
        self.enabled_checkbox = QCheckBox("启用该 Profile")
        self.system_prompt_edit = CodeEditor()
        self.system_prompt_edit.setMaximumHeight(160)

        form.addRow("名称", self.profile_name_edit)
        form.addRow("Provider 类型", self.provider_type_combo)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("Model", self.model_edit)
        form.addRow("Temperature", self.temperature_spin)
        form.addRow("状态", self.enabled_checkbox)
        form.addRow("System Prompt", self.system_prompt_edit)

        save_current_button = QPushButton("保存当前 Profile")
        save_current_button.clicked.connect(self.save_current_profile)
        self.llm_result_editor = CodeEditor(read_only=True)

        form_layout.addLayout(form_header)
        form_layout.addLayout(form)
        form_layout.addWidget(save_current_button)
        form_layout.addWidget(self.llm_result_editor, 1)

        llm_splitter.addWidget(profile_list_card)
        llm_splitter.addWidget(form_card)
        llm_splitter.setStretchFactor(0, 1)
        llm_splitter.setStretchFactor(1, 2)
        llm_splitter.setSizes([280, 620])

        llm_card_layout.addWidget(llm_title)
        llm_card_layout.addWidget(llm_hint)
        llm_card_layout.addLayout(llm_buttons)
        llm_card_layout.addWidget(llm_splitter, 1)
        llm_layout.addWidget(llm_card, 1)

        tabs.addTab(env_page, "环境路径")
        tabs.addTab(llm_page, "模型 API")

        self.reload_paths()
        self.reload_llm_profiles()

    def reload_paths(self) -> None:
        config_path, values = load_path_config()
        for key, edit in self.path_fields.items():
            edit.setText(values.get(key, ""))
        self.path_result_editor.setPlainText(_json_text({"config_path": str(config_path), "values": values}))

    def init_path_config(self) -> None:
        written = write_path_config_template()
        self.reload_paths()
        self.path_result_editor.setPlainText(_json_text({"written": str(written)}))
        self.paths_saved.emit()

    def save_paths(self) -> None:
        values = {key: edit.text().strip() for key, edit in self.path_fields.items()}
        written = save_path_config(values)
        self.path_result_editor.setPlainText(_json_text({"saved": str(written), "values": values}))
        self.paths_saved.emit()

    def doctor_paths(self) -> None:
        task = BackgroundTask(doctor_path_config)
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            lambda result: self.path_result_editor.setPlainText(_json_text(result.to_dict())),
            lambda text: self.path_result_editor.setPlainText(text),
        )

    def _browse_path(self, key: str) -> None:
        current = self.path_fields[key].text().strip() or str(REPO_ROOT)
        if key in {"keil_uv4_path", "keil_fromelf_path", "renode_exe_path"}:
            if key == "keil_uv4_path":
                title = "选择 UV4.exe"
            elif key == "keil_fromelf_path":
                title = "选择 fromelf.exe"
            else:
                title = "选择 renode.exe"
            file_path, _ = QFileDialog.getOpenFileName(self, title, current, "Executable (*.exe)")
            if file_path:
                self.path_fields[key].setText(file_path)
            return
        directory = QFileDialog.getExistingDirectory(self, f"选择 {PATH_LABELS.get(key, key)}", current)
        if directory:
            self.path_fields[key].setText(directory)

    def reload_llm_profiles(self) -> None:
        config = load_llm_config()
        self.profiles = list(config.profiles)
        self.default_profile_id = config.default_profile_id
        self._refresh_profile_list()
        self.llm_result_editor.setPlainText(_json_text(config.to_dict()))
        if self.profiles:
            self.profile_list.setCurrentRow(0)

    def init_llm_config(self) -> None:
        written = write_llm_config_template()
        self.reload_llm_profiles()
        self.llm_result_editor.setPlainText(_json_text({"written": str(written)}))
        self.profiles_changed.emit()

    def _refresh_profile_list(self) -> None:
        self.profile_list.clear()
        for profile in self.profiles:
            title = profile.name
            if profile.profile_id == self.default_profile_id:
                title += "  [默认]"
            if not profile.enabled:
                title += "  [停用]"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, profile.profile_id)
            self.profile_list.addItem(item)

    def add_profile(self) -> None:
        profile = LlmProfile(
            profile_id=uuid.uuid4().hex,
            name="New Profile",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="",
            model="",
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            temperature=0.2,
            enabled=True,
        )
        self.profiles.append(profile)
        self._refresh_profile_list()
        self.profile_list.setCurrentRow(len(self.profiles) - 1)

    def remove_profile(self) -> None:
        row = self.profile_list.currentRow()
        if row < 0 or row >= len(self.profiles):
            return
        profile = self.profiles.pop(row)
        if profile.profile_id == self.default_profile_id:
            self.default_profile_id = self.profiles[0].profile_id if self.profiles else ""
        self._refresh_profile_list()
        self.save_profiles()

    def set_selected_as_default(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        self.default_profile_id = profile.profile_id
        self._refresh_profile_list()
        self._update_default_chip(profile)
        self.save_profiles()

    def _selected_profile(self) -> LlmProfile | None:
        row = self.profile_list.currentRow()
        if row < 0 or row >= len(self.profiles):
            return None
        return self.profiles[row]

    def _load_selected_profile(self, row: int) -> None:
        if row < 0 or row >= len(self.profiles):
            return
        profile = self.profiles[row]
        self.profile_name_edit.setText(profile.name)
        self.provider_type_combo.setCurrentText(profile.provider_type)
        self.base_url_edit.setText(profile.base_url)
        self.api_key_edit.setText(profile.api_key)
        self.model_edit.setText(profile.model)
        self.temperature_spin.setValue(profile.temperature)
        self.enabled_checkbox.setChecked(profile.enabled)
        self.system_prompt_edit.setPlainText(profile.system_prompt)
        self._update_default_chip(profile)

    def _update_default_chip(self, profile: LlmProfile) -> None:
        if profile.profile_id == self.default_profile_id:
            self.default_chip.set_status("默认 Profile", "success")
        else:
            self.default_chip.set_status("非默认", "neutral")

    def save_current_profile(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        updated = LlmProfile(
            profile_id=profile.profile_id,
            name=self.profile_name_edit.text().strip() or "Unnamed Profile",
            provider_type=self.provider_type_combo.currentText().strip(),
            base_url=self.base_url_edit.text().strip(),
            api_key=self.api_key_edit.text(),
            model=self.model_edit.text().strip(),
            system_prompt=self.system_prompt_edit.toPlainText().strip() or DEFAULT_SYSTEM_PROMPT,
            temperature=float(self.temperature_spin.value()),
            enabled=self.enabled_checkbox.isChecked(),
        )
        self.profiles[self.profile_list.currentRow()] = updated
        self._refresh_profile_list()
        self.profile_list.setCurrentRow(self.profile_list.currentRow())
        self.llm_result_editor.setPlainText(_json_text(updated.to_dict()))

    def save_profiles(self) -> None:
        self.save_current_profile()
        written = save_llm_config(self.profiles, self.default_profile_id)
        self.llm_result_editor.setPlainText(
            _json_text(
                {
                    "saved": str(written),
                    "default_profile_id": self.default_profile_id,
                    "profile_count": len(self.profiles),
                }
            )
        )
        self.profiles_changed.emit()

    def test_selected_profile(self) -> None:
        self.save_current_profile()
        profile = self._selected_profile()
        if profile is None:
            return
        task = BackgroundTask(lambda: test_profile_connection(profile))
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            self._on_profile_test_finished,
            lambda text: self.llm_result_editor.setPlainText(text),
        )

    def _on_profile_test_finished(self, result: object) -> None:
        ok, detail = result
        self.llm_result_editor.setPlainText(_json_text({"ok": ok, "detail": detail}))


