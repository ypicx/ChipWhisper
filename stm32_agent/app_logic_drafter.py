from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence

from .app_logic_ir import has_nonempty_app_logic_ir, normalize_app_logic_ir
from .desktop.llm_client import complete_chat_completion
from .generated_files import normalize_generated_files
from .keil_generator import (
    _render_app_config,
    _render_peripherals_h,
)
from .keil_generator_context import _collect_generated_units
from .keil_generator_project import collect_custom_template_roots as _collect_custom_template_roots
from .keil_generator_project import resolve_template_content as _resolve_template_content
from .keil_generator_units import _render_app_header, _render_module_header
from .llm_config import LlmProfile
from .planner import PlanResult


APP_LOGIC_SECTIONS = ("AppTop", "AppInit", "AppLoop", "AppCallbacks")


@dataclass
class AppLogicDraftResult:
    ok: bool
    raw_response: str
    app_logic: Dict[str, str]
    app_logic_ir: Dict[str, object]
    generated_files: Dict[str, str]
    warnings: List[str]
    errors: List[str]


def has_nonempty_app_logic(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return any(str(value.get(section, "")).strip() for section in APP_LOGIC_SECTIONS)


def has_nonempty_generated_files(value: object) -> bool:
    return bool(normalize_generated_files(value))


def draft_app_logic_for_plan(
    profile: LlmProfile,
    user_prompt: str,
    request_payload: Dict[str, object],
    plan: PlanResult,
    *,
    retrieved_context: str = "",
    thread_context: str = "",
    revision_feedback: str = "",
    plan_warnings: Sequence[str] | None = None,
    module_snippets: Dict[str, Dict[str, Any]] | None = None,
    matched_scenarios: Sequence[Dict[str, Any]] | None = None,
    completion_fn: Callable[[LlmProfile, List[dict[str, object]]], str] = complete_chat_completion,
) -> AppLogicDraftResult:
    goal = str(request_payload.get("app_logic_goal", "")).strip()
    if not goal:
        return AppLogicDraftResult(
            ok=True,
            raw_response="",
            app_logic=_empty_app_logic(),
            app_logic_ir=normalize_app_logic_ir(request_payload.get("app_logic_ir", {})),
            generated_files=normalize_generated_files(request_payload.get("generated_files", {})),
            warnings=[],
            errors=[],
        )

    if has_nonempty_app_logic(request_payload.get("app_logic")) or has_nonempty_generated_files(
        request_payload.get("generated_files")
    ) or has_nonempty_app_logic_ir(request_payload.get("app_logic_ir")):
        return AppLogicDraftResult(
            ok=True,
            raw_response="",
            app_logic=_normalize_app_logic(request_payload.get("app_logic")),
            app_logic_ir=normalize_app_logic_ir(request_payload.get("app_logic_ir", {})),
            generated_files=normalize_generated_files(request_payload.get("generated_files", {})),
            warnings=[
                "Skipped automatic app-logic drafting because the request payload already contains manual "
                "app_logic, app_logic_ir, or generated_files content."
            ],
            errors=[],
        )

    prompt = _build_user_prompt(
        user_prompt,
        request_payload,
        plan,
        retrieved_context=retrieved_context,
        thread_context=thread_context,
        revision_feedback=revision_feedback,
        plan_warnings=plan_warnings,
        module_snippets=module_snippets,
        matched_scenarios=matched_scenarios,
    )
    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": prompt},
    ]

    try:
        raw_response = completion_fn(profile, messages)
    except Exception as exc:  # pragma: no cover - provider/runtime path
        return AppLogicDraftResult(
            ok=False,
            raw_response="",
            app_logic=_empty_app_logic(),
            app_logic_ir={},
            generated_files={},
            warnings=[],
            errors=[f"Automatic app-logic drafting failed: {exc}"],
        )

    sections = _extract_tagged_app_logic(raw_response)
    app_logic_ir = _extract_tagged_app_logic_ir(raw_response)
    generated_files = _extract_tagged_generated_files(raw_response)
    if not sections and not generated_files and not app_logic_ir:
        return AppLogicDraftResult(
            ok=False,
            raw_response=raw_response,
            app_logic=_empty_app_logic(),
            app_logic_ir={},
            generated_files={},
            warnings=[],
            errors=[
                "Automatic app-logic drafting did not return any <AppTop>/<AppInit>/<AppLoop>/<AppCallbacks> sections "
                "or <File path=\"...\"> blocks or an <AppLogicIR> JSON block."
            ],
        )

    return AppLogicDraftResult(
        ok=True,
        raw_response=raw_response,
        app_logic={**_empty_app_logic(), **sections},
        app_logic_ir=app_logic_ir,
        generated_files=generated_files,
        warnings=[],
        errors=[],
    )


