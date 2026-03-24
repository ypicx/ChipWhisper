from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from uuid import uuid4

from .engineering_state import ThreadEngineeringState
from .proposal_state import PendingProposalState


DEFAULT_THREAD_TITLE = "新建工程会话"
MAX_PERSISTED_MODEL_MESSAGES = 24
MAX_PERSISTED_MESSAGE_TEXT = 4000
_IMAGE_ATTACHMENT_NOTE = "[图片附件已省略，仅保留文字上下文]"


@dataclass
class DesktopChatThread:
    thread_id: str
    title: str = DEFAULT_THREAD_TITLE
    project_dir: str = ""
    model_messages: List[Dict[str, object]] = field(default_factory=list)
    display_messages: List[Dict[str, str]] = field(default_factory=list)
    proposal_state: Dict[str, object] = field(default_factory=dict)
    engineering_state: Dict[str, object] = field(default_factory=dict)
    summary_text: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, object]:
        proposal_state = PendingProposalState.from_dict(self.proposal_state)
        engineering_state = ThreadEngineeringState.from_dict(self.engineering_state)
        return {
            "thread_id": self.thread_id,
            "title": self.title,
            "project_dir": self.project_dir,
            "model_messages": sanitize_model_messages_for_storage(self.model_messages),
            "display_messages": [dict(item) for item in self.display_messages],
            "proposal_state": proposal_state.to_dict(),
            "engineering_state": engineering_state.to_dict(),
            "summary_text": self.summary_text,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "DesktopChatThread":
        proposal_state = PendingProposalState.from_dict(payload.get("proposal_state"))
        engineering_state = ThreadEngineeringState.from_dict(payload.get("engineering_state"))
        return cls(
            thread_id=str(payload.get("thread_id", "")).strip() or uuid4().hex,
            title=str(payload.get("title", "")).strip() or DEFAULT_THREAD_TITLE,
            project_dir=str(payload.get("project_dir", "")).strip(),
            model_messages=[
                dict(item)
                for item in payload.get("model_messages", [])
                if isinstance(item, dict)
            ],
            display_messages=[
                {
                    "role": str(item.get("role", "")).strip(),
                    "text": str(item.get("text", "")),
                }
                for item in payload.get("display_messages", [])
                if isinstance(item, dict)
            ],
            proposal_state=proposal_state.to_dict(),
            engineering_state=engineering_state.to_dict(),
            summary_text=str(payload.get("summary_text", "")),
            updated_at=str(payload.get("updated_at", "")).strip(),
        )


def get_default_chat_threads_path(repo_root: str | Path | None = None) -> Path:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    root = Path(repo_root)
    return root / ".chipwhisper_cache" / "desktop_chat_threads.json"


def load_chat_thread_store(path: str | Path | None = None) -> Tuple[List[DesktopChatThread], str]:
    resolved = Path(path) if path is not None else get_default_chat_threads_path()
    if not resolved.exists():
        return [], ""
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], ""
    if isinstance(payload, list):
        threads = [DesktopChatThread.from_dict(item) for item in payload if isinstance(item, dict)]
        return sorted(threads, key=_thread_sort_key, reverse=True), ""
    if not isinstance(payload, dict):
        return [], ""
    thread_items = payload.get("threads", [])
    if not isinstance(thread_items, list):
        return [], ""
    threads = [DesktopChatThread.from_dict(item) for item in thread_items if isinstance(item, dict)]
    current_thread_id = str(payload.get("current_thread_id", "")).strip()
    return sorted(threads, key=_thread_sort_key, reverse=True), current_thread_id


def load_chat_threads(path: str | Path | None = None) -> List[DesktopChatThread]:
    threads, _ = load_chat_thread_store(path)
    return threads


