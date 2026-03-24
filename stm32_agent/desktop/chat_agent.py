from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ..app_logic_drafter import draft_app_logic_for_plan, merge_generated_app_logic
from ..builder import build_project, doctor_project, get_builder_display_name
from ..keil_generator import scaffold_from_request
from ..llm_config import LlmProfile
from ..planner import plan_request
from .attachments import AttachmentDigest
from .request_bridge import draft_request_json


@dataclass
class ChatAgentResult:
    handled: bool
    action: str
    ok: bool
    message: str
    project_dir: str = ""
    request_payload: Dict[str, object] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ChatProposalResult:
    handled: bool
    ok: bool
    message: str
    request_payload: Dict[str, object] = field(default_factory=dict)
    plan_summary: Dict[str, object] = field(default_factory=dict)
    change_preview: List[str] = field(default_factory=list)
    output_dir: str = ""
    mode: str = "create"
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


_BUILD_KEYWORDS = (
    "build",
    "编译",
    "构建",
    "生成hex",
    "导出hex",
    "烧录",
    "flash",
)

_DOCTOR_KEYWORDS = (
    "doctor",
    "检查工程",
    "检查当前工程",
    "检查keil",
    "诊断",
    "检查一下工程",
)

_SCAFFOLD_ACTION_KEYWORDS = (
    "帮我做",
    "做个",
    "做一个",
    "做一套",
    "生成工程",
    "创建工程",
    "新建工程",
    "搭一个",
    "搭个",
    "写个",
    "搞个",
    "scaffold",
    "project",
    "工程",
    "项目",
)

_HARDWARE_HINTS = (
    "stm32",
    "流水灯",
    "跑马灯",
    "led",
    "button",
    "oled",
    "uart",
    "i2c",
    "imu",
    "温湿度",
    "传感器",
    "门禁",
    "舵机",
    "蜂鸣器",
)

_QUESTION_HINTS = (
    "是什么",
    "为什么",
    "怎么",
    "who are you",
    "what are you",
    "什么意思",
)


def detect_agent_action(user_prompt: str) -> str:
    text = user_prompt.strip().lower()
    if not text:
        return "none"
    if any(keyword in text for keyword in _BUILD_KEYWORDS):
        return "build"
    if any(keyword in text for keyword in _DOCTOR_KEYWORDS):
        return "doctor"
    if any(keyword in text for keyword in _SCAFFOLD_ACTION_KEYWORDS):
        return "scaffold"
    if any(keyword in text for keyword in _HARDWARE_HINTS) and not any(
        keyword in text for keyword in _QUESTION_HINTS
    ):
        return "scaffold"
    return "none"


def run_chat_agent_workflow(
    profile: LlmProfile,
    user_prompt: str,
    repo_root: str | Path,
    active_project_dir: str = "",
    attachments: List[AttachmentDigest] | None = None,
    thread_context: str = "",
) -> ChatAgentResult:
    action = detect_agent_action(user_prompt)
    if action == "build":
        return _run_build(active_project_dir)
    if action == "doctor":
        return _run_doctor(active_project_dir)
    if action == "scaffold":
        return _run_scaffold(profile, user_prompt, repo_root, active_project_dir, attachments, thread_context)
    return ChatAgentResult(
        handled=False,
        action="none",
        ok=False,
        message="",
    )


def prepare_chat_project_proposal(
    profile: LlmProfile,
    user_prompt: str,
    repo_root: str | Path,
    active_project_dir: str = "",
    attachments: List[AttachmentDigest] | None = None,
    thread_context: str = "",
) -> ChatProposalResult:
    retrieved_context = _retrieve_request_context(user_prompt, repo_root, active_project_dir)
    draft = draft_request_json(
        profile,
        user_prompt,
        active_project_dir=active_project_dir,
        attachments=attachments,
        retrieved_context=retrieved_context,
        thread_context=thread_context,
    )
    if not draft.ok:
        errors = list(draft.errors)
        return ChatProposalResult(
            handled=True,
            ok=False,
            message=_render_failure_message(
                "我尝试先把你的自然语言需求整理成工程配置，但模型没有返回有效的结构化结果。",
                errors,
                draft.warnings,
            ),
            request_payload=draft.request_payload,
            warnings=draft.warnings,
            errors=errors,
        )

    payload, plan, app_logic_warnings = _apply_post_plan_app_logic(profile, user_prompt, draft.request_payload)
    warnings = [*draft.warnings, *plan.warnings, *app_logic_warnings]
    mode = "modify" if active_project_dir.strip() else "create"
    output_dir = active_project_dir.strip() or str(_make_output_dir(repo_root, user_prompt, payload))

    if not plan.feasible:
        errors = list(plan.errors)
        return ChatProposalResult(
            handled=True,
            ok=False,
            message=_render_failure_message(
                "我已经整理出工程配置，但当前这套芯片、模块或引脚条件还无法通过本地规划检查。",
                errors,
                warnings,
            ),
            request_payload=payload,
            plan_summary=plan.to_dict(),
            output_dir=output_dir,
            mode=mode,
            warnings=warnings,
            errors=errors,
        )

    return ChatProposalResult(
        handled=True,
        ok=True,
        message=_render_proposal_message(
            payload,
            plan,
            output_dir,
            mode,
            warnings,
        ),
        request_payload=payload,
        plan_summary=plan.to_dict(),
        change_preview=_build_change_preview_lines(payload, plan, output_dir, mode),
        output_dir=output_dir,
        mode=mode,
        warnings=warnings,
        errors=[],
    )


