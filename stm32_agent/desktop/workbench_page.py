from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, List

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..app_logic_drafter import draft_app_logic_for_plan, merge_generated_app_logic
from ..builder import build_project, doctor_project, get_builder_display_name
from ..cube_repository import doctor_cube_f1_package
from ..keil_generator import scaffold_from_request
from ..llm_config import LlmProfile, load_llm_config
from ..path_config import doctor_path_config
from ..planner import plan_request
from ..renode_runner import run_renode_project
from ..extension_packs import doctor_packs
from ..graph import render_retrieved_context, retrieve_relevant_chunks
from .attachments import collect_attachment_digests, render_attachment_list
from .request_bridge import draft_request_json
from .project_explorer import AttachmentPickerWidget, ProjectExplorerWidget
from .widgets import (
    REPO_ROOT,
    BackgroundTask,
    Card,
    CodeEditor,
    GuideCard,
    MetricCard,
    _json_text,
    _run_task_with_lifetime,
    _timestamp,
)

class WorkbenchPage(QWidget):
    project_activated = Signal(str)

    def __init__(self):
        super().__init__()
        self.thread_pool = QThreadPool.globalInstance()
        self._active_tasks: set[BackgroundTask] = set()
        self.repo_root = REPO_ROOT
        self.current_project_dir = ""
        self.current_hex_file = ""
        self.llm_profiles: List[LlmProfile] = []
        self.default_llm_profile_id = ""

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(18)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self.paths_card = MetricCard("环境准备", "检查 Keil、CubeMX 和固件包路径是否就绪。")
        self.packs_card = MetricCard("模块库", "查看当前能用的芯片、模块和扩展包数量。")
        self.project_card = MetricCard("当前项目", "生成成功后，这里会显示当前工程并联动右侧项目树。")
        cards_row.addWidget(self.paths_card, 1)
        cards_row.addWidget(self.packs_card, 1)
        cards_row.addWidget(self.project_card, 1)

        main_splitter = QSplitter(Qt.Horizontal)

        request_card = Card()
        request_layout = QVBoxLayout(request_card)
        request_layout.setContentsMargins(18, 16, 18, 16)
        request_layout.setSpacing(12)
        request_title = QLabel("高级工具（可选）")
        request_title.setObjectName("SectionTitle")
        request_hint = QLabel("这里保留给熟悉流程的用户。新手更推荐直接去左侧“对话”页，用自然语言说需求。")
        request_hint.setObjectName("SectionHint")
        request_hint.setWordWrap(True)

        self.guide_card = GuideCard()

        bridge_hint = QLabel("不会写 JSON 也没关系，直接在下面用中文描述需求。")
        bridge_hint.setObjectName("SectionHint")
        bridge_hint.setWordWrap(True)
        self.bridge_prompt_editor = QPlainTextEdit()
        self.bridge_prompt_editor.setObjectName("CodeEditor")
        self.bridge_prompt_editor.setPlaceholderText("例如：用 STM32F103C8T6 做一个带 AS608 指纹模块和 OLED 的门禁原型。")
        self.bridge_prompt_editor.setMaximumHeight(100)
        self.bridge_attachments = AttachmentPickerWidget(
            "需求附件（可选）",
            "支持 PDF、DOCX、XLSX、CSV、TXT、JSON 和图片。已选文件会随下一次 AI 起草一起提交。",
        )

        bridge_row = QHBoxLayout()
        self.bridge_profile_combo = QComboBox()
        self.bridge_profile_combo.setToolTip("用于把中文需求起草成工程配置的模型 Profile")
        self.bridge_generate_button = QPushButton("AI 帮我转成配置")
        self.bridge_generate_button.setObjectName("PrimaryButton")
        self.bridge_generate_button.clicked.connect(self.run_bridge_request)
        bridge_row.addWidget(self.bridge_profile_combo, 1)
        bridge_row.addWidget(self.bridge_generate_button)

        example_row = QHBoxLayout()
        self.example_combo = QComboBox()
        self.load_example_button = QPushButton("载入示例")
        self.load_example_button.clicked.connect(self.load_selected_example)
        example_row.addWidget(self.example_combo, 1)
        example_row.addWidget(self.load_example_button)

        output_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(str(self.repo_root / "out" / "desktop_workbench_project"))
        self.output_dir_edit.setPlaceholderText("工程输出目录（生成出来的 Keil 工程会放这里）")
        browse_output_button = QPushButton("选择工程保存位置")
        browse_output_button.clicked.connect(self._browse_output_dir)
        output_row.addWidget(self.output_dir_edit, 1)
        output_row.addWidget(browse_output_button)

        plan_row = QHBoxLayout()
        self.plan_button = QPushButton("先检查能不能做")
        self.plan_button.setObjectName("PrimaryButton")
        self.plan_button.clicked.connect(self.run_plan)
        self.scaffold_button = QPushButton("生成 Keil 工程")
        self.scaffold_button.setObjectName("PrimaryButton")
        self.scaffold_button.clicked.connect(self.run_scaffold)
        plan_row.addWidget(self.plan_button)
        plan_row.addWidget(self.scaffold_button)
        plan_row.addStretch(1)

        request_json_hint = QLabel("工程配置 JSON（高级）")
        request_json_hint.setObjectName("SectionTitle")
        request_json_caption = QLabel("如果你不熟悉 JSON，可以先不用改这里，直接用上面的自然语言和按钮。")
        request_json_caption.setObjectName("SectionHint")
        request_json_caption.setWordWrap(True)
        self.request_editor = CodeEditor()
        self.request_editor.setPlaceholderText("这里会显示工程配置 JSON。不懂也没关系，先用上面的中文输入。")

        request_layout.addWidget(request_title)
        request_layout.addWidget(request_hint)
        request_layout.addWidget(self.guide_card)
        request_layout.addWidget(bridge_hint)
        request_layout.addWidget(self.bridge_prompt_editor)
        request_layout.addWidget(self.bridge_attachments)
        request_layout.addLayout(bridge_row)
        request_layout.addLayout(example_row)
        request_layout.addLayout(output_row)
        request_layout.addLayout(plan_row)
        request_layout.addWidget(request_json_hint)
        request_layout.addWidget(request_json_caption)
        request_layout.addWidget(self.request_editor, 1)

        results_card = Card()
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(18, 16, 18, 16)
        results_layout.setSpacing(12)
        results_title = QLabel("2. 检查结果并导出文件")
        results_title.setObjectName("SectionTitle")
        results_hint = QLabel("这里会显示环境检查、规划结果、编译日志和 HEX 路径。新手常用按钮都在这一栏。")
        results_hint.setObjectName("SectionHint")
        results_hint.setWordWrap(True)

        tool_row = QHBoxLayout()
        self.doctor_paths_button = QPushButton("检查环境")
        self.doctor_paths_button.clicked.connect(self.run_doctor_paths)
        self.doctor_packs_button = QPushButton("检查模块库")
        self.doctor_packs_button.clicked.connect(self.run_doctor_packs)
        self.doctor_cube_button = QPushButton("检查 STM32 固件包")
        self.doctor_cube_button.clicked.connect(self.run_doctor_cube)
        self.doctor_keil_button = QPushButton("检查生成的工程")
        self.doctor_keil_button.clicked.connect(self.run_doctor_keil)
        self.build_keil_button = QPushButton("编译并导出 HEX")
        self.build_keil_button.clicked.connect(self.run_build_keil)
        for button in (
            self.doctor_paths_button,
            self.doctor_packs_button,
            self.doctor_cube_button,
            self.doctor_keil_button,
            self.build_keil_button,
        ):
            tool_row.addWidget(button)
        self.renode_validate_checkbox = QCheckBox("编译成功后用 Renode 做仿真验证")
        self.renode_validate_checkbox.setChecked(False)
        self.renode_validate_checkbox.setToolTip("可选。当前首版主要支持映射到 Renode STM32F103 平台的工程。")
        tool_row.addWidget(self.renode_validate_checkbox)
        tool_row.addStretch(1)

        artifact_row = QHBoxLayout()
        artifact_label = QLabel("导出的 HEX")
        artifact_label.setObjectName("SectionHint")
        self.hex_file_edit = QLineEdit()
        self.hex_file_edit.setReadOnly(True)
        self.hex_file_edit.setPlaceholderText("编译成功后，这里会显示 HEX 文件路径")
        self.open_hex_dir_button = QPushButton("打开目录")
        self.open_hex_dir_button.setEnabled(False)
        self.open_hex_dir_button.clicked.connect(self.open_hex_directory)
        artifact_row.addWidget(artifact_label)
        artifact_row.addWidget(self.hex_file_edit, 1)
        artifact_row.addWidget(self.open_hex_dir_button)

        self.result_tabs = QTabWidget()
        self.project_ir_editor = CodeEditor(read_only=True)
        self.environment_editor = CodeEditor(read_only=True)
        self.log_editor = CodeEditor(read_only=True)
        self.result_tabs.addTab(self.project_ir_editor, "工程配置结果")
        self.result_tabs.addTab(self.environment_editor, "环境与编译")
        self.result_tabs.addTab(self.log_editor, "操作记录")

        results_layout.addWidget(results_title)
        results_layout.addWidget(results_hint)
        results_layout.addLayout(tool_row)
        results_layout.addLayout(artifact_row)
        results_layout.addWidget(self.result_tabs, 1)

        self.explorer = ProjectExplorerWidget(
            title="3. 查看生成出来的工程",
            hint="生成成功后，这里会显示项目树。想看代码就点左边文件，右边会直接预览内容。",
        )

        self.explorer.hint_label.setVisible(False)
        main_splitter.addWidget(request_card)
        main_splitter.addWidget(results_card)
        main_splitter.addWidget(self.explorer)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 2)
        main_splitter.setStretchFactor(2, 3)
        main_splitter.setSizes([420, 460, 640])

        root_layout.addLayout(cards_row)
        root_layout.addWidget(main_splitter, 1)

        self._load_examples()
        self.reload_llm_profiles()
        self.run_doctor_paths()
        self.run_doctor_packs()
        self.project_card.update_metric("还没生成", "先输入需求或载入示例，再点“生成 Keil 工程”。", "下一步", "warning")

    def _load_examples(self) -> None:
        self.example_combo.clear()
        self.example_combo.addItem("可选：载入一个示例", "")
        examples_dir = self.repo_root / "examples"
        example_files = sorted(examples_dir.glob("*.json"))
        for file_path in example_files:
            self.example_combo.addItem(file_path.name, str(file_path))
        self.example_combo.setCurrentIndex(0)

    def _set_beginner_step(self, step_text: str, title: str, hint: str, kind: str = "neutral") -> None:
        self.guide_card.set_step(step_text, title, hint, kind)

    def reload_llm_profiles(self) -> None:
        config = load_llm_config()
        self.llm_profiles = [profile for profile in config.profiles if profile.enabled]
        self.default_llm_profile_id = config.default_profile_id
        self.bridge_profile_combo.clear()
        for profile in self.llm_profiles:
            self.bridge_profile_combo.addItem(profile.name, profile.profile_id)
        if not self.llm_profiles:
            self.bridge_profile_combo.addItem("未配置可用 Profile", "")
            self.bridge_profile_combo.setEnabled(False)
            self.bridge_generate_button.setEnabled(False)
            return
        self.bridge_profile_combo.setEnabled(True)
        self.bridge_generate_button.setEnabled(True)
        default_index = 0
        for index, profile in enumerate(self.llm_profiles):
            if profile.profile_id == self.default_llm_profile_id:
                default_index = index
                break
        self.bridge_profile_combo.setCurrentIndex(default_index)

    def load_selected_example(self) -> None:
        path = self.example_combo.currentData()
        if not path:
            return
        file_path = Path(path)
        self.request_editor.setPlainText(file_path.read_text(encoding="utf-8"))
        self.output_dir_edit.setText(str(self.repo_root / "out" / f"{file_path.stem}_desktop"))
        self.append_log(f"已载入示例请求: {file_path.name}")
        self._set_beginner_step(
            "第 2 步",
            "示例已经载入，可以直接往下走",
            "现在点“先检查能不能做”。如果你想看配置细节，可以看下面的 JSON。",
            "success",
        )

    def _browse_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", str(self.repo_root / "out"))
        if directory:
            self.output_dir_edit.setText(directory)

    def append_log(self, message: str) -> None:
        existing = self.log_editor.toPlainText()
        block = f"[{_timestamp()}] {message}"
        self.log_editor.setPlainText(existing + ("\n" if existing else "") + block)
        self.log_editor.verticalScrollBar().setValue(self.log_editor.verticalScrollBar().maximum())

    def _set_hex_file(self, path: str) -> None:
        self.current_hex_file = path.strip()
        self.hex_file_edit.setText(self.current_hex_file)
        self.open_hex_dir_button.setEnabled(bool(self.current_hex_file and Path(self.current_hex_file).exists()))

    def _parse_payload(self) -> dict[str, object] | None:
        try:
            payload = json.loads(self.request_editor.toPlainText())
        except ValueError as exc:
            QMessageBox.critical(self, "请求 JSON 无效", f"无法解析请求 JSON:\n{exc}")
            self.append_log(f"请求 JSON 解析失败: {exc}")
            return None
        if not isinstance(payload, dict):
            QMessageBox.critical(self, "请求 JSON 无效", "请求根节点必须是对象。")
            return None
        return payload

    def _current_bridge_profile(self) -> LlmProfile | None:
        profile_id = self.bridge_profile_combo.currentData()
        for profile in self.llm_profiles:
            if profile.profile_id == profile_id:
                return profile
        return self.llm_profiles[0] if self.llm_profiles else None

    def run_bridge_request(self) -> None:
        profile = self._current_bridge_profile()
        if profile is None:
            QMessageBox.warning(self, "缺少模型 Profile", "请先在配置页启用一个可用的模型 Profile。")
            return
        prompt = self.bridge_prompt_editor.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "缺少自然语言需求", "请先输入自然语言需求描述。")
            return
        attachment_batch = collect_attachment_digests(self.bridge_attachments.paths())
        if attachment_batch.errors:
            QMessageBox.warning(self, "附件读取失败", "\n".join(attachment_batch.errors[:8]))
            return
        self.bridge_generate_button.setEnabled(False)
        self.append_log(f"开始通过 {profile.name} 起草 request JSON。")
        if attachment_batch.attachments:
            self.append_log("本次会一起参考这些附件:\n" + render_attachment_list(self.bridge_attachments.paths()))
        self._set_beginner_step(
            "第 1 步",
            "正在把中文需求转成工程配置",
            "这一步完成后，下面会自动生成 JSON。你不需要自己手写。",
            "warning",
        )
        self._start_task(
            lambda: self._draft_request_with_retrieval(profile, prompt, attachment_batch.attachments),
            self._on_bridge_request_finished,
            "AI 请求起草",
        )

    def _on_bridge_request_finished(self, result) -> None:
        self.bridge_generate_button.setEnabled(bool(self.llm_profiles))
        self.environment_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.environment_editor)
        if not result.ok:
            self.append_log(f"AI 请求起草失败: {'; '.join(result.errors)}")
            self._set_beginner_step(
                "第 1 步",
                "AI 生成配置失败了",
                "先去“配置”页确认模型 API 可用，或者先载入一个示例继续体验流程。",
                "error",
            )
            QMessageBox.warning(self, "AI 请求起草失败", "\n".join(result.errors))
            return
        self.request_editor.setPlainText(_json_text(result.request_payload))
        warning_text = f" 警告 {len(result.warnings)} 条。" if result.warnings else ""
        self.append_log(f"AI 请求起草完成，已回填 request JSON。{warning_text}")
        self._set_beginner_step(
            "第 2 步",
            "工程配置已经准备好了",
            "现在建议点“先检查能不能做”，确认芯片、模块和引脚分配都没问题。",
            "success",
        )

    def _start_task(
        self,
        fn: Callable[[], object],
        on_finished: Callable[[object], None],
        error_prefix: str,
    ) -> None:
        task = BackgroundTask(fn)
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            on_finished,
            lambda text: self._handle_task_error(error_prefix, text),
        )

    def _handle_task_error(self, prefix: str, details: str) -> None:  # pragma: no cover - GUI runtime path
        self.bridge_generate_button.setEnabled(bool(self.llm_profiles))
        self.environment_editor.setPlainText(details)
        self.result_tabs.setCurrentWidget(self.environment_editor)
        self.append_log(f"{prefix}失败，请查看详细错误。")
        self._set_beginner_step(
            "出错了",
            f"{prefix}失败",
            "先看右侧“环境与编译”里的错误信息，再继续下一步。",
            "error",
        )
        QMessageBox.critical(self, f"{prefix}失败", details)

    def _retrieve_chat_context(self, user_prompt: str) -> str:
        prompt = str(user_prompt or "").strip()
        if not prompt:
            return ""
        try:
            chunks, _filters = retrieve_relevant_chunks(
                prompt,
                self.repo_root,
                active_project_dir=self.active_project_dir,
            )
            return render_retrieved_context(chunks)
        except Exception:
            return ""

    def _draft_request_with_retrieval(self, profile: LlmProfile, prompt: str, attachments) -> object:
        retrieved_context = self._retrieve_chat_context(prompt)
        return draft_request_json(
            profile,
            prompt,
            active_project_dir=self.current_project_dir,
            attachments=attachments,
            retrieved_context=retrieved_context,
        )

    def run_plan(self) -> None:
        payload = self._parse_payload()
        if payload is None:
            return
        self.append_log("开始执行规划。")
        self._start_task(lambda: plan_request(payload), self._on_plan_finished, "规划")

    def _on_plan_finished(self, result) -> None:
        self.project_ir_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.project_ir_editor)
        if result.feasible:
            module_count = len(result.project_ir.get("modules", []))
            self.append_log(f"规划完成，可行。芯片: {result.chip}，模块数: {module_count}")
            self.project_card.update_metric("已规划", f"{result.chip} · {module_count} 个模块", "可行", "success")
        else:
            self.append_log(f"规划失败: {'; '.join(result.errors)}")
            self.project_card.update_metric("规划失败", "请修正请求或扩展资源定义。", "阻塞", "error")

    def run_scaffold(self) -> None:
        payload = self._parse_payload()
        if payload is None:
            return
        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "缺少输出目录", "请先指定生成工程输出目录。")
            return
        profile = self._current_bridge_profile()
        user_prompt = self.bridge_prompt_editor.toPlainText().strip()
        self.append_log(f"开始生成工程: {output_dir}")
        self._start_task(
            lambda: scaffold_from_request(
                self._prepare_payload_for_generation(
                    payload,
                    profile,
                    user_prompt,
                ),
                output_dir,
            ),
            self._on_scaffold_finished,
            "生成工程",
        )

    def _on_scaffold_finished(self, result) -> None:
        self.project_ir_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.project_ir_editor)
        if not result.feasible:
            self.append_log("工程生成失败。")
            self.project_card.update_metric("生成失败", "请检查请求和规划结果。", "失败", "error")
            return
        self.current_project_dir = str(Path(result.project_dir).resolve())
        self._set_hex_file("")
        self.project_card.update_metric(Path(self.current_project_dir).name, self.current_project_dir, "已生成", "success")
        self.explorer.set_root_path(self.current_project_dir)
        self.project_activated.emit(self.current_project_dir)
        self.append_log(f"工程生成完成: {self.current_project_dir}")

    def _prepare_payload_for_generation(
        self,
        payload: dict[str, object],
        profile: LlmProfile | None,
        user_prompt: str,
    ) -> dict[str, object]:
        working_payload = dict(payload)
        if profile is None or not str(working_payload.get("app_logic_goal", "")).strip():
            return working_payload
        current_logic = working_payload.get("app_logic", {})
        if isinstance(current_logic, dict) and any(
            str(current_logic.get(section, "")).strip()
            for section in ("AppTop", "AppInit", "AppLoop", "AppCallbacks")
        ):
            return working_payload
        plan = plan_request(working_payload)
        if not plan.feasible:
            return working_payload
        draft = draft_app_logic_for_plan(
            profile,
            user_prompt or "Generate the project from the current request JSON.",
            working_payload,
            plan,
        )
        if draft.ok and (any(draft.app_logic.values()) or draft.app_logic_ir):
            return merge_generated_app_logic(
                working_payload,
                draft.app_logic,
                app_logic_ir=draft.app_logic_ir,
            )
        return working_payload

    def run_doctor_paths(self) -> None:
        self.append_log("开始检查路径配置。")
        self._start_task(doctor_path_config, self._on_doctor_paths_finished, "路径检查")

    def _on_doctor_paths_finished(self, result) -> None:
        self.environment_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.environment_editor)
        valid_count = sum(1 for item in result.paths if item.exists)
        total_count = len(result.paths)
        chip_kind = "success" if valid_count == total_count else "warning"
        chip_text = "就绪" if valid_count == total_count else "待补"
        self.paths_card.update_metric(
            f"{valid_count} / {total_count}",
            f"配置文件: {result.config_path}",
            chip_text,
            chip_kind,
        )
        self.append_log(f"路径检查完成: {valid_count}/{total_count} 项存在。")

    def run_doctor_packs(self) -> None:
        self.append_log("开始检查扩展 Packs。")
        self._start_task(doctor_packs, self._on_doctor_packs_finished, "Packs 检查")

    def _on_doctor_packs_finished(self, result) -> None:
        self.environment_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.environment_editor)
        chip_kind = "success" if not result.errors else "warning"
        chip_text = "已载入" if not result.errors else "有问题"
        module_count = len(result.modules)
        chip_count = len(result.chips)
        self.packs_card.update_metric(
            f"{module_count} 模块",
            f"{chip_count} 芯片 · packs 目录: {result.packs_dir}",
            chip_text,
            chip_kind,
        )
        self.append_log(f"Packs 检查完成: 芯片 {chip_count}，模块 {module_count}。")

    def run_doctor_cube(self) -> None:
        self.append_log("开始检查 STM32Cube 固件包。")
        self._start_task(doctor_cube_f1_package, self._on_doctor_cube_finished, "固件包检查")

    def _on_doctor_cube_finished(self, result) -> None:
        self.environment_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.environment_editor)
        self.append_log("固件包检查完成。")

    def _project_target(self) -> str:
        if self.current_project_dir:
            return self.current_project_dir
        return self.output_dir_edit.text().strip()

    def run_doctor_keil(self) -> None:
        project_target = self._project_target()
        if not project_target:
            QMessageBox.warning(self, "缺少工程目录", "请先生成工程或指定工程目录。")
            return
        self.append_log("开始检查 Keil 工程。")
        self._start_task(
            lambda: doctor_project(project_target),
            self._on_doctor_keil_finished,
            "Keil 工程检查",
        )

    def _on_doctor_keil_finished(self, result) -> None:
        self.environment_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.environment_editor)
        builder_name = get_builder_display_name(getattr(result, "builder_kind", ""))
        self.append_log(f"{builder_name} 工程检查完成。")

    def run_build_keil(self) -> None:
        project_target = self._project_target()
        if not project_target:
            QMessageBox.warning(self, "缺少工程目录", "请先生成工程或指定工程目录。")
            return
        self.append_log("开始执行 Keil 编译并导出 HEX。")
        self._start_task(
            lambda: build_project(project_target),
            self._on_build_keil_finished,
            "Keil 构建",
        )

    def _on_build_keil_finished(self, result) -> None:
        self.environment_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.environment_editor)
        builder_name = get_builder_display_name(getattr(result, "builder_kind", ""))
        if result.built:
            if getattr(result, "hex_generated", False) and getattr(result, "hex_file", ""):
                hex_path = str(Path(result.hex_file).resolve())
                self._set_hex_file(hex_path)
                self.append_log(f"{builder_name} 构建完成，HEX 已生成: {hex_path}")
            else:
                self._set_hex_file("")
                self.append_log(f"{builder_name} 构建完成，但当前没有导出 HEX。")
            if self.renode_validate_checkbox.isChecked():
                project_target = str(getattr(result, "project_dir", "")).strip() or self._project_target()
                self.append_log("开始执行 Renode 仿真验证。")
                self._start_task(
                    lambda project_target=project_target: run_renode_project(project_target),
                    self._on_renode_validation_finished,
                    "Renode 仿真验证",
                )
        else:
            self._set_hex_file("")
            self.append_log(f"{builder_name} 构建失败，请检查 build.log。")

    def _on_renode_validation_finished(self, result) -> None:
        self.environment_editor.setPlainText(_json_text(result.to_dict()))
        self.result_tabs.setCurrentWidget(self.environment_editor)
        if result.ran:
            summary = result.summary_lines[0] if result.summary_lines else "Renode 运行结束，未检测到显式错误。"
            if getattr(result, "validation_passed", None) is True:
                summary = "Renode 运行结束，UART 期望校验通过。"
            self.append_log(f"Renode 仿真验证完成: {summary}")
            if getattr(result, "log_path", ""):
                self.append_log(f"Renode 日志: {result.log_path}")
            if getattr(result, "uart_capture_path", ""):
                self.append_log(f"UART 捕获: {result.uart_capture_path}")
            return

        if getattr(result, "errors", None):
            self.append_log(f"Renode 仿真验证未通过: {result.errors[0]}")
        else:
            self.append_log("Renode 仿真验证未通过，请查看环境与编译页。")

    def open_hex_directory(self) -> None:
        if not self.current_hex_file:
            QMessageBox.information(self, "尚无 HEX", "请先执行一次“编译并导出 HEX”。")
            return
        hex_path = Path(self.current_hex_file)
        if not hex_path.exists():
            QMessageBox.warning(self, "HEX 不存在", f"没有找到 HEX 文件:\n{hex_path}")
            self._set_hex_file("")
            return
        os.startfile(str(hex_path.parent))  # pragma: no cover - GUI runtime path