def merge_generated_app_logic(
    request_payload: Dict[str, object],
    generated: Dict[str, str],
    generated_files: Dict[str, str] | None = None,
    app_logic_ir: Dict[str, object] | None = None,
) -> Dict[str, object]:
    merged = dict(request_payload)
    merged["app_logic"] = {
        **_normalize_app_logic(request_payload.get("app_logic")),
        **{key: value for key, value in generated.items() if str(value).strip()},
    }
    merged["app_logic_ir"] = {
        **normalize_app_logic_ir(request_payload.get("app_logic_ir", {})),
        **normalize_app_logic_ir(app_logic_ir or {}),
    }
    merged["generated_files"] = {
        **normalize_generated_files(request_payload.get("generated_files", {})),
        **normalize_generated_files(generated_files or {}),
    }
    return merged


def _build_system_prompt() -> str:
    return "\n".join(
        [
            "You generate C application logic for ChipWhisper after planning has already finished.",
            "You are given the exact generated macros, peripheral handles, and local header files.",
            "Use only APIs that appear in the provided headers, plus standard STM32 HAL APIs.",
            "Do not invent driver names, macro names, or function signatures.",
            "Do not rely on adding new #include lines in app_main.c; stay within the already available headers whenever possible.",
            "If the requested behavior needs an unavailable API, leave a short TODO comment instead of hallucinating.",
            "When a debug UART helper is available and the behavior has meaningful milestones, emit concise state lines so automated simulation can observe progress.",
            "",
            "IMPORTANT — Reference snippets and scenario templates:",
            "- If 'Reference code snippets' are provided in the user prompt, use those exact API names and calling conventions.",
            "- Do NOT invent alternative function names when a snippet already shows the correct API.",
            "- If a 'Matched scenario template' is provided, use it as a structural baseline but adapt the details to match the actual user request.",
            "- Algorithm module APIs (PID_*, MovingAvg_*, RingBuf_*) are pre-verified — use them as-is without reimplementing.",
            "",
            "Return only XML blocks with these exact tags and no Markdown fences:",
            "<AppTop>...</AppTop>",
            "<AppInit>...</AppInit>",
            "<AppLoop>...</AppLoop>",
            "<AppCallbacks>...</AppCallbacks>",
            "<AppLogicIR>{...}</AppLogicIR>",
            'Optional helper files may use <File path="app/your_helper.c">...</File>, <File path="app/tasks/your_helper.c">...</File>, or <File path="modules/drivers/your_helper.h">...</File>.',
            "Use AppLogicIR when the behavior fits startup steps, periodic tasks, or a simple state machine.",
            "In AppLogicIR, loop.events[] may declare named event conditions, optional flag_var defaults, optional clear_actions, and callbacks[].signature/body blocks.",
            "In AppLogicIR, loop.state_machine.states[].transitions[] may contain guard, actions, and target fields.",
            "Transitions may also use event, after_ms, max_retries, retry_target, retry_actions, failure_target, and failure_actions.",
            "AppLogicIR may also include acceptance.uart_contains/uart_sequence/log_contains/log_not_contains for runtime validation goals.",
            "Keep sections empty when not needed.",
        ]
    )


