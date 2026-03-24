from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class RetrievedChunk(TypedDict):
    content: str
    source: str
    score: float
    metadata: Dict[str, Any]


class STM32ProjectState(TypedDict, total=False):
    user_input: str
    thread_context: Optional[str]
    attachments: List[Dict[str, Any]]
    active_project_dir: Optional[str]

    retrieved_docs: List[RetrievedChunk]
    retrieval_filters: Dict[str, Any]

    request_payload: Optional[Dict[str, Any]]
    draft_raw_response: str
    draft_warnings: List[str]
    draft_errors: List[str]
    app_logic_raw_response: str
    app_logic_warnings: List[str]
    app_logic_errors: List[str]

    plan_result: Optional[Dict[str, Any]]
    project_ir: Optional[Dict[str, Any]]
    plan_warnings: List[str]
    review_kind: str
    negotiation_options: List[Dict[str, Any]]
    proposal_text: str
    change_preview: List[str]
    file_change_preview: List[Dict[str, Any]]

    is_approved: bool
    user_feedback: Optional[str]

    project_dir: str
    scaffold_result: Optional[Dict[str, Any]]
    driver_import_result: Optional[Dict[str, Any]]

    build_success: bool
    build_logs: Annotated[List[str], operator.add]
    build_result: Optional[Dict[str, Any]]
    simulate_result: Optional[Dict[str, Any]]
    evaluation_result: Optional[Dict[str, Any]]
    runtime_validation_passed: Optional[bool]

    repair_count: int
    repair_strategy: Optional[str]

    generation_phase: Optional[str]  # 'infrastructure' | 'app_logic' | None (legacy single-pass)

    warnings: List[str]
    errors: List[str]
