from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

from ..desktop.llm_client import complete_chat_completion
from ..llm_config import LlmProfile
from .state import STM32ProjectState


CompletionFn = Callable[[LlmProfile, List[dict[str, object]]], str]

ERROR_PATTERNS = (
    re.compile(r"(?P<path>[^:\n]+?\.(?:c|h))\((?P<line>\d+)\):\s*(?P<level>error|warning):\s*(?P<message>.+)", re.I),
    re.compile(r"(?P<path>[^:\n]+?\.(?:c|h)):(?P<line>\d+)(?::\d+)?:\s*(?P<level>error|warning):\s*(?P<message>.+)", re.I),
)
ALLOWED_SUFFIXES = {".c", ".h"}
ALLOWED_PATCH_DIRS = ("App", "Core", "Modules")
MAX_PATCHES = 4
MAX_PATCH_TEXT = 4000
MAX_UNIFIED_DIFF_TEXT = 24000


@dataclass(frozen=True)
class BuildErrorSnippet:
    source_path: str
    line: int
    level: str
    message: str
    snippet: str

    def to_prompt_block(self) -> str:
        return (
            f"File: {self.source_path}\n"
            f"Line: {self.line}\n"
            f"Level: {self.level}\n"
            f"Message: {self.message}\n"
            f"Snippet:\n{self.snippet}"
        )


@dataclass(frozen=True)
class RepairPatch:
    path: str
    reason: str
    start_line: int | None = None
    end_line: int | None = None
    replace_code: str = ""
    search: str = ""
    replace: str = ""


@dataclass(frozen=True)
class RepairPlan:
    strategy: str
    patches: List[RepairPatch]
    unified_diff: str = ""


@dataclass(frozen=True)
class UnifiedDiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str]


@dataclass(frozen=True)
class UnifiedDiffFilePatch:
    path: str
    hunks: List[UnifiedDiffHunk]


@dataclass(frozen=True)
class RuntimeSourceSnippet:
    source_path: str
    purpose: str
    snippet: str

    def to_prompt_block(self) -> str:
        return (
            f"File: {self.source_path}\n"
            f"Purpose: {self.purpose}\n"
            f"Snippet:\n{self.snippet}"
        )


def build_default_repair_fn(
    profile: LlmProfile,
    completion_fn: CompletionFn | None = None,
) -> Callable[[STM32ProjectState], Dict[str, object]]:
    def _repair(state: STM32ProjectState) -> Dict[str, object]:
        return attempt_llm_build_repair(state, profile, completion_fn=completion_fn)

    return _repair


def attempt_llm_build_repair(
    state: STM32ProjectState,
    profile: LlmProfile,
    completion_fn: CompletionFn | None = None,
) -> Dict[str, object]:
    project_dir = Path(str(state.get("project_dir", "")).strip())
    if not project_dir.exists():
        return _manual_review("Current project directory was not found, so automatic repair cannot run.")

    error_snippets = _collect_error_snippets(state, project_dir)
    if error_snippets:
        try:
            response_text = _run_repair_completion(profile, error_snippets, completion_fn=completion_fn, project_dir=project_dir)
        except Exception as exc:
            return _manual_review(f"Automatic repair could not query the model: {exc}")

        try:
            repair_plan = _parse_repair_response(response_text)
        except ValueError as exc:
            return _manual_review(f"Automatic repair returned invalid JSON: {exc}")

        if not repair_plan.unified_diff and not repair_plan.patches:
            return _manual_review("The model did not return any safe patches.")

        applied_files, notes = _apply_repair_plan(project_dir, repair_plan)
        if not applied_files:
            detail = "; ".join(notes[:4]) if notes else "No returned patch passed local safety checks."
            return _manual_review(detail)

        warning_lines = [
            "A controlled automatic repair patch was applied and the build will be retried.",
            *[f"Updated: {item}" for item in applied_files[:8]],
            *[f"Note: {item}" for item in notes[:4]],
        ]
        return {
            "repair_strategy": "retry_build",
            "warnings": warning_lines,
            "errors": [],
        }

    if _runtime_validation_failed(state):
        runtime_contexts = _collect_runtime_snippets(project_dir)
        if not runtime_contexts:
            return _manual_review(
                "Runtime validation failed, but no editable App/Core source snippets were available for a safe repair attempt."
            )

        try:
            response_text = _run_runtime_repair_completion(
                state,
                profile,
                runtime_contexts,
                completion_fn=completion_fn,
            )
        except Exception as exc:
            return _manual_review(f"Automatic runtime repair could not query the model: {exc}")

        try:
            repair_plan = _parse_repair_response(response_text)
        except ValueError as exc:
            return _manual_review(f"Automatic runtime repair returned invalid JSON: {exc}")

        if not repair_plan.unified_diff and not repair_plan.patches:
            return _manual_review("The runtime-repair model did not return any safe patches.")

        applied_files, notes = _apply_repair_plan(project_dir, repair_plan)
        if not applied_files:
            detail = "; ".join(notes[:4]) if notes else "No returned runtime patch passed local safety checks."
            return _manual_review(detail)

        warning_lines = [
            "A controlled automatic runtime repair patch was applied and the build/simulate cycle will be retried.",
            *[f"Updated: {item}" for item in applied_files[:8]],
            *[f"Note: {item}" for item in notes[:4]],
        ]
        return {
            "repair_strategy": "retry_build",
            "warnings": warning_lines,
            "errors": [],
        }

    return _manual_review("No actionable compile errors or runtime validation failures were available for automatic repair.")