def save_chat_thread_store(
    threads: List[DesktopChatThread],
    current_thread_id: str = "",
    path: str | Path | None = None,
) -> Path:
    resolved = Path(path) if path is not None else get_default_chat_threads_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "current_thread_id": str(current_thread_id or "").strip(),
        "threads": [thread.to_dict() for thread in sorted(threads, key=_thread_sort_key, reverse=True)],
    }
    resolved.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resolved


def save_chat_threads(threads: List[DesktopChatThread], path: str | Path | None = None) -> Path:
    return save_chat_thread_store(threads, path=path)


def create_chat_thread(title: str = DEFAULT_THREAD_TITLE, project_dir: str = "") -> DesktopChatThread:
    return DesktopChatThread(
        thread_id=uuid4().hex,
        title=title.strip() or DEFAULT_THREAD_TITLE,
        project_dir=str(project_dir or "").strip(),
        updated_at=current_timestamp(),
    )


def current_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sanitize_model_messages_for_storage(
    messages: List[Dict[str, object]],
    max_messages: int = MAX_PERSISTED_MODEL_MESSAGES,
) -> List[Dict[str, object]]:
    normalized_messages = [dict(item) for item in messages if isinstance(item, dict)]
    recent_messages = normalized_messages[-max(1, max_messages) :]
    return [_sanitize_model_message_for_storage(item) for item in recent_messages]


def _sanitize_model_message_for_storage(message: Dict[str, object]) -> Dict[str, object]:
    sanitized: Dict[str, object] = {}
    role = str(message.get("role", "")).strip()
    if role:
        sanitized["role"] = role
    for key in ("name", "tool_call_id"):
        value = str(message.get(key, "")).strip()
        if value:
            sanitized[key] = value
    sanitized["content"] = _sanitize_message_content_for_storage(message.get("content", ""))
    return sanitized


def _sanitize_message_content_for_storage(content: object) -> object:
    if isinstance(content, str):
        return content[:MAX_PERSISTED_MESSAGE_TEXT]
    if isinstance(content, list):
        text_parts: List[str] = []
        image_seen = False
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).strip().lower()
            if item_type in {"text", "input_text"}:
                text = str(item.get("text", "")).strip()
                if text:
                    text_parts.append(text)
                continue
            if item_type in {"image_url", "input_image"}:
                if not image_seen:
                    text_parts.append(_IMAGE_ATTACHMENT_NOTE)
                    image_seen = True
                continue
            text = str(item.get("text", "")).strip()
            if text:
                text_parts.append(text)
        return "\n\n".join(part for part in text_parts if part)[:MAX_PERSISTED_MESSAGE_TEXT]
    if isinstance(content, dict):
        normalized = str(content.get("text") or content.get("content") or "").strip()
        if normalized:
            return normalized[:MAX_PERSISTED_MESSAGE_TEXT]
    return str(content)[:MAX_PERSISTED_MESSAGE_TEXT]


def derive_thread_title(
    display_messages: List[Dict[str, str]],
    project_dir: str = "",
    fallback: str = DEFAULT_THREAD_TITLE,
) -> str:
    normalized_project = str(project_dir or "").strip()
    if normalized_project:
        return Path(normalized_project).name or fallback
    for item in display_messages:
        if str(item.get("role", "")).strip().lower() != "user":
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        first_line = text.splitlines()[0].strip()
        if not first_line:
            continue
        compact = " ".join(first_line.split())
        return compact[:36] + ("..." if len(compact) > 36 else "")
    return fallback


def summarize_thread(thread: DesktopChatThread) -> str:
    project_dir = str(thread.project_dir or "").strip()
    if project_dir:
        return Path(project_dir).name or "当前工程"
    if thread.display_messages:
        return f"{len(thread.display_messages)} 条消息"
    return "未绑定工程"


