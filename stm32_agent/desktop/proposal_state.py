from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


def _normalize_dict(value: object) -> Dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_dict_list(value: object) -> List[Dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _normalize_str_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


@dataclass
class PendingProposalState:
    proposal_text: str = ""
    proposal_status_text: str = ""
    proposal_status_kind: str = "neutral"
    proposal_feedback: str = ""
    request_payload: Dict[str, object] = field(default_factory=dict)
    plan_summary: Dict[str, object] = field(default_factory=dict)
    review_kind: str = "proposal"
    negotiation_options: List[Dict[str, object]] = field(default_factory=list)
    change_preview: List[str] = field(default_factory=list)
    file_change_preview: List[Dict[str, object]] = field(default_factory=list)
    output_dir: str = ""
    mode: str = "create"
    confirm_enabled: bool = False
    revise_enabled: bool = False
    clear_enabled: bool = False
    confirm_text: str = ""
    clear_text: str = ""
    graph_thread_id: str = ""
    graph_profile_id: str = ""
    graph_runtime_validation_enabled: bool | None = None

    @classmethod
    def from_dict(cls, payload: Dict[str, object] | None) -> "PendingProposalState":
        data = dict(payload or {})
        graph_runtime_validation_enabled = data.get("graph_runtime_validation_enabled")
        if graph_runtime_validation_enabled is None:
            normalized_runtime_validation = None
        else:
            normalized_runtime_validation = bool(graph_runtime_validation_enabled)
        return cls(
            proposal_text=str(data.get("proposal_text", "")),
            proposal_status_text=str(data.get("proposal_status_text", "")),
            proposal_status_kind=str(data.get("proposal_status_kind", "") or "neutral").strip() or "neutral",
            proposal_feedback=str(data.get("proposal_feedback", "")),
            request_payload=_normalize_dict(data.get("request_payload")),
            plan_summary=_normalize_dict(data.get("plan_summary")),
            review_kind=str(data.get("review_kind", "proposal") or "proposal").strip() or "proposal",
            negotiation_options=_normalize_dict_list(data.get("negotiation_options")),
            change_preview=_normalize_str_list(data.get("change_preview")),
            file_change_preview=_normalize_dict_list(data.get("file_change_preview")),
            output_dir=str(data.get("output_dir", "")).strip(),
            mode=str(data.get("mode", "create") or "create").strip() or "create",
            confirm_enabled=bool(data.get("confirm_enabled", False)),
            revise_enabled=bool(data.get("revise_enabled", False)),
            clear_enabled=bool(data.get("clear_enabled", False)),
            confirm_text=str(data.get("confirm_text", "")),
            clear_text=str(data.get("clear_text", "")),
            graph_thread_id=str(data.get("graph_thread_id", "")).strip(),
            graph_profile_id=str(data.get("graph_profile_id", "")).strip(),
            graph_runtime_validation_enabled=normalized_runtime_validation,
        )

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "proposal_text": self.proposal_text,
            "proposal_status_text": self.proposal_status_text,
            "proposal_status_kind": self.proposal_status_kind,
            "proposal_feedback": self.proposal_feedback,
            "request_payload": dict(self.request_payload),
            "plan_summary": dict(self.plan_summary),
            "review_kind": self.review_kind,
            "negotiation_options": [dict(item) for item in self.negotiation_options],
            "change_preview": list(self.change_preview),
            "file_change_preview": [dict(item) for item in self.file_change_preview],
            "output_dir": self.output_dir,
            "mode": self.mode,
            "confirm_enabled": self.confirm_enabled,
            "revise_enabled": self.revise_enabled,
            "clear_enabled": self.clear_enabled,
            "confirm_text": self.confirm_text,
            "clear_text": self.clear_text,
            "graph_thread_id": self.graph_thread_id,
            "graph_profile_id": self.graph_profile_id,
        }
        if self.graph_runtime_validation_enabled is not None:
            payload["graph_runtime_validation_enabled"] = self.graph_runtime_validation_enabled
        return payload

    def preferred_feedback(self) -> str:
        if self.proposal_feedback.strip():
            return self.proposal_feedback
        if self.review_kind == "negotiate" and self.negotiation_options:
            return str(self.negotiation_options[0].get("feedback", "")).strip()
        return ""
