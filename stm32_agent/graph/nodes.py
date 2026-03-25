from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from langgraph.types import interrupt

from ..app_logic_drafter import draft_app_logic_for_plan, merge_generated_app_logic
from ..builder import ProjectBuildResult, build_project
from ..cube_repository import import_cube_drivers
from ..desktop.attachments import AttachmentDigest
from ..desktop.request_bridge import draft_request_json
from ..extension_packs import load_catalog, match_scenarios
from ..keil_builder import read_text_with_fallback
from ..keil_generator import ScaffoldResult, preview_project_file_changes, scaffold_from_request
from ..llm_config import LlmProfile
from ..planner import plan_request
from ..renode_runner import (
    derive_runtime_expectation_payload as _shared_derive_runtime_expectation_payload,
    derive_runtime_uart_expectations as _shared_derive_runtime_uart_expectations,
    ensure_runtime_expectations as _shared_ensure_runtime_expectations,
    run_renode_project,
)
from .repair import build_default_repair_fn
from .retrieval import render_retrieved_context, retrieve_relevant_chunks
from .state import STM32ProjectState


@dataclass(frozen=True)
class GraphRuntime:
    profile: LlmProfile
    repo_root: Path
    packs_dir: str | Path | None = None
    completion_fn: Callable[[LlmProfile, List[dict[str, object]]], str] | None = None
    scaffold_fn: Callable[..., ScaffoldResult] = scaffold_from_request
    build_fn: Callable[..., ProjectBuildResult] = build_project
    simulate_fn: Callable[..., Any] = run_renode_project
    import_drivers_fn: Callable[..., Any] = import_cube_drivers
    repair_fn: Callable[[STM32ProjectState], Dict[str, object]] | None = None
    max_repairs: int = 2
    generate_makefile: bool = False
    enable_runtime_validation: bool = False
    runtime_validation_seconds: float = 5.0


def make_retrieve_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        chunks, filters = retrieve_relevant_chunks(
            state.get("user_input", ""),
            runtime.repo_root,
            packs_dir=runtime.packs_dir,
            active_project_dir=state.get("active_project_dir") or "",
        )
        return {
            "retrieved_docs": chunks,
            "retrieval_filters": filters,
        }

    return _node


def make_draft_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        attachments = _normalize_attachments(state.get("attachments", []))
        retrieved_context = render_retrieved_context(state.get("retrieved_docs", []))
        draft = draft_request_json(
            runtime.profile,
            state.get("user_input", ""),
            packs_dir=runtime.packs_dir,
            active_project_dir=state.get("active_project_dir") or "",
            attachments=attachments,
            retrieved_context=retrieved_context,
            thread_context=state.get("thread_context", "") or "",
            revision_feedback=state.get("user_feedback") or "",
            **({"completion_fn": runtime.completion_fn} if runtime.completion_fn is not None else {}),
        )
        update: Dict[str, object] = {
            "draft_raw_response": draft.raw_response,
            "draft_warnings": list(draft.warnings),
            "draft_errors": list(draft.errors),
            "warnings": list(draft.warnings),
            "errors": list(draft.errors),
            "user_feedback": None,
        }
        if draft.ok:
            update["request_payload"] = draft.request_payload
        return update

    return _node


def validate_request_node(state: STM32ProjectState) -> Dict[str, object]:
    payload = state.get("request_payload") or {}
    warnings: List[str] = []
    errors: List[str] = []
    if not payload:
        errors.append("LangGraph draft stage did not produce a request_payload.")
    modules = payload.get("modules", [])
    if not isinstance(modules, list):
        errors.append("request_payload.modules must be a list.")
    if isinstance(modules, list) and not modules:
        warnings.append("Current request_payload has no modules; planner may only generate a very small scaffold.")
    if payload and not str(payload.get("chip", "")).strip():
        warnings.append("request_payload did not contain a chip; planner will likely reject the request.")
    return {
        "warnings": warnings,
        "errors": errors,
    }


def make_plan_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        payload = state.get("request_payload") or {}
        plan = plan_request(payload, packs_dir=runtime.packs_dir)
        output_dir = state.get("active_project_dir") or str(_make_output_dir(runtime.repo_root, state.get("user_input", ""), payload))
        combined_warnings = _merge_messages(state.get("warnings", []), plan.warnings)
        update: Dict[str, object] = {
            "plan_result": plan.to_dict(),
            "project_ir": plan.project_ir,
            "plan_warnings": list(plan.warnings),
            "project_dir": output_dir,
            "review_kind": "proposal",
            "negotiation_options": [],
            "warnings": combined_warnings,
            "errors": list(plan.errors),
        }
        if not plan.feasible:
            negotiation_options = _build_negotiation_options(payload, plan)
            update["review_kind"] = "negotiate" if negotiation_options else "proposal"
            update["negotiation_options"] = negotiation_options
            update["proposal_text"] = (
                _render_negotiation_message(plan, negotiation_options)
                if negotiation_options
                else _render_plan_failure_message(plan)
            )
            update["change_preview"] = []
            update["file_change_preview"] = []
            return update
        return update

    return _node


