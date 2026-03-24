from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from .keil_generator_hal import _uart_handle_name
from .planner import PlanResult


APP_LOGIC_PLACEHOLDERS = {
    "AppTop": "/* APP_LOGIC_PLACEHOLDER:AppTop */",
    "AppInit": "/* APP_LOGIC_PLACEHOLDER:AppInit */",
    "AppLoop": "/* APP_LOGIC_PLACEHOLDER:AppLoop */",
    "AppCallbacks": "/* APP_LOGIC_PLACEHOLDER:AppCallbacks */",
}


def _render_app_main_h() -> str:
    return """#ifndef __APP_MAIN_H
#define __APP_MAIN_H

/* 应用层头文件：
 * - App_Init() 负责业务初始化。
 * - App_Loop() 负责主循环中的应用调度。
 */

void App_Init(void);
void App_Loop(void);

#endif
"""

def _render_app_main_c(plan: PlanResult, app_headers: Iterable[str], module_headers: Iterable[str]) -> str:
    includes = ['#include "app_main.h"', '#include "main.h"', '#include "peripherals.h"']
    for header in sorted(set(app_headers)):
        includes.append(f'#include "{header}"')
    for header in sorted(set(module_headers)):
        includes.append(f'#include "{header}"')

    lines = [
        "/*",
        " * 应用层实现文件：",
        " * 1. 放置用户业务逻辑、软件中间件调度以及回调函数。",
        " * 2. 建议优先在 USER CODE 区域中补充业务代码，避免与重新生成冲突。",
        " */",
        "",
        *includes,
        "",
    ]
    top_lines = _render_app_top_lines_v2(plan)
    lines.extend(
        [
            "/* 文件级静态变量、局部工具函数等可放在这里。 */",
            "/* USER CODE BEGIN AppTop */",
            *top_lines,
            *([""] if top_lines else []),
            APP_LOGIC_PLACEHOLDERS["AppTop"],
            "/* USER CODE END AppTop */",
            "",
        ]
    )

    lines.extend(
        [
            "void App_Init(void)",
            "{",
            "    /* 应用层初始化入口：先执行用户逻辑，再初始化模块级软件组件。 */",
            "    /* USER CODE BEGIN AppInit */",
            f"    {APP_LOGIC_PLACEHOLDERS['AppInit']}",
            "    /* USER CODE END AppInit */",
            "",
        ]
    )
    init_lines = _render_app_init_calls_v2(plan)
    if init_lines:
        lines.extend(init_lines)
    else:
        lines.append("    /* 当前规划没有额外的软件模块初始化需求。 */")
    loop_lines = _render_app_loop_lines_v2(plan)
    callback_lines = _render_app_callback_lines_v2(plan)
    lines.extend(
        [
            "}",
            "",
            "void App_Loop(void)",
            "{",
            "    /* 主循环中的应用调度入口：建议保持非阻塞。 */",
            "    /* USER CODE BEGIN AppLoop */",
            *loop_lines,
            *([""] if loop_lines else []),
            f"    {APP_LOGIC_PLACEHOLDERS['AppLoop']}",
            "    /* USER CODE END AppLoop */",
            "",
        ]
    )
    lines.extend(
        [
            "}",
            "",
            "/* HAL 回调、模块桥接回调等建议集中放在这里。 */",
            "/* USER CODE BEGIN AppCallbacks */",
            *callback_lines,
            *([""] if callback_lines else []),
            APP_LOGIC_PLACEHOLDERS["AppCallbacks"],
            "/* USER CODE END AppCallbacks */",
            "",
        ]
    )
    return _inject_project_app_logic("\n".join(lines), plan)

def _inject_project_app_logic(content: str, plan: PlanResult) -> str:
    build = plan.project_ir.get("build", {})
    app_logic = build.get("app_logic", {}) if isinstance(build, dict) else {}
    if not isinstance(app_logic, dict):
        return content
    updated = content
    for section, placeholder in APP_LOGIC_PLACEHOLDERS.items():
        value = app_logic.get(section, "")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            replacement = text.replace("\r\n", "\n")
            updated = updated.replace(placeholder, replacement)
    return updated

