from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List
from uuid import uuid4
import warnings

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ..desktop.attachments import AttachmentDigest
from .nodes import (
    GraphRuntime,
    advance_phase_node,
    make_build_node,
    make_draft_node,
    make_draft_app_logic_node,
    make_evaluate_node,
    make_import_drivers_node,
    make_plan_node,
    make_repair_node,
    make_retrieve_node,
    make_scaffold_node,
    make_simulate_node,
    review_proposal_node,
    route_after_advance_phase,
    route_after_build,
    route_after_app_logic,
    route_after_evaluate,
    route_after_import_drivers,
    route_after_plan,
    route_after_repair,
    route_after_review,
    route_after_scaffold,
    route_after_simulate,
    route_after_validation,
    validate_request_node,
)
from .state import STM32ProjectState
from .sqlite_checkpointer import SQLiteCheckpointer, get_default_graph_checkpoints_path


@dataclass
class GraphStepResult:
    thread_id: str
    values: Dict[str, Any]
    next_nodes: tuple[str, ...]
    interrupts: List[Dict[str, Any]]
    raw_output: Dict[str, Any]


def build_project_graph(runtime: GraphRuntime, checkpointer: Any | None = None):
    graph = StateGraph(STM32ProjectState)
    graph.add_node("retrieve", make_retrieve_node(runtime))
    graph.add_node("draft", make_draft_node(runtime))
    graph.add_node("validate_request", validate_request_node)
    graph.add_node("plan", make_plan_node(runtime))
    graph.add_node("draft_app_logic", make_draft_app_logic_node(runtime))
    graph.add_node("review", review_proposal_node)
    graph.add_node("scaffold", make_scaffold_node(runtime))
    graph.add_node("import_drivers", make_import_drivers_node(runtime))
    graph.add_node("build", make_build_node(runtime))
    graph.add_node("simulate", make_simulate_node(runtime))
    graph.add_node("evaluate", make_evaluate_node(runtime))
    graph.add_node("repair", make_repair_node(runtime))
    graph.add_node("advance_phase", advance_phase_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "validate_request")
    graph.add_conditional_edges("validate_request", route_after_validation, {"plan": "plan", "end": END})
    graph.add_conditional_edges("plan", route_after_plan, {"draft_app_logic": "draft_app_logic", "end": END})
    graph.add_conditional_edges("draft_app_logic", route_after_app_logic, {"review": "review", "end": END})
    graph.add_conditional_edges("review", route_after_review, {"scaffold": "scaffold", "draft": "draft", "end": END})
    graph.add_conditional_edges(
        "scaffold",
        route_after_scaffold,
        {"import_drivers": "import_drivers", "end": END},
    )
    graph.add_conditional_edges(
        "import_drivers",
        route_after_import_drivers,
        {"build": "build", "end": END},
    )
    graph.add_conditional_edges(
        "build",
        lambda state: route_after_build(state, runtime),
        {"simulate": "simulate", "repair": "repair", "advance_phase": "advance_phase", "end": END},
    )
    graph.add_conditional_edges(
        "simulate",
        route_after_simulate,
        {"evaluate": "evaluate", "end": END},
    )
    graph.add_conditional_edges(
        "evaluate",
        lambda state: route_after_evaluate(state, runtime),
        {"repair": "repair", "end": END},
    )
    graph.add_conditional_edges(
        "repair",
        route_after_repair,
        {"build": "build", "scaffold": "scaffold", "draft": "draft", "end": END},
    )
    graph.add_conditional_edges(
        "advance_phase",
        route_after_advance_phase,
        {"draft_app_logic": "draft_app_logic"},
    )

    return graph.compile(checkpointer=checkpointer)


class STM32ProjectGraphSession:
    def __init__(self, runtime: GraphRuntime, checkpointer: Any | None = None):
        self.runtime = runtime
        self.checkpointer = checkpointer or _create_default_checkpointer(runtime.repo_root)
        self.app = build_project_graph(runtime, checkpointer=self.checkpointer)

    def start(
        self,
        user_input: str,
        attachments: Iterable[AttachmentDigest | Dict[str, Any]] | None = None,
        active_project_dir: str = "",
        thread_context: str = "",
        thread_id: str | None = None,
    ) -> GraphStepResult:
        resolved_thread_id = thread_id or uuid4().hex
        initial_state: STM32ProjectState = {
            "user_input": user_input,
            "thread_context": thread_context or "",
            "attachments": [_serialize_attachment(item) for item in attachments or []],
            "active_project_dir": active_project_dir or None,
            "retrieved_docs": [],
            "retrieval_filters": {},
            "request_payload": None,
            "draft_raw_response": "",
            "draft_warnings": [],
            "draft_errors": [],
            "app_logic_raw_response": "",
            "app_logic_warnings": [],
            "app_logic_errors": [],
            "project_ir": None,
            "plan_result": None,
            "plan_warnings": [],
            "review_kind": "proposal",
            "negotiation_options": [],
            "proposal_text": "",
            "change_preview": [],
            "file_change_preview": [],
            "is_approved": False,
            "user_feedback": None,
            "project_dir": active_project_dir or "",
            "build_success": False,
            "build_logs": [],
            "simulate_result": None,
            "evaluation_result": None,
            "runtime_validation_passed": None,
            "repair_count": 0,
            "generation_phase": None,
            "warnings": [],
            "errors": [],
        }
        config = _thread_config(resolved_thread_id)
        output = self.app.invoke(initial_state, config)
        return self._snapshot_result(resolved_thread_id, output)

    def resume(self, thread_id: str, approved: bool, user_feedback: str = "") -> GraphStepResult:
        config = _thread_config(thread_id)
        output = self.app.invoke(
            Command(
                resume={
                    "approved": approved,
                    "user_feedback": user_feedback,
                }
            ),
            config,
        )
        return self._snapshot_result(thread_id, output)

    def get_state(self, thread_id: str) -> GraphStepResult:
        return self._snapshot_result(thread_id, {})

    def _snapshot_result(self, thread_id: str, raw_output: Dict[str, Any]) -> GraphStepResult:
        snapshot = self.app.get_state(_thread_config(thread_id))
        interrupts = [
            {
                "id": getattr(item, "id", ""),
                "value": getattr(item, "value", None),
            }
            for item in snapshot.interrupts
        ]
        return GraphStepResult(
            thread_id=thread_id,
            values=dict(snapshot.values),
            next_nodes=tuple(snapshot.next),
            interrupts=interrupts,
            raw_output=dict(raw_output),
        )


def _thread_config(thread_id: str) -> Dict[str, Dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _serialize_attachment(item: AttachmentDigest | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(item, AttachmentDigest):
        return item.to_state_dict()
    if isinstance(item, dict):
        return dict(item)
    raise TypeError(f"Unsupported attachment type: {type(item)!r}")


def _create_default_checkpointer(repo_root: str | Path) -> Any:
    checkpoint_path = get_default_graph_checkpoints_path(repo_root)
    try:
        return SQLiteCheckpointer(checkpoint_path)
    except Exception as exc:  # pragma: no cover - fallback safety
        warnings.warn(
            f"Falling back to in-memory LangGraph checkpoints because SQLite initialization failed: {exc}",
            RuntimeWarning,
        )
        return InMemorySaver()