def make_draft_app_logic_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        payload = dict(state.get("request_payload") or {})
        working_payload = payload
        extra_warnings: List[str] = []

        initial_plan = plan_request(working_payload, packs_dir=runtime.packs_dir)
        if initial_plan.feasible:
            # Collect app_logic_snippets from catalog for planned modules
            catalog = load_catalog(runtime.packs_dir)
            module_snippets: Dict[str, Dict[str, Any]] = {}
            for mod_spec in catalog.modules.values():
                if mod_spec.app_logic_snippets:
                    module_snippets[mod_spec.key] = dict(mod_spec.app_logic_snippets)

            # Match scenario templates
            matched = match_scenarios(state.get("user_input", ""), runtime.packs_dir, max_results=2)
            matched_scenario_dicts = [s.to_dict() for s in matched] if matched else None

            draft_result = draft_app_logic_for_plan(
                runtime.profile,
                state.get("user_input", ""),
                working_payload,
                initial_plan,
                retrieved_context=render_retrieved_context(state.get("retrieved_docs", [])),
                thread_context=state.get("thread_context", "") or "",
                plan_warnings=initial_plan.warnings,
                module_snippets=module_snippets if module_snippets else None,
                matched_scenarios=matched_scenario_dicts,
                **({"completion_fn": runtime.completion_fn} if runtime.completion_fn is not None else {}),
            )
            extra_warnings.extend(draft_result.warnings)
            if draft_result.ok and (
                any(draft_result.app_logic.values()) or draft_result.generated_files or draft_result.app_logic_ir
            ):
                working_payload = merge_generated_app_logic(
                    working_payload,
                    draft_result.app_logic,
                    generated_files=draft_result.generated_files,
                    app_logic_ir=draft_result.app_logic_ir,
                )
            elif draft_result.errors:
                extra_warnings.extend(f"App logic draft skipped: {item}" for item in draft_result.errors)
        else:
            draft_result = None

        plan = plan_request(working_payload, packs_dir=runtime.packs_dir)
        output_dir = state.get("project_dir") or state.get("active_project_dir") or str(
            _make_output_dir(runtime.repo_root, state.get("user_input", ""), working_payload)
        )
        combined_warnings = _merge_messages(state.get("warnings", []), extra_warnings, plan.warnings)
        update: Dict[str, object] = {
            "request_payload": working_payload,
            "plan_result": plan.to_dict(),
            "project_ir": plan.project_ir,
            "plan_warnings": list(plan.warnings),
            "project_dir": output_dir,
            "review_kind": "proposal",
            "negotiation_options": [],
            "app_logic_raw_response": draft_result.raw_response if draft_result is not None else "",
            "app_logic_warnings": list(extra_warnings),
            "app_logic_errors": list(draft_result.errors) if draft_result is not None else [],
            "warnings": combined_warnings,
            "errors": list(plan.errors),
        }
        if not plan.feasible:
            negotiation_options = _build_negotiation_options(working_payload, plan)
            update["review_kind"] = "negotiate" if negotiation_options else "proposal"
            update["negotiation_options"] = negotiation_options
            update["proposal_text"] = (
                _render_negotiation_message(plan, negotiation_options)
                if negotiation_options
                else _render_plan_failure_message(plan)
            )
            update["change_preview"] = []
            update["file_change_preview"] = []
            return update

        registry = load_catalog(runtime.packs_dir)
        chip = registry.chips[plan.chip]
        try:
            file_changes = [item.to_dict() for item in preview_project_file_changes(plan, output_dir, chip)]
        except ValueError as exc:
            update["proposal_text"] = _render_failure_message(
                "The current chip family is not supported by the code generator yet.",
                [str(exc)],
                combined_warnings,
            )
            update["change_preview"] = []
            update["file_change_preview"] = []
            update["errors"] = [str(exc)]
            return update
        update["proposal_text"] = _render_proposal_message(
            working_payload,
            plan,
            output_dir,
            _resolve_mode(state),
            combined_warnings,
            file_changes,
        )
        update["change_preview"] = _build_change_preview_lines(
            working_payload,
            plan,
            output_dir,
            _resolve_mode(state),
            file_changes,
        )
        update["file_change_preview"] = file_changes
        return update

    return _node


def review_proposal_node(state: STM32ProjectState) -> Dict[str, object]:
    response = interrupt(
        {
            "review_kind": state.get("review_kind", "proposal"),
            "proposal_text": state.get("proposal_text", ""),
            "change_preview": list(state.get("change_preview", [])),
            "file_change_preview": list(state.get("file_change_preview", [])),
            "negotiation_options": list(state.get("negotiation_options", [])),
            "warnings": list(state.get("warnings", [])),
            "project_dir": state.get("project_dir", ""),
        }
    )
    approved = False
    feedback = ""
    if isinstance(response, dict):
        approved = bool(response.get("approved", False))
        feedback = str(response.get("user_feedback", "") or "").strip()
    else:
        approved = bool(response)
    return {
        "is_approved": approved,
        "user_feedback": feedback or None,
    }


def make_scaffold_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        payload = state.get("request_payload") or {}
        output_dir = state.get("project_dir") or state.get("active_project_dir") or str(
            _make_output_dir(runtime.repo_root, state.get("user_input", ""), payload)
        )
        scaffold = runtime.scaffold_fn(
            payload,
            output_dir,
            packs_dir=runtime.packs_dir,
            generate_makefile=runtime.generate_makefile,
        )
        update: Dict[str, object] = {
            "scaffold_result": scaffold.to_dict(),
            "project_dir": scaffold.project_dir or output_dir,
            "warnings": list(scaffold.warnings),
            "errors": list(scaffold.errors),
        }
        return update

    return _node