def _run_scaffold(
    profile: LlmProfile,
    user_prompt: str,
    repo_root: str | Path,
    active_project_dir: str,
    attachments: List[AttachmentDigest] | None,
    thread_context: str = "",
) -> ChatAgentResult:
    retrieved_context = _retrieve_request_context(user_prompt, repo_root, active_project_dir)
    draft = draft_request_json(
        profile,
        user_prompt,
        active_project_dir=active_project_dir,
        attachments=attachments,
        retrieved_context=retrieved_context,
        thread_context=thread_context,
    )
    if not draft.ok:
        errors = list(draft.errors)
        return ChatAgentResult(
            handled=True,
            action="scaffold",
            ok=False,
            message=_render_failure_message(
                "我尝试按本地 Agent 工作流起草 request JSON，但模型没有返回有效的结构化结果。",
                errors,
                draft.warnings,
            ),
            request_payload=draft.request_payload,
            warnings=draft.warnings,
            errors=errors,
        )

    payload, plan, app_logic_warnings = _apply_post_plan_app_logic(profile, user_prompt, draft.request_payload)
    if not plan.feasible:
        errors = list(plan.errors)
        return ChatAgentResult(
            handled=True,
            action="scaffold",
            ok=False,
            message=_render_failure_message(
                "我已经把自然语言需求转成了 request JSON，但本地规划没有通过。",
                errors,
                [*draft.warnings, *plan.warnings, *app_logic_warnings],
            ),
            request_payload=payload,
            warnings=[*draft.warnings, *plan.warnings, *app_logic_warnings],
            errors=errors,
        )

    output_dir = _make_output_dir(repo_root, user_prompt, payload)
    scaffold = scaffold_from_request(payload, output_dir)
    if not scaffold.feasible:
        errors = list(scaffold.errors)
        return ChatAgentResult(
            handled=True,
            action="scaffold",
            ok=False,
            message=_render_failure_message(
                "本地规划已经通过，但生成工程时失败了。",
                errors,
                [*draft.warnings, *plan.warnings, *app_logic_warnings, *scaffold.warnings],
            ),
            project_dir=scaffold.project_dir,
            request_payload=payload,
            warnings=[*draft.warnings, *plan.warnings, *app_logic_warnings, *scaffold.warnings],
            errors=errors,
        )

    warnings = [*draft.warnings, *plan.warnings, *app_logic_warnings, *scaffold.warnings]
    return ChatAgentResult(
        handled=True,
        action="scaffold",
        ok=True,
        message=_render_scaffold_message(payload, plan.chip, scaffold.project_dir, warnings),
        project_dir=scaffold.project_dir,
        request_payload=payload,
        warnings=warnings,
        errors=[],
    )


def _apply_post_plan_app_logic(
    profile: LlmProfile,
    user_prompt: str,
    request_payload: Dict[str, object],
) -> tuple[Dict[str, object], object, List[str]]:
    working_payload = dict(request_payload)
    plan = plan_request(working_payload)
    if not plan.feasible:
        return working_payload, plan, []

    draft_result = draft_app_logic_for_plan(profile, user_prompt, working_payload, plan)
    warnings = list(draft_result.warnings)
    if draft_result.ok and (
        any(draft_result.app_logic.values()) or draft_result.generated_files or draft_result.app_logic_ir
    ):
        working_payload = merge_generated_app_logic(
            working_payload,
            draft_result.app_logic,
            generated_files=draft_result.generated_files,
            app_logic_ir=draft_result.app_logic_ir,
        )
        plan = plan_request(working_payload)
    elif draft_result.errors:
        warnings.extend(f"App logic draft skipped: {item}" for item in draft_result.errors)
    return working_payload, plan, warnings


