from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

from ..extension_packs import load_catalog
from ..generated_files import normalize_generated_files
from ..llm_config import LlmProfile
from .attachments import AttachmentDigest, compose_multimodal_user_content
from .llm_client import complete_chat_completion


@dataclass
class RequestDraftResult:
    ok: bool
    profile_name: str
    user_prompt: str
    raw_response: str
    request_payload: Dict[str, object]
    attachment_files: List[str]
    warnings: List[str]
    errors: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "profile_name": self.profile_name,
            "user_prompt": self.user_prompt,
            "raw_response": self.raw_response,
            "request_payload": self.request_payload,
            "attachment_files": self.attachment_files,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def draft_request_json(
    profile: LlmProfile,
    user_prompt: str,
    packs_dir: str | Path | None = None,
    active_project_dir: str = "",
    attachments: List[AttachmentDigest] | None = None,
    retrieved_context: str = "",
    thread_context: str = "",
    revision_feedback: str = "",
    completion_fn: Callable[[LlmProfile, List[dict[str, object]]], str] = complete_chat_completion,
) -> RequestDraftResult:
    prompt = user_prompt.strip()
    if not prompt:
        raise ValueError("user_prompt must not be empty")

    attachment_files = [item.path for item in attachments or []]
    attachment_warnings = [
        warning
        for item in attachments or []
        for warning in item.warnings
    ]
    attachment_errors = [
        error
        for item in attachments or []
        for error in item.errors
    ]
    registry = load_catalog(packs_dir)
    messages = [
        {"role": "system", "content": _build_system_prompt(registry, prompt, retrieved_context=retrieved_context)},
        {
            "role": "user",
            "content": compose_multimodal_user_content(
                _build_user_prompt(
                    prompt,
                    active_project_dir,
                    attachments,
                    retrieved_context=retrieved_context,
                    thread_context=thread_context,
                    revision_feedback=revision_feedback,
                ),
                attachments,
            ),
        },
    ]
    raw_response = completion_fn(profile, messages)

    warnings = [*registry.warnings, *registry.errors, *attachment_warnings]
    errors: List[str] = list(attachment_errors)

    try:
        payload = _extract_json_object(raw_response)
    except ValueError as exc:
        errors.append(str(exc))
        return RequestDraftResult(
            ok=False,
            profile_name=profile.name,
            user_prompt=prompt,
            raw_response=raw_response,
            request_payload={},
            attachment_files=attachment_files,
            warnings=warnings,
            errors=errors,
        )

    extracted_app_logic = _extract_tagged_app_logic(raw_response)
    if extracted_app_logic:
        warnings.append(
            "Model returned legacy tagged app logic during request drafting; the code was ignored and should be regenerated after planning."
        )

    normalized_payload, normalize_warnings = _normalize_request_payload(payload, registry)
    warnings.extend(normalize_warnings)

    return RequestDraftResult(
        ok=not errors,
        profile_name=profile.name,
        user_prompt=prompt,
        raw_response=raw_response,
        request_payload=normalized_payload,
        attachment_files=attachment_files,
        warnings=warnings,
        errors=errors,
    )


def build_chat_system_prompt(
    base_system_prompt: str = "",
    packs_dir: str | Path | None = None,
    active_project_dir: str = "",
    user_prompt: str = "",
    retrieved_context: str = "",
) -> str:
    registry = load_catalog(packs_dir)
    chip_lines = [f"- {name}" for name in sorted(registry.chips)]
    module_lines = _select_chat_module_prompt_lines(registry, user_prompt, retrieved_context)

    sections: List[str] = []
    if base_system_prompt.strip():
        sections.append(base_system_prompt.strip())

    sections.append(
        "\n".join(
            [
                "You are ChipWhisper's STM32 desktop copilot inside a project workbench.",
                "This is not a generic chat page. Prefer concrete engineering help over broad follow-up questions.",
                "Stay grounded in the supported local catalog below. Do not invent unsupported chip names or module kinds.",
                "If the user asks for a simple STM32 demo and does not specify a supported chip, you may assume STM32F103C8T6 and HAL, and briefly state that assumption.",
                "If the request is missing only non-critical details, provide a practical starter solution first and list assumptions instead of blocking on questions.",
                "Only ask follow-up questions when the missing detail would materially change the hardware design, pin assignment, or implementation path.",
                "The user may attach requirement files such as PDF, DOCX, XLSX, CSV, JSON, TXT, or images. Use them as grounded context when present.",
            ]
        )
    )

    if active_project_dir.strip():
        sections.append(
            "\n".join(
                [
                    f"Current active project directory: {active_project_dir.strip()}",
                    "Use it as context only. Do not assume files exist unless the user or context already established that.",
                ]
            )
        )

    sections.append("Supported chips:\n" + "\n".join(chip_lines))
    if module_lines:
        sections.append("Supported module kinds:\n" + "\n".join(module_lines))
    if retrieved_context.strip():
        sections.append(
            "\n".join(
                [
                    "Relevant local knowledge snippets for this turn:",
                    retrieved_context.strip(),
                ]
            )
        )

    if registry.warnings or registry.errors:
        sections.append(
            "Catalog notes:\n"
            + "\n".join(f"- {item}" for item in [*registry.warnings, *registry.errors])
        )

    return "\n\n".join(section for section in sections if section.strip())