def _build_user_prompt(
    user_prompt: str,
    request_payload: Dict[str, object],
    plan: PlanResult,
    *,
    retrieved_context: str = "",
    thread_context: str = "",
    revision_feedback: str = "",
    plan_warnings: Sequence[str] | None = None,
    module_snippets: Dict[str, Dict[str, Any]] | None = None,
    matched_scenarios: Sequence[Dict[str, Any]] | None = None,
) -> str:
    app_headers, _app_sources, module_headers, _module_sources = _collect_generated_units(plan.template_files)
    template_roots = _collect_custom_template_roots(plan)
    header_blocks: List[str] = []
    requirement_lines = _bullet_lines(request_payload.get("requirements", []))
    if not requirement_lines:
        requirement_lines = ["- (none)"]
    assumption_lines = _bullet_lines(request_payload.get("assumptions", []))
    open_question_lines = _bullet_lines(request_payload.get("open_questions", []))
    plan_warning_lines = _bullet_lines(plan_warnings or ())

    for header in app_headers:
        content = _resolve_template_content(
            template_roots,
            f"app/{header}",
            default_content=_render_app_header(header),
        )
        header_blocks.append(_header_block(f"App/Inc/{header}", content))

    for header in module_headers:
        content = _resolve_template_content(
            template_roots,
            f"modules/{header}",
            default_content=_render_module_header(header),
        )
        header_blocks.append(_header_block(f"Modules/Inc/{header}", content))

    lines = [
        "Original user request:",
        user_prompt.strip(),
        "",
        "Structured app logic goal:",
        str(request_payload.get("app_logic_goal", "")).strip(),
        "",
        "High-level requirements:",
        *requirement_lines,
        "",
        "Planned modules and assignments:",
        _render_plan_summary(plan),
        "",
        "Generated Core/Inc/app_config.h:",
        _code_block(_render_app_config(plan)),
        "",
        "Generated Core/Inc/peripherals.h:",
        _code_block(_render_peripherals_h(plan)),
    ]

    if assumption_lines:
        lines.extend(
            [
                "",
                "Assumptions to preserve:",
                *assumption_lines,
            ]
        )

    if open_question_lines:
        lines.extend(
            [
                "",
                "Open questions that remain unresolved:",
                *open_question_lines,
            ]
        )

    if retrieved_context.strip():
        lines.extend(
            [
                "",
                "Grounded local knowledge snippets:",
                retrieved_context.strip(),
            ]
        )

    scenario_text = _format_scenario_context(matched_scenarios)
    if scenario_text:
        lines.extend(
            [
                "",
                "Matched scenario template (use as a reference baseline, adapt to the actual user request):",
                scenario_text,
            ]
        )

    if thread_context.strip():
        lines.extend(
            [
                "",
                "Existing project/thread context:",
                thread_context.strip(),
            ]
        )

    if revision_feedback.strip():
        lines.extend(
            [
                "",
                "Latest user revision feedback:",
                revision_feedback.strip(),
            ]
        )

    if plan_warning_lines:
        lines.extend(
            [
                "",
                "Planner warnings / constraints to respect:",
                *plan_warning_lines,
            ]
        )

    if header_blocks:
        lines.extend(
            [
                "",
                "Generated reusable headers you may call:",
                *header_blocks,
            ]
        )

    snippet_text = _format_module_snippets(plan, module_snippets)
    if snippet_text:
        lines.extend(
            [
                "",
                "Reference code snippets for the planned modules (use these real APIs, do NOT invent function names):",
                snippet_text,
            ]
        )

    lines.extend(
        [
            "",
            "Implementation rules:",
            "- Prefer using the generated macros from app_config.h instead of hard-coded pins.",
            "- Honor the listed requirements and assumptions instead of silently dropping them.",
            "- If an open question stays unresolved, choose the safest minimal behavior and leave a short TODO for the ambiguous policy.",
            "- Prefer returning AppLogicIR for startup actions, periodic jobs, and simple state-machine behavior so the project keeps a structured business plan.",
            "- When an event comes from a callback flag or debounced input, prefer declaring it once in AppLogicIR loop.events[] with flag_var and optional callbacks[], then reference its name from transitions[].event.",
            "- For state transitions, prefer AppLogicIR transitions with guard/actions/target instead of hand-writing large switch-case code in AppLoop.",
            "- For wait-retry-fail flows, prefer AppLogicIR transition fields like event/after_ms/max_retries/retry_target/failure_target.",
            "- When the request has observable success criteria, capture them in AppLogicIR acceptance fields instead of leaving validation fully implicit.",
            "- Put one-time setup in <AppInit>, cooperative foreground behavior in <AppLoop>, and HAL callback overrides in <AppCallbacks>.",
            "- Avoid blocking delays unless the user explicitly asked for a simple polling demo.",
            "- If DebugUart_WriteLine or an equivalent UART helper is available, prefer short boot/event/status logs over silent state changes.",
            "- Only emit <File path=\"...\"> blocks when the behavior is large enough to justify extra helper files.",
            "- Keep the code concise and compilable in plain C.",
        ]
    )
    return "\n".join(lines)