def _retrieve_request_context(user_prompt: str, repo_root: str | Path, active_project_dir: str = "") -> str:
    prompt = str(user_prompt or "").strip()
    if not prompt:
        return ""
    try:
        from ..graph.retrieval import render_retrieved_context, retrieve_relevant_chunks

        chunks, _filters = retrieve_relevant_chunks(
            prompt,
            repo_root,
            active_project_dir=active_project_dir,
        )
        return render_retrieved_context(chunks)
    except Exception:
        return ""


def _run_build(active_project_dir: str) -> ChatAgentResult:
    if not active_project_dir.strip():
        return ChatAgentResult(
            handled=True,
            action="build",
            ok=False,
            message="当前还没有激活工程目录，所以我没法直接执行编译。先让我生成一个工程，或者先在“项目”页选中已有工程。",
            errors=["active_project_dir is empty"],
        )

    result = build_project(active_project_dir)
    builder_name = get_builder_display_name(getattr(result, "builder_kind", ""))
    if not result.ready:
        return ChatAgentResult(
            handled=True,
            action="build",
            ok=False,
            message=_render_failure_message("我尝试执行本地 Keil 构建，但环境还没准备好。", result.errors, result.warnings),
            project_dir=result.project_dir,
            warnings=result.warnings,
            errors=result.errors,
        )

    if not result.built:
        return ChatAgentResult(
            handled=True,
            action="build",
            ok=False,
            message=_render_failure_message("我已经调用了 Keil 构建，但这次编译没有通过。", result.errors, result.warnings),
            project_dir=result.project_dir,
            warnings=result.warnings,
            errors=result.errors,
        )

    lines = [
        f"我已经对当前工程执行了本地 `build-{str(getattr(result, 'builder_kind', 'project')).strip() or 'project'}`。",
        f"- 工程目录: `{result.project_dir}`",
        f"- Builder: `{builder_name}`",
        f"- build.log: `{result.build_log_path}`",
    ]
    if result.hex_generated and result.hex_file:
        lines.append(f"- HEX: `{result.hex_file}`")
    if result.summary_lines:
        lines.append("- 构建摘要: " + " | ".join(result.summary_lines[:3]))
    if result.warnings:
        lines.append("- 警告: " + "; ".join(result.warnings[:3]))
    return ChatAgentResult(
        handled=True,
        action="build",
        ok=True,
        message="\n".join(lines),
        project_dir=result.project_dir,
        warnings=result.warnings,
        errors=result.errors,
    )


def _run_doctor(active_project_dir: str) -> ChatAgentResult:
    if not active_project_dir.strip():
        return ChatAgentResult(
            handled=True,
            action="doctor",
            ok=False,
            message="当前还没有激活工程目录，所以我没法直接检查 Keil 工程。先让我生成一个工程，或者先在“项目”页选中已有工程。",
            errors=["active_project_dir is empty"],
        )

    result = doctor_project(active_project_dir)
    builder_name = get_builder_display_name(getattr(result, "builder_kind", ""))
    if not result.ready:
        return ChatAgentResult(
            handled=True,
            action="doctor",
            ok=False,
            message=_render_failure_message("我已经检查了当前工程，但 Keil 环境还没有准备好。", result.errors, result.warnings),
            project_dir=result.project_dir,
            warnings=result.warnings,
            errors=result.errors,
        )

    lines = [
        f"我已经检查了当前工程对应的 {builder_name} 构建环境。",
        f"- 工程目录: `{result.project_dir}`",
        f"- Builder: `{builder_name}`",
        f"- UV4: `{result.uv4_path}`",
        f"- fromelf: `{result.fromelf_path or '未找到'}`",
        f"- build.log: `{result.build_log_path}`",
    ]
    if result.warnings:
        lines.append("- 警告: " + "; ".join(result.warnings[:3]))
    return ChatAgentResult(
        handled=True,
        action="doctor",
        ok=True,
        message="\n".join(lines),
        project_dir=result.project_dir,
        warnings=result.warnings,
        errors=result.errors,
    )


def _render_scaffold_message(
    request_payload: Dict[str, object],
    chip: str,
    project_dir: str,
    warnings: List[str],
) -> str:
    modules = request_payload.get("modules", [])
    module_kinds = [
        str(item.get("kind", "")).strip()
        for item in modules
        if isinstance(item, dict) and str(item.get("kind", "")).strip()
    ]
    lines = [
        "我已经按本地 Agent 工作流把这条需求落成工程了。",
        f"- 目标芯片: `{chip}`",
        f"- 模块: `{', '.join(module_kinds) if module_kinds else '无'}`",
        f"- 工程目录: `{project_dir}`",
        "- 当前项目上下文已经切到这个工程，接下来你可以继续让我编译、检查 Keil，或者改需求后再生成一版。",
    ]
    if warnings:
        lines.append("- 备注: " + "; ".join(warnings[:3]))
    return "\n".join(lines)