def _build_system_prompt(registry, user_prompt: str = "", retrieved_context: str = "") -> str:
    chip_lines = [f"- {name}" for name in sorted(registry.chips)]
    module_lines = _select_module_prompt_lines(registry, user_prompt, retrieved_context)
    module_intro = "Supported module kinds:"
    if retrieved_context.strip() and module_lines:
        module_intro = "Relevant module kinds recalled from local retrieval:"
    elif retrieved_context.strip():
        module_intro = "Relevant module kinds:"
    return "\n".join(
        [
            "You convert STM32 development requirements into ChipWhisper request JSON.",
            "Return one JSON object first.",
            "Do not use Markdown fences.",
            "Stay grounded in the supported catalog below. Do not invent unsupported chip names or module kinds.",
            "If the user requests unsupported hardware, keep the unsupported details in open_questions or assumptions.",
            "If the user only says STM32 generically and no supported chip is named, you may default chip to STM32F103C8T6 and record that in assumptions.",
            "The JSON object should follow this shape:",
            '{'
            '"chip": "STM32F103C8T6", '
            '"board": "", '
            '"keep_swd": true, '
            '"reserved_pins": [], '
            '"avoid_pins": [], '
            '"modules": [{"kind": "led", "name": "status_led", "options": {}}], '
            '"app_logic_goal": "", '
            '"app_logic": {"AppTop": "", "AppInit": "", "AppLoop": "", "AppCallbacks": ""}, '
            '"generated_files": {}, '
            '"requirements": [], '
            '"assumptions": [], '
            '"open_questions": []'
            '}',
            "Use only supported module kinds in modules[].",
            "Use module options only when they are explicitly useful, for example instance, bus, address, use_int, use_rst, use_bl.",
            'Use board="" when the user did not name a concrete development board.',
            'Use board="chip_only" only when the user explicitly wants a chip-only wiring flow and has provided exact module pin connections.',
            "Do not generate C code in this draft stage.",
            "If the user expects runtime behavior, summarize it in app_logic_goal using one or two short sentences.",
            "Leave every app_logic section empty in the JSON draft. App logic will be generated later after planning and pin assignment.",
            "Supported chips:",
            *chip_lines,
            module_intro,
            *module_lines,
        ]
    )


def _build_user_prompt(
    user_prompt: str,
    active_project_dir: str,
    attachments: List[AttachmentDigest] | None = None,
    retrieved_context: str = "",
    thread_context: str = "",
    revision_feedback: str = "",
) -> str:
    lines = [
        "Generate a request JSON draft for this user requirement:",
        user_prompt,
    ]
    if retrieved_context.strip():
        lines.extend(
            [
                "",
                "The local retriever found these grounded knowledge snippets. Use them when they materially constrain chips, boards, buses, addresses, or module choices:",
                retrieved_context.strip(),
            ]
        )
    if thread_context.strip():
        lines.extend(
            [
                "",
                "This is a follow-up inside an existing desktop project thread. Keep the next JSON draft consistent with the established project context unless the new request explicitly changes it:",
                thread_context.strip(),
            ]
        )
    if revision_feedback.strip():
        lines.extend(
            [
                "",
                "The user reviewed the previous proposal and asked for these changes. Apply them to the next JSON draft instead of ignoring them:",
                revision_feedback.strip(),
            ]
        )
    if attachments:
        lines.extend(
            [
                "",
                "The user also attached requirement files. Read their extracted content and attached images carefully before drafting the JSON.",
                "Keep the JSON grounded in those files instead of inventing hardware details.",
            ]
        )
    if active_project_dir.strip():
        lines.extend(
            [
                "",
                f"Current active project directory: {active_project_dir.strip()}",
                "Use this only as context. Still return a standalone request JSON object.",
            ]
        )
    return "\n".join(lines)


def _extract_json_object(raw_response: str) -> Dict[str, object]:
    text = raw_response.strip()
    if not text:
        raise ValueError("Model returned an empty response; no JSON object was found.")

    candidate_texts = [text]
    fence_start = text.find("```")
    if fence_start >= 0:
        fence_end = text.rfind("```")
        if fence_end > fence_start:
            fenced = text[fence_start + 3 : fence_end].strip()
            if fenced.lower().startswith("json"):
                fenced = fenced[4:].strip()
            candidate_texts.insert(0, fenced)

    for candidate in candidate_texts:
        parsed = _try_parse_json_object(candidate)
        if parsed is not None:
            return parsed

    extracted = _slice_first_braced_object(text)
    parsed = _try_parse_json_object(extracted) if extracted else None
    if parsed is not None:
        return parsed
    raise ValueError("Model response did not contain a valid JSON object.")


