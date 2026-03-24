from __future__ import annotations

import re
from typing import Dict, List, Sequence


APP_LOGIC_SECTIONS = ("AppTop", "AppInit", "AppLoop", "AppCallbacks")
RUNTIME_EXPECTATION_KEYS = (
    "uart_contains",
    "uart_any_contains",
    "uart_not_contains",
    "uart_sequence",
    "log_contains",
    "log_not_contains",
)


def normalize_app_logic_ir(value: object) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}

    normalized: Dict[str, object] = {}

    macros = _normalize_macros(value.get("macros", []))
    if macros:
        normalized["macros"] = macros

    types = _normalize_types(value.get("types", []))
    if types:
        normalized["types"] = types

    globals_list = _normalize_globals(value.get("globals", []))
    if globals_list:
        normalized["globals"] = globals_list

    helpers = _normalize_helpers(value.get("helpers", []))
    if helpers:
        normalized["helpers"] = helpers

    acceptance = normalize_app_logic_ir_acceptance(value.get("acceptance", {}))
    if acceptance:
        normalized["acceptance"] = acceptance

    init_lines = _normalize_code_lines(value.get("init", []))
    if init_lines:
        normalized["init"] = init_lines

    loop = _normalize_loop(value.get("loop", {}))
    if loop:
        normalized["loop"] = loop

    callbacks = _normalize_code_lines(value.get("callbacks", []))
    if callbacks:
        normalized["callbacks"] = callbacks

    return normalized


def has_nonempty_app_logic_ir(value: object) -> bool:
    return bool(normalize_app_logic_ir(value))


def normalize_app_logic_ir_acceptance(value: object) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}

    normalized: Dict[str, object] = {}
    for key in RUNTIME_EXPECTATION_KEYS:
        items = _normalize_text_lines(value.get(key))
        if items:
            normalized[key] = items

    notes = _normalize_text_lines(value.get("notes"))
    if notes:
        normalized["notes"] = notes
    return normalized


def render_app_logic_from_ir(
    app_logic: Dict[str, str] | None = None,
    app_logic_ir: Dict[str, object] | None = None,
) -> Dict[str, str]:
    resolved = _normalize_app_logic_sections(app_logic)
    normalized_ir = normalize_app_logic_ir(app_logic_ir)
    if not normalized_ir:
        return resolved

    rendered = _render_ir_sections(normalized_ir)
    for section in APP_LOGIC_SECTIONS:
        if not resolved.get(section, "").strip() and rendered.get(section, "").strip():
            resolved[section] = rendered[section]
    return resolved


def _render_ir_sections(app_logic_ir: Dict[str, object]) -> Dict[str, str]:
    sections = {section: "" for section in APP_LOGIC_SECTIONS}

    top_lines: List[str] = []

    # Render macro definitions first
    macro_lines = _render_macros(app_logic_ir.get("macros", []))
    if macro_lines:
        top_lines.extend(macro_lines)

    for type_item in app_logic_ir.get("types", []):
        if not isinstance(type_item, dict):
            continue
        rendered_type = _render_type(type_item)
        if rendered_type:
            if top_lines:
                top_lines.append("")
            top_lines.extend(rendered_type)

    loop = app_logic_ir.get("loop", {})
    if isinstance(loop, dict):
        event_globals = _render_event_flag_globals(loop.get("events", []), app_logic_ir.get("globals", []))
        if event_globals:
            if top_lines:
                top_lines.append("")
            top_lines.extend(event_globals)
        periodic_tasks = loop.get("tasks", [])
        if isinstance(periodic_tasks, list):
            task_var_lines = _render_periodic_task_vars(periodic_tasks)
            if task_var_lines:
                if top_lines:
                    top_lines.append("")
                top_lines.extend(task_var_lines)
        state_machine = loop.get("state_machine", {})
        if isinstance(state_machine, dict):
            state_runtime_lines = _render_state_machine_runtime_vars(state_machine)
            if state_runtime_lines:
                if top_lines:
                    top_lines.append("")
                top_lines.extend(state_runtime_lines)

    global_lines = _render_globals(app_logic_ir.get("globals", []))
    if global_lines:
        if top_lines:
            top_lines.append("")
        top_lines.extend(global_lines)

    # Render helper functions
    helper_lines = _render_helpers(app_logic_ir.get("helpers", []))
    if helper_lines:
        if top_lines:
            top_lines.append("")
        top_lines.extend(helper_lines)

    init_lines = _indent_code_lines(_normalize_code_lines(app_logic_ir.get("init", [])), "    ")
    if isinstance(loop, dict):
        state_machine = loop.get("state_machine", {})
        if isinstance(state_machine, dict):
            state_init_lines = _render_state_machine_init_lines(state_machine)
            if state_init_lines:
                init_lines = [*state_init_lines, *([""] if init_lines else []), *init_lines]
    callback_lines = _indent_code_lines(_normalize_code_lines(app_logic_ir.get("callbacks", [])), "")
    if isinstance(loop, dict):
        event_callback_lines = _render_event_callbacks(loop.get("events", []))
        if event_callback_lines:
            if callback_lines:
                callback_lines.append("")
            callback_lines.extend(event_callback_lines)

    loop_lines: List[str] = []
    if isinstance(loop, dict):
        loop_lines.extend(_indent_code_lines(_normalize_code_lines(loop.get("always", [])), "    "))
        if loop_lines and (loop.get("tasks") or loop.get("state_machine")):
            loop_lines.append("")
        loop_lines.extend(_render_loop_tasks(loop.get("tasks", [])))
        state_machine_lines = _render_state_machine(loop.get("state_machine", {}), loop.get("events", []))
        if state_machine_lines:
            if loop_lines:
                loop_lines.append("")
            loop_lines.extend(state_machine_lines)

    sections["AppTop"] = "\n".join(top_lines).strip()
    sections["AppInit"] = "\n".join(init_lines).strip()
    sections["AppLoop"] = "\n".join(loop_lines).strip()
    sections["AppCallbacks"] = "\n".join(callback_lines).strip()
    return sections


