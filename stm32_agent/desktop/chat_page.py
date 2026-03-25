from __future__ import annotations

import json
import traceback
import uuid
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Callable, List

from PySide6.QtCore import (
    QSettings,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..app_logic_drafter import draft_app_logic_for_plan, merge_generated_app_logic
from ..builder import build_project, doctor_project, get_builder_display_name
from ..keil_generator import scaffold_from_request
from ..llm_config import LlmProfile, load_llm_config, save_llm_config
from ..path_config import doctor_path_config, load_path_config
from ..planner import plan_request
from ..renode_runner import run_renode_project
from ..graph import (
    GraphRuntime,
    STM32ProjectGraphSession,
    render_retrieved_context,
    retrieve_relevant_chunks,
)
from .attachments import (
    ATTACHMENT_FILE_FILTER,
    collect_attachment_digests,
    render_attachment_list,
    compose_multimodal_user_content,
)
from .chat_agent import detect_agent_action, run_chat_agent_workflow
from .chat_threads import (
    DesktopChatThread,
    build_thread_context_summary,
    build_thread_followup_context,
    create_chat_thread,
    derive_thread_title,
    derive_thread_status,
    format_thread_timeline,
    format_thread_list_label,
    format_thread_timestamp,
    get_default_chat_threads_path,
    load_chat_thread_store,
    save_chat_thread_store,
    summarize_thread,
    current_timestamp,
)
from .dialogs import ProposalDiffReviewDialog
from .engineering_state import ThreadEngineeringState
from .llm_client import get_supported_provider_types, stream_chat_completion, test_profile_connection
from .project_explorer import AttachmentPickerWidget, ProjectExplorerWidget
from .proposal_state import PendingProposalState
from .request_bridge import build_chat_system_prompt, draft_request_json
from .settings_page import PATH_LABELS
from .widgets import (
    REPO_ROOT,
    BackgroundTask,
    Card,
    ChatStreamThread,
    CodeEditor,
    LoadingOverlay,
    StatusChip,
    WorkflowDot,
    _decode_text_with_fallback,
    _json_text,
    _run_task_with_lifetime,
    _safe_icon,
    _simple_markdown_to_html,
    _timestamp,
)

class MessageBubble(QFrame):
    def __init__(self, role: str, text: str):
        super().__init__()
        self._role = role
        self._raw_text = text
        self.setProperty("chatRole", role)
        self.style().unpolish(self)
        self.style().polish(self)

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        if role == "user":
            self.setMaximumWidth(560)
            layout.setContentsMargins(14, 10, 14, 10)
        else:
            self.setMaximumWidth(760)
            layout.setContentsMargins(14, 12, 14, 12)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        header_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        if role != "user":
            self.avatar = QLabel("✧")
            self.avatar.setObjectName("ChatAvatar")
            self.avatar.setFixedSize(24, 24)
            self.avatar.setAlignment(Qt.AlignCenter)
            self.avatar.setStyleSheet(
                "background: #FAFAFA; color: #000000; border-radius: 12px; "
                "font-weight: 800; font-size: 14px;"
            )
            header_row.addWidget(self.avatar, 0, Qt.AlignVCenter)

            self.role_label = QLabel("ChipWhisper")
            self.role_label.setObjectName("ChatBubbleRole")
            header_row.addWidget(self.role_label, 0, Qt.AlignVCenter)

            self.timestamp_label = QLabel(_timestamp())
            self.timestamp_label.setObjectName("ChatTimestamp")
            header_row.addWidget(self.timestamp_label, 0, Qt.AlignVCenter)
            header_row.addStretch(1)
        else:
            self.avatar = None
            self.role_label = QLabel("")
            self.timestamp_label = QLabel(_timestamp())
            self.timestamp_label.setObjectName("ChatTimestamp")
            header_row.addStretch(1)
            header_row.addWidget(self.timestamp_label, 0, Qt.AlignVCenter)

        self.text_label = QTextBrowser()
        self.text_label.setObjectName("ChatBubbleContent")
        self.text_label.setOpenExternalLinks(True)
        self.text_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_label.setFrameShape(QFrame.NoFrame)
        self.text_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.text_label.document().setDocumentMargin(3)
        self.text_label.setViewportMargins(0, 1, 0, 3)
        self.text_label.document().contentsChanged.connect(self._adjust_height)
        self._set_html(text)

        layout.addLayout(header_row)
        layout.addWidget(self.text_label)

    def _set_html(self, text: str) -> None:
        self._raw_text = text
        if self._role == "user":
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self.text_label.setHtml(f"<p style='margin:0; line-height: 1.5;'>{escaped}</p>")
        else:
            self.text_label.setHtml(_simple_markdown_to_html(text))
        QTimer.singleShot(0, self._adjust_height)

    def _adjust_height(self) -> None:
        doc_height = self.text_label.document().documentLayout().documentSize().height()
        viewport_margins = self.text_label.viewportMargins()
        vertical_padding = viewport_margins.top() + viewport_margins.bottom() + 8
        target_height = int(doc_height + vertical_padding)
        self.text_label.setFixedHeight(max(30, min(target_height, 2000)))

    def append_text(self, chunk: str) -> None:
        self._raw_text += chunk
        self._set_html(self._raw_text)

    def set_text(self, text: str) -> None:
        self._set_html(text)


class NegotiationInlineCard(QFrame):
    """协商交互卡片，嵌入到聊天消息流中，替代侧边栏的协商 UI。"""

    def __init__(
        self,
        options: list,
        on_submit: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NegotiationInlineCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title_label = QLabel("方案协商")
        title_label.setObjectName("SidebarSectionTitle")
        hint_label = QLabel("规划遇到阻塞，请点击下方方案选项，或直接填写修改意见后提交：")
        hint_label.setObjectName("SectionHint")
        hint_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)

        self._feedback_input = QPlainTextEdit()
        self._feedback_input.setObjectName("CodeEditor")
        self._feedback_input.setPlaceholderText("选择上方方案后自动填入，或直接在此写修改意见…")
        self._feedback_input.setFixedHeight(72)

        for option in options[:3]:
            btn_title = str(option.get("title", "")).strip() or "建议方案"
            btn_summary = str(option.get("summary", "")).strip()
            btn_feedback = str(option.get("feedback", "")).strip()
            btn = QPushButton(btn_title)
            btn.setObjectName("NegotiationOptionButton")
            if btn_summary:
                btn.setToolTip(btn_summary)
            btn.clicked.connect(
                lambda _checked=False, fb=btn_feedback: self._feedback_input.setPlainText(fb)
            )
            layout.addWidget(btn)

        layout.addWidget(self._feedback_input)

        submit_btn = QPushButton("采纳并重算")
        submit_btn.setObjectName("PrimaryButton")
        submit_btn.clicked.connect(lambda: on_submit(self._feedback_input.toPlainText().strip()))
        layout.addWidget(submit_btn)

    def get_feedback(self) -> str:
        return self._feedback_input.toPlainText().strip()


class ChatPage(QWidget):
    project_activated = Signal(str)

    def __init__(self):
        super().__init__()
        self.thread_pool = QThreadPool.globalInstance()
        self._active_tasks: set[BackgroundTask] = set()
        self.conversation: List[dict[str, object]] = []
        self.display_conversation: List[dict[str, str]] = []
        self.chat_thread: ChatStreamThread | None = None
        self.active_assistant_bubble: MessageBubble | None = None
        self.active_project_dir = ""
        self.chat_threads: List[DesktopChatThread] = []
        self.current_thread_id = ""
        self.chat_threads_path = get_default_chat_threads_path(REPO_ROOT)
        self._thread_engineering_state = ThreadEngineeringState()
        self.thread_graph_sessions: dict[str, STM32ProjectGraphSession] = {}
        self.thread_graph_thread_ids: dict[str, str] = {}
        self.max_context_messages = 12
        self._pending_proposal_state = PendingProposalState()
        self._active_negotiation_card: NegotiationInlineCard | None = None
        self.pending_graph_session: STM32ProjectGraphSession | None = None
        self.profiles: List[LlmProfile] = []
        self.default_profile_id = ""
        self.sidebar_profile_records: List[LlmProfile] = []

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(16, 14, 16, 16)
        root_layout.setSpacing(0)

        thread_panel = self._build_thread_panel()
        left_panel = self._build_dialogue_workspace_panel()

        right_panel = QFrame()
        right_panel.setObjectName("SolutionSidebarPanel")
        self.right_panel = right_panel
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_panel.setMinimumWidth(400)
        right_panel.setMaximumWidth(520)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)
        sidebar_title = QLabel("方案与工程侧栏")
        sidebar_title.setObjectName("SectionTitle")
        self.sidebar_title_label = sidebar_title
        self.sidebar_toggle_button = QToolButton()
        self.sidebar_toggle_button.setObjectName("PanelToggleButton")
        self.sidebar_toggle_button.setText("‹")
        self.sidebar_toggle_button.setAutoRaise(True)
        self.sidebar_toggle_button.setFixedSize(32, 32)
        self.sidebar_toggle_button.setText("‹")
        self.sidebar_toggle_button.setToolTip("中央工作区固定展开")
        self.sidebar_toggle_button.clicked.connect(self._toggle_sidebar_panel)
        self.sidebar_toggle_button.setVisible(False)
        sidebar_hint = QLabel("把方案摘要、工程文件和执行状态固定在右侧，聊天区保持中间为主。")
        sidebar_hint.setObjectName("SectionHint")
        sidebar_hint.setWordWrap(True)
        sidebar_title.setToolTip(sidebar_hint.text())
        sidebar_hint.setVisible(False)
        sidebar_title_row = QHBoxLayout()
        sidebar_title_row.setContentsMargins(0, 0, 0, 0)
        sidebar_title_row.setSpacing(8)
        sidebar_title_row.addWidget(sidebar_title)
        sidebar_title_row.addStretch(1)
        sidebar_title_row.addWidget(self.sidebar_toggle_button)
        self.profile_summary_text = "模型：未配置"
        self.project_summary_text = "工程：未打开"
        self.sidebar_meta_label = QLabel()
        self.sidebar_meta_label.setObjectName("MetricCaption")
        self.sidebar_meta_label.setWordWrap(True)
        self.sidebar_model_value = QLabel("未配置")
        self.sidebar_model_value.setObjectName("SidebarSummaryValue")
        self.sidebar_model_value.setWordWrap(True)
        self.sidebar_project_value = QLabel("未打开")
        self.sidebar_project_value.setObjectName("SidebarSummaryValue")
        self.sidebar_project_value.setWordWrap(True)
        self.sidebar_model_caption = QLabel("模型")
        self.sidebar_model_caption.setObjectName("SidebarSummaryCaption")
        self.sidebar_project_caption = QLabel("工程")
        self.sidebar_project_caption.setObjectName("SidebarSummaryCaption")
        self.sidebar_summary_card = Card()
        self.sidebar_summary_card.setObjectName("SidebarSummaryCard")
        sidebar_summary_layout = QVBoxLayout(self.sidebar_summary_card)
        sidebar_summary_layout.setContentsMargins(12, 10, 12, 10)
        sidebar_summary_layout.setSpacing(8)
        sidebar_summary_layout.addWidget(self.sidebar_meta_label)
        sidebar_summary_grid = QGridLayout()
        sidebar_summary_grid.setHorizontalSpacing(8)
        sidebar_summary_grid.setVerticalSpacing(4)
        sidebar_summary_grid.addWidget(self.sidebar_model_caption, 0, 0)
        sidebar_summary_grid.addWidget(self.sidebar_model_value, 1, 0, 1, 2)
        sidebar_summary_grid.addWidget(self.sidebar_project_caption, 2, 0)
        sidebar_summary_grid.addWidget(self.sidebar_project_value, 3, 0, 1, 2)
        sidebar_summary_grid.setColumnStretch(0, 1)
        sidebar_summary_layout.addLayout(sidebar_summary_grid)

        self.workflow_card = QFrame()
        self.workflow_card.setObjectName("WorkflowStrip")
        workflow_layout = QHBoxLayout(self.workflow_card)
        workflow_layout.setContentsMargins(16, 8, 16, 8)
        workflow_layout.setSpacing(10)
        self.workflow_stage_chip = StatusChip("空闲", "neutral")
        self.workflow_dots = []
        workflow_dots_row = QHBoxLayout()
        workflow_dots_row.setSpacing(6)
        for dot_label in ["提案", "生成", "编译", "仿真"]:
            dot = WorkflowDot()
            dot.setFixedSize(6, 6)
            dot.setToolTip(dot_label)
            self.workflow_dots.append(dot)
            workflow_dots_row.addWidget(dot)
        self.workflow_status_line = QLabel("当前流程还没有开始。")
        self.workflow_status_line.setObjectName("MetricCaption")
        self.workflow_meta_label = QLabel("")
        self.workflow_meta_label.setObjectName("MetricCaption")
        workflow_layout.addWidget(self.workflow_stage_chip)
        workflow_layout.addLayout(workflow_dots_row)
        workflow_layout.addWidget(self.workflow_status_line, 1)
        workflow_layout.addWidget(self.workflow_meta_label)

        context_card = Card()
        self.context_card = context_card
        context_layout = QVBoxLayout(context_card)
        context_layout.setContentsMargins(12, 10, 12, 10)
        context_layout.setSpacing(6)
        context_header = QHBoxLayout()
        self.thread_context_caption = QLabel("等待上下文")
        self.thread_context_caption.setObjectName("SidebarSectionTitle")
        context_header.addWidget(self.thread_context_caption)
        context_header.addStretch(1)
        self.context_project_value = QLabel("未绑定")
        self.context_project_value.setObjectName("SidebarMetricValue")
        self.context_status_value = QLabel("待开始")
        self.context_status_value.setObjectName("SidebarMetricValue")
        self.context_build_value = QLabel("未构建")
        self.context_build_value.setObjectName("SidebarMetricValue")
        self.context_runtime_value = QLabel("未验证")
        self.context_runtime_value.setObjectName("SidebarMetricValue")
        self.context_project_caption = QLabel("工程")
        self.context_project_caption.setObjectName("SidebarMetricCaption")
        self.context_status_caption = QLabel("状态")
        self.context_status_caption.setObjectName("SidebarMetricCaption")
        self.context_build_caption = QLabel("构建")
        self.context_build_caption.setObjectName("SidebarMetricCaption")
        self.context_runtime_caption = QLabel("仿真")
        self.context_runtime_caption.setObjectName("SidebarMetricCaption")
        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(0)
        metrics_grid.setVerticalSpacing(0)
        context_metrics_card = Card()
        context_metrics_card.setObjectName("SidebarListCard")
        context_metrics_layout = QGridLayout(context_metrics_card)
        context_metrics_layout.setContentsMargins(10, 8, 10, 8)
        context_metrics_layout.setHorizontalSpacing(12)
        context_metrics_layout.setVerticalSpacing(6)
        for row, (caption, value) in enumerate(
            (
                (self.context_project_caption, self.context_project_value),
                (self.context_status_caption, self.context_status_value),
                (self.context_build_caption, self.context_build_value),
                (self.context_runtime_caption, self.context_runtime_value),
            )
        ):
            context_metrics_layout.addWidget(caption, row, 0)
            context_metrics_layout.addWidget(value, row, 1, Qt.AlignRight)
        context_metrics_layout.setColumnStretch(0, 1)
        metrics_grid.addWidget(context_metrics_card, 0, 0)
        self.thread_context_view = QTextBrowser()
        self.thread_context_view.setObjectName("SidebarViewer")
        self.thread_context_view.setPlainText("当前线程的方案摘要、工程状态、最近构建和仿真结果会显示在这里。")
        self.thread_context_view.setMinimumHeight(120)
        self.thread_timeline_caption = QLabel("最近流程")
        self.thread_timeline_caption.setObjectName("SidebarSectionTitle")
        self.thread_timeline_view = QTextBrowser()
        self.thread_timeline_view.setObjectName("SidebarViewer")
        self.thread_timeline_view.setPlainText("当前线程还没有可展示的执行时间线。")
        self.thread_timeline_view.setMinimumHeight(96)
        context_actions_card = Card()
        self.context_actions_card = context_actions_card
        context_actions_card.setObjectName("ActionDeck")
        context_actions_layout = QGridLayout(context_actions_card)
        context_actions_layout.setContentsMargins(8, 7, 8, 7)
        context_actions_layout.setHorizontalSpacing(6)
        context_actions_layout.setVerticalSpacing(6)
        self.context_open_project_button = QPushButton("打开工程")
        self.context_open_project_button.clicked.connect(self._open_context_project_dir)
        self.context_open_build_log_button = QPushButton("构建日志")
        self.context_open_build_log_button.clicked.connect(self._open_context_build_log)
        self.context_open_runtime_log_button = QPushButton("仿真日志")
        self.context_open_runtime_log_button.clicked.connect(self._open_context_runtime_log)
        self.context_open_uart_button = QPushButton("UART 捕获")
        self.context_open_uart_button.clicked.connect(self._open_context_uart_capture)
        context_actions_layout.addWidget(self.context_open_project_button, 0, 0)
        context_actions_layout.addWidget(self.context_open_build_log_button, 0, 1)
        context_actions_layout.addWidget(self.context_open_runtime_log_button, 1, 0)
        context_actions_layout.addWidget(self.context_open_uart_button, 1, 1)
        context_summary_card = Card()
        self.context_summary_card = context_summary_card
        context_summary_layout = QVBoxLayout(context_summary_card)
        context_summary_layout.setContentsMargins(8, 7, 8, 7)
        context_summary_layout.setSpacing(6)
        context_summary_label = QLabel("线程摘要")
        context_summary_label.setObjectName("SidebarSectionTitle")
        context_summary_layout.addWidget(context_summary_label)
        context_summary_layout.addWidget(self.thread_context_view, 1)
        context_timeline_card = Card()
        self.context_timeline_card = context_timeline_card
        context_timeline_layout = QVBoxLayout(context_timeline_card)
        context_timeline_layout.setContentsMargins(8, 7, 8, 7)
        context_timeline_layout.setSpacing(6)
        context_timeline_layout.addWidget(self.thread_timeline_caption)
        context_timeline_layout.addWidget(self.thread_timeline_view, 1)
        self.context_splitter = QSplitter(Qt.Vertical)
        self.context_splitter.setChildrenCollapsible(False)
        self.context_splitter.addWidget(context_summary_card)
        self.context_splitter.addWidget(context_timeline_card)
        self.context_splitter.setStretchFactor(0, 3)
        self.context_splitter.setStretchFactor(1, 2)
        self.context_splitter.setSizes([220, 150])
        context_layout.addLayout(context_header)
        context_layout.addLayout(metrics_grid)
        context_layout.addWidget(context_actions_card)
        context_layout.addWidget(self.context_splitter, 1)

        proposal_host = QWidget()
        proposal_layout = QVBoxLayout(proposal_host)
        proposal_layout.setContentsMargins(0, 0, 0, 0)
        proposal_layout.setSpacing(8)
        self.proposal_status_label = StatusChip("等待需求", "neutral")
        proposal_status_row = QHBoxLayout()
        proposal_status_row.addWidget(self.proposal_status_label)
        proposal_status_row.addStretch(1)
        proposal_metrics_layout = QGridLayout()
        proposal_metrics_layout.setHorizontalSpacing(0)
        proposal_metrics_layout.setVerticalSpacing(0)
        self.proposal_target_value = QLabel("待解析")
        self.proposal_target_value.setObjectName("SidebarMetricValue")
        self.proposal_target_caption = QLabel("目标")
        self.proposal_target_caption.setObjectName("SidebarMetricCaption")
        self.proposal_modules_value = QLabel("0")
        self.proposal_modules_value.setObjectName("SidebarMetricValue")
        self.proposal_modules_caption = QLabel("模块")
        self.proposal_modules_caption.setObjectName("SidebarMetricCaption")
        self.proposal_changes_value = QLabel("0")
        self.proposal_changes_value.setObjectName("SidebarMetricValue")
        self.proposal_changes_caption = QLabel("变更")
        self.proposal_changes_caption.setObjectName("SidebarMetricCaption")
        self.proposal_output_value = QLabel("新建")
        self.proposal_output_value.setObjectName("SidebarMetricValue")
        self.proposal_output_caption = QLabel("输出")
        self.proposal_output_caption.setObjectName("SidebarMetricCaption")
        proposal_metrics_card = Card()
        proposal_metrics_card.setObjectName("SidebarListCard")
        proposal_metrics_rows = QGridLayout(proposal_metrics_card)
        proposal_metrics_rows.setContentsMargins(10, 8, 10, 8)
        proposal_metrics_rows.setHorizontalSpacing(12)
        proposal_metrics_rows.setVerticalSpacing(6)
        for row, (caption, value) in enumerate(
            (
                (self.proposal_target_caption, self.proposal_target_value),
                (self.proposal_modules_caption, self.proposal_modules_value),
                (self.proposal_changes_caption, self.proposal_changes_value),
                (self.proposal_output_caption, self.proposal_output_value),
            )
        ):
            proposal_metrics_rows.addWidget(caption, row, 0)
            proposal_metrics_rows.addWidget(value, row, 1, Qt.AlignRight)
        proposal_metrics_rows.setColumnStretch(0, 1)
        proposal_metrics_layout.addWidget(proposal_metrics_card, 0, 0)
        self.proposal_view = QTextBrowser()
        self.proposal_view.setObjectName("SidebarViewer")
        self.proposal_view.setPlainText("你输入需求后，这里会显示可行性、推荐板子、模块清单和引脚接线。")
        self.proposal_change_hint = QLabel("当前还没有待确认变更。")
        self.proposal_change_hint.setObjectName("SectionHint")
        self.proposal_change_hint.setWordWrap(True)
        self.proposal_feedback_input = QPlainTextEdit()
        self.proposal_feedback_input.setObjectName("CodeEditor")
        self.proposal_feedback_input.setPlaceholderText("如果方案不合适，在这里写修改意见，例如：I2C 固定到 PB6/PB7，或者不要用 PC13。")
        self.proposal_view.setMinimumHeight(60)
        self.proposal_feedback_input.setMinimumHeight(60)
        self.proposal_actions_widget = QWidget()
        proposal_actions = QHBoxLayout(self.proposal_actions_widget)
        proposal_actions.setContentsMargins(0, 0, 0, 0)
        proposal_actions.setSpacing(8)
        self.confirm_proposal_button = QPushButton("确认方案并开始生成")
        self.confirm_proposal_button.setObjectName("PrimaryButton")
        self.confirm_proposal_button.setEnabled(False)
        self.confirm_proposal_button.clicked.connect(self.confirm_pending_proposal)
        self.revise_proposal_button = QPushButton("打回并重算")
        self.revise_proposal_button.setEnabled(False)
        self.revise_proposal_button.clicked.connect(self.revise_pending_proposal)
        self.clear_proposal_button = QPushButton("清空待确认方案")
        self.clear_proposal_button.setEnabled(False)
        self.clear_proposal_button.clicked.connect(self.clear_pending_proposal)
        proposal_actions.addWidget(self.confirm_proposal_button)
        proposal_actions.addWidget(self.revise_proposal_button)
        proposal_actions.addWidget(self.clear_proposal_button)
        proposal_summary_card = Card()
        self.proposal_summary_card = proposal_summary_card
        proposal_summary_layout = QVBoxLayout(proposal_summary_card)
        proposal_summary_layout.setContentsMargins(8, 7, 8, 7)
        proposal_summary_layout.setSpacing(6)
        proposal_summary_label = QLabel("方案摘要")
        proposal_summary_label.setObjectName("SidebarSectionTitle")
        proposal_summary_layout.addWidget(proposal_summary_label)
        proposal_summary_layout.addWidget(self.proposal_view, 1)
        proposal_change_card = Card()
        self.proposal_change_card = proposal_change_card
        proposal_change_layout = QVBoxLayout(proposal_change_card)
        proposal_change_layout.setContentsMargins(8, 7, 8, 7)
        proposal_change_layout.setSpacing(6)
        proposal_change_label = QLabel("关键变更")
        proposal_change_label.setObjectName("SidebarSectionTitle")
        proposal_change_layout.addWidget(proposal_change_label)
        proposal_change_layout.addWidget(self.proposal_change_hint)
        self.negotiation_options_widget = QWidget()
        self.negotiation_options_layout = QVBoxLayout(self.negotiation_options_widget)
        self.negotiation_options_layout.setContentsMargins(0, 0, 0, 0)
        self.negotiation_options_layout.setSpacing(6)
        self.negotiation_option_buttons: List[QPushButton] = []
        proposal_change_layout.addWidget(self.negotiation_options_widget)
        proposal_feedback_card = Card()
        self.proposal_feedback_card = proposal_feedback_card
        proposal_feedback_layout = QVBoxLayout(proposal_feedback_card)
        proposal_feedback_layout.setContentsMargins(8, 7, 8, 7)
        proposal_feedback_layout.setSpacing(6)
        proposal_feedback_label = QLabel("修改意见")
        proposal_feedback_label.setObjectName("SidebarSectionTitle")
        proposal_feedback_layout.addWidget(proposal_feedback_label)
        proposal_feedback_layout.addWidget(self.proposal_feedback_input, 1)
        self.proposal_splitter = QSplitter(Qt.Vertical)
        self.proposal_splitter.setChildrenCollapsible(False)
        self.proposal_splitter.addWidget(proposal_summary_card)
        self.proposal_splitter.addWidget(proposal_feedback_card)
        self.proposal_splitter.setStretchFactor(0, 4)
        self.proposal_splitter.setStretchFactor(1, 2)
        self.proposal_splitter.setSizes([160, 80])
        proposal_layout.addLayout(proposal_status_row)
        proposal_layout.addLayout(proposal_metrics_layout)
        proposal_layout.addWidget(proposal_change_card)
        proposal_layout.addWidget(self.proposal_splitter, 1)
        proposal_layout.addWidget(self.proposal_actions_widget)

        blueprint_host = QWidget()
        blueprint_layout = QVBoxLayout(blueprint_host)
        blueprint_layout.setContentsMargins(0, 0, 0, 0)
        blueprint_layout.setSpacing(10)

        blueprint_overview_card = QFrame()
        blueprint_overview_card.setObjectName("WorkspaceSummaryCard")
        blueprint_overview_layout = QGridLayout(blueprint_overview_card)
        blueprint_overview_layout.setContentsMargins(14, 12, 14, 12)
        blueprint_overview_layout.setHorizontalSpacing(16)
        blueprint_overview_layout.setVerticalSpacing(6)
        self.blueprint_chip_caption = QLabel("芯片")
        self.blueprint_chip_caption.setObjectName("SidebarMetricCaption")
        self.blueprint_chip_value = QLabel("待解析")
        self.blueprint_chip_value.setObjectName("SidebarMetricValue")
        self.blueprint_board_caption = QLabel("板卡")
        self.blueprint_board_caption.setObjectName("SidebarMetricCaption")
        self.blueprint_board_value = QLabel("待解析")
        self.blueprint_board_value.setObjectName("SidebarMetricValue")
        self.blueprint_modules_caption = QLabel("模块")
        self.blueprint_modules_caption.setObjectName("SidebarMetricCaption")
        self.blueprint_modules_value = QLabel("0")
        self.blueprint_modules_value.setObjectName("SidebarMetricValue")
        self.blueprint_assignments_caption = QLabel("引脚")
        self.blueprint_assignments_caption.setObjectName("SidebarMetricCaption")
        self.blueprint_assignments_value = QLabel("0")
        self.blueprint_assignments_value.setObjectName("SidebarMetricValue")
        blueprint_items = (
            (self.blueprint_chip_caption, self.blueprint_chip_value),
            (self.blueprint_board_caption, self.blueprint_board_value),
            (self.blueprint_modules_caption, self.blueprint_modules_value),
            (self.blueprint_assignments_caption, self.blueprint_assignments_value),
        )
        for index, (caption, value) in enumerate(blueprint_items):
            row = (index // 2) * 2
            column = index % 2
            blueprint_overview_layout.addWidget(caption, row, column)
            blueprint_overview_layout.addWidget(value, row + 1, column)
            blueprint_overview_layout.setColumnStretch(column, 1)

        blueprint_canvas_card = QFrame()
        blueprint_canvas_card.setObjectName("BlueprintCanvasCard")
        blueprint_canvas_layout = QVBoxLayout(blueprint_canvas_card)
        blueprint_canvas_layout.setContentsMargins(14, 12, 14, 12)
        blueprint_canvas_layout.setSpacing(10)
        blueprint_canvas_title = QLabel("Hardware Blueprint")
        blueprint_canvas_title.setObjectName("SidebarSectionTitle")
        self.blueprint_view = QTextBrowser()
        self.blueprint_view.setObjectName("BlueprintViewer")
        self.blueprint_view.setOpenExternalLinks(False)
        self.blueprint_view.setMinimumHeight(80)
        blueprint_canvas_layout.addWidget(blueprint_canvas_title)
        blueprint_canvas_layout.addWidget(self.blueprint_view, 1)

        self.blueprint_detail_splitter = QSplitter(Qt.Horizontal)
        self.blueprint_detail_splitter.setChildrenCollapsible(False)
        self.blueprint_detail_splitter.addWidget(proposal_host)
        self.blueprint_detail_splitter.setStretchFactor(0, 1)
        self.blueprint_detail_splitter.setSizes([860])

        self.blueprint_splitter = QSplitter(Qt.Vertical)
        self.blueprint_splitter.setChildrenCollapsible(False)
        self.blueprint_splitter.addWidget(blueprint_canvas_card)
        self.blueprint_splitter.addWidget(self.blueprint_detail_splitter)
        self.blueprint_splitter.setStretchFactor(0, 5)
        self.blueprint_splitter.setStretchFactor(1, 4)
        self.blueprint_splitter.setSizes([200, 400])

        blueprint_layout.addWidget(blueprint_overview_card)
        blueprint_layout.addWidget(self.blueprint_splitter, 1)

        self.chat_project_explorer = ProjectExplorerWidget(
            title="当前工程文件",
            hint="生成成功后，这里会直接显示工程树和源码预览。修改当前项目时，也会一直联动这里。",
            compact=True,
        )

        project_ir_host = QWidget()
        project_ir_layout = QVBoxLayout(project_ir_host)
        project_ir_layout.setContentsMargins(0, 0, 0, 0)
        project_ir_layout.setSpacing(10)
        project_ir_title = QLabel("project_ir.json")
        project_ir_title.setObjectName("SidebarSectionTitle")
        project_ir_hint = QLabel("这里展示当前线程最近一次规划或落盘后的结构化工程描述。")
        project_ir_hint.setObjectName("SectionHint")
        project_ir_hint.setWordWrap(True)
        self.project_ir_editor = CodeEditor(read_only=True)
        self.project_ir_editor.setPlainText("当前还没有可展示的 project_ir.json。")
        project_ir_layout.addWidget(project_ir_title)
        project_ir_layout.addWidget(project_ir_hint)
        project_ir_layout.addWidget(self.project_ir_editor, 1)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName("SidebarTabs")
        self.sidebar_tabs.addTab(blueprint_host, "方案")
        self.sidebar_tabs.addTab(self.chat_project_explorer, "文件")
        self.sidebar_tabs.addTab(project_ir_host, "IR")
        self.sidebar_tabs.setDocumentMode(True)
        self.sidebar_tabs.setMovable(False)
        self.sidebar_tabs.tabBar().setExpanding(False)
        self.sidebar_tabs.currentChanged.connect(self._update_sidebar_for_current_tab)

        self.sidebar_body = QWidget()
        sidebar_body_layout = QVBoxLayout(self.sidebar_body)
        sidebar_body_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_body_layout.setSpacing(10)

        terminal_host = QFrame()
        terminal_host.setObjectName("TerminalDeck")
        terminal_layout = QVBoxLayout(terminal_host)
        terminal_layout.setContentsMargins(12, 10, 12, 10)
        terminal_layout.setSpacing(8)
        terminal_title_row = QHBoxLayout()
        terminal_title_row.setContentsMargins(0, 0, 0, 0)
        terminal_title_row.setSpacing(8)
        terminal_title = QLabel("控制台与日志")
        terminal_title.setObjectName("SidebarSectionTitle")
        terminal_hint = QLabel("把构建、仿真和 UART 输出都暴露出来，尽量减少黑盒感。")
        terminal_hint.setObjectName("SectionHint")
        terminal_hint.setWordWrap(True)
        terminal_title_row.addWidget(terminal_title)
        terminal_title_row.addStretch(1)

        self.terminal_tabs = QTabWidget()
        self.terminal_tabs.setObjectName("TerminalTabs")
        self.terminal_overview_view = CodeEditor(read_only=True)
        self.terminal_overview_view.setPlainText("当前还没有可展示的终端事件。")
        self.build_log_view = CodeEditor(read_only=True)
        self.build_log_view.setPlainText("构建日志会在生成并编译后显示在这里。")
        self.uart_capture_view = CodeEditor(read_only=True)
        self.uart_capture_view.setPlainText("Renode UART 捕获会在仿真后显示在这里。")
        self.terminal_tabs.addTab(self.terminal_overview_view, "Terminal")
        self.terminal_tabs.addTab(self.build_log_view, "Keil Build Log")
        self.terminal_tabs.addTab(self.uart_capture_view, "Renode UART Capture")
        self.terminal_tabs.tabBar().setExpanding(False)

        terminal_layout.addLayout(terminal_title_row)
        terminal_layout.addWidget(terminal_hint)
        terminal_layout.addWidget(self.terminal_tabs, 1)

        self.asset_splitter = QSplitter(Qt.Vertical)
        self.asset_splitter.setChildrenCollapsible(False)
        self.asset_splitter.addWidget(self.sidebar_tabs)
        self.asset_splitter.addWidget(terminal_host)
        self.asset_splitter.setStretchFactor(0, 5)
        self.asset_splitter.setStretchFactor(1, 2)
        terminal_host.hide()
        self.asset_splitter.setSizes([1000, 0])
        sidebar_body_layout.addWidget(self.asset_splitter, 1)

        self.environment_tabs = QTabWidget()
        self.environment_tabs.setObjectName("SidebarTabs")
        self.path_summary_view = QTextBrowser()
        self.path_summary_view.setObjectName("SidebarViewer")
        self.path_summary_view.setOpenExternalLinks(False)
        self.profile_summary_view = QTextBrowser()
        self.profile_summary_view.setObjectName("SidebarViewer")
        self.profile_summary_view.setOpenExternalLinks(False)
        self.environment_tabs.addTab(self.path_summary_view, "环境路径")
        self.environment_tabs.addTab(self.profile_summary_view, "模型 API")

        environment_card = QFrame()
        environment_card.setObjectName("EnvironmentSidebarCard")
        environment_layout = QVBoxLayout(environment_card)
        environment_layout.setContentsMargins(12, 10, 12, 10)
        environment_layout.setSpacing(8)
        environment_title = QLabel("环境配置")
        environment_title.setObjectName("SectionTitle")
        environment_layout.addWidget(environment_title)
        environment_layout.addWidget(self.environment_tabs, 1)
        sidebar_body_layout.addWidget(environment_card)

        self.dialogue_workspace_layout.insertWidget(1, self.workflow_card)
        right_layout.addLayout(sidebar_title_row)
        right_layout.addWidget(self.sidebar_summary_card)
        right_layout.addWidget(self.sidebar_body, 1)

        workspace_splitter = QSplitter(Qt.Horizontal)
        self.workspace_splitter = workspace_splitter
        workspace_splitter.setChildrenCollapsible(False)
        workspace_splitter.addWidget(left_panel)
        workspace_splitter.addWidget(right_panel)
        workspace_splitter.setStretchFactor(0, 0)
        workspace_splitter.setStretchFactor(1, 1)
        workspace_splitter.setSizes([920, 420])

        root_layout.addWidget(thread_panel)
        root_layout.addWidget(workspace_splitter, 1)

        self.thread_panel_collapsed = False
        self.sidebar_panel_collapsed = False

        self.reload_profiles()
        self._load_chat_threads()
        self._update_agent_mode_banner()
        self._update_sidebar_for_current_tab()
        self._refresh_proposal_summary_cards()
        self._refresh_workflow_strip()
        self._refresh_workspace_views()

    def _build_thread_panel(self) -> QFrame:
        thread_panel = QFrame()
        thread_panel.setObjectName("SidebarPanel")
        self.thread_panel = thread_panel
        thread_panel.setMinimumWidth(248)
        thread_panel.setMaximumWidth(312)
        thread_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        thread_layout = QVBoxLayout(thread_panel)
        thread_layout.setContentsMargins(14, 14, 14, 14)
        thread_layout.setSpacing(12)

        thread_title_row = QHBoxLayout()
        thread_title_row.setContentsMargins(0, 0, 0, 0)
        thread_title_row.setSpacing(8)
        thread_title = QLabel("工程线程")
        thread_title.setObjectName("SectionTitle")
        self.thread_title_label = thread_title
        self.thread_status_label = QLabel("进行中")
        self.thread_status_label.setObjectName("MetricCaption")
        self.thread_panel_toggle_button = QToolButton()
        self.thread_panel_toggle_button.setObjectName("PanelToggleButton")
        self.thread_panel_toggle_button.setAutoRaise(True)
        self.thread_panel_toggle_button.setFixedSize(28, 28)
        self.thread_panel_toggle_button.setText("‹")
        self.thread_panel_toggle_button.setToolTip("隐藏线程栏")
        self.thread_panel_toggle_button.clicked.connect(self._toggle_thread_panel)
        thread_title_row.addWidget(thread_title)
        thread_title_row.addStretch(1)
        thread_title_row.addWidget(self.thread_status_label)
        thread_title_row.addWidget(self.thread_panel_toggle_button)

        self.new_thread_button = QPushButton("＋ 新线程")
        self.new_thread_button.setObjectName("PrimaryButton")
        self.new_thread_button.clicked.connect(self._create_new_thread)
        self.thread_list = QListWidget()
        self.thread_list.setObjectName("ProjectThreadList")
        self.thread_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.thread_list.currentItemChanged.connect(self._on_thread_selection_changed)

        thread_layout.addLayout(thread_title_row)
        self.thread_panel_body = QWidget()
        thread_body_layout = QVBoxLayout(self.thread_panel_body)
        thread_body_layout.setContentsMargins(0, 0, 0, 0)
        thread_body_layout.setSpacing(10)
        thread_body_layout.addWidget(self.new_thread_button)
        thread_body_layout.addWidget(self.thread_list, 1)
        thread_layout.addWidget(self.thread_panel_body, 1)
        return thread_panel

    def _build_dialogue_workspace_panel(self) -> QFrame:
        left_panel = QFrame()
        left_panel.setObjectName("DialogueWorkspacePanel")
        self.chat_sidebar_panel = left_panel
        left_panel.setMinimumWidth(640)
        left_panel.setMaximumWidth(16777215)
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        left_layout = QVBoxLayout(left_panel)
        self.dialogue_workspace_layout = left_layout
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        header_top_row = QHBoxLayout()
        header_top_row.setContentsMargins(0, 0, 0, 0)
        header_top_row.setSpacing(8)
        copilot_title = QLabel("对话工作区")
        copilot_title.setObjectName("SectionTitle")
        self.clear_chat_button = QPushButton("清空对话")
        self.clear_chat_button.setObjectName("GhostButton")
        self.clear_chat_button.clicked.connect(self.clear_conversation)
        header_top_row.addWidget(copilot_title)
        header_top_row.addStretch(1)

        toolbar_card = QFrame()
        toolbar_card.setObjectName("WorkspaceToolbarCard")
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.setSpacing(10)

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(220)
        self.profile_combo.currentIndexChanged.connect(self._update_profile_sidebar)
        self.chat_renode_checkbox = QCheckBox("仿真验证")
        self.chat_status = StatusChip("等待输入", "neutral")
        toolbar_layout.addWidget(self.profile_combo, 1)
        toolbar_layout.addWidget(self.chat_renode_checkbox)
        toolbar_layout.addWidget(self.clear_chat_button)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.chat_status)
        header_layout.addLayout(header_top_row)
        header_layout.addWidget(toolbar_card)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("ChatScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.messages_host = QWidget()
        self.messages_host.setObjectName("ChatCanvas")
        self.messages_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.messages_layout = QVBoxLayout(self.messages_host)
        self.messages_layout.setContentsMargins(10, 14, 10, 14)
        self.messages_layout.setSpacing(16)
        self.messages_layout.addStretch(1)
        self.scroll_area.setWidget(self.messages_host)

        composer_container = QWidget()
        composer_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        composer_outer_layout = QVBoxLayout(composer_container)
        composer_outer_layout.setContentsMargins(0, 0, 0, 0)
        composer_outer_layout.setSpacing(0)

        composer_card = QFrame()
        composer_card.setObjectName("ComposerCard")
        composer_card.setProperty("composerActive", False)
        composer_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.composer_card = composer_card
        composer_layout = QVBoxLayout(composer_card)
        composer_layout.setContentsMargins(14, 14, 14, 12)
        composer_layout.setSpacing(8)

        self.chat_input = QPlainTextEdit()
        self.chat_input.setObjectName("ComposerInput")
        self.chat_input.setPlaceholderText("描述需求、修改当前项目，或让 ChipWhisper 直接构建/仿真…")
        self.chat_input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.chat_input.setMinimumHeight(84)
        self.chat_input.setMaximumHeight(180)
        self.chat_input.textChanged.connect(self._update_agent_mode_banner)
        self.chat_input.textChanged.connect(self._update_chat_input_height)
        self.chat_input.installEventFilter(self)

        self.chat_attachments = AttachmentPickerWidget("附件", "支持文档和图片", collapsed=True)
        self.chat_attachments.set_header_visible(False)
        self.chat_attachments.hint_label.hide()
        self.chat_attachments.count_label.hide()

        composer_actions = QHBoxLayout()
        composer_actions.setContentsMargins(0, 0, 0, 0)
        composer_actions.setSpacing(8)
        self.chat_attachments.toggle_button.setText("📎")
        self.chat_attachments.toggle_button.setFixedSize(30, 30)
        self.chat_attachments.toggle_button.setObjectName("GhostButton")
        self.agent_mode_chip = StatusChip("普通对话", "neutral")
        self.composer_shortcut_label = QLabel("Ctrl+Enter")
        self.composer_shortcut_label.setObjectName("MetricCaption")
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedSize(84, 32)
        self.send_button.setToolTip("Ctrl+Enter 发送")
        self.send_button.clicked.connect(self.send_message)
        composer_actions.addWidget(self.chat_attachments.toggle_button)
        composer_actions.addStretch(1)
        composer_actions.addWidget(self.agent_mode_chip)
        composer_actions.addWidget(self.composer_shortcut_label)
        composer_actions.addWidget(self.send_button)

        composer_layout.addWidget(self.chat_input)
        composer_layout.addWidget(self.chat_attachments.details_widget)
        composer_layout.addLayout(composer_actions)
        composer_outer_layout.addWidget(composer_card)

        left_layout.addWidget(header_widget)
        left_layout.addWidget(self.scroll_area, 1)
        left_layout.addWidget(composer_container)
        self._update_chat_input_height()
        self.loading_overlay = LoadingOverlay(left_panel)
        return left_panel

    @property
    def pending_request_payload(self) -> dict[str, object]:
        return self._pending_proposal_state.request_payload

    @pending_request_payload.setter
    def pending_request_payload(self, value: dict[str, object] | None) -> None:
        self._pending_proposal_state.request_payload = dict(value or {})

    @property
    def pending_plan_summary(self) -> dict[str, object]:
        return self._pending_proposal_state.plan_summary

    @pending_plan_summary.setter
    def pending_plan_summary(self, value: dict[str, object] | None) -> None:
        self._pending_proposal_state.plan_summary = dict(value or {})

    @property
    def pending_review_kind(self) -> str:
        return self._pending_proposal_state.review_kind

    @pending_review_kind.setter
    def pending_review_kind(self, value: str) -> None:
        self._pending_proposal_state.review_kind = str(value or "").strip() or "proposal"

    @property
    def pending_negotiation_options(self) -> List[dict[str, object]]:
        return self._pending_proposal_state.negotiation_options

    @pending_negotiation_options.setter
    def pending_negotiation_options(self, value: List[dict[str, object]] | None) -> None:
        self._pending_proposal_state.negotiation_options = [
            dict(item) for item in value or [] if isinstance(item, dict)
        ]

    @property
    def pending_change_preview(self) -> List[str]:
        return self._pending_proposal_state.change_preview

    @pending_change_preview.setter
    def pending_change_preview(self, value: List[str] | None) -> None:
        self._pending_proposal_state.change_preview = [str(item) for item in value or []]

    @property
    def pending_file_change_preview(self) -> List[dict[str, object]]:
        return self._pending_proposal_state.file_change_preview

    @pending_file_change_preview.setter
    def pending_file_change_preview(self, value: List[dict[str, object]] | None) -> None:
        self._pending_proposal_state.file_change_preview = [
            dict(item) for item in value or [] if isinstance(item, dict)
        ]

    @property
    def pending_output_dir(self) -> str:
        return self._pending_proposal_state.output_dir

    @pending_output_dir.setter
    def pending_output_dir(self, value: str) -> None:
        self._pending_proposal_state.output_dir = str(value or "").strip()

    @property
    def pending_mode(self) -> str:
        return self._pending_proposal_state.mode

    @pending_mode.setter
    def pending_mode(self, value: str) -> None:
        self._pending_proposal_state.mode = str(value or "").strip() or "create"

    @property
    def pending_graph_thread_id(self) -> str:
        return self._pending_proposal_state.graph_thread_id

    @pending_graph_thread_id.setter
    def pending_graph_thread_id(self, value: str) -> None:
        self._pending_proposal_state.graph_thread_id = str(value or "").strip()

    @property
    def thread_engineering_state(self) -> dict[str, object]:
        return self._thread_engineering_state.to_dict()

    @thread_engineering_state.setter
    def thread_engineering_state(self, value: dict[str, object] | None) -> None:
        self._thread_engineering_state = ThreadEngineeringState.from_dict(value)

    def save_ui_state(self, settings: QSettings) -> None:
        settings.beginGroup("chatPage")
        settings.setValue("threadPanelCollapsed", self.thread_panel_collapsed)
        settings.setValue("sidebarPanelCollapsed", self.sidebar_panel_collapsed)
        settings.setValue("sidebarTabIndex", self.sidebar_tabs.currentIndex())
        settings.setValue("workspaceSplitterState", self.workspace_splitter.saveState())
        settings.setValue("contextSplitterState", self.context_splitter.saveState())
        settings.setValue("proposalSplitterState", self.proposal_splitter.saveState())
        settings.setValue("projectExplorerSplitterState", self.chat_project_explorer.splitter.saveState())
        settings.endGroup()

    def load_ui_state(self, settings: QSettings) -> None:
        settings.beginGroup("chatPage")
        context_state = settings.value("contextSplitterState")
        proposal_state = settings.value("proposalSplitterState")
        project_explorer_state = settings.value("projectExplorerSplitterState")
        workspace_state = settings.value("workspaceSplitterState")
        sidebar_tab_index = settings.value("sidebarTabIndex", self.sidebar_tabs.currentIndex(), type=int)
        thread_panel_collapsed = settings.value("threadPanelCollapsed", self.thread_panel_collapsed, type=bool)
        sidebar_panel_collapsed = settings.value("sidebarPanelCollapsed", self.sidebar_panel_collapsed, type=bool)
        settings.endGroup()

        if context_state:
            self.context_splitter.restoreState(context_state)
        if proposal_state:
            self.proposal_splitter.restoreState(proposal_state)
        if project_explorer_state:
            self.chat_project_explorer.splitter.restoreState(project_explorer_state)

        self.sidebar_tabs.setCurrentIndex(max(0, min(sidebar_tab_index, self.sidebar_tabs.count() - 1)))
        self._set_thread_panel_collapsed(thread_panel_collapsed)
        self._set_sidebar_panel_collapsed(sidebar_panel_collapsed)
        if workspace_state and not self.sidebar_panel_collapsed:
            self.workspace_splitter.restoreState(workspace_state)
        elif not self.sidebar_panel_collapsed:
            self._update_sidebar_for_current_tab()

    def reload_profiles(self) -> None:
        config = load_llm_config()
        self.profiles = [profile for profile in config.profiles if profile.enabled]
        self.default_profile_id = config.default_profile_id
        self.profile_combo.clear()
        for profile in self.profiles:
            self.profile_combo.addItem(profile.name, profile.profile_id)
        if self.profiles:
            default_index = 0
            for index, profile in enumerate(self.profiles):
                if profile.profile_id == self.default_profile_id:
                    default_index = index
                    break
            self.profile_combo.setCurrentIndex(default_index)
        self._update_profile_sidebar()
        self._refresh_sidebar_meta()
        self._refresh_environment_sidebar()

    def _welcome_message(self) -> str:
        return "可以直接描述工程需求，我会先整理方案，再继续生成、编译或仿真。"

    def _default_proposal_text(self) -> str:
        return "你输入需求后，这里会显示可行性、推荐板子、模块清单和引脚接线。"

    def _refresh_sidebar_meta(self) -> None:
        model_text = str(self.profile_summary_text).replace("模型：", "", 1).strip()
        project_text = str(self.project_summary_text).replace("工程：", "", 1).strip()
        compact_model = self._clip_single_line_text(model_text or "未配置", max_chars=38)
        compact_project = (
            self._summarize_path_for_ui(project_text, max_chars=24)
            if project_text and project_text != "未打开"
            else "未打开"
        )
        self.sidebar_meta_label.setText(f"模型: {compact_model}  ·  工程: {compact_project}")
        self.sidebar_meta_label.setToolTip(f"{self.profile_summary_text}\n{self.project_summary_text}")
        self.sidebar_model_value.setText(compact_model or "未配置")
        self.sidebar_model_value.setToolTip(model_text or "未配置")
        self.sidebar_project_value.setText(compact_project)
        self.sidebar_project_value.setToolTip(project_text or "未打开")

    def refresh_environment_sidebar(self) -> None:
        self._refresh_environment_sidebar()

    def _refresh_environment_sidebar(self) -> None:
        if not hasattr(self, "path_summary_view") or not hasattr(self, "profile_summary_view"):
            return
        config_path, values = load_path_config()
        path_rows: list[str] = []
        for key in (
            "keil_uv4_path",
            "keil_fromelf_path",
            "stm32cubemx_install_path",
            "stm32cube_repository_path",
            "stm32cube_f1_package_path",
            "renode_exe_path",
        ):
            raw = str(values.get(key, "")).strip()
            status = "已配置" if raw else "未配置"
            tone = "#10B981" if raw else "#71717A"
            display = escape(self._summarize_path_for_ui(raw, max_chars=30)) if raw else "未设置"
            path_rows.append(
                "<tr>"
                f"<td style='padding:4px 0; color:#A1A1AA;'>{escape(PATH_LABELS.get(key, key))}</td>"
                f"<td style='padding:4px 0; color:{tone}; text-align:right;'>{status}</td>"
                "</tr>"
                f"<tr><td colspan='2' style='padding:0 0 8px 0; color:#E4E4E7; font-size:11px;'>{display}</td></tr>"
            )
        self.path_summary_view.setHtml(
            "<div style='color:#E4E4E7;'>"
            f"<div style='margin-bottom:10px; color:#71717A;'>配置文件: {escape(self._summarize_path_for_ui(str(config_path), 36))}</div>"
            "<table style='width:100%; border-collapse:collapse;'>"
            + "".join(path_rows)
            + "</table></div>"
        )

        llm_config = load_llm_config()
        enabled_profiles = [profile for profile in llm_config.profiles if profile.enabled]
        if not enabled_profiles:
            self.profile_summary_view.setHtml(
                "<div style='color:#A1A1AA; line-height:1.8;'>当前还没有启用的模型 Profile。"
                "<br>到“环境配置”页里补充 API 信息后，这里会同步显示摘要。</div>"
            )
            return

        profile_cards: list[str] = []
        for profile in enabled_profiles[:4]:
            badges: list[str] = []
            if profile.profile_id == llm_config.default_profile_id:
                badges.append("<span style='color:#60A5FA;'>默认</span>")
            badges.append("<span style='color:#10B981;'>已启用</span>")
            badge_html = " · ".join(badges)
            profile_cards.append(
                "<div style='margin-bottom:10px; padding:10px 12px; border-radius:10px; "
                "background:#1C1C1F; border:1px solid rgba(255,255,255,0.06);'>"
                f"<div style='font-weight:600; color:#FAFAFA;'>{escape(profile.name)}</div>"
                f"<div style='margin-top:4px; color:#A1A1AA;'>{escape(profile.provider_type)} / {escape(self._clip_single_line_text(profile.model or '未指定模型', 22))}</div>"
                f"<div style='margin-top:4px; color:#71717A; font-size:11px;'>{escape(self._summarize_path_for_ui(profile.base_url or '', 34) if profile.base_url else '未配置 Base URL')}</div>"
                f"<div style='margin-top:6px; font-size:12px;'>{badge_html}</div>"
                "</div>"
            )
        self.profile_summary_view.setHtml("".join(profile_cards))

    def _refresh_proposal_summary_cards(self) -> None:
        target = {}
        if isinstance(self.pending_request_payload.get("target"), dict):
            target = dict(self.pending_request_payload.get("target") or {})
        elif isinstance(self.pending_plan_summary.get("target"), dict):
            target = dict(self.pending_plan_summary.get("target") or {})
        chip = str(target.get("chip", "") or "").strip()
        board = str(target.get("board", "") or "").strip()
        if chip and board and board != "chip_only":
            target_text = f"{chip} / {board}"
        else:
            target_text = chip or board or "待解析"
        if len(target_text) > 18:
            target_text = target_text[:18] + "..."
        modules = self.pending_plan_summary.get("modules", [])
        module_count = len(modules) if isinstance(modules, list) else 0
        change_count = len(self.pending_change_preview) or len(self.pending_file_change_preview)
        if self.pending_review_kind == "negotiate" and self.pending_negotiation_options:
            change_count = len(self.pending_negotiation_options)
        output_text = "更新当前项目" if self.pending_mode == "modify" else "新建工程"
        output_text = "重新规划" if self.pending_review_kind == "negotiate" else output_text
        self.proposal_target_value.setText(target_text)
        self.proposal_modules_value.setText(str(module_count))
        self.proposal_changes_value.setText(str(change_count))
        self.proposal_output_value.setText(output_text)
        change_excerpt = self._render_pending_change_excerpt()
        self.proposal_change_hint.setText(change_excerpt)
        self.proposal_change_hint.setToolTip(change_excerpt)
        self._refresh_negotiation_option_buttons()
        self._refresh_sidebar_density()

    def _refresh_negotiation_option_buttons(self) -> None:
        while self.negotiation_options_layout.count():
            item = self.negotiation_options_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.negotiation_option_buttons = []
        options = [dict(item) for item in self.pending_negotiation_options if isinstance(item, dict)]
        self.negotiation_options_widget.setVisible(bool(options))
        if options:
            hint = QLabel("点击选择一个折中方案，或在下方修改意见框中自定义：")
            hint.setObjectName("SectionHint")
            hint.setWordWrap(True)
            self.negotiation_options_layout.addWidget(hint)
        for option in options[:3]:
            title = str(option.get("title", "")).strip() or "建议方案"
            summary = str(option.get("summary", "")).strip()
            feedback = str(option.get("feedback", "")).strip()
            button = QPushButton(title)
            button.setObjectName("NegotiationOptionButton")
            if summary:
                button.setToolTip(summary)
            button.clicked.connect(
                lambda _checked=False, feedback=feedback, title=title: self._select_negotiation_option(title, feedback)
            )
            self.negotiation_options_layout.addWidget(button)
            self.negotiation_option_buttons.append(button)

    def _select_negotiation_option(self, title: str, feedback: str) -> None:
        self.proposal_feedback_input.setPlainText(feedback)
        self.proposal_feedback_input.setFocus()
        self.chat_status.set_status(f"已选: {self._clip_single_line_text(title, 14)}", "warning")
        self._refresh_sidebar_density()

    def _refresh_sidebar_density(self) -> None:
        has_project = bool(str(self.active_project_dir or "").strip())
        has_timeline = bool(str(self.thread_timeline_view.toPlainText()).strip()) and "还没有可展示" not in self.thread_timeline_view.toPlainText()
        has_context_actions = any(
            button.isEnabled()
            for button in (
                self.context_open_project_button,
                self.context_open_build_log_button,
                self.context_open_runtime_log_button,
                self.context_open_uart_button,
            )
        )
        pending_visible = bool(self.pending_request_payload) or bool(self.confirm_proposal_button.isEnabled())
        change_visible = bool(
            self.pending_change_preview or self.pending_file_change_preview or self.pending_negotiation_options
        )
        feedback_visible = pending_visible or bool(self.proposal_feedback_input.toPlainText().strip())
        in_negotiate = pending_visible and self.pending_review_kind == "negotiate"
        self.context_actions_card.setVisible(has_context_actions)
        self.context_timeline_card.setVisible(has_timeline and has_project)
        self.blueprint_detail_splitter.setVisible(pending_visible)
        self.proposal_change_card.setVisible(change_visible)
        # 协商模式：内联卡片处理选项和反馈，侧边栏只保留状态徽章和回退按钮
        self.proposal_change_card.setVisible(change_visible and not in_negotiate)
        self.proposal_feedback_card.setVisible(feedback_visible and not in_negotiate)
        self.proposal_summary_card.setVisible(not in_negotiate)
        self.proposal_actions_widget.setVisible(pending_visible)

    def _load_project_ir_payload(self) -> dict[str, object]:
        project_dir = str(self.active_project_dir or "").strip()
        if project_dir:
            ir_path = Path(project_dir) / "project_ir.json"
            if ir_path.exists():
                try:
                    payload = json.loads(ir_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    payload = {}
                if isinstance(payload, dict):
                    return payload
        project_ir = self.pending_plan_summary.get("project_ir")
        return dict(project_ir) if isinstance(project_ir, dict) else {}

    def _read_artifact_text(self, raw_path: str, empty_text: str) -> str:
        path = str(raw_path or "").strip()
        if not path:
            return empty_text
        target = Path(path)
        if not target.exists() or not target.is_file():
            return empty_text
        try:
            raw = target.read_bytes()
        except OSError as exc:
            return f"无法读取文件：{exc}"
        text, _ = _decode_text_with_fallback(raw)
        normalized = text.strip() or empty_text
        if len(normalized) > 40_000:
            normalized = normalized[:40_000].rstrip() + "\n\n... 日志已截断，仅显示前 40,000 个字符 ..."
        return normalized

    def _render_blueprint_html(self) -> str:
        project_ir = self._load_project_ir_payload()
        target = {}
        if isinstance(project_ir.get("target"), dict):
            target = dict(project_ir.get("target") or {})
        elif isinstance(self.pending_plan_summary.get("target"), dict):
            target = dict(self.pending_plan_summary.get("target") or {})
        elif isinstance(self.pending_request_payload.get("target"), dict):
            target = dict(self.pending_request_payload.get("target") or {})
        chip = str(target.get("chip", "") or self.pending_plan_summary.get("chip", "") or "").strip()
        board = str(target.get("board", "") or self.pending_plan_summary.get("board", "") or "").strip()
        modules = project_ir.get("modules", [])
        if not isinstance(modules, list):
            modules = self.pending_plan_summary.get("modules", [])
        if not isinstance(modules, list):
            modules = []
        assignments = self.pending_plan_summary.get("assignments", [])
        if not isinstance(assignments, list):
            assignments = []
        buses = self.pending_plan_summary.get("buses", [])
        if not isinstance(buses, list):
            buses = []
        peripherals = project_ir.get("peripherals", {})
        if not isinstance(peripherals, dict):
            peripherals = {}

        cards: list[str] = []
        seen_keys: set[str] = set()

        def _badge(text: str, tone: str = "blue") -> str:
            bg = {
                "blue": "rgba(59,130,246,0.14)",
                "green": "rgba(16,185,129,0.14)",
                "amber": "rgba(245,158,11,0.16)",
                "rose": "rgba(239,68,68,0.16)",
            }.get(tone, "rgba(59,130,246,0.14)")
            color = {
                "blue": "#93C5FD",
                "green": "#6EE7B7",
                "amber": "#FCD34D",
                "rose": "#FDA4AF",
            }.get(tone, "#93C5FD")
            return (
                "<span style=\"display:inline-block; margin:4px 6px 0 0; padding:4px 10px; "
                f"border-radius:999px; background:{bg}; color:{color}; border:1px solid rgba(255,255,255,0.06); "
                "font-family:'JetBrains Mono','Cascadia Code',Consolas,monospace; font-size:12px;\">"
                f"{escape(text)}</span>"
            )

        def _add_card(title: str, subtitle: str, badges: list[str], notes: list[str]) -> None:
            normalized_title = title.strip() or "未命名资源"
            normalized_badges = [item for item in badges if item]
            dedupe_key = normalized_title + "|" + "|".join(normalized_badges)
            if dedupe_key in seen_keys:
                return
            seen_keys.add(dedupe_key)
            badge_html = "".join(_badge(item) for item in normalized_badges[:8]) or _badge("等待引脚映射", "amber")
            note_html = ""
            if notes:
                note_html = (
                    "<div style=\"margin-top:10px; color:#A1A1AA; font-size:12px; line-height:1.6;\">"
                    + "<br>".join(escape(item) for item in notes[:3] if item)
                    + "</div>"
                )
            cards.append(
                "<div style=\"background:#1C1C1F; border:1px solid rgba(255,255,255,0.08); border-radius:14px; "
                "padding:14px;\">"
                f"<div style=\"color:#FAFAFA; font-size:14px; font-weight:600; margin-bottom:4px;\">{escape(normalized_title)}</div>"
                f"<div style=\"color:#71717A; font-size:12px; margin-bottom:10px;\">{escape(subtitle)}</div>"
                f"<div>{badge_html}</div>{note_html}</div>"
            )

        for bus in buses[:8]:
            if not isinstance(bus, dict):
                continue
            pins = bus.get("pins", {})
            if not isinstance(pins, dict):
                pins = {}
            devices = bus.get("devices", [])
            if not isinstance(devices, list):
                devices = []
            notes = [str(item).strip() for item in bus.get("notes", []) if str(item).strip()]
            device_names = [str(item.get("module") or item.get("name") or "").strip() for item in devices if isinstance(item, dict)]
            title = str(bus.get("bus", "") or bus.get("option_id", "") or "Shared Bus").strip()
            subtitle = str(bus.get("kind", "") or "bus").upper()
            badges = [f"{signal.upper()} -> {pin}" for signal, pin in pins.items() if str(pin).strip()]
            if device_names:
                notes.append("挂载模块: " + ", ".join(item for item in device_names if item))
            _add_card(title, subtitle, badges, notes)

        grouped_assignments: dict[str, list[dict[str, object]]] = {}
        for item in assignments:
            if not isinstance(item, dict):
                continue
            module_name = str(item.get("module", "") or "unnamed_module").strip()
            grouped_assignments.setdefault(module_name, []).append(item)
        for module_name, items in list(grouped_assignments.items())[:10]:
            badges = []
            notes = []
            for item in items[:8]:
                signal = str(item.get("signal", "")).strip() or "signal"
                pin = str(item.get("pin", "")).strip() or "--"
                reason = str(item.get("reason", "")).strip()
                badges.append(f"{signal} -> {pin}")
                if reason:
                    notes.append(reason)
            _add_card(module_name, "Planner Assignments", badges, notes)

        if not assignments:
            peripheral_buses = peripherals.get("buses", [])
            if isinstance(peripheral_buses, list):
                for bus in peripheral_buses[:8]:
                    if not isinstance(bus, dict):
                        continue
                    pins = bus.get("pins", {})
                    if not isinstance(pins, dict):
                        pins = {}
                    badges = [f"{signal.upper()} -> {pin}" for signal, pin in pins.items() if str(pin).strip()]
                    notes = [str(item).strip() for item in bus.get("notes", []) if str(item).strip()]
                    _add_card(
                        str(bus.get("instance", "") or bus.get("bus", "") or "Shared Bus").strip(),
                        str(bus.get("kind", "") or "peripheral").upper(),
                        badges,
                        notes,
                    )
            for kind, entries in peripherals.items():
                if kind == "buses" or not isinstance(entries, list):
                    continue
                for entry in entries[:10]:
                    if not isinstance(entry, dict):
                        continue
                    pins = entry.get("pins", {})
                    if not isinstance(pins, dict) or not pins:
                        continue
                    title = str(
                        entry.get("module_name", "")
                        or entry.get("name", "")
                        or entry.get("instance", "")
                        or kind
                    ).strip()
                    badges = [f"{signal.upper()} -> {pin}" for signal, pin in pins.items() if str(pin).strip()]
                    notes = []
                    if entry.get("timer"):
                        notes.append(f"Timer: {entry.get('timer')}")
                    if entry.get("channel_macro"):
                        notes.append(f"Channel: {entry.get('channel_macro')}")
                    _add_card(title, kind.replace("_", " ").title(), badges, notes)

        if not cards:
            for module in modules[:8]:
                if isinstance(module, dict):
                    title = str(module.get("name", "") or module.get("key", "") or "module").strip()
                    subtitle = str(module.get("kind", "") or module.get("key", "") or "module").strip()
                else:
                    title = str(module).strip() or "module"
                    subtitle = "module"
                _add_card(title, subtitle, [], [])

        header_lines = []
        if chip:
            header_lines.append(f"目标芯片：{chip}")
        if board:
            header_lines.append(f"板卡：{board}")
        summary = str(self.pending_plan_summary.get("summary", "") or "").strip()
        if summary:
            header_lines.append(summary)
        header_html = "<br>".join(escape(item) for item in header_lines if item)
        if not header_html:
            header_html = "当前还没有成型的规划结果。先在左侧发需求，中央这里会切成引脚蓝图。"
        # Build a 2-column table layout compatible with QTextBrowser (no CSS Grid support)
        rows_html = ""
        card_list = cards
        for i in range(0, len(card_list), 2):
            left = card_list[i]
            right = card_list[i + 1] if i + 1 < len(card_list) else ""
            right_td = (
                f"<td width=\"50%\" style=\"padding:0 0 10px 5px; vertical-align:top;\">{right}</td>"
                if right else
                "<td width=\"50%\"></td>"
            )
            rows_html += (
                f"<tr><td width=\"50%\" style=\"padding:0 5px 10px 0; vertical-align:top;\">{left}</td>"
                f"{right_td}</tr>"
            )
        cards_html = f"<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\">{rows_html}</table>" if rows_html else ""
        return (
            "<div style=\"color:#E4E4E7;\">"
            f"<div style=\"margin-bottom:14px; color:#A1A1AA; line-height:1.7;\">{header_html}</div>"
            f"{cards_html}</div>"
        )

    def _refresh_workspace_views(self) -> None:
        project_ir = self._load_project_ir_payload()
        target = {}
        if isinstance(project_ir.get("target"), dict):
            target = dict(project_ir.get("target") or {})
        elif isinstance(self.pending_plan_summary.get("target"), dict):
            target = dict(self.pending_plan_summary.get("target") or {})
        elif isinstance(self.pending_request_payload.get("target"), dict):
            target = dict(self.pending_request_payload.get("target") or {})
        chip = str(target.get("chip", "") or self.pending_plan_summary.get("chip", "") or "").strip() or "待解析"
        board = str(target.get("board", "") or self.pending_plan_summary.get("board", "") or "").strip() or "待解析"
        modules = project_ir.get("modules", [])
        if not isinstance(modules, list):
            modules = self.pending_plan_summary.get("modules", [])
        if not isinstance(modules, list):
            modules = []
        assignments = self.pending_plan_summary.get("assignments", [])
        if not isinstance(assignments, list):
            assignments = []
        if not assignments and isinstance(project_ir.get("peripherals"), dict):
            derived_assignments = []
            for entries in project_ir.get("peripherals", {}).values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    pins = entry.get("pins", {})
                    if not isinstance(pins, dict):
                        continue
                    for signal, pin in pins.items():
                        derived_assignments.append({"signal": signal, "pin": pin})
            assignments = derived_assignments
        self.blueprint_chip_value.setText(self._clip_single_line_text(chip, 22))
        self.blueprint_chip_value.setToolTip(chip)
        self.blueprint_board_value.setText(self._clip_single_line_text(board, 22))
        self.blueprint_board_value.setToolTip(board)
        self.blueprint_modules_value.setText(str(len(modules)))
        self.blueprint_assignments_value.setText(str(len(assignments)))
        self.blueprint_view.setHtml(self._render_blueprint_html())
        if project_ir:
            self.project_ir_editor.setPlainText(_json_text(project_ir))
        else:
            self.project_ir_editor.setPlainText("当前还没有可展示的 project_ir.json。")

        state = dict(self.thread_engineering_state or {})
        terminal_lines = [
            f"[thread] {self.current_thread_id or 'unselected'}",
            f"[project] {self.active_project_dir or '未绑定工程'}",
            f"[status] {state.get('status_text', '空闲')}",
        ]
        timeline = state.get("timeline", [])
        if isinstance(timeline, list):
            for item in timeline[-6:]:
                if not isinstance(item, dict):
                    continue
                terminal_lines.append(
                    f"[{item.get('timestamp', '--')}] {item.get('stage', 'stage')} / {item.get('status', 'status')} / {item.get('detail', '')}"
                )
        warning_excerpt = [str(item).strip() for item in state.get("warning_excerpt", []) if str(item).strip()]
        error_excerpt = [str(item).strip() for item in state.get("error_excerpt", []) if str(item).strip()]
        if warning_excerpt:
            terminal_lines.append("[warning] " + " | ".join(warning_excerpt[:3]))
        if error_excerpt:
            terminal_lines.append("[error] " + " | ".join(error_excerpt[:3]))
        self.terminal_overview_view.setPlainText("\n".join(terminal_lines))

        build_log_path = str(state.get("build_log_path", "") or "").strip()
        build_summary = [str(item).strip() for item in state.get("build_summary", []) if str(item).strip()]
        build_fallback = "\n".join(build_summary) if build_summary else "构建日志会在生成并编译后显示在这里。"
        self.build_log_view.setPlainText(self._read_artifact_text(build_log_path, build_fallback))

        uart_capture_path = str(state.get("uart_capture_path", "") or "").strip()
        renode_log_path = str(state.get("renode_log_path", "") or "").strip()
        uart_fallback = str(state.get("simulate_summary", "") or "").strip() or "Renode UART 捕获会在仿真后显示在这里。"
        uart_text = self._read_artifact_text(uart_capture_path, "")
        if not uart_text:
            uart_text = self._read_artifact_text(renode_log_path, uart_fallback)
        self.uart_capture_view.setPlainText(uart_text or uart_fallback)

    def _clip_multiline_text(self, text: str, max_lines: int) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        lines = normalized.splitlines()
        if len(lines) <= max_lines:
            return normalized
        clipped = lines[:max_lines]
        clipped.append(f"... 还有 {len(lines) - max_lines} 行，完整内容可在对话区查看 ...")
        return "\n".join(clipped)

    def _clip_single_line_text(self, text: str, max_chars: int = 34) -> str:
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return ""
        if len(normalized) <= max_chars:
            return normalized
        if max_chars <= 8:
            return normalized[:max_chars]
        head = max(3, (max_chars - 3) // 2)
        tail = max(2, max_chars - 3 - head)
        return normalized[:head].rstrip() + "..." + normalized[-tail:].lstrip()

    def _summarize_path_for_ui(self, raw_path: str, max_chars: int = 28) -> str:
        normalized = str(raw_path or "").strip()
        if not normalized:
            return "未设置"
        path = Path(normalized)
        parts: list[str] = []
        if path.parent and str(path.parent) not in {"", "."}:
            parts.append(path.parent.name)
        parts.append(path.name or normalized)
        compact = "\\".join(part for part in parts if part) or normalized
        return self._clip_single_line_text(compact, max_chars=max_chars)

    def _render_pending_change_excerpt(self) -> str:
        if self.pending_review_kind == "negotiate" and self.pending_negotiation_options:
            excerpt: List[str] = []
            for option in self.pending_negotiation_options[:3]:
                title = str(option.get("title", "")).strip() or "建议方案"
                summary = str(option.get("summary", "")).strip()
                excerpt.append(f"- {title}" + (f": {summary}" if summary else ""))
            return "\n".join(excerpt)
        changes = [str(item).strip() for item in self.pending_change_preview if str(item).strip()]
        if changes:
            excerpt = changes[:4]
            if len(changes) > 4:
                excerpt.append(f"... 还有 {len(changes) - 4} 条变更")
            return "\n".join(f"- {item}" for item in excerpt)
        file_changes = [
            str(item.get("relative_path", "") or item.get("path", "")).strip()
            for item in self.pending_file_change_preview
            if isinstance(item, dict)
        ]
        file_changes = [item for item in file_changes if item]
        if file_changes:
            excerpt = file_changes[:4]
            if len(file_changes) > 4:
                excerpt.append(f"... 还有 {len(file_changes) - 4} 个文件")
            return "\n".join(f"- {item}" for item in excerpt)
        return "当前还没有待确认变更。"

    def _refresh_workflow_strip(self) -> None:
        state = dict(self.thread_engineering_state or {})
        if self.pending_request_payload and self.confirm_proposal_button.isEnabled():
            modules = self.pending_plan_summary.get("modules", [])
            module_count = len(modules) if isinstance(modules, list) else 0
            if self.pending_review_kind == "negotiate":
                self.workflow_stage_chip.set_status("待协商", "warning")
                self.workflow_status_line.setText(
                    f"规划有阻塞问题，已准备 {len(self.pending_negotiation_options)} 个折中方案等待选择。"
                )
                self.workflow_meta_label.setText("重新规划")
                return
            self.workflow_stage_chip.set_status("待确认", "warning")
            self.workflow_status_line.setText(f"方案已整理完成，等待确认。模块数：{module_count}")
            self.workflow_meta_label.setText(self.pending_mode == "modify" and "更新当前项目" or "新建工程")
            return
        if not state:
            self.workflow_stage_chip.set_status("空闲", "neutral")
            self.workflow_status_line.setText("当前流程还没有开始。")
            self.workflow_meta_label.setText("")
            return
        status_text = str(state.get("status_text", "") or "处理中").strip()
        status_kind = str(state.get("status_kind", "") or "neutral").strip() or "neutral"
        action = str(state.get("action", "") or "").strip()
        detail = ""
        for key in ("simulate_summary", "build_summary", "error_excerpt", "warning_excerpt"):
            value = state.get(key)
            if isinstance(value, list):
                value = next((str(item).strip() for item in value if str(item).strip()), "")
            else:
                value = str(value or "").strip()
            if value:
                detail = value
                break
        stage_map = {
            "proposal": "提案",
            "confirm_generation": "生成",
            "simulate": "仿真",
            "build": "编译",
            "doctor": "检查",
            "workflow_failed": "失败",
        }
        stage_label = stage_map.get(action, action or "流程")
        self.workflow_stage_chip.set_status(status_text, status_kind)
        self.workflow_status_line.setText(f"{stage_label} · {detail or status_text}")
        repair_count = int(state.get("repair_count", 0) or 0)
        self.workflow_meta_label.setText(f"修复 {repair_count} 次" if repair_count else "")
        self._update_workflow_dots(action, status_kind)

    def _update_workflow_dots(self, action: str = "", kind: str = "neutral") -> None:
        stage_order = ["proposal", "confirm_generation", "build", "simulate"]
        current_index = -1
        for idx, stage in enumerate(stage_order):
            if stage == action:
                current_index = idx
                break
        for idx, dot in enumerate(self.workflow_dots):
            if current_index < 0:
                dot.set_state("idle")
            elif idx < current_index:
                dot.set_state("done")
            elif idx == current_index:
                if kind in ("error",):
                    dot.set_state("error")
                elif kind == "success":
                    dot.set_state("done")
                else:
                    dot.set_state("active")
            else:
                dot.set_state("idle")

    def _build_live_thread_snapshot(self) -> DesktopChatThread | None:
        thread = self._current_thread()
        if thread is None:
            return None
        snapshot = DesktopChatThread(
            thread_id=thread.thread_id,
            title=thread.title,
            project_dir=self.active_project_dir.strip(),
            model_messages=[dict(item) for item in self.conversation],
            display_messages=[
                {
                    "role": str(item.get("role", "")).strip(),
                    "text": str(item.get("text", "")),
                }
                for item in self.display_conversation
            ],
            proposal_state=self._serialize_pending_proposal_state(),
            engineering_state=self._serialize_engineering_state(),
            updated_at=thread.updated_at,
        )
        snapshot.title = derive_thread_title(snapshot.display_messages, snapshot.project_dir, fallback=thread.title)
        return snapshot

    def _refresh_thread_context_panel(self) -> None:
        snapshot = self._build_live_thread_snapshot()
        if snapshot is None:
            self.thread_context_caption.setText("空线程")
            self.context_project_value.setText("未绑定")
            self.context_status_value.setText("待开始")
            self.context_build_value.setText("未构建")
            self.context_runtime_value.setText("未验证")
            self.thread_context_view.setPlainText("当前线程还没有可展示的结构化上下文。")
            self.thread_timeline_caption.setText("最近流程")
            self.thread_timeline_view.setPlainText("当前线程还没有可展示的执行时间线。")
            self._update_context_action_buttons("", "", "", "")
            self._refresh_sidebar_density()
            self._refresh_workspace_views()
            return
        status_text, _ = derive_thread_status(snapshot)
        engineering_state = dict(snapshot.engineering_state or {})
        summary_text = build_thread_context_summary(snapshot).strip()
        timeline_text = format_thread_timeline(snapshot)
        timeline_count = len([
            item
            for item in engineering_state.get("timeline", [])
            if isinstance(item, dict)
        ])
        project_value = Path(snapshot.project_dir).name if str(snapshot.project_dir or "").strip() else "未绑定"
        build_summary = [str(item).strip() for item in engineering_state.get("build_summary", []) if str(item).strip()]
        build_value = build_summary[0] if build_summary else "未构建"
        if len(build_value) > 18:
            build_value = build_value[:18] + "..."
        simulate_value = str(engineering_state.get("simulate_summary", "") or "").strip()
        if not simulate_value:
            simulate_value = "未验证"
        if len(simulate_value) > 18:
            simulate_value = simulate_value[:18] + "..."
        project_dir = str(snapshot.project_dir or "").strip()
        build_log_path = str(engineering_state.get("build_log_path", "") or "").strip()
        renode_log_path = str(engineering_state.get("renode_log_path", "") or "").strip()
        uart_capture_path = str(engineering_state.get("uart_capture_path", "") or "").strip()
        self.thread_context_caption.setText(f"{status_text} · 最近上下文")
        self.context_project_value.setText(project_value)
        self.context_status_value.setText(status_text)
        self.context_build_value.setText(build_value)
        self.context_runtime_value.setText(simulate_value)
        self.context_project_value.setToolTip(project_dir or project_value)
        self.context_build_value.setToolTip(build_log_path or build_value)
        self.context_runtime_value.setToolTip(renode_log_path or uart_capture_path or simulate_value)
        self.thread_context_view.setPlainText(
            self._clip_multiline_text(summary_text or "当前线程还没有可展示的结构化上下文。", 8)
        )
        self.thread_context_view.setToolTip(summary_text)
        self.thread_timeline_caption.setText(f"最近流程 · {timeline_count} 条")
        self.thread_timeline_view.setPlainText(self._clip_multiline_text(timeline_text, 6))
        self.thread_timeline_view.setToolTip(timeline_text)
        self._update_context_action_buttons(project_dir, build_log_path, renode_log_path, uart_capture_path)
        self._refresh_sidebar_density()
        self._refresh_workspace_views()

    def _update_context_action_buttons(
        self,
        project_dir: str,
        build_log_path: str,
        renode_log_path: str,
        uart_capture_path: str,
    ) -> None:
        button_states = (
            (self.context_open_project_button, project_dir, "打开工程目录"),
            (self.context_open_build_log_button, build_log_path, "打开构建日志"),
            (self.context_open_runtime_log_button, renode_log_path, "打开仿真日志"),
            (self.context_open_uart_button, uart_capture_path, "打开 UART 捕获"),
        )
        for button, raw_path, tooltip in button_states:
            normalized = str(raw_path or "").strip()
            exists = bool(normalized and Path(normalized).exists())
            button.setEnabled(exists)
            button.setToolTip(normalized if exists else tooltip)
        if hasattr(self, "_refresh_sidebar_density"):
            self._refresh_sidebar_density()

    def _open_local_path(self, raw_path: str, title: str) -> None:
        path = str(raw_path or "").strip()
        if not path:
            QMessageBox.information(self, title, f"当前没有可打开的{title}。")
            return
        target = Path(path)
        if not target.exists():
            QMessageBox.warning(self, title, f"目标不存在：\n{target}")
            return
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
        except AttributeError:
            QMessageBox.information(self, title, f"当前平台暂不支持直接打开：\n{target}")
        except OSError as exc:
            QMessageBox.warning(self, title, f"无法打开：\n{target}\n\n{exc}")

    def _open_context_project_dir(self) -> None:
        self._open_local_path(self.active_project_dir, "工程目录")

    def _open_context_build_log(self) -> None:
        self._open_local_path(str(self.thread_engineering_state.get("build_log_path", "") or ""), "构建日志")

    def _open_context_runtime_log(self) -> None:
        self._open_local_path(str(self.thread_engineering_state.get("renode_log_path", "") or ""), "仿真日志")

    def _open_context_uart_capture(self) -> None:
        self._open_local_path(str(self.thread_engineering_state.get("uart_capture_path", "") or ""), "UART 捕获")

    def _set_thread_panel_collapsed(self, collapsed: bool) -> None:
        self.thread_panel_collapsed = bool(collapsed)
        self.thread_panel_body.setVisible(not self.thread_panel_collapsed)
        self.thread_title_label.setVisible(not self.thread_panel_collapsed)
        self.thread_status_label.setVisible(not self.thread_panel_collapsed)
        if self.thread_panel_collapsed:
            self.thread_panel.setMinimumWidth(56)
            self.thread_panel.setMaximumWidth(56)
        else:
            self.thread_panel.setMinimumWidth(248)
            self.thread_panel.setMaximumWidth(312)
        self.thread_panel_toggle_button.setText("›" if self.thread_panel_collapsed else "‹")
        self.thread_panel_toggle_button.setToolTip("展开线程栏" if self.thread_panel_collapsed else "隐藏线程栏")
        self._update_sidebar_for_current_tab()

    def _toggle_thread_panel(self) -> None:
        self._set_thread_panel_collapsed(not self.thread_panel_collapsed)

    def _update_sidebar_for_current_tab(self) -> None:
        sizes = self.workspace_splitter.sizes()
        total = sum(sizes) or 1520
        sidebar_width = max(400, min(520, int(total * 0.31)))
        center_width = max(760, total - sidebar_width)
        self.right_panel.setMinimumWidth(400)
        self.right_panel.setMaximumWidth(520)
        self.workspace_splitter.setSizes([center_width, sidebar_width])

    def _set_sidebar_panel_collapsed(self, collapsed: bool) -> None:
        self.sidebar_panel_collapsed = collapsed
        self.sidebar_body.setVisible(not collapsed)
        self.sidebar_title_label.setVisible(not collapsed)
        if collapsed:
            self.sidebar_toggle_button.setText("›")
            self.sidebar_toggle_button.setToolTip("展开方案面板")
            self.right_panel.setMinimumWidth(48)
            self.right_panel.setMaximumWidth(48)
        else:
            self.sidebar_toggle_button.setText("‹")
            self.sidebar_toggle_button.setToolTip("收起方案面板")
            self._update_sidebar_for_current_tab()

    def _toggle_sidebar_panel(self) -> None:
        self._set_sidebar_panel_collapsed(not self.sidebar_panel_collapsed)

    def _is_chat_busy(self) -> bool:
        if self.chat_thread is not None and self.chat_thread.isRunning():
            return True
        return bool(self._active_tasks)

    def _load_chat_threads(self) -> None:
        self.chat_threads, selected_thread_id = load_chat_thread_store(self.chat_threads_path)
        if not self.chat_threads:
            self.chat_threads = [create_chat_thread()]
        selected_ids = {thread.thread_id for thread in self.chat_threads}
        active_thread_id = selected_thread_id if selected_thread_id in selected_ids else self.chat_threads[0].thread_id
        self._refresh_thread_list(select_thread_id=active_thread_id)
        self._select_thread(active_thread_id, refresh_list=False)

    def _save_all_chat_threads(self) -> None:
        save_chat_thread_store(self.chat_threads, self.current_thread_id, self.chat_threads_path)

    def _thread_sort_key(self, thread: DesktopChatThread) -> tuple[str, str]:
        return (str(thread.updated_at or "").strip(), str(thread.thread_id))

    def _sync_thread_runtime_state(self) -> None:
        if not self.current_thread_id:
            return
        if self.pending_graph_session is not None and self.pending_graph_thread_id:
            self.thread_graph_sessions[self.current_thread_id] = self.pending_graph_session
            self.thread_graph_thread_ids[self.current_thread_id] = self.pending_graph_thread_id
            return
        self.thread_graph_sessions.pop(self.current_thread_id, None)
        self.thread_graph_thread_ids.pop(self.current_thread_id, None)

    def _serialize_pending_proposal_state(self) -> dict[str, object]:
        current_profile = self._current_profile()
        proposal_state = PendingProposalState(
            proposal_text=self.proposal_view.toPlainText(),
            proposal_status_text=self.proposal_status_label.text(),
            proposal_status_kind=str(self.proposal_status_label.property("statusKind") or "neutral"),
            proposal_feedback=self.proposal_feedback_input.toPlainText(),
            request_payload=self.pending_request_payload,
            plan_summary=self.pending_plan_summary,
            review_kind=self.pending_review_kind,
            negotiation_options=self.pending_negotiation_options,
            change_preview=self.pending_change_preview,
            file_change_preview=self.pending_file_change_preview,
            output_dir=self.pending_output_dir,
            mode=self.pending_mode,
            confirm_enabled=self.confirm_proposal_button.isEnabled(),
            revise_enabled=self.revise_proposal_button.isEnabled(),
            clear_enabled=self.clear_proposal_button.isEnabled(),
            confirm_text=self.confirm_proposal_button.text(),
            clear_text=self.clear_proposal_button.text(),
            graph_thread_id=self.pending_graph_thread_id,
            graph_profile_id=current_profile.profile_id if current_profile is not None else "",
            graph_runtime_validation_enabled=self.chat_renode_checkbox.isChecked(),
        )
        return proposal_state.to_dict()

    def _restore_pending_graph_runtime(self, thread_id: str, proposal_state: dict[str, object] | None = None) -> None:
        self.pending_graph_session = self.thread_graph_sessions.get(thread_id)
        self.pending_graph_thread_id = self.thread_graph_thread_ids.get(thread_id, "")
        if self.pending_graph_session is not None and self.pending_graph_thread_id:
            return

        payload = PendingProposalState.from_dict(proposal_state)
        graph_thread_id = payload.graph_thread_id
        if not graph_thread_id:
            return
        enable_runtime_validation = (
            payload.graph_runtime_validation_enabled
            if payload.graph_runtime_validation_enabled is not None
            else self.chat_renode_checkbox.isChecked()
        )
        session = self._restore_persisted_graph_session(
            graph_thread_id,
            profile_id=payload.graph_profile_id,
            enable_runtime_validation=enable_runtime_validation,
        )
        if session is None:
            return
        self.pending_graph_session = session
        self.pending_graph_thread_id = graph_thread_id
        self.thread_graph_sessions[thread_id] = session
        self.thread_graph_thread_ids[thread_id] = graph_thread_id

    def _serialize_engineering_state(self) -> dict[str, object]:
        return self._thread_engineering_state.to_dict()

    def _update_engineering_state(self, persist: bool = True, **kwargs: object) -> None:
        self._thread_engineering_state = self._thread_engineering_state.merge_updates(**kwargs)
        self._refresh_thread_context_panel()
        self._refresh_workflow_strip()
        if persist and self.current_thread_id:
            self._persist_current_thread()

    def _append_thread_timeline_event(
        self,
        stage: str,
        status: str,
        detail: str = "",
        persist: bool = True,
    ) -> None:
        self._thread_engineering_state = self._thread_engineering_state.append_timeline_event(
            stage=stage,
            status=status,
            detail=detail,
            timestamp=datetime.now().strftime("%m-%d %H:%M"),
        )
        self._refresh_thread_context_panel()
        self._refresh_workflow_strip()
        if persist and self.current_thread_id:
            self._persist_current_thread()

    def _apply_proposal_state(self, state: dict[str, object] | None) -> None:
        proposal_state = PendingProposalState.from_dict(state)
        self._pending_proposal_state = proposal_state

        proposal_text = proposal_state.proposal_text.strip() or self._default_proposal_text()
        proposal_status_text = proposal_state.proposal_status_text.strip() or "等待需求"
        proposal_status_kind = proposal_state.proposal_status_kind
        proposal_feedback = proposal_state.preferred_feedback()
        confirm_text = proposal_state.confirm_text.strip() or "确认方案并开始生成"
        clear_text = proposal_state.clear_text.strip() or "清空待确认方案"

        self.proposal_view.setPlainText(self._clip_multiline_text(proposal_text, 18))
        self.proposal_view.setToolTip(proposal_text)
        self.proposal_status_label.set_status(proposal_status_text, proposal_status_kind)
        self.proposal_feedback_input.setPlainText(proposal_feedback)
        self._refresh_negotiation_option_buttons()
        self.confirm_proposal_button.setText(confirm_text)
        self.clear_proposal_button.setText(clear_text)

        self.confirm_proposal_button.setEnabled(proposal_state.confirm_enabled)
        self.revise_proposal_button.setEnabled(proposal_state.revise_enabled)
        self.clear_proposal_button.setEnabled(proposal_state.clear_enabled)

        if proposal_state.graph_runtime_validation_enabled is not None:
            self.chat_renode_checkbox.setChecked(proposal_state.graph_runtime_validation_enabled)

        if self.current_thread_id:
            self._restore_pending_graph_runtime(self.current_thread_id, proposal_state.to_dict())

        if self.pending_request_payload and self.pending_graph_session is None:
            self.confirm_proposal_button.setEnabled(False)
            self.revise_proposal_button.setEnabled(False)
            self.clear_proposal_button.setEnabled(True)
            self.thread_status_label.setText("提案已恢复")
        self._refresh_proposal_summary_cards()
        self._refresh_workflow_strip()
        self._refresh_workspace_views()

    def _current_thread(self) -> DesktopChatThread | None:
        for thread in self.chat_threads:
            if thread.thread_id == self.current_thread_id:
                return thread
        return None

    def _persist_current_thread(self, refresh_list: bool = True) -> None:
        thread = self._current_thread()
        if thread is None:
            return
        thread.project_dir = self.active_project_dir.strip()
        thread.model_messages = [dict(item) for item in self.conversation]
        thread.display_messages = [
            {"role": str(item.get("role", "")).strip(), "text": str(item.get("text", ""))}
            for item in self.display_conversation
        ]
        self._sync_thread_runtime_state()
        thread.proposal_state = self._serialize_pending_proposal_state()
        thread.engineering_state = self._serialize_engineering_state()
        thread.title = derive_thread_title(thread.display_messages, thread.project_dir)
        thread.summary_text = build_thread_context_summary(thread)
        thread.updated_at = current_timestamp()
        self._refresh_thread_context_panel()
        self.chat_threads = sorted(self.chat_threads, key=self._thread_sort_key, reverse=True)
        self._save_all_chat_threads()
        if refresh_list:
            self._refresh_thread_list(select_thread_id=thread.thread_id)

    def _refresh_thread_list(self, select_thread_id: str = "") -> None:
        selected = select_thread_id or self.current_thread_id
        self.chat_threads = sorted(self.chat_threads, key=self._thread_sort_key, reverse=True)
        self.thread_list.blockSignals(True)
        self.thread_list.clear()
        current_row = -1
        status_colors = {
            "success": QColor("#5ac67a"),
            "warning": QColor("#f3c56b"),
            "error": QColor("#ff7a7a"),
            "neutral": QColor("#c6d2e1"),
        }
        for index, thread in enumerate(self.chat_threads):
            status_text, status_kind = derive_thread_status(thread)
            item = QListWidgetItem(format_thread_list_label(thread))
            item.setData(Qt.UserRole, thread.thread_id)
            item.setData(Qt.UserRole + 1, status_kind)
            item.setForeground(status_colors.get(status_kind, status_colors["neutral"]))
            item.setSizeHint(QSize(item.sizeHint().width(), 72))
            item.setToolTip(
                f"状态: {status_text}\n摘要: {summarize_thread(thread)}\n最近更新: {format_thread_timestamp(thread)}"
            )
            self.thread_list.addItem(item)
            if thread.thread_id == selected:
                current_row = index
        if current_row >= 0:
            self.thread_list.setCurrentRow(current_row)
        self.thread_list.blockSignals(False)

    def _clear_message_bubbles(self) -> None:
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.active_assistant_bubble = None
        self._active_negotiation_card = None

    def _rebuild_message_bubbles(self) -> None:
        self._clear_message_bubbles()
        if not self.display_conversation:
            self._append_system_message(self._welcome_message())
            return
        max_render = getattr(self, "max_render_messages", 50)
        total = len(self.display_conversation)
        start = max(0, total - max_render)
        if start > 0:
            load_more = QPushButton(f"加载更早的 {start} 条消息")
            load_more.setObjectName("GhostButton")
            load_more.clicked.connect(lambda: self._load_all_messages())
            self.messages_layout.insertWidget(0, load_more)
        for item in self.display_conversation[start:]:
            role = str(item.get("role", "")).strip() or "assistant"
            text = str(item.get("text", ""))
            self._append_message(role, text)
        self._scroll_to_bottom()

    def _load_all_messages(self) -> None:
        self.max_render_messages = len(self.display_conversation) + 100
        self._rebuild_message_bubbles()

    def _restore_thread_state(self, thread: DesktopChatThread) -> None:
        self.current_thread_id = thread.thread_id
        self.conversation = [dict(item) for item in thread.model_messages]
        self.display_conversation = [
            {"role": str(item.get("role", "")).strip(), "text": str(item.get("text", ""))}
            for item in thread.display_messages
        ]
        self.thread_engineering_state = dict(thread.engineering_state or {})
        self.active_project_dir = str(thread.project_dir or "").strip()
        self.project_summary_text = f"工程：{self.active_project_dir or '未打开'}"
        self._refresh_sidebar_meta()
        self.chat_project_explorer.set_root_path(self.active_project_dir)
        thread_status_text, _ = derive_thread_status(thread)
        self.thread_status_label.setText(thread_status_text)
        self._apply_proposal_state(thread.proposal_state)
        self._refresh_thread_context_panel()
        self._rebuild_message_bubbles()
        self.project_activated.emit(self.active_project_dir)

    def _select_thread(self, thread_id: str, refresh_list: bool = True) -> None:
        for thread in self.chat_threads:
            if thread.thread_id != thread_id:
                continue
            self._restore_thread_state(thread)
            if refresh_list:
                self._refresh_thread_list(select_thread_id=thread_id)
            return

    def _create_new_thread(self) -> None:
        if self._is_chat_busy():
            QMessageBox.information(self, "请稍候", "当前仍有任务在运行，暂时不能切换线程。")
            return
        if self.current_thread_id:
            self._persist_current_thread(refresh_list=False)
        thread = create_chat_thread()
        self.chat_threads.insert(0, thread)
        self._refresh_thread_list(select_thread_id=thread.thread_id)
        self._select_thread(thread.thread_id, refresh_list=False)

    def _on_thread_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        thread_id = str(current.data(Qt.UserRole) or "").strip()
        if not thread_id or thread_id == self.current_thread_id:
            return
        if self._is_chat_busy():
            self._refresh_thread_list(select_thread_id=self.current_thread_id)
            QMessageBox.information(self, "请稍候", "当前仍有任务在运行，暂时不能切换线程。")
            return
        if self.current_thread_id:
            self._persist_current_thread(refresh_list=False)
        self._select_thread(thread_id, refresh_list=False)

    def set_project_root(self, project_dir: str) -> None:
        self.active_project_dir = project_dir
        self.project_summary_text = f"工程：{project_dir or '未打开'}"
        self._refresh_sidebar_meta()
        self.chat_project_explorer.set_root_path(project_dir)
        if project_dir:
            self.sidebar_tabs.setCurrentIndex(1)
        if self.current_thread_id:
            self._persist_current_thread()
        self._update_agent_mode_banner()
        self._refresh_workspace_views()

    def clear_pending_proposal(self) -> None:
        self._remove_negotiation_inline_card()
        self._pending_proposal_state = PendingProposalState()
        self.pending_graph_session = None
        self.proposal_status_label.set_status("等待需求", "neutral")
        self.proposal_view.setPlainText(self._default_proposal_text())
        self.proposal_view.setToolTip(self._default_proposal_text())
        self.proposal_feedback_input.clear()
        self.confirm_proposal_button.setEnabled(False)
        self.revise_proposal_button.setEnabled(False)
        self.clear_proposal_button.setEnabled(False)
        self.confirm_proposal_button.setText("确认方案并开始生成")
        self.clear_proposal_button.setText("清空待确认方案")
        self._refresh_proposal_summary_cards()
        self._refresh_workflow_strip()
        self._refresh_workspace_views()
        if self.current_thread_id:
            self._persist_current_thread()

    def _apply_quick_prompt(self, text: str) -> None:
        self.chat_input.setPlainText(text)
        self.chat_input.setFocus()

    def _run_quick_prompt(self, text: str) -> None:
        self.chat_input.setPlainText(text)
        self.send_message()

    def _update_agent_mode_banner(self) -> None:
        action = detect_agent_action(self.chat_input.toPlainText())
        if action == "scaffold":
            self.agent_mode_chip.set_status("方案确认", "success")
            self.agent_mode_chip.setToolTip("这条消息会先走方案提案流程，确认后再生成工程。")
            return
        if action == "build":
            status_kind = "success" if self.active_project_dir else "warning"
            self.agent_mode_chip.set_status("编译工程", status_kind)
            if self.active_project_dir:
                self.agent_mode_chip.setToolTip("这条消息会对当前激活工程直接执行本地 build-keil。")
            else:
                self.agent_mode_chip.setToolTip("这条消息会尝试编译工程，但当前还没有激活项目目录。")
            return
        if action == "doctor":
            status_kind = "success" if self.active_project_dir else "warning"
            self.agent_mode_chip.set_status("检查工程", status_kind)
            if self.active_project_dir:
                self.agent_mode_chip.setToolTip("这条消息会对当前激活工程直接执行本地 Keil 环境检查。")
            else:
                self.agent_mode_chip.setToolTip("这条消息会尝试检查工程，但当前还没有激活项目目录。")
            return
        self.agent_mode_chip.set_status("普通对话", "neutral")
        self.agent_mode_chip.setToolTip("当前输入看起来像普通问答，不会直接触发工程生成。")

    def _set_composer_active(self, active: bool) -> None:
        if not hasattr(self, "composer_card"):
            return
        active = bool(active)
        if bool(self.composer_card.property("composerActive")) == active:
            return
        self.composer_card.setProperty("composerActive", active)
        self.composer_card.style().unpolish(self.composer_card)
        self.composer_card.style().polish(self.composer_card)
        self.composer_card.update()

    def _update_chat_input_height(self) -> None:
        if not hasattr(self, "chat_input"):
            return
        document_height = self.chat_input.document().size().height()
        frame_height = self.chat_input.frameWidth() * 2
        target_height = int(document_height + frame_height + 28)
        target_height = max(84, min(target_height, 180))
        if self.chat_input.height() != target_height:
            self.chat_input.setFixedHeight(target_height)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.chat_input:
            if event.type() == event.Type.FocusIn:
                self._set_composer_active(True)
            elif event.type() == event.Type.FocusOut:
                QTimer.singleShot(0, lambda: self._set_composer_active(self.chat_input.hasFocus()))
            elif event.type() == event.Type.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
                    self.send_message()
                    return True
        return super().eventFilter(obj, event)

    def clear_conversation(self) -> None:
        self.conversation.clear()
        self.display_conversation.clear()
        self._clear_message_bubbles()
        self.active_assistant_bubble = None
        self.clear_pending_proposal()
        if self.current_thread_id:
            self._persist_current_thread()
        self._append_system_message("会话已清空。")

    def _collect_chat_attachments(self):
        return collect_attachment_digests(self.chat_attachments.paths())

    def _render_user_message_text(self, text: str) -> str:
        attachment_text = render_attachment_list(self.chat_attachments.paths())
        if not attachment_text:
            return text
        return text + "\n\n[附件]\n" + attachment_text

    def _record_display_message(self, role: str, text: str, persist: bool = True) -> None:
        self.display_conversation.append({"role": role, "text": text})
        if persist and self.current_thread_id:
            self._persist_current_thread()

    def _record_assistant_message(self, text: str) -> None:
        self.conversation.append({"role": "assistant", "content": text})
        self._record_display_message("assistant", text)

    def _build_model_context_messages(self, system_prompt: str) -> List[dict[str, object]]:
        messages: List[dict[str, object]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})

        thread = self._current_thread()
        recent_messages = self.conversation[-self.max_context_messages :]
        if thread is not None and thread.summary_text.strip() and len(self.conversation) > self.max_context_messages:
            messages.append(
                {
                    "role": "system",
                    "content": "当前工程线程摘要如下，请结合它理解后续最近几轮消息：\n" + thread.summary_text.strip(),
                }
            )
        messages.extend(recent_messages)
        return messages

    def _current_thread_followup_context(self, exclude_latest_user_message: bool = False) -> str:
        thread = self._current_thread()
        if thread is None:
            return ""
        return build_thread_followup_context(
            thread,
            max_recent_messages=self.max_context_messages,
            exclude_latest_user_message=exclude_latest_user_message,
        )

    def _retrieve_chat_context(self, user_prompt: str) -> str:
        prompt = str(user_prompt or "").strip()
        if not prompt:
            return ""
        try:
            chunks, _filters = retrieve_relevant_chunks(
                prompt,
                REPO_ROOT,
                active_project_dir=self.active_project_dir,
            )
            return render_retrieved_context(chunks)
        except Exception:
            return ""

    def send_message(self) -> None:
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        attachment_batch = self._collect_chat_attachments()
        if attachment_batch.errors:
            QMessageBox.warning(self, "附件读取失败", "\n".join(attachment_batch.errors[:8]))
            return
        self.chat_input.clear()
        user_display_text = self._render_user_message_text(text)
        self._append_message("user", user_display_text)
        self._record_display_message("user", user_display_text, persist=False)
        self.conversation.append(
            {
                "role": "user",
                "content": compose_multimodal_user_content(text, attachment_batch.attachments),
            }
        )
        if self.current_thread_id:
            self._persist_current_thread()

        profile = self._current_profile()
        if profile is None:
            self._append_system_message("当前没有启用的模型 Profile。请先去“配置 -> 模型 API”里新增并启用一个。")
            self.conversation.pop()
            if self.current_thread_id:
                self._persist_current_thread()
            return

        action = detect_agent_action(text)
        if action != "none":
            if action == "scaffold":
                self._start_proposal_workflow(profile, text, attachment_batch.attachments)
                return
            self._start_agent_workflow(profile, text, action, attachment_batch.attachments)
            return

        retrieved_context = self._retrieve_chat_context(text)
        chat_system_prompt = build_chat_system_prompt(
            profile.system_prompt,
            active_project_dir=self.active_project_dir,
            user_prompt=text,
            retrieved_context=retrieved_context,
        )
        messages = self._build_model_context_messages(chat_system_prompt)

        self.chat_status.set_status("请求中", "warning")
        self.send_button.setEnabled(False)
        self.send_button.setToolTip("正在处理中，请等待完成")
        self.active_assistant_bubble = self._append_message("assistant", "")
        self.chat_thread = ChatStreamThread(profile, messages)
        self.chat_thread.chunk.connect(self._on_chat_chunk)
        self.chat_thread.completed.connect(self._on_chat_complete)
        self.chat_thread.failed.connect(self._on_chat_failed)
        self.chat_thread.start()

    def _start_proposal_workflow(self, profile: LlmProfile, text: str, attachments) -> None:
        self.chat_status.set_status("整理方案中", "warning")
        self.send_button.setEnabled(False)
        self.send_button.setToolTip("正在处理中，请等待完成")
        self.loading_overlay.show_with_text("整理方案中")
        self._append_thread_timeline_event("提案", "进行中", "开始整理模块、板子和接线方案")
        self.active_assistant_bubble = self._append_message(
            "assistant",
            "我先通过 LangGraph 工作流整理模块、板子和接线方案，确认后再继续生成工程……",
        )
        self.pending_graph_session = STM32ProjectGraphSession(self._make_graph_runtime(profile))
        self.pending_graph_thread_id = uuid.uuid4().hex
        thread_context = self._current_thread_followup_context(exclude_latest_user_message=True)
        task = BackgroundTask(
            lambda: self.pending_graph_session.start(
                text,
                attachments=attachments,
                active_project_dir=self.active_project_dir,
                thread_context=thread_context,
                thread_id=self.pending_graph_thread_id,
            )
        )
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            self._on_proposal_workflow_finished,
            self._on_agent_workflow_failed,
        )

    def _start_agent_workflow(self, profile: LlmProfile, text: str, action: str, attachments) -> None:
        action_label = {
            "scaffold": "生成工程",
            "build": "编译工程",
            "doctor": "检查工程",
        }.get(action, "执行本地工作流")
        self.chat_status.set_status("执行中", "warning")
        self.send_button.setEnabled(False)
        self.send_button.setToolTip("正在处理中，请等待完成")
        self.loading_overlay.show_with_text(action_label)
        self._append_thread_timeline_event(action_label, "进行中", f"开始执行 {action_label}")
        self.active_assistant_bubble = self._append_message(
            "assistant",
            f"正在按本地 Agent 工作流执行“{action_label}”...",
        )
        thread_context = self._current_thread_followup_context(exclude_latest_user_message=True)
        task = BackgroundTask(
            lambda: run_chat_agent_workflow(
                profile,
                text,
                REPO_ROOT,
                active_project_dir=self.active_project_dir,
                attachments=attachments,
                thread_context=thread_context,
            )
        )
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            self._on_agent_workflow_finished,
            self._on_agent_workflow_failed,
        )

    def _on_proposal_workflow_finished(self, result) -> None:
        values = dict(result.values)
        self.loading_overlay.hide_overlay()
        proposal_message = str(values.get("proposal_text", "")).strip() or self._render_graph_error_message(values)
        request_payload = values.get("request_payload") or {}
        plan_result = values.get("plan_result") or {}
        change_preview = list(values.get("change_preview", []))
        file_change_preview = list(values.get("file_change_preview", []))
        output_dir = str(values.get("project_dir", "")).strip()
        mode = "modify" if self.active_project_dir.strip() else "create"
        proposal_ready = bool(result.interrupts) and bool(request_payload)

        self.chat_status.set_status("已整理方案" if proposal_ready else "方案失败", "success" if proposal_ready else "error")
        self.send_button.setEnabled(True)
        self.send_button.setToolTip("Ctrl+Enter 发送")
        if self.active_assistant_bubble is None:
            self.active_assistant_bubble = self._append_message("assistant", "")
        self.active_assistant_bubble.set_text(proposal_message)
        self._record_assistant_message(proposal_message)
        self.proposal_view.setPlainText(self._clip_multiline_text(proposal_message, 18))
        self.proposal_view.setToolTip(proposal_message)
        self.sidebar_tabs.setCurrentIndex(0)
        self.pending_request_payload = dict(request_payload)
        self.pending_plan_summary = dict(plan_result)
        self.pending_review_kind = str(values.get("review_kind", "proposal") or "proposal").strip() or "proposal"
        self.pending_negotiation_options = [
            dict(item) for item in values.get("negotiation_options", []) if isinstance(item, dict)
        ]
        self.pending_change_preview = change_preview
        self.pending_file_change_preview = file_change_preview
        self.pending_output_dir = output_dir
        self.pending_mode = mode
        if self.pending_review_kind == "negotiate" and self.pending_negotiation_options and not self.proposal_feedback_input.toPlainText().strip():
            default_feedback = str(self.pending_negotiation_options[0].get("feedback", "")).strip()
            if default_feedback:
                self.proposal_feedback_input.setPlainText(default_feedback)
        if proposal_ready:
            self._append_thread_timeline_event("提案", "待确认", "方案已整理完成，等待确认", persist=False)
            self._update_engineering_state(
                persist=False,
                status_text="等待确认",
                status_kind="warning",
                action="proposal",
                project_dir=output_dir or self.active_project_dir,
                plan_module_count=len(plan_result.get("modules", [])) if isinstance(plan_result, dict) else 0,
            )
            self.proposal_status_label.set_status("等待确认", "warning")
            button_text = "确认方案并更新当前项目" if mode == "modify" else "确认方案并开始生成"
            self.confirm_proposal_button.setText(button_text)
            self.confirm_proposal_button.setEnabled(True)
            self.revise_proposal_button.setEnabled(True)
            self.clear_proposal_button.setEnabled(True)
            if self.pending_review_kind == "negotiate":
                self.chat_status.set_status("等待协商", "warning")
                self.proposal_status_label.set_status("等待协商", "warning")
                self.confirm_proposal_button.setText("采纳当前方案并重算")
                self._show_negotiation_inline_card(self.pending_negotiation_options)
        else:
            self._append_thread_timeline_event("提案", "失败", "方案整理未通过，请查看错误摘要", persist=False)
            self._update_engineering_state(
                persist=False,
                status_text="方案失败",
                status_kind="error",
                action="proposal",
                project_dir=output_dir or self.active_project_dir,
                error_excerpt=[str(item).strip() for item in values.get("errors", []) if str(item).strip()][:3],
            )
            self.proposal_status_label.set_status("方案失败", "error")
            self.confirm_proposal_button.setEnabled(False)
            self.revise_proposal_button.setEnabled(False)
            self.clear_proposal_button.setEnabled(True)
            self.pending_graph_session = None
            self.pending_graph_thread_id = ""
            self.pending_review_kind = "proposal"
            self.pending_negotiation_options = []
        self._refresh_proposal_summary_cards()
        if self.current_thread_id:
            self._persist_current_thread()
        self._scroll_to_bottom()

    def confirm_pending_proposal(self) -> None:
        if not self.pending_request_payload or self.pending_graph_session is None or not self.pending_graph_thread_id:
            QMessageBox.information(self, "尚无待确认方案", "请先输入需求，让 Agent 先整理方案。")
            return
        if self.pending_review_kind == "negotiate":
            feedback = self.proposal_feedback_input.toPlainText().strip()
            if not feedback and self.pending_negotiation_options:
                feedback = str(self.pending_negotiation_options[0].get("feedback", "")).strip()
                if feedback:
                    self.proposal_feedback_input.setPlainText(feedback)
            if not feedback:
                QMessageBox.information(self, "请先选择调整方向", "先点一个建议方案，或在反馈框里写你希望的调整方式。")
                return
            self.chat_status.set_status("协商重算中", "warning")
            self.proposal_status_label.set_status("正在重算", "warning")
            self.send_button.setEnabled(False)
            self.send_button.setToolTip("正在处理中，请等待完成")
            self.confirm_proposal_button.setEnabled(False)
            self.revise_proposal_button.setEnabled(False)
            self.clear_proposal_button.setEnabled(False)
            self._append_thread_timeline_event("协商", "进行中", f"采纳折中方案后重新规划：{feedback[:80]}")
            if self.current_thread_id:
                self._persist_current_thread()
            self.active_assistant_bubble = self._append_message(
                "assistant",
                f"收到协商方案，正在按这个方向重新规划：{feedback}",
            )
            task = BackgroundTask(
                lambda feedback=feedback: self.pending_graph_session.resume(
                    self.pending_graph_thread_id,
                    approved=True,
                    user_feedback=feedback,
                )
            )
            _run_task_with_lifetime(
                self,
                self.thread_pool,
                task,
                self._on_revised_proposal_finished,
                self._on_agent_workflow_failed,
            )
            return
        confirm_message = self._render_confirm_change_message(
            self.pending_change_preview,
            self.pending_file_change_preview,
        )
        button_label = "确认并更新" if self.pending_mode == "modify" else "确认并生成"
        if not self._confirm_pending_changes_with_preview(confirm_message, button_label):
            return
        self.chat_status.set_status("生成中", "warning")
        self.send_button.setEnabled(False)
        self.send_button.setToolTip("正在处理中，请等待完成")
        self.confirm_proposal_button.setEnabled(False)
        self.revise_proposal_button.setEnabled(False)
        self.clear_proposal_button.setEnabled(False)
        self._append_thread_timeline_event("生成", "进行中", "已确认方案，开始生成工程并尝试编译")
        if self.current_thread_id:
            self._persist_current_thread()
        self.active_assistant_bubble = self._append_message(
            "assistant",
            f"已收到“{button_label}”确认，正在生成工程、导入驱动并尝试编译……",
        )
        task = BackgroundTask(self._run_confirmed_generation)
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            self._on_confirmed_generation_finished,
            self._on_agent_workflow_failed,
        )

    def revise_pending_proposal(self) -> None:
        if self.pending_graph_session is None or not self.pending_graph_thread_id:
            QMessageBox.information(self, "当前没有可打回方案", "请先让 Agent 整理出一份待确认方案。")
            return

        feedback = self.proposal_feedback_input.toPlainText().strip() or self.chat_input.toPlainText().strip()
        if not feedback:
            QMessageBox.information(self, "请先写修改意见", "例如：不要用 PC13，或者 I2C 固定到 PB6/PB7。")
            return

        self.chat_status.set_status("按意见重算中", "warning")
        self.proposal_status_label.set_status("正在重算", "warning")
        self.send_button.setEnabled(False)
        self.send_button.setToolTip("正在处理中，请等待完成")
        self.confirm_proposal_button.setEnabled(False)
        self.revise_proposal_button.setEnabled(False)
        self.clear_proposal_button.setEnabled(False)
        self._append_thread_timeline_event("提案", "重算中", f"根据反馈重算：{feedback[:80]}")
        if self.current_thread_id:
            self._persist_current_thread()
        self.active_assistant_bubble = self._append_message(
            "assistant",
            f"收到修改意见，正在基于当前待审方案重新起草和规划：{feedback}",
        )
        task = BackgroundTask(lambda: self._run_revise_proposal(feedback))
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            self._on_revised_proposal_finished,
            self._on_agent_workflow_failed,
        )

    def _run_confirmed_generation(self):
        return self.pending_graph_session.resume(self.pending_graph_thread_id, approved=True)

    def _run_revise_proposal(self, feedback: str):
        return self.pending_graph_session.resume(
            self.pending_graph_thread_id,
            approved=False,
            user_feedback=feedback,
        )

    def _on_confirmed_generation_finished(self, result) -> None:
        self.send_button.setEnabled(True)
        self.send_button.setToolTip("Ctrl+Enter 发送")
        self.loading_overlay.hide_overlay()
        values = dict(result.values)
        scaffold = values.get("scaffold_result", {}) or {}
        build = values.get("build_result", {}) or {}
        driver_import = values.get("driver_import_result", {}) or {}
        simulate = values.get("simulate_result", {}) or {}
        evaluation = values.get("evaluation_result", {}) or {}
        project_dir = str(values.get("project_dir", "")).strip()
        state_warnings = [str(item).strip() for item in values.get("warnings", []) if str(item).strip()]
        repair_count = int(values.get("repair_count", 0) or 0)
        engineering_status_text = "已生成"
        engineering_status_kind = "success"
        hex_file = ""
        validation_summary = ""
        validation_passed = evaluation.get("passed")
        uart_capture_path = ""
        lines: List[str] = []
        if scaffold.get("feasible"):
            lines.append("工程已经生成完成。")
            if project_dir:
                self.active_project_dir = str(Path(project_dir).resolve())
                self.project_summary_text = f"工程：{self.active_project_dir}"
                self._refresh_sidebar_meta()
                self.chat_project_explorer.set_root_path(self.active_project_dir)
                self.project_activated.emit(self.active_project_dir)
                lines.append(f"- 工程目录: `{self.active_project_dir}`")
        else:
            lines.append("工程生成失败了。")
            for item in scaffold.get("errors", [])[:4]:
                lines.append(f"- 错误: {item}")

        if driver_import and not driver_import.get("imported", True):
            self.chat_status.set_status("驱动导入失败", "error")
            self.proposal_status_label.set_status("待处理", "warning")
            lines.append("- 官方 STM32Cube 驱动导入失败。")
            for item in driver_import.get("errors", [])[:4]:
                lines.append(f"- 错误: {item}")
        elif build:
            if build.get("built"):
                self.chat_status.set_status("已完成", "success")
                self.proposal_status_label.set_status("已生成", "success")
                engineering_status_text = "编译通过"
                engineering_status_kind = "success"
                hex_file = str(build.get("hex_file", "")).strip()
                if hex_file:
                    self.pending_output_dir = project_dir
                    lines.append(f"- HEX: `{hex_file}`")
                for item in build.get("summary_lines", [])[:2]:
                    lines.append(f"- 构建摘要: {item}")
                if self.chat_renode_checkbox.isChecked() and project_dir:
                    lines.append("- 已启用 Renode 仿真验证，构建结果整理完成后会继续执行。")
            else:
                self.chat_status.set_status("编译失败", "error")
                self.proposal_status_label.set_status("待处理", "warning")
                engineering_status_text = "编译失败"
                engineering_status_kind = "error"
                lines.append("- 编译还没有通过。")
                for item in build.get("errors", [])[:4]:
                    lines.append(f"- 错误: {item}")
        else:
            self.chat_status.set_status("已生成", "success")
            self.proposal_status_label.set_status("已生成", "success")

        if repair_count > 0:
            lines.append(f"- 自动修复尝试: {repair_count} 次")
            for item in state_warnings[:6]:
                lines.append(f"- 修复备注: {item}")

        if simulate:
            validation_summary = str(evaluation.get("summary", "")).strip()
            validation_reasons = [str(item).strip() for item in evaluation.get("reasons", []) if str(item).strip()]
            if evaluation.get("passed") is True:
                self.chat_status.set_status("已完成", "success")
                engineering_status_text = "仿真通过"
                engineering_status_kind = "success"
                lines.append("- Renode 运行验证: 通过")
            else:
                self.chat_status.set_status("Renode 验证失败", "error")
                self.proposal_status_label.set_status("待处理", "warning")
                engineering_status_text = "仿真失败"
                engineering_status_kind = "error"
                lines.append("- Renode 运行验证: 未通过")
            if validation_summary:
                lines.append(f"- 验证摘要: {validation_summary}")
            for item in validation_reasons[:3]:
                lines.append(f"- 验证细节: {item}")
            log_path = str(simulate.get("log_path", "")).strip()
            uart_capture_path = str(simulate.get("uart_capture_path", "")).strip()
            if log_path:
                lines.append(f"- Renode 日志: `{log_path}`")
            if uart_capture_path:
                lines.append(f"- UART 捕获: `{uart_capture_path}`")

        if scaffold.get("feasible"):
            self._append_thread_timeline_event("生成", "完成", "工程文件已经写入", persist=False)
        if build:
            build_detail = ""
            summary_lines = build.get("summary_lines", []) or []
            if summary_lines:
                build_detail = str(summary_lines[0]).strip()
            elif not build.get("built"):
                errors = build.get("errors", []) or []
                if errors:
                    build_detail = str(errors[0]).strip()
            self._append_thread_timeline_event(
                "编译",
                "通过" if build.get("built") else "失败",
                build_detail,
                persist=False,
            )
        if simulate:
            self._append_thread_timeline_event(
                "仿真",
                "通过" if evaluation.get("passed") is True else "失败",
                validation_summary or "Renode 运行验证已完成",
                persist=False,
            )
        if repair_count > 0:
            self._append_thread_timeline_event(
                "修复",
                "已尝试",
                f"自动修复尝试 {repair_count} 次",
                persist=False,
            )

        if self.active_assistant_bubble is None:
            self.active_assistant_bubble = self._append_message("assistant", "")
        final_message = "\n".join(lines)
        self.active_assistant_bubble.set_text(final_message)
        self._record_assistant_message(final_message)
        self.proposal_view.setPlainText(final_message)
        self.confirm_proposal_button.setEnabled(False)
        self.revise_proposal_button.setEnabled(False)
        self.clear_proposal_button.setEnabled(True)
        self.clear_proposal_button.setText("清空当前提案")
        self.pending_request_payload = {}
        self.pending_plan_summary = {}
        self.pending_change_preview = []
        self.pending_file_change_preview = []
        self.pending_graph_session = None
        self.pending_graph_thread_id = ""
        self._update_engineering_state(
            persist=False,
            status_text=engineering_status_text,
            status_kind=engineering_status_kind,
            action="confirm_generation",
            project_dir=self.active_project_dir or project_dir,
            build_summary=[str(item) for item in build.get("summary_lines", [])[:2]],
            build_errors=[str(item) for item in build.get("errors", [])[:3]],
            build_log_path=str(build.get("build_log_path", "") or "").strip(),
            hex_file=hex_file,
            simulate_summary=validation_summary or ("通过" if validation_passed is True else "未通过" if validation_passed is False else ""),
            simulate_passed=validation_passed if validation_passed in {True, False} else None,
            renode_log_path=str(simulate.get("log_path", "") or "").strip(),
            uart_capture_path=uart_capture_path,
            repair_count=repair_count,
            warning_excerpt=state_warnings[:3],
        )
        if self.current_thread_id:
            self._persist_current_thread()
        self._scroll_to_bottom()
        if build.get("built") and self.chat_renode_checkbox.isChecked() and self.active_project_dir and not simulate:
            self._start_chat_renode_validation(self.active_project_dir, "构建完成")

    def _on_revised_proposal_finished(self, result) -> None:
        self.proposal_feedback_input.clear()
        self._on_proposal_workflow_finished(result)

    def _start_chat_renode_validation(self, project_dir: str, source_label: str) -> None:
        if not project_dir.strip():
            return
        self.chat_status.set_status("Renode 验证中", "warning")
        self._append_thread_timeline_event("仿真", "进行中", f"{source_label}后开始 Renode 验证")
        self.active_assistant_bubble = self._append_message(
            "assistant",
            f"{source_label}，现在开始执行 Renode 仿真验证。",
        )
        task = BackgroundTask(lambda project_dir=project_dir: run_renode_project(project_dir))
        _run_task_with_lifetime(
            self,
            self.thread_pool,
            task,
            self._on_chat_renode_validation_finished,
            self._on_agent_workflow_failed,
        )

    def _on_chat_renode_validation_finished(self, result) -> None:
        if result.ran:
            self.chat_status.set_status("已完成", "success")
            lines = [
                "Renode 仿真验证完成。",
                f"- 工程目录: `{result.project_dir}`",
            ]
            if getattr(result, "log_path", ""):
                lines.append(f"- 日志: `{result.log_path}`")
            if result.summary_lines:
                lines.append(f"- 摘要: {result.summary_lines[0]}")
            if getattr(result, "validation_passed", None) is True:
                lines.append("- UART 期望校验: 通过")
            if getattr(result, "uart_output", None):
                first_uart = next(iter(result.uart_output.items()))
                preview = first_uart[1].splitlines()[0].strip() if first_uart[1].splitlines() else ""
                if preview:
                    lines.append(f"- UART 预览: {preview}")
            if result.warnings:
                lines.append("- 备注: " + "; ".join(result.warnings[:3]))
            self._append_thread_timeline_event(
                "仿真",
                "通过",
                str(result.summary_lines[0]).strip() if result.summary_lines else "Renode 仿真验证通过",
                persist=False,
            )
            self._update_engineering_state(
                persist=False,
                status_text="仿真通过",
                status_kind="success",
                action="simulate",
                project_dir=result.project_dir,
                simulate_summary=str(result.summary_lines[0]).strip() if result.summary_lines else "通过",
                simulate_passed=True,
                renode_log_path=str(getattr(result, "log_path", "") or "").strip(),
                uart_capture_path=str(getattr(result, "uart_capture_path", "") or "").strip(),
            )
            self.sidebar_tabs.setCurrentIndex(1 if result.project_dir else 0)
        else:
            self.chat_status.set_status("Renode 验证失败", "error")
            lines = [
                "Renode 仿真验证未通过。",
                f"- 工程目录: `{result.project_dir}`",
            ]
            for item in result.errors[:4]:
                lines.append(f"- 错误: {item}")
            if getattr(result, "validation_passed", None) is False:
                lines.append("- UART 期望校验: 未通过")
            if getattr(result, "log_path", ""):
                lines.append(f"- 日志: `{result.log_path}`")
            if getattr(result, "uart_capture_path", ""):
                lines.append(f"- UART 捕获: `{result.uart_capture_path}`")
            self._append_thread_timeline_event(
                "仿真",
                "失败",
                str(result.errors[0]).strip() if result.errors else "Renode 仿真验证未通过",
                persist=False,
            )
            self._update_engineering_state(
                persist=False,
                status_text="仿真失败",
                status_kind="error",
                action="simulate",
                project_dir=result.project_dir,
                simulate_summary=str(result.errors[0]).strip() if result.errors else "未通过",
                simulate_passed=False,
                renode_log_path=str(getattr(result, "log_path", "") or "").strip(),
                uart_capture_path=str(getattr(result, "uart_capture_path", "") or "").strip(),
            )
            self.sidebar_tabs.setCurrentIndex(0)

        if self.active_assistant_bubble is None:
            self.active_assistant_bubble = self._append_message("assistant", "")
        message = "\n".join(lines)
        self.active_assistant_bubble.set_text(message)
        self._record_assistant_message(message)
        self._scroll_to_bottom()

    def _make_graph_runtime(self, profile: LlmProfile) -> GraphRuntime:
        validation = self.chat_renode_checkbox.isChecked()
        return GraphRuntime(
            profile=profile,
            repo_root=REPO_ROOT,
            enable_runtime_validation=validation,
            generate_makefile=validation,
        )

    def _render_confirm_change_message(
        self,
        change_preview: List[str],
        file_change_preview: List[dict[str, object]],
    ) -> str:
        preview_lines = change_preview or ["将按当前方案生成或更新工程文件。"]
        message_lines = ["确认后将执行这些变更：", ""]
        message_lines.extend(f"- {item}" for item in preview_lines)
        if file_change_preview:
            message_lines.append("")
            message_lines.append("重点文件预览：")
            status_map = {
                "create": "create",
                "update": "update",
                "unchanged": "same",
            }
            for item in file_change_preview[:16]:
                status = status_map.get(str(item.get("status", "")).strip(), "file")
                relative_path = str(item.get("relative_path", "")).strip() or str(item.get("path", "")).strip()
                message_lines.append(f"- [{status}] {relative_path}")
            if len(file_change_preview) > 16:
                message_lines.append(f"- ... 还有 {len(file_change_preview) - 16} 个文件条目")
        return "\n".join(message_lines)

    def _confirm_pending_changes_with_preview(self, confirm_message: str, button_label: str) -> bool:
        dialog = ProposalDiffReviewDialog(
            summary_lines=confirm_message.splitlines(),
            file_changes=self.pending_file_change_preview,
            confirm_label=button_label,
            parent=self,
        )
        return dialog.exec() == QDialog.Accepted

    def _render_graph_error_message(self, values: dict[str, object]) -> str:
        lines: List[str] = []
        proposal_text = str(values.get("proposal_text", "") or "").strip()
        if proposal_text:
            lines.append(proposal_text)
        errors = [str(item) for item in values.get("errors", []) if str(item).strip()]
        warnings = [str(item) for item in values.get("warnings", []) if str(item).strip()]
        if errors:
            if not lines:
                lines.append("方案整理没有通过。")
            lines.append("错误：")
            lines.extend(f"- {item}" for item in errors[:6])
        if warnings:
            lines.append("备注：")
            lines.extend(f"- {item}" for item in warnings[:6])
        return "\n".join(lines) or "方案整理没有返回可展示结果。"

    def _current_profile(self) -> LlmProfile | None:
        profile_id = self.profile_combo.currentData()
        return self._find_profile(profile_id)

    def _find_profile(self, profile_id: str | None) -> LlmProfile | None:
        resolved_profile_id = str(profile_id or "").strip()
        for profile in self.profiles:
            if resolved_profile_id and profile.profile_id == resolved_profile_id:
                return profile
        return self.profiles[0] if self.profiles else None

    def _restore_persisted_graph_session(
        self,
        graph_thread_id: str,
        *,
        profile_id: str = "",
        enable_runtime_validation: bool | None = None,
    ) -> STM32ProjectGraphSession | None:
        resolved_graph_thread_id = str(graph_thread_id or "").strip()
        if not resolved_graph_thread_id:
            return None
        profile = self._find_profile(profile_id)
        if profile is None:
            return None
        validation = (
            self.chat_renode_checkbox.isChecked()
            if enable_runtime_validation is None
            else bool(enable_runtime_validation)
        )
        runtime = GraphRuntime(
            profile=profile,
            repo_root=REPO_ROOT,
            enable_runtime_validation=validation,
            generate_makefile=validation,
        )
        session = STM32ProjectGraphSession(runtime)
        snapshot = session.get_state(resolved_graph_thread_id)
        if not snapshot.values and not snapshot.interrupts and not snapshot.next_nodes:
            return None
        return session

    def _on_chat_chunk(self, chunk: str) -> None:  # pragma: no cover - GUI runtime path
        if self.active_assistant_bubble is None:
            self.active_assistant_bubble = self._append_message("assistant", "")
        self.active_assistant_bubble.append_text(chunk)
        self._scroll_to_bottom()

    def _on_chat_complete(self) -> None:  # pragma: no cover - GUI runtime path
        self.chat_status.set_status("完成", "success")
        self.send_button.setEnabled(True)
        self.send_button.setToolTip("Ctrl+Enter 发送")
        self.loading_overlay.hide_overlay()
        if self.active_assistant_bubble is not None:
            self._record_assistant_message(self.active_assistant_bubble._raw_text)
        self.chat_thread = None

    def _on_agent_workflow_finished(self, result) -> None:
        self.chat_status.set_status("完成" if result.ok else "失败", "success" if result.ok else "error")
        self.send_button.setEnabled(True)
        self.send_button.setToolTip("Ctrl+Enter 发送")
        self.loading_overlay.hide_overlay()
        if self.active_assistant_bubble is None:
            self.active_assistant_bubble = self._append_message("assistant", "")
        self.active_assistant_bubble.set_text(result.message)
        self._record_assistant_message(result.message)
        if result.project_dir:
            self.active_project_dir = result.project_dir
            self.project_summary_text = f"工程：{result.project_dir}"
            self._refresh_sidebar_meta()
            self.chat_project_explorer.set_root_path(result.project_dir)
            self.sidebar_tabs.setCurrentIndex(1 if result.ok else 0)
            self.project_activated.emit(result.project_dir)
        status_text = {
            "scaffold": "已生成" if result.ok else "生成失败",
            "build": "编译通过" if result.ok else "编译失败",
            "doctor": "检查通过" if result.ok else "检查失败",
        }.get(result.action or "", "完成" if result.ok else "失败")
        self._update_engineering_state(
            persist=False,
            status_text=status_text,
            status_kind="success" if result.ok else "error",
            action=result.action or "chat_action",
            project_dir=result.project_dir or self.active_project_dir,
            build_log_path=str(getattr(result, "build_log_path", "") or "").strip(),
            warning_excerpt=[str(item) for item in result.warnings[:3]],
            error_excerpt=[str(item) for item in result.errors[:3]],
        )
        self._append_thread_timeline_event(
            result.action or "chat_action",
            "通过" if result.ok else "失败",
            status_text,
            persist=False,
        )
        self._scroll_to_bottom()
        if result.ok and result.action == "build" and self.chat_renode_checkbox.isChecked() and result.project_dir:
            self._start_chat_renode_validation(result.project_dir, "当前项目构建完成")

    def _on_agent_workflow_failed(self, details: str) -> None:  # pragma: no cover - GUI runtime path
        self.chat_status.set_status("失败", "error")
        self.proposal_status_label.set_status("处理失败", "error")
        self.send_button.setEnabled(True)
        self.send_button.setToolTip("Ctrl+Enter 发送")
        self.loading_overlay.hide_overlay()
        if self.active_assistant_bubble is None:
            self.active_assistant_bubble = self._append_message("assistant", "")
        self.active_assistant_bubble.set_text("本地 Agent 工作流执行失败。\n\n" + details)
        self._update_engineering_state(
            persist=False,
            status_text="处理失败",
            status_kind="error",
            action="workflow_failed",
            project_dir=self.active_project_dir,
            error_excerpt=[line.strip() for line in str(details).splitlines()[:3] if line.strip()],
        )
        self._append_thread_timeline_event("工作流", "失败", "本地 Agent 工作流执行失败", persist=False)
        self._record_assistant_message(self.active_assistant_bubble.text_label.text())
        if self.current_thread_id:
            self._persist_current_thread()
        self._scroll_to_bottom()

    def _on_chat_failed(self, details: str) -> None:  # pragma: no cover - GUI runtime path
        self.chat_status.set_status("失败", "error")
        self.send_button.setEnabled(True)
        self.send_button.setToolTip("Ctrl+Enter 发送")
        self.loading_overlay.hide_overlay()
        if self.active_assistant_bubble is None:
            self.active_assistant_bubble = self._append_message("assistant", "")
        profile = self._current_profile()
        profile_hint = ""
        if profile is not None:
            profile_hint = f"\n\n**当前模型配置**: {profile.name} ({profile.base_url or 'default'})"
        details_lower = str(details).lower()
        if "401" in details or "unauthorized" in details_lower or "api_key" in details_lower:
            guidance = "API Key 无效或已过期，请在「配置」页检查对应模型的 API Key。"
        elif "timeout" in details_lower or "timed out" in details_lower:
            guidance = "请求超时，请检查网络连接，或尝试切换到响应更快的模型。"
        elif "connection" in details_lower or "connect" in details_lower:
            guidance = "无法连接到模型服务，请检查网络或确认 API 地址是否正确。"
        elif "404" in details or "not found" in details_lower:
            guidance = "模型接口地址或模型名称有误，请在「配置」页检查 Base URL 和 Model。"
        elif "429" in details or "rate" in details_lower:
            guidance = "请求频率过高，请稍后再试。"
        else:
            guidance = "调用模型失败，请检查连接、API Key 或接口配置。"
        self.active_assistant_bubble.set_text(f"{guidance}{profile_hint}\n\n```\n{details.strip()}\n```")
        self._record_assistant_message(self.active_assistant_bubble.text_label.text())
        self.chat_thread = None
        self._scroll_to_bottom()

    def _append_message(self, role: str, text: str) -> MessageBubble:
        bubble = MessageBubble(role, text)
        row = QWidget()
        row.setObjectName("ChatRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble, 0, Qt.AlignRight)
        else:
            row_layout.addWidget(bubble, 0, Qt.AlignLeft)
            row_layout.addStretch(1)
        bubble.setProperty("chatRowRole", role)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row)
        self._scroll_to_bottom()
        return bubble

    def _append_system_message(self, text: str) -> None:
        bubble = self._append_message("assistant", text)
        bubble.role_label.setText("系统")

    def _show_negotiation_inline_card(self, options: list) -> None:
        self._remove_negotiation_inline_card()

        def _on_submit(feedback: str) -> None:
            if not feedback:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "请填写修改意见", "请先选择一个建议方案，或在输入框中写修改意见。")
                return
            self.proposal_feedback_input.setPlainText(feedback)
            self.confirm_pending_proposal()

        card = NegotiationInlineCard(options, _on_submit, parent=self.messages_host)
        self._active_negotiation_card = card
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, card)
        self._scroll_to_bottom()

    def _remove_negotiation_inline_card(self) -> None:
        if self._active_negotiation_card is not None:
            self._active_negotiation_card.deleteLater()
            self._active_negotiation_card = None

    def _scroll_to_bottom(self) -> None:  # pragma: no cover - GUI runtime path
        scroll_bar = self.scroll_area.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def _update_profile_sidebar(self) -> None:
        profile = self._current_profile()
        if profile is None:
            self.profile_summary_text = "模型：未配置"
            self._refresh_sidebar_meta()
            return
        model_text = profile.model or "未指定模型"
        self.profile_summary_text = f"模型：{profile.name} / {model_text}"
        self._refresh_sidebar_meta()