def make_import_drivers_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        project_ir = state.get("project_ir") or {}
        target = project_ir.get("target", {}) if isinstance(project_ir, dict) else {}
        family = str(target.get("family", "")).strip() or _infer_family_from_payload(state.get("request_payload") or {})
        result = runtime.import_drivers_fn(state.get("project_dir", ""), family)
        update: Dict[str, object] = {
            "driver_import_result": result.to_dict(),
            "warnings": list(result.warnings),
            "errors": list(result.errors),
        }
        return update

    return _node


def make_build_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        result = runtime.build_fn(state.get("project_dir", ""))
        build_logs = _collect_build_logs(result)
        update: Dict[str, object] = {
            "build_success": bool(result.built),
            "build_result": result.to_dict(),
            "build_logs": build_logs,
            "warnings": list(result.warnings),
            "errors": list(result.errors),
        }
        return update

    return _node


def make_simulate_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        project_dir = str(state.get("project_dir", "") or "").strip()
        inherited_warnings = list(state.get("warnings", []))
        if not project_dir:
            result = {
                "ready": False,
                "ran": False,
                "project_dir": "",
                "errors": ["No project_dir was available for Renode validation."],
                "warnings": [],
            }
            return {
                "simulate_result": result,
                "warnings": _merge_messages(inherited_warnings, result["errors"]),
            }

        expectation_warnings = _ensure_runtime_expectations(
            Path(project_dir),
            state.get("request_payload") or {},
            state.get("project_ir") or {},
        )
        result = runtime.simulate_fn(project_dir, run_seconds=runtime.runtime_validation_seconds)
        result_dict = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        return {
            "simulate_result": result_dict,
            "warnings": _merge_messages(
                inherited_warnings,
                expectation_warnings,
                list(result_dict.get("warnings", [])),
            ),
        }

    return _node


def make_evaluate_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        evaluation = evaluate_runtime_validation(state.get("simulate_result") or {})
        return {
            "evaluation_result": evaluation,
            "runtime_validation_passed": evaluation.get("passed"),
            "warnings": _merge_messages(state.get("warnings", []), list(evaluation.get("warnings", []))),
        }

    return _node


def make_repair_node(runtime: GraphRuntime):
    def _node(state: STM32ProjectState) -> Dict[str, object]:
        repair_fn = runtime.repair_fn or build_default_repair_fn(
            runtime.profile,
            completion_fn=runtime.completion_fn,
        )
        update = dict(repair_fn(state))

        update["repair_count"] = int(state.get("repair_count", 0)) + 1
        return update

    return _node


def route_after_validation(state: STM32ProjectState) -> str:
    if state.get("request_payload"):
        return "plan"
    return "end"


def route_after_plan(state: STM32ProjectState) -> str:
    if state.get("project_ir") and not state.get("errors"):
        return "draft_app_logic"
    if state.get("request_payload") and state.get("review_kind") == "negotiate":
        return "review"
    return "end"


def route_after_app_logic(state: STM32ProjectState) -> str:
    phase = str(state.get("generation_phase", "") or "").strip().lower()
    if phase == "infrastructure":
        # Infrastructure phase: skip app logic review, go straight to scaffold
        if state.get("project_ir") and not state.get("errors"):
            return "review"
        return "end"
    if state.get("project_ir") and not state.get("errors"):
        return "review"
    return "end"


def route_after_review(state: STM32ProjectState) -> str:
    review_kind = str(state.get("review_kind", "proposal") or "proposal").strip().lower()
    feedback = str(state.get("user_feedback", "") or "").strip()
    if review_kind == "negotiate":
        if feedback:
            return "draft"
        return "end"
    if state.get("is_approved"):
        return "scaffold"
    if feedback:
        return "draft"
    return "end"


def route_after_scaffold(state: STM32ProjectState) -> str:
    scaffold_result = state.get("scaffold_result") or {}
    if scaffold_result and scaffold_result.get("feasible") and not state.get("errors"):
        return "import_drivers"
    return "end"


def route_after_import_drivers(state: STM32ProjectState) -> str:
    result = state.get("driver_import_result") or {}
    if result and result.get("imported") and not state.get("errors"):
        return "build"
    return "end"


def route_after_build(state: STM32ProjectState, runtime: GraphRuntime) -> str:
    if state.get("build_success"):
        phase = str(state.get("generation_phase", "") or "").strip().lower()
        if phase == "infrastructure":
            # Infrastructure compiled OK → advance to app_logic phase
            return "advance_phase"
        if runtime.enable_runtime_validation:
            return "simulate"
        return "end"
    if int(state.get("repair_count", 0)) >= runtime.max_repairs:
        return "end"
    return "repair"


def route_after_simulate(state: STM32ProjectState) -> str:
    if state.get("simulate_result"):
        return "evaluate"
    return "end"