def derive_thread_status(thread: DesktopChatThread) -> tuple[str, str]:
    proposal_state = dict(thread.proposal_state or {})
    engineering_state = ThreadEngineeringState.from_dict(thread.engineering_state).to_dict()
    proposal_status_text = str(proposal_state.get("proposal_status_text", "")).strip()
    proposal_status_kind = str(proposal_state.get("proposal_status_kind", "")).strip() or "neutral"
    if bool(proposal_state.get("confirm_enabled", False)) or bool(proposal_state.get("revise_enabled", False)):
        return proposal_status_text or "待确认", proposal_status_kind if proposal_status_text else "warning"
    engineering_status_text = str(engineering_state.get("status_text", "")).strip()
    engineering_status_kind = str(engineering_state.get("status_kind", "")).strip() or "neutral"
    if engineering_status_text:
        return engineering_status_text, engineering_status_kind
    if proposal_status_text and proposal_status_text not in {"等待需求"}:
        return proposal_status_text, proposal_status_kind
    if thread.project_dir and thread.display_messages:
        return "进行中", "success"
    if thread.project_dir:
        return "已绑定工程", "neutral"
    if thread.display_messages:
        return "对话中", "neutral"
    return "空线程", "neutral"


def format_thread_list_label(thread: DesktopChatThread) -> str:
    status_text, _ = derive_thread_status(thread)
    return f"{thread.title}\n{status_text} | {summarize_thread(thread)}\n{format_thread_timestamp(thread)}"


def format_thread_timestamp(thread: DesktopChatThread) -> str:
    raw = str(thread.updated_at or "").strip()
    if not raw:
        return "未记录时间"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    return parsed.strftime("%m-%d %H:%M")


def build_thread_context_summary(thread: DesktopChatThread) -> str:
    lines: List[str] = []
    project_dir = str(thread.project_dir or "").strip()
    if project_dir:
        lines.append(f"当前工程: {Path(project_dir).name}")

    status_text, _ = derive_thread_status(thread)
    lines.append(f"线程状态: {status_text}")

    proposal_state = dict(thread.proposal_state or {})
    engineering_state = ThreadEngineeringState.from_dict(thread.engineering_state).to_dict()
    proposal_status_text = str(proposal_state.get("proposal_status_text", "")).strip()
    if proposal_status_text and proposal_status_text not in {"等待需求"}:
        lines.append(f"提案状态: {proposal_status_text}")

    engineering_status_text = str(engineering_state.get("status_text", "")).strip()
    engineering_action = str(engineering_state.get("action", "")).strip()
    if engineering_status_text:
        lines.append(f"工程状态: {engineering_status_text}")
    if engineering_action:
        lines.append(f"最近动作: {engineering_action}")

    build_summary = [
        str(item).strip()
        for item in engineering_state.get("build_summary", [])
        if str(item).strip()
    ]
    if build_summary:
        lines.append("最近构建:")
        for item in build_summary[:2]:
            lines.append(f"- {item}")

    simulate_summary = str(engineering_state.get("simulate_summary", "")).strip()
    if simulate_summary:
        lines.append(f"最近仿真: {simulate_summary}")

    repair_count = int(engineering_state.get("repair_count", 0) or 0)
    if repair_count > 0:
        lines.append(f"自动修复: {repair_count} 次")

    request_payload = proposal_state.get("request_payload", {})
    if isinstance(request_payload, dict):
        target = request_payload.get("target", {})
        if isinstance(target, dict):
            chip = str(target.get("chip", "")).strip()
            board = str(target.get("board", "")).strip()
            if chip:
                lines.append(f"目标芯片: {chip}")
            if board:
                lines.append(f"目标板卡: {board}")

    plan_summary = proposal_state.get("plan_summary", {})
    if isinstance(plan_summary, dict):
        modules = plan_summary.get("modules", [])
        if isinstance(modules, list):
            module_names = []
            for item in modules:
                if not isinstance(item, dict):
                    continue
                name = str(
                    item.get("instance")
                    or item.get("name")
                    or item.get("kind")
                    or item.get("key")
                    or ""
                ).strip()
                if name:
                    module_names.append(name)
            if module_names:
                lines.append("当前模块: " + ", ".join(module_names[:6]))

    change_preview = proposal_state.get("change_preview", [])
    if isinstance(change_preview, list):
        normalized_changes = [str(item).strip() for item in change_preview if str(item).strip()]
        if normalized_changes:
            lines.append("待应用变更:")
            lines.extend(f"- {item}" for item in normalized_changes[:4])

    recent_user_messages = [
        " ".join(str(item.get("text", "")).strip().split())
        for item in thread.display_messages
        if str(item.get("role", "")).strip().lower() == "user" and str(item.get("text", "")).strip()
    ]
    if recent_user_messages:
        lines.append("最近用户意图:")
        for item in recent_user_messages[-3:]:
            lines.append(f"- {item[:120]}")

    recent_assistant_messages = [
        " ".join(str(item.get("text", "")).strip().split())
        for item in thread.display_messages
        if str(item.get("role", "")).strip().lower() == "assistant" and str(item.get("text", "")).strip()
    ]
    if recent_assistant_messages:
        lines.append("最近助手结论:")
        for item in recent_assistant_messages[-2:]:
            lines.append(f"- {item[:120]}")

    return "\n".join(lines).strip()


