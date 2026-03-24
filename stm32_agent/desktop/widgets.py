from __future__ import annotations

import json
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, List

try:
    import qtawesome as qta
except Exception:  # pragma: no cover - optional fallback
    qta = None

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRegularExpression,
    QRunnable,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    Signal,
    QObject,
)
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..llm_config import LlmProfile

from .llm_client import stream_chat_completion


REPO_ROOT = Path(__file__).resolve().parents[2]


TEXT_PREVIEW_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk")


def _json_text(data: object) -> str:
    if hasattr(data, "to_dict"):
        data = data.to_dict()
    return json.dumps(data, ensure_ascii=False, indent=2)


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _decode_text_with_fallback(raw: bytes) -> tuple[str, str]:
    for encoding in TEXT_PREVIEW_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)")


def _simple_markdown_to_html(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    code_blocks: list[str] = []

    def _save_code_block(match: re.Match) -> str:
        lang = match.group(1) or ""
        code = match.group(2).rstrip("\n")
        placeholder = f"\x00CODE{len(code_blocks)}\x00"
        code_blocks.append(
            f'<pre style="background: #000000; padding: 16px; '
            f"border-radius: 8px; font-family: 'JetBrains Mono', Cascadia Code, Consolas, monospace; "
            f'font-size: 13.5px; line-height: 1.5; margin: 12px 0; overflow-x: auto; '
            f'border: 1px solid rgba(255,255,255,0.08);">'
            f"<code style='color: #E4E4E7;'>{code}</code></pre>"
        )
        return placeholder

    text = _CODE_BLOCK_RE.sub(_save_code_block, text)
    text = _INLINE_CODE_RE.sub(
        r'<code style="background: rgba(255,255,255,0.1); padding: 2px 6px; '
        r"border-radius: 4px; font-family: 'JetBrains Mono', Cascadia Code, monospace; "
        r'font-size: 13px; color: #E4E4E7;">\1</code>',
        text,
    )
    text = _BOLD_RE.sub(r"<b style='color:#FFFFFF;'>\1</b>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)
    lines = text.split("\n")
    result_lines: list[str] = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            if not in_list:
                result_lines.append("<ul style='margin: 6px 0; padding-left: 20px; color: #D4D4D8;'>")
                in_list = True
            result_lines.append(f"<li style='margin-bottom: 6px; line-height: 1.6;'>{stripped[2:]}</li>")
        else:
            if in_list:
                result_lines.append("</ul>")
                in_list = False
            if stripped.startswith("### "):
                result_lines.append(
                    f"<h4 style='margin: 20px 0 8px 0; font-size: 14.5px; color: #FFFFFF;'>{stripped[4:]}</h4>"
                )
            elif stripped.startswith("## "):
                result_lines.append(
                    f"<h3 style='margin: 24px 0 10px 0; font-size: 15.5px; color: #FFFFFF;'>{stripped[3:]}</h3>"
                )
            elif stripped.startswith("# "):
                result_lines.append(
                    f"<h2 style='margin: 24px 0 12px 0; font-size: 17px; color: #FFFFFF;'>{stripped[2:]}</h2>"
                )
            elif stripped == "":
                result_lines.append("<div style='height: 8px;'></div>")
            else:
                result_lines.append(f"<p style='margin: 6px 0; line-height: 1.7; color: #E4E4E7;'>{line}</p>")
    if in_list:
        result_lines.append("</ul>")
    html = "\n".join(result_lines)
    for idx, block in enumerate(code_blocks):
        html = html.replace(f"\x00CODE{idx}\x00", block)
    return html


def _safe_icon(name: str, color: str = "#dfe8f4"):
    if qta is None:
        return QApplication.style().standardIcon(QApplication.style().SP_FileIcon)
    return qta.icon(name, color=color)


class TaskSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class BackgroundTask(QRunnable):
    def __init__(self, fn: Callable[[], object]):
        super().__init__()
        self.fn = fn
        self.signals = TaskSignals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception:  # pragma: no cover - GUI runtime path
            self.signals.error.emit(traceback.format_exc())
            return
        self.signals.finished.emit(result)


def _run_task_with_lifetime(
    owner: object,
    thread_pool: QThreadPool,
    task: BackgroundTask,
    on_finished: Callable[[object], None],
    on_error: Callable[[str], None],
) -> None:
    task_bucket = getattr(owner, "_active_tasks", None)
    if task_bucket is None:
        task_bucket = set()
        setattr(owner, "_active_tasks", task_bucket)

    task_bucket.add(task)

    def _finished(result: object) -> None:
        task_bucket.discard(task)
        on_finished(result)

    def _failed(details: str) -> None:
        task_bucket.discard(task)
        on_error(details)

    task.signals.finished.connect(_finished)
    task.signals.error.connect(_failed)
    thread_pool.start(task)


class ChatStreamThread(QThread):
    chunk = Signal(str)
    completed = Signal()
    failed = Signal(str)

    def __init__(self, profile: LlmProfile, messages: List[dict[str, object]]):
        super().__init__()
        self.profile = profile
        self.messages = messages

    def run(self) -> None:
        try:
            stream_chat_completion(self.profile, self.messages, self.chunk.emit)
        except Exception:  # pragma: no cover - GUI runtime path
            self.failed.emit(traceback.format_exc())
            return
        self.completed.emit()


class JsonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)
        self.rules = []

        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#78b7ff"))
        key_format.setFontWeight(QFont.Bold)
        self.rules.append((QRegularExpression(r'"[^"]*"\s*:'), key_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#9ad08f"))
        self.rules.append((QRegularExpression(r':\s*"[^"]*"'), string_format))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#f3c56b"))
        self.rules.append((QRegularExpression(r"\b-?(0x[a-fA-F0-9]+|\d+(\.\d+)?)\b"), number_format))

        bool_format = QTextCharFormat()
        bool_format.setForeground(QColor("#d391ff"))
        self.rules.append((QRegularExpression(r"\b(true|false|null)\b"), bool_format))

    def highlightBlock(self, text: str) -> None:  # pragma: no cover - visual
        for expression, fmt in self.rules:
            iterator = expression.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class StatusChip(QLabel):
    def __init__(self, text: str = "未检查", kind: str = "neutral"):
        super().__init__(text)
        self.setObjectName("StatusChip")
        self.set_status(text, kind)

    def set_status(self, text: str, kind: str = "neutral") -> None:
        self.setText(text)
        self.setProperty("statusKind", kind)
        self.style().unpolish(self)
        self.style().polish(self)


class WorkflowDot(QLabel):
    """Small status dot for workflow step indicators."""

    def __init__(self, label: str = "", state: str = "idle"):
        super().__init__(label)
        self.setObjectName("WorkflowDot")
        self.setFixedSize(12, 12)
        self.setAlignment(Qt.AlignCenter)
        self.set_state(state)

    def set_state(self, state: str) -> None:
        self.setProperty("stepState", state)
        self.style().unpolish(self)
        self.style().polish(self)


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with pulsing loading text."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("LoadingOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self._label = QLabel("处理中...")
        self._label.setObjectName("LoadingLabel")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)
        self._pulse_timer = QTimer(self)
        self._pulse_dots = 0
        self._pulse_timer.timeout.connect(self._update_dots)
        self.hide()

    def show_with_text(self, text: str = "处理中") -> None:
        self._base_text = text
        self._pulse_dots = 0
        self._label.setText(text + "...")
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self._pulse_timer.start(500)

    def hide_overlay(self) -> None:
        self._pulse_timer.stop()
        self.hide()

    def _update_dots(self) -> None:
        self._pulse_dots = (self._pulse_dots + 1) % 4
        dots = "." * (self._pulse_dots + 1)
        self._label.setText(self._base_text + dots)


class CodeEditor(QPlainTextEdit):
    def __init__(self, read_only: bool = False):
        super().__init__()
        self.setObjectName("CodeEditor")
        self.setReadOnly(read_only)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(28)
        self.highlighter = JsonHighlighter(self.document())




class Card(QFrame):
    def __init__(self, elevated: bool = False):
        super().__init__()
        self.setObjectName("CardElevated" if elevated else "Card")


class MetricCard(Card):
    def __init__(self, title: str, subtitle: str):
        super().__init__(elevated=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SectionTitle")
        self.chip = StatusChip()
        top_row.addWidget(self.title_label)
        top_row.addStretch(1)
        top_row.addWidget(self.chip)

        self.value_label = QLabel("--")
        self.value_label.setObjectName("MetricValue")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("MetricCaption")
        self.subtitle_label.setWordWrap(True)

        layout.addLayout(top_row)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)

    def update_metric(self, value: str, subtitle: str, chip_text: str, chip_kind: str) -> None:
        self.value_label.setText(value)
        self.subtitle_label.setText(subtitle)
        self.chip.set_status(chip_text, chip_kind)


class GuideCard(Card):
    def __init__(self):
        super().__init__(elevated=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        title = QLabel("新手建议流程")
        title.setObjectName("SectionTitle")
        self.step_chip = StatusChip("第 1 步", "warning")
        top_row.addWidget(title)
        top_row.addStretch(1)
        top_row.addWidget(self.step_chip)

        self.current_title = QLabel("先在下面用中文描述你想做的功能")
        self.current_title.setObjectName("SectionTitle")
        self.current_hint = QLabel("比如：用 STM32F103C8T6 做一个四路流水灯。不会写 JSON 也没关系。")
        self.current_hint.setObjectName("SectionHint")
        self.current_hint.setWordWrap(True)

        steps = QLabel(
            "1. 输入一句需求，或先载入一个示例。\n"
            "2. 点“AI 帮我转成配置”，或者直接使用示例里的配置。\n"
            "3. 点“先检查能不能做”，确认引脚和模块都能分配。\n"
            "4. 点“生成 Keil 工程”，最后再“编译并导出 HEX”。"
        )
        steps.setObjectName("SectionHint")
        steps.setWordWrap(True)

        layout.addLayout(top_row)
        layout.addWidget(self.current_title)
        layout.addWidget(self.current_hint)
        layout.addWidget(steps)

    def set_step(self, step_text: str, title: str, hint: str, kind: str = "neutral") -> None:
        self.step_chip.set_status(step_text, kind)
        self.current_title.setText(title)
        self.current_hint.setText(hint)


class AnimatedStackedWidget(QStackedWidget):
    def __init__(self):
        super().__init__()
        self._animation: QPropertyAnimation | None = None

    def fade_to(self, index: int) -> None:
        widget = self.widget(index)
        if widget is None:
            return
        self.setCurrentIndex(index)
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(180)
        animation.setStartValue(0.78)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        self._animation = animation
        animation.start()