def _render_type(type_item: Dict[str, object]) -> List[str]:
    kind = str(type_item.get("kind", "")).strip().lower()
    if kind == "enum":
        return _render_enum_type(type_item)
    if kind == "struct":
        return _render_struct_type(type_item)
    return []


def _render_enum_type(type_item: Dict[str, object]) -> List[str]:
    name = str(type_item.get("name", "")).strip()
    values = type_item.get("values", [])
    if not name or not isinstance(values, list) or not values:
        return []

    lines = [
        "typedef enum",
        "{",
    ]
    rendered_values: List[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        value_name = str(item.get("name", "")).strip()
        value_init = str(item.get("value", "")).strip()
        if not value_name:
            continue
        rendered = f"    {value_name}"
        if value_init:
            rendered += f" = {value_init}"
        rendered_values.append(rendered + ",")
    if not rendered_values:
        return []
    lines.extend(rendered_values)
    lines.extend(
        [
            f"}} {name};",
        ]
    )
    return lines


def _render_struct_type(type_item: Dict[str, object]) -> List[str]:
    name = str(type_item.get("name", "")).strip()
    fields = type_item.get("fields", [])
    if not name or not isinstance(fields, list) or not fields:
        return []

    lines = [
        "typedef struct",
        "{",
    ]
    for field in fields:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("name", "")).strip()
        field_type = str(field.get("type", "")).strip()
        if not field_name or not field_type:
            continue
        array_size = str(field.get("array_size", "")).strip()
        comment = str(field.get("comment", "")).strip()
        line = f"    {field_type} {field_name}"
        if array_size:
            line += f"[{array_size}]"
        line += ";"
        if comment:
            line += f"  /* {comment} */"
        lines.append(line)
    lines.append(f"}} {name};")
    return lines