def _render_app_top_lines_v2(plan: PlanResult) -> List[str]:
    lines: List[str] = []
    for module in _ordered_project_modules(plan, phase="init"):
        template_lines = _render_pack_module_section_lines(plan, module, "c_top_template")
        if template_lines:
            if lines:
                lines.append("")
            lines.extend(template_lines)
    return lines

def _render_app_init_calls_v2(plan: PlanResult) -> List[str]:
    lines: List[str] = []
    for module in _ordered_project_modules(plan, phase="init"):
        name = str(module.get("name", ""))
        pack_template_lines = _render_pack_module_section_lines(plan, module, "c_init_template")
        if pack_template_lines is not None:
            lines.extend(pack_template_lines)
            continue
        lines.append(f"    /* 模块初始化占位：{name} ({module.get('kind', '')}) */")
    return lines

def _render_app_loop_lines_v2(plan: PlanResult) -> List[str]:
    lines: List[str] = []
    for module in _ordered_project_modules(plan, phase="loop"):
        template_lines = _render_pack_module_section_lines(plan, module, "c_loop_template")
        if template_lines:
            if lines:
                lines.append("")
            lines.extend(template_lines)
    return lines

def _render_app_callback_lines_v2(plan: PlanResult) -> List[str]:
    lines: List[str] = []
    for module in _ordered_project_modules(plan, phase="init"):
        template_lines = _render_pack_module_section_lines(plan, module, "c_callbacks_template")
        if template_lines:
            if lines:
                lines.append("")
            lines.extend(template_lines)
    return lines

def _ordered_project_modules(plan: PlanResult, phase: str) -> List[Dict[str, object]]:
    modules = [
        module
        for module in plan.project_ir.get("modules", [])
        if isinstance(module, dict)
    ]
    if len(modules) <= 1:
        return modules

    name_to_module = {
        str(module.get("name", "")).strip(): module
        for module in modules
        if str(module.get("name", "")).strip()
    }
    kind_to_names: Dict[str, List[str]] = {}
    dependencies: Dict[str, List[str]] = {}
    indegree: Dict[str, int] = {}

    for name, module in name_to_module.items():
        kind = str(module.get("kind", "")).strip()
        if kind:
            kind_to_names.setdefault(kind, []).append(name)

    for name, module in name_to_module.items():
        dependency_names: List[str] = []
        for dependency in module.get("depends_on", []):
            dependency_key = str(dependency).strip()
            if not dependency_key:
                continue
            if dependency_key in name_to_module and dependency_key != name:
                dependency_names.append(dependency_key)
                continue
            for matched_name in kind_to_names.get(dependency_key, []):
                if matched_name != name and matched_name not in dependency_names:
                    dependency_names.append(matched_name)
        dependencies[name] = dependency_names
        indegree[name] = len(dependency_names)

    ordered_names: List[str] = []
    ready = [name for name, degree in indegree.items() if degree == 0]
    while ready:
        ready.sort(key=lambda item: (_module_phase_priority(name_to_module[item], phase), item))
        current = ready.pop(0)
        ordered_names.append(current)
        for candidate, dependency_names in dependencies.items():
            if current not in dependency_names:
                continue
            indegree[candidate] -= 1
            if indegree[candidate] == 0:
                ready.append(candidate)

    if len(ordered_names) != len(name_to_module):
        remaining = [
            name
            for name in name_to_module
            if name not in ordered_names
        ]
        remaining.sort(key=lambda item: (_module_phase_priority(name_to_module[item], phase), item))
        ordered_names.extend(remaining)

    return [name_to_module[name] for name in ordered_names]