def route_after_evaluate(state: STM32ProjectState, runtime: GraphRuntime) -> str:
    if state.get("runtime_validation_passed") is True:
        return "end"
    if int(state.get("repair_count", 0)) >= runtime.max_repairs:
        return "end"
    return "repair"


def route_after_repair(state: STM32ProjectState) -> str:
    strategy = str(state.get("repair_strategy", "") or "").strip().lower()
    if strategy == "retry_build":
        return "build"
    if strategy == "regenerate":
        return "scaffold"
    if strategy == "replan":
        return "draft"
    return "end"


def advance_phase_node(state: STM32ProjectState) -> Dict[str, object]:
    """Transition from infrastructure phase to app_logic phase.

    After infrastructure builds successfully, this node resets build state
    and advances the generation_phase so the next iteration generates
    full application logic on top of the verified infrastructure.
    """
    return {
        "generation_phase": "app_logic",
        "build_success": False,
        "build_logs": [],
        "repair_count": 0,
        "warnings": ["Infrastructure build succeeded. Advancing to app_logic phase."],
    }


def route_after_advance_phase(state: STM32ProjectState) -> str:
    """After advancing phase, re-enter the draft_app_logic node."""
    return "draft_app_logic"


def _normalize_attachments(raw_items: List[object]) -> List[AttachmentDigest]:
    attachments: List[AttachmentDigest] = []
    for item in raw_items:
        if isinstance(item, AttachmentDigest):
            attachments.append(item)
            continue
        if isinstance(item, dict):
            attachments.append(AttachmentDigest.from_state_dict(item))
    return attachments


def _collect_build_logs(result: ProjectBuildResult) -> List[str]:
    lines: List[str] = []
    if result.summary_lines:
        lines.extend(str(item) for item in result.summary_lines if str(item).strip())
    build_log_path = str(result.build_log_path).strip()
    if build_log_path:
        path = Path(build_log_path)
        if path.exists():
            try:
                text = read_text_with_fallback(path).strip()
                if text:
                    lines.append(text)
            except OSError:
                pass
    return lines


def _merge_messages(*groups: List[str]) -> List[str]:
    merged: List[str] = []
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text and text not in merged:
                merged.append(text)
    return merged


def _resolve_mode(state: STM32ProjectState) -> str:
    return "modify" if str(state.get("active_project_dir", "") or "").strip() else "create"


def _infer_family_from_payload(payload: Dict[str, object]) -> str:
    chip_name = str(payload.get("chip", "")).strip().upper()
    if chip_name.startswith("STM32G4"):
        return "STM32G4"
    return "STM32F1"


def _make_output_dir(repo_root: Path, user_prompt: str, request_payload: Dict[str, object]) -> Path:
    root = repo_root / "out"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(user_prompt)
    modules = request_payload.get("modules", [])
    first_kind = ""
    if isinstance(modules, list):
        for item in modules:
            if isinstance(item, dict):
                first_kind = str(item.get("kind", "")).strip()
                if first_kind:
                    break
    pieces = ["langgraph", slug]
    if first_kind:
        pieces.append(first_kind)
    pieces.append(timestamp)
    return root / "_".join(part for part in pieces if part)


