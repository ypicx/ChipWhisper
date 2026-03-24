from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


def _normalize_text_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


@dataclass
class ThreadTimelineEvent:
    timestamp: str = ""
    stage: str = ""
    status: str = ""
    detail: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, object] | None) -> "ThreadTimelineEvent":
        data = dict(payload or {})
        return cls(
            timestamp=str(data.get("timestamp", "")).strip(),
            stage=str(data.get("stage", "")).strip(),
            status=str(data.get("status", "")).strip(),
            detail=str(data.get("detail", "")).strip(),
        )

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {}
        if self.timestamp:
            payload["timestamp"] = self.timestamp
        if self.stage:
            payload["stage"] = self.stage
        if self.status:
            payload["status"] = self.status
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class ThreadEngineeringState:
    status_text: str = ""
    status_kind: str = "neutral"
    action: str = ""
    project_dir: str = ""
    build_summary: List[str] = field(default_factory=list)
    build_errors: List[str] = field(default_factory=list)
    build_log_path: str = ""
    hex_file: str = ""
    simulate_summary: str = ""
    simulate_passed: bool | None = None
    renode_log_path: str = ""
    uart_capture_path: str = ""
    repair_count: int = 0
    warning_excerpt: List[str] = field(default_factory=list)
    error_excerpt: List[str] = field(default_factory=list)
    plan_module_count: int = 0
    timeline: List[ThreadTimelineEvent] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict[str, object] | None) -> "ThreadEngineeringState":
        data = dict(payload or {})
        raw_timeline = data.get("timeline", [])
        timeline = []
        if isinstance(raw_timeline, list):
            timeline = [
                ThreadTimelineEvent.from_dict(item)
                for item in raw_timeline
                if isinstance(item, dict)
            ]
        simulate_passed = data.get("simulate_passed")
        if simulate_passed in {True, False}:
            normalized_simulate_passed = bool(simulate_passed)
        else:
            normalized_simulate_passed = None
        return cls(
            status_text=str(data.get("status_text", "")).strip(),
            status_kind=str(data.get("status_kind", "") or "neutral").strip() or "neutral",
            action=str(data.get("action", "")).strip(),
            project_dir=str(data.get("project_dir", "")).strip(),
            build_summary=_normalize_text_list(data.get("build_summary")),
            build_errors=_normalize_text_list(data.get("build_errors")),
            build_log_path=str(data.get("build_log_path", "")).strip(),
            hex_file=str(data.get("hex_file", "")).strip(),
            simulate_summary=str(data.get("simulate_summary", "")).strip(),
            simulate_passed=normalized_simulate_passed,
            renode_log_path=str(data.get("renode_log_path", "")).strip(),
            uart_capture_path=str(data.get("uart_capture_path", "")).strip(),
            repair_count=int(data.get("repair_count", 0) or 0),
            warning_excerpt=_normalize_text_list(data.get("warning_excerpt")),
            error_excerpt=_normalize_text_list(data.get("error_excerpt")),
            plan_module_count=int(data.get("plan_module_count", 0) or 0),
            timeline=timeline,
        )

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {}
        if self.status_text:
            payload["status_text"] = self.status_text
        if self.status_kind and self.status_kind != "neutral":
            payload["status_kind"] = self.status_kind
        if self.action:
            payload["action"] = self.action
        if self.project_dir:
            payload["project_dir"] = self.project_dir
        if self.build_summary:
            payload["build_summary"] = list(self.build_summary)
        if self.build_errors:
            payload["build_errors"] = list(self.build_errors)
        if self.build_log_path:
            payload["build_log_path"] = self.build_log_path
        if self.hex_file:
            payload["hex_file"] = self.hex_file
        if self.simulate_summary:
            payload["simulate_summary"] = self.simulate_summary
        if self.simulate_passed in {True, False}:
            payload["simulate_passed"] = self.simulate_passed
        if self.renode_log_path:
            payload["renode_log_path"] = self.renode_log_path
        if self.uart_capture_path:
            payload["uart_capture_path"] = self.uart_capture_path
        if self.repair_count:
            payload["repair_count"] = self.repair_count
        if self.warning_excerpt:
            payload["warning_excerpt"] = list(self.warning_excerpt)
        if self.error_excerpt:
            payload["error_excerpt"] = list(self.error_excerpt)
        if self.plan_module_count:
            payload["plan_module_count"] = self.plan_module_count
        timeline = [item.to_dict() for item in self.timeline if item.to_dict()]
        if timeline:
            payload["timeline"] = timeline
        return payload

    def merge_updates(self, **kwargs: object) -> "ThreadEngineeringState":
        payload = self.to_dict()
        for key, value in kwargs.items():
            if value in (None, "", [], {}):
                payload.pop(key, None)
            else:
                payload[key] = value
        return ThreadEngineeringState.from_dict(payload)

    def append_timeline_event(
        self,
        stage: str,
        status: str,
        detail: str = "",
        timestamp: str = "",
        limit: int = 12,
    ) -> "ThreadEngineeringState":
        normalized = list(self.timeline)
        normalized.append(
            ThreadTimelineEvent(
                timestamp=str(timestamp or "").strip(),
                stage=str(stage or "").strip(),
                status=str(status or "").strip(),
                detail=str(detail or "").strip(),
            )
        )
        payload = self.to_dict()
        payload["timeline"] = [item.to_dict() for item in normalized[-max(1, limit):]]
        return ThreadEngineeringState.from_dict(payload)