def _module_phase_priority(module: Dict[str, object], phase: str) -> int:
    key = "loop_priority" if phase == "loop" else "init_priority"
    try:
        return int(module.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0

def _render_pack_module_section_lines(
    plan: PlanResult,
    module: Dict[str, object],
    key: str,
) -> List[str] | None:
    template_lines = module.get(key, [])
    if not isinstance(template_lines, list) or not template_lines:
        return None

    context = _build_module_template_context(plan, module)
    return [_replace_pack_tokens(str(line), context) for line in template_lines]

def _build_module_template_context(plan: PlanResult, module: Dict[str, object]) -> Dict[str, str]:
    name = str(module.get("name", "")).strip()
    kind = str(module.get("kind", "")).strip()
    context: Dict[str, str] = {
        "module_name": name,
        "module_kind": kind,
        "module_identifier": _app_static_identifier(name, "module"),
    }

    options = module.get("options", {})
    if isinstance(options, dict):
        for key, value in options.items():
            normalized_key = _template_token_name(str(key))
            if isinstance(value, (str, int, float, bool)):
                stringified = _stringify_template_value(value)
                context[f"option_{normalized_key}"] = stringified
                context[f"option_{normalized_key}_brackets"] = f"[{stringified}]"

    for item in plan.assignments:
        if item.module != name:
            continue
        signal_key = _template_token_name(item.signal)
        prefix = _macro_name(name, item.signal)
        context[signal_key] = item.pin
        context[f"{signal_key}_pin"] = item.pin
        context[f"{signal_key}_port_macro"] = f"{prefix}_PORT"
        context[f"{signal_key}_pin_macro"] = f"{prefix}_PIN"

    i2c_binding = _i2c_binding_for_module(plan, name)
    if i2c_binding is not None:
        handle, address_macro = i2c_binding
        context["i2c_handle"] = handle
        context["i2c_address_macro"] = address_macro

    uart_handle = _uart_handle_for_module(plan, name)
    if uart_handle is not None:
        context["uart_handle"] = uart_handle

    pwm_binding = _pwm_binding_for_module(plan, name)
    if pwm_binding is not None:
        handle, channel = pwm_binding
        context["pwm_handle"] = handle
        context["pwm_channel"] = channel

    for dependency in module.get("depends_on", []):
        dependency_key = str(dependency).strip()
        if not dependency_key:
            continue
        dependency_modules = _dependency_modules(plan, dependency_key)
        if not dependency_modules:
            continue
        _inject_module_dependency_context(
            plan,
            context,
            dependency_modules[0],
            token_prefix=f"dep_{_template_token_name(dependency_key)}",
        )

    return context

def _replace_pack_tokens(text: str, context: Dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        default_value = match.group(2)
        if key in context:
            return context[key]
        if default_value is not None:
            return default_value
        return match.group(0)

    return re.sub(r"\[\[([A-Za-z0-9_]+)(?:\|(.*?))?\]\]", replace, text)

def _template_token_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    return normalized.strip("_").lower() or "value"

def _stringify_template_value(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)

def _uart_handle_for_module(plan: PlanResult, module_name: str) -> str | None:
    for item in plan.assignments:
        if item.module != module_name or "." not in item.signal:
            continue
        prefix, _signal = item.signal.split(".", 1)
        if prefix.upper().startswith("USART"):
            return _uart_handle_name(prefix.upper())
    return None

def _first_debug_uart_handle(plan: PlanResult) -> str | None:
    module_name = _first_module_name(plan, "uart_debug")
    if module_name is None:
        return None
    return _uart_handle_for_module(plan, module_name)

def _first_module_name(plan: PlanResult, kind: str) -> str | None:
    for module in plan.project_ir.get("modules", []):
        if str(module.get("kind", "")) == kind:
            return str(module.get("name", ""))
    return None

def _module_names(plan: PlanResult, kind: str) -> List[str]:
    names: List[str] = []
    for module in plan.project_ir.get("modules", []):
        if str(module.get("kind", "")) == kind:
            names.append(str(module.get("name", "")))
    return names

def _module_record_by_name(plan: PlanResult, module_name: str) -> Dict[str, object] | None:
    for module in plan.project_ir.get("modules", []):
        if str(module.get("name", "")) == module_name:
            return module if isinstance(module, dict) else None
    return None

def _module_records_by_kind(plan: PlanResult, kind: str) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for module in plan.project_ir.get("modules", []):
        if not isinstance(module, dict):
            continue
        if str(module.get("kind", "")) != kind:
            continue
        records.append(module)
    return records

def _dependency_modules(plan: PlanResult, dependency_key: str) -> List[Dict[str, object]]:
    record = _module_record_by_name(plan, dependency_key)
    if record is not None:
        return [record]
    return _module_records_by_kind(plan, dependency_key)

def _inject_module_dependency_context(
    plan: PlanResult,
    context: Dict[str, str],
    dependency_module: Dict[str, object],
    token_prefix: str,
) -> None:
    dependency_name = str(dependency_module.get("name", "")).strip()
    dependency_kind = str(dependency_module.get("kind", "")).strip()
    if not dependency_name or not token_prefix:
        return

    context[f"{token_prefix}_module_name"] = dependency_name
    context[f"{token_prefix}_module_kind"] = dependency_kind
    context[f"{token_prefix}_module_identifier"] = _app_static_identifier(dependency_name, "module")

    for item in plan.assignments:
        if item.module != dependency_name:
            continue
        signal_key = _template_token_name(item.signal)
        prefix = _macro_name(dependency_name, item.signal)
        context[f"{token_prefix}_{signal_key}"] = item.pin
        context[f"{token_prefix}_{signal_key}_pin"] = item.pin
        context[f"{token_prefix}_{signal_key}_port_macro"] = f"{prefix}_PORT"
        context[f"{token_prefix}_{signal_key}_pin_macro"] = f"{prefix}_PIN"

    i2c_binding = _i2c_binding_for_module(plan, dependency_name)
    if i2c_binding is not None:
        handle, address_macro = i2c_binding
        context[f"{token_prefix}_i2c_handle"] = handle
        context[f"{token_prefix}_i2c_address_macro"] = address_macro

    uart_handle = _uart_handle_for_module(plan, dependency_name)
    if uart_handle is not None:
        context[f"{token_prefix}_uart_handle"] = uart_handle

    pwm_binding = _pwm_binding_for_module(plan, dependency_name)
    if pwm_binding is not None:
        handle, channel = pwm_binding
        context[f"{token_prefix}_pwm_handle"] = handle
        context[f"{token_prefix}_pwm_channel"] = channel

def _pwm_binding_for_module(plan: PlanResult, module_name: str) -> Tuple[str, str] | None:
    for item in plan.assignments:
        if item.module != module_name or "." not in item.signal:
            continue
        prefix, _signal = item.signal.split(".", 1)
        timer_signal = prefix.upper()
        if not timer_signal.startswith("TIM"):
            continue
        timer_name, channel_name = timer_signal.split("_", 1)
        return (f"h{timer_name.lower()}", f"TIM_CHANNEL_{channel_name.replace('CH', '')}")
    return None

def _i2c_binding_for_module(plan: PlanResult, module_name: str) -> Tuple[str, str] | None:
    for bus in plan.buses:
        if bus.kind != "i2c":
            continue
        for device in bus.devices:
            if str(device.get("module")) == module_name:
                return (f"h{bus.bus.lower()}", f"{_macro_name(module_name, 'i2c')}_ADDRESS")
    return None

def _macro_name(module: str, signal: str) -> str:
    base = f"{module}_{signal}"
    return re.sub(r"[^A-Za-z0-9]+", "_", base).upper().strip("_")

def _app_static_identifier(module: str, suffix: str) -> str:
    return f"g_{_macro_name(module, suffix).lower()}"