def _slugify(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    if not words:
        return "task"
    return ("_".join(words[:4]))[:32].strip("_") or "task"


def _ensure_runtime_expectations(
    project_dir: Path,
    request_payload: Dict[str, object],
    project_ir: Dict[str, object],
) -> List[str]:
    _payload, warnings = _shared_ensure_runtime_expectations(
        project_dir,
        request_payload=request_payload,
        project_ir=project_ir,
    )
    return warnings


def _derive_runtime_expectation_payload(
    request_payload: Dict[str, object],
    project_ir: Dict[str, object],
) -> Dict[str, object]:
    return _shared_derive_runtime_expectation_payload(
        request_payload=request_payload,
        project_ir=project_ir,
    )


def _derive_runtime_uart_expectations(
    request_payload: Dict[str, object],
    project_ir: Dict[str, object],
) -> List[str]:
    return _shared_derive_runtime_uart_expectations(
        request_payload=request_payload,
        project_ir=project_ir,
    )


def evaluate_runtime_validation(simulate_result: Dict[str, object]) -> Dict[str, object]:
    warnings: List[str] = []
    reasons: List[str] = []
    if bool(simulate_result.get("timed_out", False)):
        warnings.append("Renode reached the validation time window and was terminated after collecting output.")

    if not simulate_result:
        return {
            "status": "skipped",
            "passed": False,
            "mode": "skipped",
            "summary": "Runtime validation did not run.",
            "reasons": ["No Renode simulation result was produced."],
            "warnings": warnings,
        }

    if not bool(simulate_result.get("ready", True)):
        reasons.extend(str(item) for item in simulate_result.get("errors", []) if str(item).strip())
        return {
            "status": "fail",
            "passed": False,
            "mode": "startup_failure",
            "summary": "Renode validation could not start because the simulation environment was not ready.",
            "reasons": reasons or ["Renode validation was not ready."],
            "warnings": warnings,
        }

    validation_passed = simulate_result.get("validation_passed")
    validation_details = simulate_result.get("validation_details", {})
    checks = validation_details.get("checks", {}) if isinstance(validation_details, dict) else {}
    if validation_passed is True:
        matched = [str(item) for item in simulate_result.get("matched_uart_contains", []) if str(item).strip()]
        if matched:
            reasons.append("Matched: " + "; ".join(matched[:4]))
        reasons.extend(_summarize_runtime_validation_checks(checks, passed_only=True))
        mode = "expected_rules" if checks else "expected_uart"
        summary = (
            "Renode runtime validation matched all configured rules."
            if checks
            else "Renode UART validation matched all expected substrings."
        )
        return {
            "status": "pass",
            "passed": True,
            "mode": mode,
            "summary": summary,
            "reasons": reasons,
            "warnings": warnings,
        }

    if validation_passed is False:
        reasons.extend(_summarize_runtime_validation_checks(checks, passed_only=False))
        if not reasons:
            missing = [str(item) for item in simulate_result.get("missing_uart_contains", []) if str(item).strip()]
            reasons.extend(missing or ["Expected UART text was not observed."])
        mode = "expected_rules" if checks else "expected_uart"
        summary = (
            "Renode runtime validation missed one or more configured rules."
            if checks
            else "Renode UART validation missed one or more expected substrings."
        )
        return {
            "status": "fail",
            "passed": False,
            "mode": mode,
            "summary": summary,
            "reasons": reasons,
            "warnings": warnings,
        }

    if not bool(simulate_result.get("ran", False)):
        reasons.extend(str(item) for item in simulate_result.get("errors", []) if str(item).strip())
        if not reasons:
            reasons.append("Renode exited without a passing run result.")
        return {
            "status": "fail",
            "passed": False,
            "mode": "run_failure",
            "summary": "Renode executed, but the validation run did not pass.",
            "reasons": reasons,
            "warnings": warnings,
        }

    uart_output = simulate_result.get("uart_output", {})
    combined_output = ""
    if isinstance(uart_output, dict):
        combined_output = "\n".join(str(value) for value in uart_output.values() if str(value).strip())

    analyzers = [str(item).strip() for item in simulate_result.get("uart_analyzers", []) if str(item).strip()]
    if combined_output.strip():
        preview = [line.strip() for line in combined_output.splitlines() if line.strip()]
        if preview:
            reasons.append("Observed UART: " + "; ".join(preview[:3]))
        warnings.append(
            "Runtime validation fell back to heuristic UART-output detection because no explicit expectations were available."
        )
        return {
            "status": "pass",
            "passed": True,
            "mode": "uart_observed",
            "summary": "Renode observed UART output, but no explicit expectation file was provided.",
            "reasons": reasons,
            "warnings": warnings,
        }

    if analyzers:
        return {
            "status": "fail",
            "passed": False,
            "mode": "uart_missing",
            "summary": "Renode ran successfully, but no UART output was observed.",
            "reasons": ["No UART text was observed during the Renode run."],
            "warnings": warnings,
        }

    return {
        "status": "fail",
        "passed": False,
        "mode": "unsupported",
        "summary": "Runtime validation currently relies on UART observability, but no UART analyzer was configured.",
        "reasons": ["No UART analyzer was configured for this project."],
        "warnings": warnings,
    }


def _summarize_runtime_validation_checks(checks: Dict[str, object], passed_only: bool) -> List[str]:
    if not isinstance(checks, dict):
        return []

    lines: List[str] = []

    contains = checks.get("uart_contains", {})
    if isinstance(contains, dict):
        if passed_only and contains.get("passed") is True:
            matched = [str(item) for item in contains.get("matched", []) if str(item).strip()]
            if matched:
                lines.append("Matched all required UART text: " + "; ".join(matched[:4]))
        elif not passed_only and contains.get("passed") is False:
            missing = [str(item) for item in contains.get("missing", []) if str(item).strip()]
            if missing:
                lines.append("Missing required UART text: " + "; ".join(missing[:4]))

    any_contains = checks.get("uart_any_contains", {})
    if isinstance(any_contains, dict):
        if passed_only and any_contains.get("passed") is True:
            matched_any = [str(item) for item in any_contains.get("matched", []) if str(item).strip()]
            if matched_any:
                lines.append("Matched at least one optional UART text: " + "; ".join(matched_any[:4]))
        elif not passed_only and any_contains.get("passed") is False:
            expected_any = [str(item) for item in any_contains.get("expected", []) if str(item).strip()]
            if expected_any:
                lines.append("Did not match any expected UART alternatives: " + "; ".join(expected_any[:4]))

    not_contains = checks.get("uart_not_contains", {})
    if isinstance(not_contains, dict):
        if passed_only and not_contains.get("passed") is True:
            expected_forbidden = [str(item) for item in not_contains.get("expected", []) if str(item).strip()]
            if expected_forbidden:
                lines.append("Forbidden UART text was not observed.")
        elif not passed_only and not_contains.get("passed") is False:
            forbidden = [str(item) for item in not_contains.get("matched", []) if str(item).strip()]
            if forbidden:
                lines.append("Observed forbidden UART text: " + "; ".join(forbidden[:4]))

    sequence = checks.get("uart_sequence", {})
    if isinstance(sequence, dict):
        if passed_only and sequence.get("passed") is True:
            expected_sequence = [str(item) for item in sequence.get("expected", []) if str(item).strip()]
            if expected_sequence:
                lines.append("Matched UART sequence: " + " -> ".join(expected_sequence[:4]))
        elif not passed_only and sequence.get("passed") is False:
            missing_sequence = [str(item) for item in sequence.get("missing", []) if str(item).strip()]
            if missing_sequence:
                lines.append("Missing UART sequence steps: " + " -> ".join(missing_sequence[:4]))

    log_contains = checks.get("log_contains", {})
    if isinstance(log_contains, dict):
        if passed_only and log_contains.get("passed") is True:
            matched_log = [str(item) for item in log_contains.get("matched", []) if str(item).strip()]
            if matched_log:
                lines.append("Matched monitor log text: " + "; ".join(matched_log[:4]))
        elif not passed_only and log_contains.get("passed") is False:
            missing_log = [str(item) for item in log_contains.get("missing", []) if str(item).strip()]
            if missing_log:
                lines.append("Missing monitor log text: " + "; ".join(missing_log[:4]))

    log_not_contains = checks.get("log_not_contains", {})
    if isinstance(log_not_contains, dict):
        if passed_only and log_not_contains.get("passed") is True:
            lines.append("Forbidden monitor log text was not observed.")
        elif not passed_only and log_not_contains.get("passed") is False:
            matched_log = [str(item) for item in log_not_contains.get("matched", []) if str(item).strip()]
            if matched_log:
                lines.append("Observed forbidden monitor log text: " + "; ".join(matched_log[:4]))

    exit_code = checks.get("exit_code", {})
    if isinstance(exit_code, dict):
        if passed_only and exit_code.get("passed") is True:
            lines.append(f"Exit code matched expected value: {exit_code.get('expected')}.")
        elif not passed_only and exit_code.get("passed") is False:
            lines.append(
                f"Unexpected Renode exit code: got {exit_code.get('actual')}, expected {exit_code.get('expected')}."
            )

    return lines


def _render_failure_message(summary: str, errors: List[str], warnings: List[str]) -> str:
    lines = [summary]
    if errors:
        lines.append("- 错误: " + "; ".join(errors[:3]))
    if warnings:
        lines.append("- 备注: " + "; ".join(warnings[:3]))
    return "\n".join(lines)


def _render_plan_failure_message(plan) -> str:
    lines = [
        "本地规则规划没有通过，暂时不会进入生成工程阶段。",
        f"- 芯片: {getattr(plan, 'chip', '(unknown)')}",
        f"- 板子: {getattr(plan, 'board', 'chip_only')}",
    ]
    if getattr(plan, "errors", None):
        lines.append("- 错误: " + "; ".join(getattr(plan, "errors", [])[:4]))
    if getattr(plan, "warnings", None):
        lines.append("- 备注: " + "; ".join(getattr(plan, "warnings", [])[:4]))
    return "\n".join(lines)


def _render_negotiation_message(plan, options: List[Dict[str, object]]) -> str:
    lines = [
        "本地规划没有直接通过，但我已经整理出几种可以继续推进的折中方案。",
        f"- 芯片: {getattr(plan, 'chip', '(unknown)')}",
        f"- 板卡: {getattr(plan, 'board', 'chip_only')}",
        f"- 失败摘要: {getattr(plan, 'summary', 'Planning failed.')}",
    ]
    if getattr(plan, "errors", None):
        lines.append("- 阻塞问题: " + "; ".join(getattr(plan, "errors", [])[:4]))
    if getattr(plan, "warnings", None):
        lines.append("- 备注: " + "; ".join(getattr(plan, "warnings", [])[:4]))
    if options:
        lines.append("")
        lines.append("可选折中方案：")
        for index, option in enumerate(options[:3], start=1):
            title = str(option.get("title", "")).strip() or f"方案 {index}"
            summary = str(option.get("summary", "")).strip()
            lines.append(f"{index}. {title}")
            if summary:
                lines.append(f"   {summary}")
        lines.append("")
        lines.append("你可以直接点一个建议方案，或自己写修改意见后重新规划。")
    return "\n".join(lines)


def _build_negotiation_options(request_payload: Dict[str, object], plan) -> List[Dict[str, object]]:
    target = request_payload.get("target", {}) if isinstance(request_payload, dict) else {}
    target = target if isinstance(target, dict) else {}
    chip = str(target.get("chip", "") or getattr(plan, "chip", "") or "").strip() or "(unknown)"
    board = str(target.get("board", "") or getattr(plan, "board", "") or "").strip() or "auto"
    summary = str(getattr(plan, "summary", "") or "").strip().lower()
    errors = [str(item).strip() for item in getattr(plan, "errors", []) if str(item).strip()]
    error_blob = " ".join(errors).lower()
    modules = [
        str(item.get("name") or item.get("kind") or "").strip()
        for item in request_payload.get("modules", [])
        if isinstance(item, dict)
    ]
    modules = [item for item in modules if item]

    options: List[Dict[str, object]] = []

    def add_option(option_id: str, title: str, summary_text: str, feedback: str) -> None:
        if not feedback.strip():
            return
        if any(str(item.get("id", "")).strip() == option_id for item in options):
            return
        options.append(
            {
                "id": option_id,
                "title": title,
                "summary": summary_text,
                "feedback": feedback.strip(),
            }
        )

    if "board is not supported" in summary or "unsupported board" in error_blob:
        add_option(
            "auto_board",
            "改成自动选板卡",
            f"保留芯片 {chip}，改为自动推荐兼容板卡。",
            f"当前板卡 {board} 不受支持。请保留芯片 {chip}，改为自动推荐兼容板卡后重新规划。",
        )
        add_option(
            "chip_only",
            "切到 chip_only",
            "不绑定具体板卡，先按最小系统把功能跑通。",
            f"请忽略当前板卡约束，改成 board=chip_only，基于芯片 {chip} 重新规划。",
        )
    elif "chip is not supported" in summary or "unsupported chip" in error_blob:
        if board not in {"", "auto", "chip_only"}:
            add_option(
                "board_default_chip",
                "改用板卡默认芯片",
                f"保留板卡 {board}，改用它对应的默认芯片。",
                f"当前芯片 {chip} 不受支持。请保留板卡 {board}，改用该板卡默认芯片后重新规划。",
            )
        add_option(
            "supported_family_chip",
            "换成已支持芯片",
            "把目标切到仓库当前已支持的 STM32 芯片。",
            "当前芯片不受支持。请换成仓库当前已支持的 STM32 芯片后重新规划，优先考虑已验证的 F103 或 G431 系列。",
        )
    elif "board and chip do not match" in summary or ("targets" in error_blob and "but request selected" in error_blob):
        add_option(
            "prefer_board_chip",
            "跟随板卡芯片",
            f"保留板卡 {board}，改用板卡声明的默认芯片。",
            f"请保留板卡 {board}，改用它声明的默认芯片后重新规划。",
        )
        add_option(
            "prefer_chip_board",
            "保留芯片改选板卡",
            f"保留芯片 {chip}，自动挑一个匹配板卡。",
            f"请保留芯片 {chip}，改为自动推荐匹配板卡后重新规划。",
        )
        add_option(
            "chip_only",
            "切到 chip_only",
            "先不绑定板卡，直接按芯片最小系统规划。",
            f"请改成 board=chip_only，基于芯片 {chip} 重新规划。",
        )
    else:
        add_option(
            "relax_pins",
            "放宽固定引脚",
            "保留功能需求，但允许自动重分配引脚、总线和外设实例。",
            "当前资源规划有冲突。请保留功能需求，但放宽固定引脚、总线和外设实例限制，允许自动重分配后重新规划。",
        )
        if modules:
            core_modules = modules[: max(1, min(2, len(modules)))]
            add_option(
                "core_modules_first",
                "先保留核心模块",
                f"先只规划 {', '.join(core_modules)}，把主路径跑通。",
                "当前模块组合过于拥挤。请先只保留核心模块 "
                + ", ".join(core_modules)
                + " 重新规划，其他模块后续再补回。",
            )
        if board not in {"", "auto", "chip_only"}:
            add_option(
                "chip_only",
                "改成 chip_only 规划",
                "去掉板卡约束，先按芯片最小系统找可用资源。",
                f"请忽略当前板卡 {board} 的限制，改成 board=chip_only 后重新规划。",
            )

    if not options:
        add_option(
            "manual_replan",
            "按当前需求重算",
            "保留当前方向，只允许 Agent 做更激进的自动调整。",
            "请保留整体功能目标，但允许更激进地调整模块组合、引脚分配和板卡约束后重新规划。",
        )
    return options[:3]


def _render_proposal_message(
    request_payload: Dict[str, object],
    plan,
    output_dir: str,
    mode: str,
    warnings: List[str],
    file_changes: List[Dict[str, object]],
) -> str:
    lines = [
        "可行性: 可以做。",
        f"目标芯片: {getattr(plan, 'chip', '')}",
        f"建议板子: {_suggest_board_text(plan)}",
    ]
    request_profile_lines = _build_request_profile_lines(request_payload)
    if request_profile_lines:
        lines.extend(
            [
                "",
                "需求画像:",
                *[f"- {item}" for item in request_profile_lines],
            ]
        )
    lines.extend(
        [
            "",
            "关键接线:",
        ]
    )
    for assignment in getattr(plan, "assignments", [])[:12]:
        lines.append(f"- {assignment.module}.{assignment.signal} -> {assignment.pin}")
    if getattr(plan, "buses", None):
        lines.append("")
        lines.append("总线分配:")
        for bus in getattr(plan, "buses", [])[:4]:
            lines.append(f"- {bus.bus}: {json.dumps(bus.pins, ensure_ascii=False)}")
    lines.append("")
    if mode == "modify":
        lines.append(f"确认后动作: 我会基于当前项目继续更新并尝试重新编译 -> {output_dir}")
    else:
        lines.append(f"确认后动作: 我会生成新的 Keil 工程并继续编译 -> {output_dir}")
    lines.append(_summarize_file_changes(file_changes))
    file_lines = _format_file_change_lines(file_changes, limit=10)
    if file_lines:
        lines.append("")
        lines.append("文件变更预览:")
        lines.extend(f"- {item}" for item in file_lines)
    lines.append("如果你认可这套模块和引脚分配，就继续确认方案。")
    if warnings:
        lines.append("")
        lines.append("备注:")
        for item in warnings[:4]:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _suggest_board_text(plan) -> str:
    if getattr(plan, "board", "") and getattr(plan, "board", "") != "chip_only":
        return str(plan.board)
    if getattr(plan, "chip", "") == "STM32F103C8T6":
        return "STM32F103C8T6 最小系统板或 Blue Pill"
    if getattr(plan, "chip", "") == "STM32F103RBT6":
        return "STM32F103RBT6 最小系统板或 Nucleo-F103RB"
    if getattr(plan, "chip", "") == "STM32G431RBT6":
        return "CT117E-M4 或 STM32G431RBT6 开发板"
    return f"{getattr(plan, 'chip', '当前芯片')} 对应开发板"


def _build_change_preview_lines(
    request_payload: Dict[str, object],
    plan,
    output_dir: str,
    mode: str,
    file_changes: List[Dict[str, object]],
) -> List[str]:
    output_path = Path(output_dir)
    modules = request_payload.get("modules", [])
    module_names = [
        str(item.get("name", "")).strip()
        for item in modules
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]
    top_level_targets = [
        "project_ir.json",
        "README.generated.md",
        "REPORT.generated.md",
        "Core/",
        "App/",
        "Modules/",
        "MDK-ARM/",
    ]
    if output_path.exists():
        existing_items = sorted(item.name for item in output_path.iterdir())
        preview = ", ".join(existing_items[:6]) if existing_items else "空目录"
        if len(existing_items) > 6:
            preview += f" 等 {len(existing_items)} 项"
        existence_text = f"目标目录已存在，可能会覆盖这些已有内容: {preview}"
    else:
        existence_text = "目标目录当前不存在，会新建整套工程目录。"

    request_profile_summary = _summarize_request_profile(request_payload)
    return [
        f"变更类型: {'修改当前项目' if mode == 'modify' else '新建工程'}",
        f"目标目录: {output_dir}",
        existence_text,
        f"芯片/资源会按本次方案重新落盘: {getattr(plan, 'chip', '')}，{len(getattr(plan, 'assignments', []))} 条引脚分配，{len(getattr(plan, 'buses', []))} 条总线",
        f"模块会写入工程: {', '.join(module_names) if module_names else '无额外模块'}",
        *([request_profile_summary] if request_profile_summary else []),
        _summarize_file_changes(file_changes),
        f"预计写入或更新: {', '.join(top_level_targets)}",
        *_format_file_change_lines(file_changes, limit=12),
        "生成完成后会继续执行 Cube 驱动导入、Keil 编译，并在可用时导出 HEX。",
    ]


def _summarize_file_changes(file_changes: List[Dict[str, object]]) -> str:
    if not file_changes:
        return "文件变更预览: 当前还没有可用的文件预览。"

    create_count = sum(1 for item in file_changes if str(item.get("status", "")).strip() == "create")
    update_count = sum(1 for item in file_changes if str(item.get("status", "")).strip() == "update")
    unchanged_count = sum(1 for item in file_changes if str(item.get("status", "")).strip() == "unchanged")
    return f"文件变更预览: 新建 {create_count}，更新 {update_count}，内容不变 {unchanged_count}。"


def _format_file_change_lines(file_changes: List[Dict[str, object]], limit: int = 12) -> List[str]:
    if not file_changes:
        return []

    status_labels = {
        "create": "[create]",
        "update": "[update]",
        "unchanged": "[same]",
    }
    lines: List[str] = []
    for item in file_changes[:limit]:
        status = status_labels.get(str(item.get("status", "")).strip(), "[file]")
        relative_path = str(item.get("relative_path", "")).strip() or str(item.get("path", "")).strip()
        lines.append(f"{status} {relative_path}")
    remaining = len(file_changes) - limit
    if remaining > 0:
        lines.append(f"... 还有 {remaining} 个文件条目可以继续预览。")
    return lines


def _build_request_profile_lines(request_payload: Dict[str, object]) -> List[str]:
    lines: List[str] = []
    app_goal = str(request_payload.get("app_logic_goal", "") or "").strip()
    if app_goal:
        lines.append(f"业务目标: {app_goal}")

    requirements = _normalize_request_note_list(request_payload.get("requirements", []))
    if requirements:
        lines.append("关键需求: " + "; ".join(requirements[:4]))

    assumptions = _normalize_request_note_list(request_payload.get("assumptions", []))
    if assumptions:
        lines.append("当前假设: " + "; ".join(assumptions[:3]))

    open_questions = _normalize_request_note_list(request_payload.get("open_questions", []))
    if open_questions:
        lines.append("待确认问题: " + "; ".join(open_questions[:3]))
    return lines


def _summarize_request_profile(request_payload: Dict[str, object]) -> str:
    requirements = _normalize_request_note_list(request_payload.get("requirements", []))
    assumptions = _normalize_request_note_list(request_payload.get("assumptions", []))
    open_questions = _normalize_request_note_list(request_payload.get("open_questions", []))

    counts: List[str] = []
    if requirements:
        counts.append(f"{len(requirements)} 条需求")
    if assumptions:
        counts.append(f"{len(assumptions)} 条假设")
    if open_questions:
        counts.append(f"{len(open_questions)} 个待确认问题")
    if not counts:
        return ""
    return "这次生成会继续保留这些业务约束: " + "，".join(counts) + "。"


def _normalize_request_note_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