def _render_plan_summary(plan: PlanResult) -> str:
    lines = [f"Target chip: {plan.chip}", f"Board: {plan.board}"]
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    modules = project_ir.get("modules", []) if isinstance(project_ir, dict) else []
    if isinstance(modules, list):
        for module in modules:
            if not isinstance(module, dict):
                continue
            name = str(module.get("name", "")).strip()
            kind = str(module.get("kind", "")).strip()
            lines.append(f"- {name or '(unnamed)'} ({kind or 'unknown'})")
            options = module.get("options", {})
            if isinstance(options, dict):
                for key, value in options.items():
                    lines.append(f"  option {key} = {value}")
            # Include module notes for richer context
            notes = module.get("notes", [])
            if isinstance(notes, list):
                for note in notes[:3]:
                    lines.append(f"  note: {note}")
    for assignment in plan.assignments:
        lines.append(f"- signal {assignment.module}.{assignment.signal} -> {assignment.pin}")
    for bus in plan.buses:
        lines.append(f"- bus {bus.bus} ({bus.kind})")
        for device in bus.devices:
            addr = device.get('address', '')
            mod = device.get('module', '')
            lines.append(f"  device {mod} address {addr}")
    return "\n".join(lines)


def _header_block(name: str, content: str) -> str:
    return f"{name}\n{_code_block(content)}"


def _code_block(content: str) -> str:
    return f"```c\n{content.rstrip()}\n```"