def _collect_error_snippets(state: STM32ProjectState, project_dir: Path) -> List[BuildErrorSnippet]:
    lines = _collect_build_log_lines(state)
    snippets: List[BuildErrorSnippet] = []
    for line in lines:
        parsed = _parse_error_line(line)
        if parsed is None:
            continue
        resolved_path = _resolve_project_source_path(project_dir, parsed["path"])
        if resolved_path is None:
            continue
        snippet_text = _read_source_snippet(resolved_path, int(parsed["line"]))
        snippets.append(
            BuildErrorSnippet(
                source_path=str(resolved_path.relative_to(project_dir)).replace("\\", "/"),
                line=int(parsed["line"]),
                level=str(parsed["level"]).lower(),
                message=str(parsed["message"]).strip(),
                snippet=snippet_text,
            )
        )
    unique: Dict[tuple[str, int, str], BuildErrorSnippet] = {}
    for item in snippets:
        unique[(item.source_path, item.line, item.message)] = item
    return list(unique.values())[:6]


def _classify_common_errors(error_snippets: Sequence[BuildErrorSnippet]) -> List[str]:
    """Classify compile errors and return targeted diagnostic hints."""
    hints: List[str] = []
    seen: set[str] = set()
    for snippet in error_snippets:
        msg = snippet.message.lower()
        if "undeclared identifier" in msg or "undeclared" in msg:
            hint = f"'{snippet.source_path}' line {snippet.line}: undeclared identifier — likely missing #include or wrong API name"
            if hint not in seen:
                seen.add(hint)
                hints.append(hint)
        elif "implicit declaration" in msg or "implicit function" in msg:
            hint = f"'{snippet.source_path}' line {snippet.line}: implicit function — add the correct #include for this API"
            if hint not in seen:
                seen.add(hint)
                hints.append(hint)
        elif "conflicting types" in msg:
            hint = f"'{snippet.source_path}' line {snippet.line}: conflicting types — match the exact prototype from the header"
            if hint not in seen:
                seen.add(hint)
                hints.append(hint)
        elif "expected" in msg and ";" in msg:
            hint = f"'{snippet.source_path}' line {snippet.line}: syntax error — likely missing semicolon or brace"
            if hint not in seen:
                seen.add(hint)
                hints.append(hint)
    return hints[:6]


def _collect_available_headers(project_dir: Path) -> List[str]:
    """Collect function declarations from project header files for repair context."""
    summaries: List[str] = []
    for header_dir in ("App/Inc", "Modules/Inc", "Core/Inc"):
        inc_dir = project_dir / header_dir
        if not inc_dir.exists():
            continue
        for header_path in sorted(inc_dir.glob("*.h")):
            try:
                text = header_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Extract function declarations (lines with common patterns)
            api_lines: List[str] = []
            for line in text.splitlines():
                stripped = line.strip()
                # Capture function prototypes (ending with ;, having parens)
                if (
                    stripped.endswith(";") 
                    and "(" in stripped 
                    and not stripped.startswith("//")
                    and not stripped.startswith("#")
                    and not stripped.startswith("typedef")
                ):
                    api_lines.append(f"  {stripped}")
            if api_lines:
                rel = header_path.relative_to(project_dir).as_posix()
                summaries.append(f"{rel}:")
                summaries.extend(api_lines[:8])
    return summaries