def _render_proposal_message(
    request_payload: Dict[str, object],
    plan,
    output_dir: str,
    mode: str,
    warnings: List[str],
) -> str:
    modules = request_payload.get("modules", [])
    module_names = [
        f"{item.get('name', '')} ({item.get('kind', '')})"
        for item in modules
        if isinstance(item, dict)
    ]
    lines = [
        "我先给你整理了一版可执行方案，还没有直接生成代码。",
        "",
        f"可行性: {'可以做' if plan.feasible else '当前不可行'}",
        f"目标芯片: {plan.chip}",
        f"推荐板子: {_suggest_board_text(plan)}",
        f"模块清单: {', '.join(module_names) if module_names else '无'}",
        "",
        "接线建议:",
    ]
    if plan.assignments:
        for item in plan.assignments[:16]:
            lines.append(f"- {item.module}.{item.signal} -> {item.pin}")
        if len(plan.assignments) > 16:
            lines.append(f"- 其余 {len(plan.assignments) - 16} 条接线可在确认后继续查看")
    else:
        lines.append("- 当前没有需要分配的外设引脚")

    if plan.buses:
        lines.append("")
        lines.append("总线与外设:")
        for bus in plan.buses[:8]:
            pins = ", ".join(f"{key.upper()}={value}" for key, value in bus.pins.items())
            devices = ", ".join(f"{item['module']}({item['address']})" for item in bus.devices)
            lines.append(f"- {bus.bus}: {pins} -> {devices}")

    lines.append("")
    lines.append("即将变更:")
    for item in _build_change_preview_lines(request_payload, plan, output_dir, mode):
        lines.append(f"- {item}")
    lines.append("")
    if mode == "modify":
        lines.append(f"确认后动作: 我会基于当前项目目录继续更新并重新编译 -> {output_dir}")
    else:
        lines.append(f"确认后动作: 我会生成新的 Keil 工程并继续编译 -> {output_dir}")
    lines.append("如果你认可这套模块和引脚分配，就点“确认方案并开始生成”。")
    if warnings:
        lines.append("")
        lines.append("备注:")
        for item in warnings[:4]:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _render_failure_message(summary: str, errors: List[str], warnings: List[str]) -> str:
    lines = [summary]
    if errors:
        lines.append("- 错误: " + "; ".join(errors[:3]))
    if warnings:
        lines.append("- 备注: " + "; ".join(warnings[:3]))
    return "\n".join(lines)


def _make_output_dir(repo_root: str | Path, user_prompt: str, request_payload: Dict[str, object]) -> Path:
    root = Path(repo_root) / "out"
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
    pieces = ["chat_agent", slug]
    if first_kind:
        pieces.append(first_kind)
    pieces.append(timestamp)
    name = "_".join(part for part in pieces if part)
    return root / name


def _slugify(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    if not words:
        return "task"
    slug = "_".join(words[:4])
    return slug[:32].strip("_") or "task"


def _suggest_board_text(plan) -> str:
    if getattr(plan, "board", "") and getattr(plan, "board", "") != "chip_only":
        return str(plan.board)
    if getattr(plan, "chip", "") == "STM32F103C8T6":
        return "STM32F103C8T6 最小系统板或 Blue Pill"
    if getattr(plan, "chip", "") == "STM32F103RBT6":
        return "STM32F103RBT6 最小系统板或 Nucleo-F103RB"
    return f"{getattr(plan, 'chip', '当前芯片')} 对应开发板"


def _build_change_preview_lines(
    request_payload: Dict[str, object],
    plan,
    output_dir: str,
    mode: str,
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
        existence_text = "目标目录当前不存在，会新建整个工程目录"

    return [
        f"变更类型: {'修改当前项目' if mode == 'modify' else '新建工程'}",
        f"目标目录: {output_dir}",
        existence_text,
        f"芯片/资源会按本次方案重新落盘: {getattr(plan, 'chip', '')}，{len(getattr(plan, 'assignments', []))} 条引脚分配，{len(getattr(plan, 'buses', []))} 条总线",
        f"模块会写入工程: {', '.join(module_names) if module_names else '无额外模块'}",
        f"预计写入或更新: {', '.join(top_level_targets)}",
        "生成完成后会继续执行驱动检查、Keil 编译，并在可用时导出 HEX",
    ]