def _extract_tagged_app_logic(raw_response: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    for section in APP_LOGIC_SECTIONS:
        match = re.search(rf"<{section}>(.*?)</{section}>", raw_response, re.DOTALL)
        if not match:
            continue
        text = _strip_wrapping_code_fence(match.group(1))
        if text:
            sections[section] = text
    return sections


def _extract_tagged_generated_files(raw_response: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for match in re.finditer(r"<File\s+path=['\"](.*?)['\"]>(.*?)</File>", raw_response, re.DOTALL):
        path = str(match.group(1) or "").strip()
        content = _strip_wrapping_code_fence(match.group(2))
        if not path or not content:
            continue
        files[path] = content
    return normalize_generated_files(files)


def _extract_tagged_app_logic_ir(raw_response: str) -> Dict[str, object]:
    match = re.search(r"<AppLogicIR>(.*?)</AppLogicIR>", raw_response, re.DOTALL)
    if not match:
        return {}
    text = _strip_wrapping_code_fence(match.group(1))
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except ValueError:
        return {}
    return normalize_app_logic_ir(payload)


def _strip_wrapping_code_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^\s*```[a-zA-Z0-9_+-]*\s*\n", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def _normalize_app_logic(value: object) -> Dict[str, str]:
    normalized = _empty_app_logic()
    if not isinstance(value, dict):
        return normalized
    for section in APP_LOGIC_SECTIONS:
        normalized[section] = str(value.get(section, "") or "").strip()
    return normalized


def _normalize_string_list(value: object) -> Sequence[str]:
    if not isinstance(value, list):
        if isinstance(value, tuple):
            return [str(item).strip() for item in value if str(item).strip()]
        return ()
    return [str(item).strip() for item in value if str(item).strip()]


def _bullet_lines(value: object) -> List[str]:
    return [f"- {item}" for item in _normalize_string_list(value)]


def _empty_app_logic() -> Dict[str, str]:
    return {section: "" for section in APP_LOGIC_SECTIONS}


def _format_module_snippets(
    plan: PlanResult,
    module_snippets: Dict[str, Dict[str, Any]] | None,
) -> str:
    """Format app_logic_snippets from planned modules into readable reference text."""
    if not module_snippets:
        return ""

    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    modules = project_ir.get("modules", []) if isinstance(project_ir, dict) else []
    if not isinstance(modules, list):
        return ""

    blocks: List[str] = []
    seen_kinds: set[str] = set()

    for module in modules:
        if not isinstance(module, dict):
            continue
        kind = str(module.get("kind", "")).strip()
        name = str(module.get("name", "")).strip()
        if not kind or kind in seen_kinds:
            continue
        seen_kinds.add(kind)

        snippets = module_snippets.get(kind)
        if not snippets or not isinstance(snippets, dict):
            continue

        for snippet_id, snippet_data in snippets.items():
            if not isinstance(snippet_data, dict):
                continue
            desc = str(snippet_data.get("description", snippet_id)).strip()
            block_lines = [f"### {name} ({kind}) — {desc}"]

            init_lines = snippet_data.get("init", [])
            if isinstance(init_lines, list) and init_lines:
                block_lines.append("Init:")
                block_lines.append("```c")
                block_lines.extend(str(line) for line in init_lines)
                block_lines.append("```")

            task = snippet_data.get("periodic_task")
            if isinstance(task, dict):
                every = task.get("every_ms", "?")
                block_lines.append(f"Periodic task (every {every}ms):")
                block_lines.append("```c")
                run_lines = task.get("run", [])
                if isinstance(run_lines, list):
                    block_lines.extend(str(line) for line in run_lines)
                block_lines.append("```")

            event = snippet_data.get("event_handler")
            if isinstance(event, dict):
                trigger = event.get("trigger", "?")
                block_lines.append(f"Event handler (trigger: {trigger}):")
                block_lines.append("```c")
                handler_lines = event.get("run", [])
                if isinstance(handler_lines, list):
                    block_lines.extend(str(line) for line in handler_lines)
                block_lines.append("```")

            api_list = snippet_data.get("key_apis", [])
            if isinstance(api_list, list) and api_list:
                block_lines.append("Key APIs: " + ", ".join(str(a) for a in api_list))

            blocks.append("\n".join(block_lines))

    return "\n\n".join(blocks)


def _format_scenario_context(
    matched_scenarios: Sequence[Dict[str, Any]] | None,
) -> str:
    """Format matched scenario templates into readable reference text for the LLM."""
    if not matched_scenarios:
        return ""
    blocks: List[str] = []
    for scenario in matched_scenarios[:2]:  # Limit to top 2 matches
        if not isinstance(scenario, dict):
            continue
        name = str(scenario.get("display_name", "")).strip()
        desc = str(scenario.get("description", "")).strip()
        goal = str(scenario.get("app_logic_goal", "")).strip()
        modules = scenario.get("modules", [])
        requirements = scenario.get("requirements", [])
        lines = [f"### {name}"]
        if desc:
            lines.append(f"Description: {desc}")
        if modules and isinstance(modules, list):
            mod_strs = [f"{m.get('name','?')}({m.get('kind','?')})" for m in modules if isinstance(m, dict)]
            lines.append(f"Modules: {', '.join(mod_strs)}")
        if goal:
            lines.append(f"Goal: {goal}")
        if requirements and isinstance(requirements, list):
            lines.append("Requirements:")
            for req in requirements[:8]:
                lines.append(f"- {req}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)