def _collect_build_log_lines(state: STM32ProjectState) -> List[str]:
    lines: List[str] = []
    for item in state.get("build_logs", []):
        text = str(item).strip()
        if not text:
            continue
        lines.extend(text.splitlines())
    return lines


def _parse_error_line(line: str) -> Dict[str, object] | None:
    for pattern in ERROR_PATTERNS:
        match = pattern.search(line)
        if match:
            return {
                "path": match.group("path").strip().strip('"'),
                "line": int(match.group("line")),
                "level": match.group("level").lower(),
                "message": match.group("message").strip(),
            }
    return None


def _resolve_project_source_path(project_dir: Path, raw_path: str) -> Path | None:
    candidate = Path(raw_path)
    candidates: List[Path] = []
    if candidate.is_absolute():
        candidates.append(candidate)
    else:
        candidates.append(project_dir / candidate)
        candidates.extend(project_dir.glob(f"**/{candidate.name}"))

    seen: set[Path] = set()
    for item in candidates:
        try:
            resolved = item.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.exists() or resolved.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        try:
            resolved.relative_to(project_dir.resolve())
        except ValueError:
            continue
        return resolved
    return None


def _read_source_snippet(path: Path, line_number: int, radius: int = 8) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(source snippet unavailable)"

    start = max(line_number - radius - 1, 0)
    end = min(line_number + radius, len(lines))
    rendered: List[str] = []
    for index in range(start, end):
        marker = ">>" if index + 1 == line_number else "  "
        rendered.append(f"{marker} {index + 1:4d}: {lines[index]}")
    return "\n".join(rendered)


def _run_repair_completion(
    profile: LlmProfile,
    error_snippets: Sequence[BuildErrorSnippet],
    completion_fn: CompletionFn | None = None,
    project_dir: Path | None = None,
) -> str:
    messages: List[dict[str, object]] = [
        {
            "role": "system",
            "content": (
                "You repair generated STM32 Keil projects after compile failures. "
                "Return JSON only. Prefer a unified_diff patch in standard git diff format when you can. "
                "Use exact search/replace patches only when unified diff is unsafe or unavailable. "
                "Use line-based patches only when exact search text is unsafe or unavailable. "
                "Do not rewrite whole files. Prefer changes inside USER CODE blocks when possible.\n\n"
                "Common fix patterns:\n"
                "- 'undeclared identifier' or 'implicit declaration': check if the correct #include is present; "
                "use APIs from the provided module headers, do NOT invent new function names.\n"
                "- 'expected ';' or type errors: fix syntax, not logic.\n"
                "- 'conflicting types': check the header for the correct prototype and match it exactly.\n"
                "- Algorithm module APIs (PID_*, MovingAvg_*, RingBuf_*) are pre-verified — use them as-is."
            ),
        },
        {
            "role": "user",
            "content": _build_repair_prompt(error_snippets, project_dir=project_dir),
        },
    ]
    if completion_fn is not None:
        return completion_fn(profile, messages)
    return complete_chat_completion(profile, messages)


def _run_runtime_repair_completion(
    state: STM32ProjectState,
    profile: LlmProfile,
    runtime_snippets: Sequence[RuntimeSourceSnippet],
    completion_fn: CompletionFn | None = None,
) -> str:
    messages: List[dict[str, object]] = [
        {
            "role": "system",
            "content": (
                "You repair generated STM32 applications after runtime validation failures. "
                "Return JSON only. Prefer a unified_diff patch in standard git diff format for minimal edits in "
                "App/Src/app_main.c or other user-editable files. "
                "Do not modify HAL drivers, generated startup files, or project metadata."
            ),
        },
        {
            "role": "user",
            "content": _build_runtime_repair_prompt(state, runtime_snippets),
        },
    ]
    if completion_fn is not None:
        return completion_fn(profile, messages)
    return complete_chat_completion(profile, messages)