def _extract_tagged_app_logic(raw_response: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    for section in ("AppTop", "AppInit", "AppLoop", "AppCallbacks"):
        match = re.search(rf"<{section}>(.*?)</{section}>", raw_response, re.DOTALL)
        if not match:
            continue
        text = _strip_wrapping_code_fence(match.group(1))
        if text:
            sections[section] = text
    return sections


def _select_module_prompt_lines(registry, user_prompt: str, retrieved_context: str, limit: int = 8) -> List[str]:
    all_specs = sorted(registry.modules.values(), key=lambda item: item.key)
    grounded_text = "\n".join(part for part in [user_prompt, retrieved_context] if str(part).strip()).lower()
    if not grounded_text:
        return [f"- {spec.key}: {spec.summary}" for spec in all_specs]

    selected = []
    for spec in all_specs:
        display_name = str(getattr(spec, "display_name", "") or "")
        candidates = [spec.key.lower(), display_name.lower()]
        if any(candidate and candidate in grounded_text for candidate in candidates):
            selected.append(spec)

    if not selected and not retrieved_context.strip():
        return [f"- {spec.key}: {spec.summary}" for spec in all_specs]
    if not selected:
        return ["- Use only module kinds that are explicitly grounded by the retrieved snippets or the user request."]
    return [f"- {spec.key}: {spec.summary}" for spec in selected[:limit]]


def _select_chat_module_prompt_lines(registry, user_prompt: str, retrieved_context: str, limit: int = 16) -> List[str]:
    if not user_prompt.strip() and not retrieved_context.strip():
        return [f"- {key}" for key in sorted(registry.modules)]
    detailed = _select_module_prompt_lines(registry, user_prompt, retrieved_context, limit=limit)
    if detailed and detailed[0].startswith("- Use only module kinds"):
        return detailed
    return [f"- {line[2:].split(':', 1)[0].strip()}" for line in detailed]


def _strip_wrapping_code_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^\s*```[a-zA-Z0-9_+-]*\s*\n", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def _try_parse_json_object(text: str) -> Dict[str, object] | None:
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _slice_first_braced_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def _normalize_request_payload(payload: Dict[str, object], registry) -> tuple[Dict[str, object], List[str]]:
    warnings: List[str] = []
    chip = str(payload.get("chip", "")).strip().upper()
    if not chip:
        chip = "STM32F103C8T6"
        warnings.append("未指定芯片，已按当前内置默认芯片 STM32F103C8T6 起草。")
    elif chip not in registry.chips:
        warnings.append(f"草稿使用了当前未支持的芯片: {chip}")

    board = str(payload.get("board", "")).strip()
    keep_swd = bool(payload.get("keep_swd", True))
    reserved_pins = _normalize_pin_list(payload.get("reserved_pins", []))
    avoid_pins = _normalize_pin_list(payload.get("avoid_pins", []))

    modules: List[Dict[str, object]] = []
    seen_names: set[str] = set()
    for index, item in enumerate(payload.get("modules", []), start=1):
        if not isinstance(item, dict):
            warnings.append(f"modules[{index - 1}] 不是对象，已忽略。")
            continue
        kind = str(item.get("kind", "")).strip()
        if not kind:
            warnings.append(f"modules[{index - 1}] 缺少 kind，已忽略。")
            continue
        if kind not in registry.modules:
            warnings.append(f"草稿使用了当前未支持的模块 kind: {kind}")
        name = str(item.get("name", "")).strip() or f"{kind}_{index}"
        base_name = name
        suffix = 2
        while name in seen_names:
            name = f"{base_name}_{suffix}"
            suffix += 1
        seen_names.add(name)
        options = item.get("options", {})
        if not isinstance(options, dict):
            warnings.append(f"{name}.options 不是对象，已重置为空对象。")
            options = {}
        modules.append({"kind": kind, "name": name, "options": options})

    normalized = {
        "chip": chip,
        "board": board,
        "keep_swd": keep_swd,
        "reserved_pins": reserved_pins,
        "avoid_pins": avoid_pins,
        "modules": modules,
        "app_logic_goal": str(payload.get("app_logic_goal", "")).strip(),
        "app_logic": _normalize_app_logic(payload.get("app_logic", {})),
        "generated_files": normalize_generated_files(payload.get("generated_files", {})),
        "requirements": _normalize_string_list(payload.get("requirements", [])),
        "assumptions": _normalize_string_list(payload.get("assumptions", [])),
        "open_questions": _normalize_string_list(payload.get("open_questions", [])),
    }
    return normalized, warnings


def _normalize_pin_list(value: object) -> List[str]:
    return [str(item).strip().upper() for item in value if str(item).strip()] if isinstance(value, list) else []


def _normalize_string_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_app_logic(value: object) -> Dict[str, str]:
    sections = {
        "AppTop": "",
        "AppInit": "",
        "AppLoop": "",
        "AppCallbacks": "",
    }
    if not isinstance(value, dict):
        return sections
    for key in sections:
        raw = value.get(key, "")
        if raw is None:
            continue
        sections[key] = str(raw).strip()
    return sections