def format_thread_timeline(thread: DesktopChatThread, limit: int = 8) -> str:
    engineering_state = ThreadEngineeringState.from_dict(thread.engineering_state).to_dict()
    raw_items = engineering_state.get("timeline", [])
    if not isinstance(raw_items, list):
        return "当前线程还没有可展示的执行时间线。"

    normalized: List[Dict[str, str]] = []
    for item in raw_items[-max(1, limit) :]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "timestamp": str(item.get("timestamp", "")).strip(),
                "stage": str(item.get("stage", "")).strip(),
                "status": str(item.get("status", "")).strip(),
                "detail": str(item.get("detail", "")).strip(),
            }
        )

    if not normalized:
        return "当前线程还没有可展示的执行时间线。"

    lines: List[str] = []
    for item in normalized:
        parts = [part for part in [item["timestamp"], item["stage"], item["status"]] if part]
        header = " · ".join(parts)
        if item["detail"]:
            header = f"{header}\n{item['detail']}" if header else item["detail"]
        lines.append(header or "未命名步骤")
    return "\n\n".join(lines).strip()


def build_thread_followup_context(
    thread: DesktopChatThread,
    max_recent_messages: int = 6,
    exclude_latest_user_message: bool = False,
) -> str:
    display_messages = [
        {
            "role": str(item.get("role", "")).strip(),
            "text": str(item.get("text", "")),
        }
        for item in thread.display_messages
        if isinstance(item, dict)
    ]
    if (
        exclude_latest_user_message
        and display_messages
        and display_messages[-1]["role"].lower() == "user"
    ):
        display_messages = display_messages[:-1]

    if not (thread.project_dir.strip() or thread.proposal_state or display_messages):
        return ""

    summary_thread = replace(thread, display_messages=display_messages, summary_text="")
    summary_text = build_thread_context_summary(summary_thread).strip()
    recent_messages = display_messages[-max(1, max_recent_messages) :]

    lines: List[str] = []
    if summary_text:
        lines.extend(
            [
                "Existing desktop project thread summary:",
                summary_text,
            ]
        )
    if recent_messages:
        lines.append("Recent dialogue in this thread:")
        for item in recent_messages:
            text = " ".join(str(item.get("text", "")).strip().split())
            if not text:
                continue
            role = "User" if str(item.get("role", "")).strip().lower() == "user" else "Assistant"
            lines.append(f"- {role}: {text[:160]}")
    return "\n".join(lines).strip()


def _thread_sort_key(thread: DesktopChatThread) -> tuple[str, str]:
    return (str(thread.updated_at or "").strip(), str(thread.thread_id))