def _build_repair_prompt(
    error_snippets: Sequence[BuildErrorSnippet],
    project_dir: Path | None = None,
) -> str:
    blocks = "\n\n".join(item.to_prompt_block() for item in error_snippets)

    # Classify errors and provide targeted hints
    hints = _classify_common_errors(error_snippets)
    hints_text = ""
    if hints:
        hints_text = (
            "\nDiagnostic hints based on error patterns:\n"
            + "\n".join(f"- {h}" for h in hints)
            + "\n"
        )

    # Collect available header files for API reference
    available_headers = ""
    if project_dir is not None:
        header_summaries = _collect_available_headers(project_dir)
        if header_summaries:
            available_headers = (
                "\nAvailable project headers (correct APIs to use):\n"
                + "\n".join(header_summaries[:12])
                + "\n"
            )

    return (
        "Keil build failed. Produce the smallest safe JSON-only repair plan.\n\n"
        "Rules:\n"
        "1. Return JSON only, without Markdown.\n"
        "2. Prefer a unified_diff patch in standard git diff format.\n"
        "3. If unified diff is unsafe or unavailable, prefer exact search/replace patches using the original code text.\n"
        "4. Use start_line/end_line/replace_code only if exact search text is unsafe or unavailable.\n"
        "5. Limit patches to 4 or fewer.\n"
        "6. If the problem is unsafe or unclear, return repair_strategy=manual_review.\n"
        f"{hints_text}"
        f"{available_headers}"
        "\nExpected JSON shape:\n"
        "{\n"
        '  "repair_strategy": "retry_build" | "manual_review",\n'
        '  "summary": "one sentence",\n'
        '  "unified_diff": "--- a/App/Src/app_main.c\\n+++ b/App/Src/app_main.c\\n@@ -1,1 +1,2 @@\\n old line\\n+new line",\n'
        '  "patches": [\n'
        "    {\n"
        '      "path": "App/Src/app_main.c",\n'
        '      "search": "original code fragment",\n'
        '      "replace": "replacement code",\n'
        '      "reason": "why"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "If you provide unified_diff, keep it minimal and valid. patches is the fallback format.\n\n"
        "Errors and source snippets:\n\n"
        f"{blocks}"
    )


def _build_runtime_repair_prompt(
    state: STM32ProjectState,
    runtime_snippets: Sequence[RuntimeSourceSnippet],
) -> str:
    evaluation = state.get("evaluation_result") or {}
    simulate = state.get("simulate_result") or {}
    request_payload = state.get("request_payload") or {}
    app_goal = str(request_payload.get("app_logic_goal", "")).strip()
    user_input = str(state.get("user_input", "")).strip()
    summary = str(evaluation.get("summary", "")).strip()
    reasons = [str(item).strip() for item in evaluation.get("reasons", []) if str(item).strip()]
    warnings = [str(item).strip() for item in simulate.get("warnings", []) if str(item).strip()]
    errors = [str(item).strip() for item in simulate.get("errors", []) if str(item).strip()]
    expected = [str(item).strip() for item in simulate.get("expected_uart_contains", []) if str(item).strip()]
    missing = [str(item).strip() for item in simulate.get("missing_uart_contains", []) if str(item).strip()]
    uart_preview = _summarize_uart_output(simulate.get("uart_output", {}))
    blocks = "\n\n".join(item.to_prompt_block() for item in runtime_snippets)

    reason_lines = "\n".join(f"- {item}" for item in reasons[:6]) or "- (none)"
    warning_lines = "\n".join(f"- {item}" for item in warnings[:6]) or "- (none)"
    error_lines = "\n".join(f"- {item}" for item in errors[:6]) or "- (none)"
    expected_lines = "\n".join(f"- {item}" for item in expected[:6]) or "- (none)"
    missing_lines = "\n".join(f"- {item}" for item in missing[:6]) or "- (none)"
    uart_lines = "\n".join(f"- {item}" for item in uart_preview[:8]) or "- (none)"

    return (
        "A generated STM32 project compiled successfully, but runtime validation failed in Renode.\n\n"
        f"Original user request:\n{user_input or '(not provided)'}\n\n"
        f"Structured app logic goal:\n{app_goal or '(not provided)'}\n\n"
        f"Runtime evaluation summary:\n{summary or '(not provided)'}\n\n"
        f"Evaluation reasons:\n{reason_lines}\n\n"
        f"Expected UART substrings:\n{expected_lines}\n\n"
        f"Missing UART substrings:\n{missing_lines}\n\n"
        f"Observed UART preview:\n{uart_lines}\n\n"
        f"Simulation warnings:\n{warning_lines}\n\n"
        f"Simulation errors:\n{error_lines}\n\n"
        "Repair rules:\n"
        "1. Return JSON only, without Markdown.\n"
        "2. Prefer the smallest unified_diff patch in standard git diff format.\n"
        "3. If unified diff is unsafe or unavailable, prefer exact search/replace patches anchored on existing code text.\n"
        "4. Use line-number patches only when exact search text is unsafe or unavailable.\n"
        "5. Do not edit HAL drivers or startup files.\n"
        "6. Limit patches to 4 or fewer.\n"
        "7. If the issue is not safely inferable from the logs and snippets, return repair_strategy=manual_review.\n\n"
        "Expected JSON shape:\n"
        "{\n"
        '  "repair_strategy": "retry_build" | "manual_review",\n'
        '  "summary": "one sentence",\n'
        '  "unified_diff": "--- a/App/Src/app_main.c\\n+++ b/App/Src/app_main.c\\n@@ -1,1 +1,2 @@\\n old line\\n+new line",\n'
        '  "patches": [\n'
        "    {\n"
        '      "path": "App/Src/app_main.c",\n'
        '      "search": "original code fragment",\n'
        '      "replace": "replacement code",\n'
        '      "reason": "why"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "If you provide unified_diff, keep it minimal and valid. patches is the fallback format.\n\n"
        "Relevant source snippets:\n\n"
        f"{blocks}"
    )