def _render_globals(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    lines: List[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        type_name = str(item.get("type", "")).strip()
        init_value = str(item.get("init", "")).strip()
        if not name or not type_name:
            continue
        line = f"static {type_name} {name}"
        if init_value:
            line += f" = {init_value}"
        line += ";"
        lines.append(line)
    return lines


def _render_periodic_task_vars(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    lines: List[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        every_ms = _coerce_positive_int(item.get("every_ms"))
        if every_ms <= 0:
            continue
        task_name = str(item.get("name", "")).strip() or "task"
        lines.append(f"static uint32_t {_task_last_run_var(task_name)} = 0U;")
    return lines


def _render_loop_tasks(value: object) -> List[str]:
    if not isinstance(value, list):
        return []

    lines: List[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        run_lines = _normalize_code_lines(item.get("run", []))
        if not run_lines:
            continue
        every_ms = _coerce_positive_int(item.get("every_ms"))
        task_name = str(item.get("name", "")).strip() or "task"
        if every_ms > 0:
            timestamp_var = _task_last_run_var(task_name)
            lines.extend(
                [
                    f"    if ((HAL_GetTick() - {timestamp_var}) >= {every_ms}U) {{",
                    f"        {timestamp_var} = HAL_GetTick();",
                    *_indent_code_lines(run_lines, "        "),
                    "    }",
                ]
            )
        else:
            lines.extend(_indent_code_lines(run_lines, "    "))
        lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _render_state_machine(value: object, events: object = None) -> List[str]:
    if not isinstance(value, dict):
        return []
    state_var = str(value.get("state_var", "")).strip()
    states = value.get("states", [])
    if not state_var or not isinstance(states, list) or not states:
        return []

    lines = [
        f"    switch ({state_var}) {{",
    ]
    any_state = False
    event_map = _index_loop_events(events)
    for state in states:
        if not isinstance(state, dict):
            continue
        state_name = str(state.get("name", "")).strip()
        run_lines = _normalize_code_lines(state.get("run", []))
        transition_lines = _render_state_transitions(state_var, value, state.get("transitions", []), event_map)
        if not state_name:
            continue
        any_state = True
        lines.append(f"        case {state_name}:")
        if run_lines:
            lines.extend(_indent_code_lines(run_lines, "            "))
        if transition_lines:
            if run_lines:
                lines.append("")
            lines.extend(transition_lines)
        if not run_lines and not transition_lines:
            lines.append("            break;")
            continue
        if bool(state.get("fallthrough", False)):
            lines.append("            /* fallthrough */")
        else:
            lines.append("            break;")
        lines.append("")

    default_lines = _normalize_code_lines(value.get("default", []))
    lines.append("        default:")
    if default_lines:
        lines.extend(_indent_code_lines(default_lines, "            "))
    lines.append("            break;")
    lines.append("    }")
    if not any_state:
        return []
    return lines


def _render_state_transitions(
    state_var: str,
    state_machine: Dict[str, object],
    value: object,
    event_map: Dict[str, Dict[str, object]] | None = None,
) -> List[str]:
    if not isinstance(value, list):
        return []

    lines: List[str] = []
    entered_var = _state_machine_entered_var(state_machine)
    retry_var = _state_machine_retry_var(state_machine)
    resolved_event_map = event_map or {}
    for item in value:
        if not isinstance(item, dict):
            continue
        guard = str(item.get("guard", "") or item.get("condition", "") or item.get("when", "")).strip()
        raw_event = str(item.get("event", "") or item.get("trigger", "")).strip()
        target = str(item.get("target", "")).strip()
        actions = _normalize_code_lines(item.get("actions", []))
        comment = str(item.get("comment", "")).strip()
        after_ms = _coerce_positive_int(item.get("after_ms", item.get("timeout_ms", 0)))
        reset_timer = bool(item.get("reset_timer", True))
        max_retries = _coerce_positive_int(item.get("max_retries", item.get("retry_limit", 0)))
        retry_target = str(item.get("retry_target", "")).strip()
        retry_actions = _normalize_code_lines(item.get("retry_actions", []))
        failure_target = str(item.get("failure_target", "")).strip()
        failure_actions = _normalize_code_lines(item.get("failure_actions", []))
        event_condition, event_clear_actions = _resolve_named_event(raw_event, resolved_event_map)
        event = event_condition or raw_event
        if not guard and not event and not target and not actions and after_ms <= 0:
            continue
        if comment:
            lines.append(f"            /* {comment} */")
        condition = _render_transition_condition(guard=guard, event=event, after_ms=after_ms, entered_var=entered_var)
        if condition:
            lines.append(f"            if ({condition}) {{")
        else:
            lines.append("            {")
        lines.extend(_indent_code_lines(event_clear_actions, "                "))
        if retry_var and max_retries > 0:
            lines.append(f"                if ({retry_var} < {max_retries}U) {{")
            lines.append(f"                    {retry_var}++;")
            lines.extend(_indent_code_lines(retry_actions or actions, "                    "))
            if retry_target:
                lines.append(f"                    {state_var} = {retry_target};")
            if entered_var and reset_timer:
                lines.append(f"                    {entered_var} = HAL_GetTick();")
            lines.append("                    break;")
            lines.append("                }")
            lines.append("")
            lines.append(f"                {retry_var} = 0U;")
            lines.extend(_indent_code_lines(failure_actions, "                "))
            if failure_target:
                lines.append(f"                {state_var} = {failure_target};")
                if entered_var and reset_timer:
                    lines.append(f"                {entered_var} = HAL_GetTick();")
            lines.append("                break;")
        else:
            if retry_var and target:
                lines.append(f"                {retry_var} = 0U;")
            lines.extend(_indent_code_lines(actions, "                "))
            if target:
                lines.append(f"                {state_var} = {target};")
                if entered_var and reset_timer:
                    lines.append(f"                {entered_var} = HAL_GetTick();")
            lines.append("                break;")
        lines.append("            }")
        lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _render_transition_condition(
    *,
    guard: str,
    event: str,
    after_ms: int,
    entered_var: str,
) -> str:
    conditions: List[str] = []
    if after_ms > 0 and entered_var:
        conditions.append(f"((HAL_GetTick() - {entered_var}) >= {after_ms}U)")
    if event:
        conditions.append(_format_condition_term(event))
    if guard:
        conditions.append(_format_condition_term(guard))
    return " && ".join(conditions)


def _format_condition_term(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("(") and text.endswith(")"):
        return text
    complex_tokens = ("&&", "||", "==", "!=", ">=", "<=", ">", "<")
    if any(token in text for token in complex_tokens):
        return f"({text})"
    return text


def _render_state_machine_runtime_vars(value: object) -> List[str]:
    if not isinstance(value, dict):
        return []
    lines: List[str] = []
    entered_var = _state_machine_entered_var(value)
    if entered_var:
        lines.append(f"static uint32_t {entered_var} = 0U;")
    retry_var = _state_machine_retry_var(value)
    if retry_var:
        lines.append(f"static uint32_t {retry_var} = 0U;")
    return lines


def _render_state_machine_init_lines(value: object) -> List[str]:
    if not isinstance(value, dict):
        return []
    lines: List[str] = []
    entered_var = _state_machine_entered_var(value)
    if entered_var:
        lines.append(f"    {entered_var} = HAL_GetTick();")
    retry_var = _state_machine_retry_var(value)
    if retry_var:
        lines.append(f"    {retry_var} = 0U;")
    return lines


def _normalize_types(value: object) -> List[Dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip().lower()
        name = str(item.get("name", "")).strip()
        if kind == "enum":
            values = item.get("values", [])
            if not name or not isinstance(values, list) or not values:
                continue
            normalized_values: List[Dict[str, str]] = []
            for raw_value in values:
                if isinstance(raw_value, dict):
                    value_name = str(raw_value.get("name", "")).strip()
                    value_init = str(raw_value.get("value", "")).strip()
                else:
                    value_name = str(raw_value).strip()
                    value_init = ""
                if not value_name:
                    continue
                normalized_values.append({"name": value_name, "value": value_init})
            if normalized_values:
                normalized.append({"kind": "enum", "name": name, "values": normalized_values})
        elif kind == "struct":
            fields = item.get("fields", [])
            if not name or not isinstance(fields, list) or not fields:
                continue
            normalized_fields: List[Dict[str, str]] = []
            for raw_field in fields:
                if not isinstance(raw_field, dict):
                    continue
                field_name = str(raw_field.get("name", "")).strip()
                field_type = str(raw_field.get("type", "")).strip()
                if field_name and field_type:
                    normalized_fields.append({
                        "name": field_name,
                        "type": field_type,
                        "array_size": str(raw_field.get("array_size", "")).strip(),
                        "comment": str(raw_field.get("comment", "")).strip(),
                    })
            if normalized_fields:
                normalized.append({"kind": "struct", "name": name, "fields": normalized_fields})
    return normalized


def _normalize_globals(value: object) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        type_name = str(item.get("type", "")).strip()
        init_value = str(item.get("init", "")).strip()
        if not name or not type_name:
            continue
        normalized.append(
            {
                "name": name,
                "type": type_name,
                "init": init_value,
            }
        )
    return normalized


def _normalize_loop(value: object) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}

    normalized: Dict[str, object] = {}
    always = _normalize_code_lines(value.get("always", []))
    if always:
        normalized["always"] = always

    tasks = _normalize_tasks(value.get("tasks", []))
    if tasks:
        normalized["tasks"] = tasks

    events = _normalize_events(value.get("events", []))
    if events:
        normalized["events"] = events

    state_machine = _normalize_state_machine(value.get("state_machine", {}))
    if state_machine:
        normalized["state_machine"] = state_machine

    return normalized


def _normalize_tasks(value: object) -> List[Dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip() or "task"
        run_lines = _normalize_code_lines(item.get("run", []))
        if not run_lines:
            continue
        normalized.append(
            {
                "name": name,
                "every_ms": _coerce_positive_int(
                    item.get("every_ms", item.get("interval_ms", item.get("period_ms", 0)))
                ),
                "run": run_lines,
            }
        )
    return normalized


def _normalize_events(value: object) -> List[Dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        flag_var = str(item.get("flag_var", "") or item.get("flag", "")).strip()
        flag_type = str(item.get("flag_type", "")).strip() or "volatile uint8_t"
        flag_init = str(item.get("flag_init", "")).strip() or "0U"
        condition = str(item.get("condition", "") or item.get("expression", "") or item.get("when", "")).strip()
        if not condition and flag_var:
            condition = f"{flag_var} != 0U"
        clear_actions = _normalize_code_lines(
            item.get("clear_actions", item.get("clear", item.get("consume", [])))
        )
        if not clear_actions and flag_var:
            clear_actions = [f"{flag_var} = 0U;"]
        callbacks = _normalize_event_callbacks(item.get("callbacks", item.get("sources", [])))
        comment = str(item.get("comment", "")).strip()
        if not name or not condition:
            continue
        event_payload: Dict[str, object] = {
            "name": name,
            "condition": condition,
        }
        if flag_var:
            event_payload["flag_var"] = flag_var
            event_payload["flag_type"] = flag_type
            event_payload["flag_init"] = flag_init
        if clear_actions:
            event_payload["clear_actions"] = clear_actions
        if callbacks:
            event_payload["callbacks"] = callbacks
        if comment:
            event_payload["comment"] = comment
        normalized.append(event_payload)
    return normalized


def _normalize_event_callbacks(value: object) -> List[Dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        signature = str(item.get("signature", "") or item.get("function", "")).strip()
        body = _normalize_code_lines(item.get("body", item.get("run", [])))
        comment = str(item.get("comment", "")).strip()
        if not signature or not body:
            continue
        callback_payload: Dict[str, object] = {
            "signature": signature,
            "body": body,
        }
        if comment:
            callback_payload["comment"] = comment
        normalized.append(callback_payload)
    return normalized


def _normalize_state_machine(value: object) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}

    state_var = str(value.get("state_var", "")).strip()
    states = value.get("states", [])
    if not state_var or not isinstance(states, list):
        return {}

    normalized_states: List[Dict[str, object]] = []
    for item in states:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        run_lines = _normalize_code_lines(item.get("run", []))
        transitions = _normalize_transitions(item.get("transitions", []))
        if not name:
            continue
        state_payload: Dict[str, object] = {
            "name": name,
            "run": run_lines,
            "fallthrough": bool(item.get("fallthrough", False)),
        }
        if transitions:
            state_payload["transitions"] = transitions
        normalized_states.append(state_payload)

    if not normalized_states:
        return {}

    normalized: Dict[str, object] = {
        "state_var": state_var,
        "states": normalized_states,
    }
    entered_at_var = str(value.get("entered_at_var", "")).strip()
    if entered_at_var:
        normalized["entered_at_var"] = entered_at_var
    default_lines = _normalize_code_lines(value.get("default", []))
    if default_lines:
        normalized["default"] = default_lines
    return normalized


def _normalize_transitions(value: object) -> List[Dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        guard = str(item.get("guard", "") or item.get("condition", "") or item.get("when", "")).strip()
        event = str(item.get("event", "") or item.get("trigger", "")).strip()
        target = str(item.get("target", "")).strip()
        actions = _normalize_code_lines(item.get("actions", []))
        retry_target = str(item.get("retry_target", "")).strip()
        retry_actions = _normalize_code_lines(item.get("retry_actions", []))
        failure_target = str(item.get("failure_target", "")).strip()
        failure_actions = _normalize_code_lines(item.get("failure_actions", []))
        comment = str(item.get("comment", "")).strip()
        after_ms = _coerce_positive_int(item.get("after_ms", item.get("timeout_ms", 0)))
        reset_timer = bool(item.get("reset_timer", True))
        max_retries = _coerce_positive_int(item.get("max_retries", item.get("retry_limit", 0)))
        if (
            not guard
            and not event
            and not target
            and not actions
            and not retry_target
            and not retry_actions
            and not failure_target
            and not failure_actions
            and after_ms <= 0
            and max_retries <= 0
        ):
            continue
        transition: Dict[str, object] = {
            "guard": guard,
            "event": event,
            "after_ms": after_ms,
            "target": target,
            "actions": actions,
            "reset_timer": reset_timer,
        }
        if max_retries > 0:
            transition["max_retries"] = max_retries
        if retry_target:
            transition["retry_target"] = retry_target
        if retry_actions:
            transition["retry_actions"] = retry_actions
        if failure_target:
            transition["failure_target"] = failure_target
        if failure_actions:
            transition["failure_actions"] = failure_actions
        if comment:
            transition["comment"] = comment
        normalized.append(transition)
    return normalized


def _normalize_code_lines(value: object) -> List[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, list):
        return []

    normalized: List[str] = []
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("code", "")).strip()
        else:
            text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_text_lines(value: object) -> List[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []

    normalized: List[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _indent_code_lines(lines: Sequence[str], indent: str) -> List[str]:
    rendered: List[str] = []
    for block in lines:
        text = str(block).replace("\r\n", "\n").strip("\n")
        if not text:
            continue
        for line in text.splitlines():
            rendered.append(f"{indent}{line.rstrip()}" if line.strip() else "")
    return rendered


def _normalize_app_logic_sections(value: Dict[str, str] | None) -> Dict[str, str]:
    sections = {section: "" for section in APP_LOGIC_SECTIONS}
    if not isinstance(value, dict):
        return sections
    for section in APP_LOGIC_SECTIONS:
        sections[section] = str(value.get(section, "") or "").strip()
    return sections


def _render_event_flag_globals(events: object, explicit_globals: object) -> List[str]:
    if not isinstance(events, list):
        return []

    explicit_names = {
        str(item.get("name", "")).strip()
        for item in explicit_globals
        if isinstance(explicit_globals, list) and isinstance(item, dict)
    }
    lines: List[str] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        flag_var = str(item.get("flag_var", "")).strip()
        flag_type = str(item.get("flag_type", "")).strip()
        flag_init = str(item.get("flag_init", "")).strip()
        if not flag_var or flag_var in explicit_names:
            continue
        line = f"static {flag_type} {flag_var}"
        if flag_init:
            line += f" = {flag_init}"
        line += ";"
        if line not in lines:
            lines.append(line)
    return lines


def _render_event_callbacks(events: object) -> List[str]:
    if not isinstance(events, list):
        return []

    grouped: Dict[str, List[List[str]]] = {}
    signature_order: List[str] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("name", "")).strip() or "event"
        callbacks = item.get("callbacks", [])
        if not isinstance(callbacks, list):
            continue
        for callback in callbacks:
            if not isinstance(callback, dict):
                continue
            signature = str(callback.get("signature", "")).strip()
            body = _normalize_code_lines(callback.get("body", []))
            comment = str(callback.get("comment", "")).strip()
            if not signature or not body:
                continue
            if signature not in grouped:
                grouped[signature] = []
                signature_order.append(signature)
            block: List[str] = [f"    /* event: {event_name} */"]
            if comment:
                block.append(f"    /* {comment} */")
            block.extend(_indent_code_lines(body, "    "))
            grouped[signature].append(block)

    lines: List[str] = []
    for signature in signature_order:
        blocks = grouped.get(signature, [])
        if not blocks:
            continue
        lines.append(signature)
        lines.append("{")
        first_block = True
        for block in blocks:
            if not first_block:
                lines.append("")
            lines.extend(block)
            first_block = False
        lines.append("}")
        lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _index_loop_events(value: object) -> Dict[str, Dict[str, object]]:
    if not isinstance(value, list):
        return {}
    indexed: Dict[str, Dict[str, object]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        condition = str(item.get("condition", "")).strip()
        if not name or not condition:
            continue
        indexed[name] = item
    return indexed


def _resolve_named_event(
    value: str,
    event_map: Dict[str, Dict[str, object]],
) -> tuple[str, List[str]]:
    token = str(value).strip()
    if not token:
        return "", []
    event = event_map.get(token)
    if not isinstance(event, dict):
        return token, []
    return (
        str(event.get("condition", "")).strip(),
        _normalize_code_lines(event.get("clear_actions", [])),
    )


def _task_last_run_var(task_name: str) -> str:
    return f"g_app_task_{_slugify(task_name)}_last_run_ms"


def _state_machine_entered_var(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    explicit = str(value.get("entered_at_var", "")).strip()
    if explicit:
        return explicit
    if not _state_machine_uses_entry_time(value):
        return ""
    state_var = str(value.get("state_var", "")).strip()
    if not state_var:
        return ""
    base = _slugify(state_var)
    if base.startswith("g_"):
        return f"{base}_entered_ms"
    return f"g_{base}_entered_ms"


def _state_machine_uses_entry_time(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    states = value.get("states", [])
    if not isinstance(states, list):
        return False
    for state in states:
        if not isinstance(state, dict):
            continue
        transitions = state.get("transitions", [])
        if not isinstance(transitions, list):
            continue
        for transition in transitions:
            if not isinstance(transition, dict):
                continue
            if _coerce_positive_int(transition.get("after_ms", transition.get("timeout_ms", 0))) > 0:
                return True
    return False


def _state_machine_retry_var(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    explicit = str(value.get("retry_counter_var", "")).strip()
    if explicit:
        return explicit
    if not _state_machine_uses_retry_counter(value):
        return ""
    state_var = str(value.get("state_var", "")).strip()
    if not state_var:
        return ""
    base = _slugify(state_var)
    if base.startswith("g_"):
        return f"{base}_retry_count"
    return f"g_{base}_retry_count"


def _state_machine_uses_retry_counter(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    states = value.get("states", [])
    if not isinstance(states, list):
        return False
    for state in states:
        if not isinstance(state, dict):
            continue
        transitions = state.get("transitions", [])
        if not isinstance(transitions, list):
            continue
        for transition in transitions:
            if not isinstance(transition, dict):
                continue
            if _coerce_positive_int(transition.get("max_retries", transition.get("retry_limit", 0))) > 0:
                return True
    return False


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip()).strip("_").lower()
    return normalized or "task"


def _coerce_positive_int(value: object) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _normalize_macros(value: object) -> List[Dict[str, str]]:
    """Normalize macros list: [{name, value, comment?}]"""
    if not isinstance(value, list):
        return []
    normalized: List[Dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        macro_value = str(item.get("value", "")).strip()
        if not name:
            continue
        normalized.append({
            "name": name,
            "value": macro_value,
            "comment": str(item.get("comment", "")).strip(),
        })
    return normalized


def _render_macros(value: object) -> List[str]:
    """Render #define lines from normalized macros."""
    if not isinstance(value, list):
        return []
    lines: List[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        macro_value = str(item.get("value", "")).strip()
        comment = str(item.get("comment", "")).strip()
        if not name:
            continue
        line = f"#define {name}"
        if macro_value:
            line += f"  {macro_value}"
        if comment:
            line += f"  /* {comment} */"
        lines.append(line)
    return lines


def _normalize_helpers(value: object) -> List[Dict[str, object]]:
    """Normalize helper function declarations: [{signature, body, comment?}]"""
    if not isinstance(value, list):
        return []
    normalized: List[Dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        signature = str(item.get("signature", "")).strip()
        body = _normalize_code_lines(item.get("body", []))
        if not signature or not body:
            continue
        helper: Dict[str, object] = {
            "signature": signature,
            "body": body,
        }
        comment = str(item.get("comment", "")).strip()
        if comment:
            helper["comment"] = comment
        normalized.append(helper)
    return normalized


def _render_helpers(value: object) -> List[str]:
    """Render static helper function definitions."""
    if not isinstance(value, list):
        return []
    lines: List[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        signature = str(item.get("signature", "")).strip()
        body = _normalize_code_lines(item.get("body", []))
        if not signature or not body:
            continue
        comment = str(item.get("comment", "")).strip()
        if comment:
            lines.append(f"/* {comment} */")
        lines.append(signature)
        lines.append("{")
        lines.extend(_indent_code_lines(body, "    "))
        lines.append("}")
        lines.append("")
    while lines and not lines[-1].strip():
        lines.pop()
    return lines