def _parse_repair_response(raw_text: str) -> RepairPlan:
    payload = _extract_repair_payload(raw_text)
    if isinstance(payload, str):
        return RepairPlan(strategy="retry_build", patches=[], unified_diff=payload.strip())
    if not isinstance(payload, dict):
        raise ValueError("repair response root must be a JSON object")

    strategy = str(payload.get("repair_strategy", "")).strip().lower() or "retry_build"
    if strategy != "retry_build":
        return RepairPlan(strategy=strategy, patches=[], unified_diff="")

    unified_diff = str(
        payload.get("unified_diff")
        or payload.get("diff")
        or payload.get("patch_text")
        or ""
    ).strip()
    return RepairPlan(
        strategy=strategy,
        patches=_parse_patches_from_payload(payload),
        unified_diff=unified_diff,
    )


def _parse_repair_patches(raw_text: str) -> List[RepairPatch]:
    return _parse_repair_response(raw_text).patches


def _parse_patches_from_payload(payload: Dict[str, Any]) -> List[RepairPatch]:
    raw_patches = payload.get("patches", [])
    if not isinstance(raw_patches, list):
        raise ValueError("patches must be a list")

    patches: List[RepairPatch] = []
    for item in raw_patches[:MAX_PATCHES]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        reason = str(item.get("reason", "")).strip()
        start_line = _parse_optional_int(item.get("start_line"))
        end_line = _parse_optional_int(item.get("end_line"))
        replace_code = str(item.get("replace_code", ""))
        search = str(item.get("search", ""))
        replace = str(item.get("replace", ""))
        if not path:
            continue
        if start_line is not None and end_line is None:
            end_line = start_line
        if start_line is None and end_line is not None:
            start_line = end_line
        if start_line is None and not search:
            continue
        patches.append(
            RepairPatch(
                path=path,
                reason=reason,
                start_line=start_line,
                end_line=end_line,
                replace_code=replace_code,
                search=search,
                replace=replace,
            )
        )
    return patches


def _extract_repair_payload(raw_text: str) -> Any:
    text = raw_text.strip()
    if not text:
        raise ValueError("empty repair response")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            return json.loads(match.group(0))
        if _looks_like_unified_diff(text):
            return text
        raise


def _looks_like_unified_diff(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and (
        stripped.startswith("--- ")
        or stripped.startswith("diff --git ")
        or "\n--- " in stripped
    )


def _apply_repair_plan(project_dir: Path, plan: RepairPlan) -> tuple[List[str], List[str]]:
    if plan.unified_diff:
        applied_files, notes = _apply_unified_diff_patch(project_dir, plan.unified_diff)
        if applied_files or not plan.patches:
            return applied_files, notes
        return _apply_repair_patches(
            project_dir,
            plan.patches,
            existing_notes=[*notes, "Unified diff could not be applied cleanly; falling back to legacy patches."],
        )
    return _apply_repair_patches(project_dir, plan.patches)


def _apply_repair_patches(
    project_dir: Path,
    patches: Sequence[RepairPatch],
    *,
    existing_notes: Sequence[str] | None = None,
) -> tuple[List[str], List[str]]:
    applied: List[str] = []
    notes: List[str] = list(existing_notes or [])
    for patch in patches[:MAX_PATCHES]:
        resolved_path = (project_dir / patch.path).resolve()
        try:
            resolved_path.relative_to(project_dir.resolve())
        except ValueError:
            notes.append(f"skip out-of-project path: {patch.path}")
            continue
        if resolved_path.suffix.lower() not in ALLOWED_SUFFIXES:
            notes.append(f"skip non-source file: {patch.path}")
            continue
        if not any(part in ALLOWED_PATCH_DIRS for part in resolved_path.parts):
            notes.append(f"skip non-whitelisted file: {patch.path}")
            continue
        if (
            len(patch.search) > MAX_PATCH_TEXT
            or len(patch.replace) > MAX_PATCH_TEXT
            or len(patch.replace_code) > MAX_PATCH_TEXT
        ):
            notes.append(f"skip oversized patch: {patch.path}")
            continue
        if not resolved_path.exists():
            notes.append(f"target file does not exist: {patch.path}")
            continue
        try:
            text = resolved_path.read_text(encoding="utf-8")
        except OSError:
            notes.append(f"cannot read file: {patch.path}")
            continue

        updated = None
        if patch.search:
            updated = _apply_search_patch(text, patch)
            if updated is None:
                if patch.start_line is None or patch.end_line is None:
                    notes.append(f"search did not uniquely match {patch.path}")
                    continue
                updated = _apply_line_patch(text, patch)
                if updated is None:
                    notes.append(
                        f"search and line patch both failed for {patch.path}: {patch.start_line}-{patch.end_line}"
                    )
                    continue
        else:
            updated = _apply_line_patch(text, patch)
            if updated is None:
                notes.append(f"line patch failed for {patch.path}: {patch.start_line}-{patch.end_line}")
                continue

        if updated == text:
            notes.append(f"patch made no change: {patch.path}")
            continue
        resolved_path.write_text(updated, encoding="utf-8")
        applied.append(str(resolved_path.relative_to(project_dir)).replace("\\", "/"))
        if patch.reason:
            notes.append(f"{patch.path}: {patch.reason}")
    return applied, notes


def _parse_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _apply_line_patch(text: str, patch: RepairPatch) -> str | None:
    if patch.start_line is None or patch.end_line is None:
        return None
    lines = text.splitlines()
    line_count = len(lines)
    start = patch.start_line - 1
    end = patch.end_line
    if start < 0 or end < patch.start_line or end > line_count:
        return None
    newline = "\r\n" if "\r\n" in text else "\n"
    replacement_lines = patch.replace_code.splitlines()
    updated_lines = [*lines[:start], *replacement_lines, *lines[end:]]
    updated = newline.join(updated_lines)
    if text.endswith(("\r\n", "\n")):
        updated += newline
    return updated


def _apply_search_patch(text: str, patch: RepairPatch) -> str | None:
    if not patch.search:
        return None
    occurrences = text.count(patch.search)
    if occurrences == 1:
        return text.replace(patch.search, patch.replace, 1)
    pattern = _build_whitespace_tolerant_pattern(patch.search)
    if pattern is None:
        return None
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    return text[: match.start()] + patch.replace + text[match.end() :]


def _build_whitespace_tolerant_pattern(search: str) -> re.Pattern[str] | None:
    parts = [part for part in re.split(r"(\s+)", search) if part]
    if not parts:
        return None
    rendered: List[str] = []
    for part in parts:
        if part.isspace():
            rendered.append(r"\s+")
        else:
            rendered.append(re.escape(part))
    try:
        return re.compile("".join(rendered), re.S)
    except re.error:
        return None


def _apply_unified_diff_patch(project_dir: Path, diff_text: str) -> tuple[List[str], List[str]]:
    if len(diff_text) > MAX_UNIFIED_DIFF_TEXT:
        return [], ["skip oversized unified diff payload"]
    try:
        file_patches = _parse_unified_diff(diff_text)
    except ValueError as exc:
        return [], [f"unified diff parse failed: {exc}"]
    if not file_patches:
        return [], ["unified diff did not contain any editable file patches"]

    pending_writes: List[tuple[Path, str]] = []
    applied: List[str] = []
    notes: List[str] = []
    project_root = project_dir.resolve()

    for file_patch in file_patches[:MAX_PATCHES]:
        resolved_path = (project_dir / file_patch.path).resolve()
        try:
            resolved_path.relative_to(project_root)
        except ValueError:
            return [], [*notes, f"skip out-of-project path in unified diff: {file_patch.path}"]
        if resolved_path.suffix.lower() not in ALLOWED_SUFFIXES:
            return [], [*notes, f"skip non-source file in unified diff: {file_patch.path}"]
        if not any(part in ALLOWED_PATCH_DIRS for part in resolved_path.parts):
            return [], [*notes, f"skip non-whitelisted file in unified diff: {file_patch.path}"]
        if not resolved_path.exists():
            return [], [*notes, f"target file does not exist in unified diff: {file_patch.path}"]
        try:
            text = resolved_path.read_text(encoding="utf-8")
        except OSError:
            return [], [*notes, f"cannot read file in unified diff: {file_patch.path}"]

        updated = _apply_unified_diff_to_text(text, file_patch)
        if updated is None:
            return [], [*notes, f"unified diff did not match current file contents: {file_patch.path}"]
        if updated == text:
            return [], [*notes, f"unified diff made no change: {file_patch.path}"]
        pending_writes.append((resolved_path, updated))
        applied.append(str(resolved_path.relative_to(project_dir)).replace("\\", "/"))

    for resolved_path, updated in pending_writes:
        resolved_path.write_text(updated, encoding="utf-8")
    return applied, notes


def _parse_unified_diff(diff_text: str) -> List[UnifiedDiffFilePatch]:
    text = diff_text.strip()
    if not text:
        return []
    lines = text.splitlines()
    file_patches: List[UnifiedDiffFilePatch] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git ") or line.startswith("index ") or line.startswith("new file mode ") or line.startswith("deleted file mode "):
            index += 1
            continue
        if not line.startswith("--- "):
            index += 1
            continue
        old_path = _normalize_diff_path(line[4:])
        index += 1
        while index < len(lines) and lines[index].startswith(("index ", "new file mode ", "deleted file mode ")):
            index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise ValueError("missing +++ header after --- line")
        new_path = _normalize_diff_path(lines[index][4:])
        index += 1
        path = new_path or old_path
        if not path:
            raise ValueError("unified diff file header did not contain a path")
        if old_path == "/dev/null" or new_path == "/dev/null":
            raise ValueError("file creation or deletion is not supported for automatic repair")

        hunks: List[UnifiedDiffHunk] = []
        while index < len(lines) and not lines[index].startswith("--- "):
            if lines[index].startswith("diff --git "):
                break
            if not lines[index].startswith("@@ "):
                index += 1
                continue
            header = lines[index]
            match = re.match(
                r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@",
                header,
            )
            if not match:
                raise ValueError(f"invalid unified diff hunk header: {header}")
            index += 1
            hunk_lines: List[str] = []
            while index < len(lines):
                current = lines[index]
                if current.startswith("--- ") or current.startswith("diff --git ") or current.startswith("@@ "):
                    break
                if current == r"\ No newline at end of file":
                    index += 1
                    continue
                if current[:1] not in {" ", "+", "-"}:
                    raise ValueError(f"invalid unified diff hunk body line: {current}")
                hunk_lines.append(current)
                index += 1
            hunks.append(
                UnifiedDiffHunk(
                    old_start=int(match.group("old_start")),
                    old_count=int(match.group("old_count") or "1"),
                    new_start=int(match.group("new_start")),
                    new_count=int(match.group("new_count") or "1"),
                    lines=hunk_lines,
                )
            )
        if not hunks:
            raise ValueError(f"unified diff did not include any hunks for {path}")
        file_patches.append(UnifiedDiffFilePatch(path=path, hunks=hunks))

    return file_patches


def _normalize_diff_path(raw_path: str) -> str:
    path = str(raw_path or "").split("\t", 1)[0].strip()
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def _apply_unified_diff_to_text(text: str, file_patch: UnifiedDiffFilePatch) -> str | None:
    lines = text.splitlines()
    newline = "\r\n" if "\r\n" in text else "\n"
    new_lines: List[str] = []
    cursor = 0

    for hunk in file_patch.hunks:
        source_lines = [line[1:] for line in hunk.lines if line.startswith((" ", "-"))]
        start_index = _find_hunk_start(lines, source_lines, hunk.old_start - 1, cursor)
        if start_index is None:
            return None
        new_lines.extend(lines[cursor:start_index])
        source_index = start_index

        for line in hunk.lines:
            marker = line[:1]
            content = line[1:]
            if marker == " ":
                if source_index >= len(lines) or lines[source_index] != content:
                    return None
                new_lines.append(lines[source_index])
                source_index += 1
            elif marker == "-":
                if source_index >= len(lines) or lines[source_index] != content:
                    return None
                source_index += 1
            elif marker == "+":
                new_lines.append(content)
            else:
                return None

        cursor = source_index

    new_lines.extend(lines[cursor:])
    updated = newline.join(new_lines)
    if text.endswith(("\r\n", "\n")):
        updated += newline
    return updated


def _find_hunk_start(
    lines: List[str],
    source_lines: List[str],
    suggested_start: int,
    minimum_start: int,
) -> int | None:
    bounded_start = max(minimum_start, suggested_start)
    if not source_lines:
        return bounded_start if bounded_start <= len(lines) else None
    if bounded_start >= 0 and lines[bounded_start : bounded_start + len(source_lines)] == source_lines:
        return bounded_start

    candidates: List[int] = []
    max_start = len(lines) - len(source_lines)
    for index in range(max(minimum_start, 0), max_start + 1):
        if lines[index : index + len(source_lines)] == source_lines:
            candidates.append(index)
            if len(candidates) > 1:
                return None
    return candidates[0] if len(candidates) == 1 else None


def _manual_review(detail: str) -> Dict[str, object]:
    return {
        "repair_strategy": "manual_review",
        "warnings": [detail],
        "errors": [],
    }


def _runtime_validation_failed(state: STM32ProjectState) -> bool:
    if state.get("runtime_validation_passed") is False:
        return True
    evaluation = state.get("evaluation_result") or {}
    if isinstance(evaluation, dict) and evaluation.get("passed") is False:
        return True
    return False


def _collect_runtime_snippets(project_dir: Path) -> List[RuntimeSourceSnippet]:
    candidates = [
        (project_dir / "App" / "Src" / "app_main.c", "Primary generated application logic"),
        (project_dir / "Core" / "Src" / "main.c", "Main initialization and generated startup flow"),
        (project_dir / "Core" / "Src" / "peripherals.c", "Peripheral initialization glue"),
        (project_dir / "Core" / "Src" / "stm32f1xx_it.c", "Interrupt handlers"),
        (project_dir / "Core" / "Src" / "stm32g4xx_it.c", "Interrupt handlers"),
    ]
    snippets: List[RuntimeSourceSnippet] = []
    for path, purpose in candidates:
        if not path.exists():
            continue
        snippet = _read_runtime_source_snippet(path)
        if not snippet:
            continue
        snippets.append(
            RuntimeSourceSnippet(
                source_path=str(path.relative_to(project_dir)).replace("\\", "/"),
                purpose=purpose,
                snippet=snippet,
            )
        )
        if len(snippets) >= 3:
            break
    return snippets


def _read_runtime_source_snippet(path: Path, max_lines: int = 140, max_chars: int = 5000) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    rendered = [f"{index + 1:4d}: {line}" for index, line in enumerate(lines[:max_lines])]
    text = "\n".join(rendered)
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n... (truncated)"
    if len(lines) > max_lines:
        return text + "\n... (truncated)"
    return text


def _summarize_uart_output(raw_uart_output: object) -> List[str]:
    if not isinstance(raw_uart_output, dict):
        return []
    summary: List[str] = []
    for uart_name, text in raw_uart_output.items():
        for line in str(text).splitlines():
            clean = line.strip()
            if not clean:
                continue
            summary.append(f"{uart_name}: {clean}")
            if len(summary) >= 8:
                return summary
    return summary
