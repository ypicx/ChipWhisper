from __future__ import annotations

import json
import re
import select
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .keil_builder import _find_axf_output, _resolve_project_paths
from .path_config import resolve_configured_path


_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-9;?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class RenodePlatformProfile:
    key: str
    platform_path: str
    chip_prefixes: Tuple[str, ...] = ()
    default_uart_analyzers: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()


RENODE_PLATFORM_PROFILES: Tuple[RenodePlatformProfile, ...] = (
    RenodePlatformProfile(
        key="stm32f103",
        platform_path="platforms/cpus/stm32f103.repl",
        chip_prefixes=("STM32F103",),
        default_uart_analyzers=("usart2",),
        notes=(
            "This first integration targets the built-in Renode STM32F103 CPU platform.",
            "STM32G431 and other STM32 variants still need dedicated Renode platform support.",
        ),
    ),
)


@dataclass
class RenodeDoctorResult:
    ready: bool
    project_dir: str
    uvprojx_path: str
    binary_path: str
    renode_path: str
    chip: str
    family: str
    board: str
    platform_key: str
    platform_path: str
    script_path: str
    run_seconds: float
    uart_analyzers: List[str]
    checked_paths: List[Dict[str, object]]
    warnings: List[str]
    errors: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "ready": self.ready,
            "project_dir": self.project_dir,
            "uvprojx_path": self.uvprojx_path,
            "binary_path": self.binary_path,
            "renode_path": self.renode_path,
            "chip": self.chip,
            "family": self.family,
            "board": self.board,
            "platform_key": self.platform_key,
            "platform_path": self.platform_path,
            "script_path": self.script_path,
            "run_seconds": self.run_seconds,
            "uart_analyzers": self.uart_analyzers,
            "checked_paths": self.checked_paths,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class RenodeSocketTerminal:
    name: str
    uart_name: str
    port: int


@dataclass(frozen=True)
class RenodeMemoryPatch:
    address: int
    value: int
    width: str = "doubleword"
    summary: str = ""


@dataclass(frozen=True)
class RenodeTimedAction:
    at_seconds: float
    command: str
    summary: str = ""


@dataclass
class RenodeExecutionCapture:
    exit_code: int | None
    output_text: str
    uart_output: Dict[str, str]
    warnings: List[str]
    errors: List[str]
    timed_out: bool = False


@dataclass
class RenodeRunResult:
    ready: bool
    ran: bool
    project_dir: str
    uvprojx_path: str
    binary_path: str
    renode_path: str
    chip: str
    family: str
    board: str
    platform_key: str
    platform_path: str
    script_path: str
    run_seconds: float
    uart_analyzers: List[str]
    applied_patches: List[str]
    attached_simulation: List[str]
    scheduled_interactions: List[str]
    command: List[str]
    exit_code: int | None
    timed_out: bool
    log_path: str
    uart_capture_path: str
    uart_output: Dict[str, str]
    expectations_path: str
    expectations: Dict[str, object]
    expected_uart_contains: List[str]
    matched_uart_contains: List[str]
    missing_uart_contains: List[str]
    validation_details: Dict[str, object]
    validation_passed: bool | None
    summary_lines: List[str]
    warnings: List[str]
    errors: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "ready": self.ready,
            "ran": self.ran,
            "project_dir": self.project_dir,
            "uvprojx_path": self.uvprojx_path,
            "binary_path": self.binary_path,
            "renode_path": self.renode_path,
            "chip": self.chip,
            "family": self.family,
            "board": self.board,
            "platform_key": self.platform_key,
            "platform_path": self.platform_path,
            "script_path": self.script_path,
            "run_seconds": self.run_seconds,
            "uart_analyzers": self.uart_analyzers,
            "applied_patches": self.applied_patches,
            "attached_simulation": self.attached_simulation,
            "scheduled_interactions": self.scheduled_interactions,
            "command": self.command,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "log_path": self.log_path,
            "uart_capture_path": self.uart_capture_path,
            "uart_output": self.uart_output,
            "expectations_path": self.expectations_path,
            "expectations": self.expectations,
            "expected_uart_contains": self.expected_uart_contains,
            "matched_uart_contains": self.matched_uart_contains,
            "missing_uart_contains": self.missing_uart_contains,
            "validation_details": self.validation_details,
            "validation_passed": self.validation_passed,
            "summary_lines": self.summary_lines,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def doctor_renode_project(
    project_path: str | Path,
    renode_path: str | Path | None = None,
    run_seconds: float = 1.0,
) -> RenodeDoctorResult:
    project_dir, uvprojx_path, errors = _resolve_project_paths(project_path)
    warnings: List[str] = []
    checked_paths: List[Dict[str, object]] = []
    target = _load_project_target(project_dir / "project_ir.json")
    chip = str(target.get("chip", "")).strip().upper()
    family = str(target.get("family", "")).strip().upper()
    board = str(target.get("board", "")).strip()
    binary_path = Path()
    resolved_renode = ""
    platform_key = ""
    platform_path = ""
    uart_analyzers: List[str] = []
    script_path = str(project_dir / "Renode" / f"{uvprojx_path.stem}.resc")

    if run_seconds <= 0:
        errors.append("Renode run duration must be greater than zero seconds.")

    if errors:
        return RenodeDoctorResult(
            ready=False,
            project_dir=str(project_dir),
            uvprojx_path=str(uvprojx_path),
            binary_path="",
            renode_path="",
            chip=chip,
            family=family,
            board=board,
            platform_key="",
            platform_path="",
            script_path=script_path,
            run_seconds=run_seconds,
            uart_analyzers=[],
            checked_paths=[],
            warnings=[],
            errors=errors,
        )

    resolved_renode_path = find_renode(renode_path)
    if resolved_renode_path is None:
        errors.append("Renode executable was not found. Pass the path explicitly or configure RENODE_PATH / renode_exe_path.")
    else:
        resolved_renode = str(resolved_renode_path)
        checked_paths.append(
            {
                "path": resolved_renode,
                "kind": "Renode executable",
                "exists": True,
            }
        )

    binary_candidate = _find_axf_output(uvprojx_path)
    if binary_candidate is None:
        errors.append("No .axf build artifact was found. Run build-keil before starting Renode simulation.")
    else:
        binary_path = binary_candidate
        checked_paths.append(
            {
                "path": str(binary_path),
                "kind": "Renode firmware binary",
                "exists": binary_path.exists(),
            }
        )

    if not chip:
        errors.append("project_ir.json does not contain a target chip, so Renode platform selection is unavailable.")
    else:
        profile = _select_platform_profile(chip)
        if profile is None:
            errors.append(
                f"Renode integration is currently available only for chips backed by the local platform map. "
                f"Current target: {chip or family or 'unknown'}."
            )
        else:
            platform_key = profile.key
            platform_path = profile.platform_path
            uart_analyzers = _collect_uart_analyzers(project_dir / "project_ir.json", profile)
            warnings.extend(profile.notes)

    return RenodeDoctorResult(
        ready=not errors,
        project_dir=str(project_dir),
        uvprojx_path=str(uvprojx_path),
        binary_path=str(binary_path) if binary_path else "",
        renode_path=resolved_renode,
        chip=chip,
        family=family,
        board=board,
        platform_key=platform_key,
        platform_path=platform_path,
        script_path=script_path,
        run_seconds=run_seconds,
        uart_analyzers=uart_analyzers,
        checked_paths=checked_paths,
        warnings=warnings,
        errors=errors,
    )


def run_renode_project(
    project_path: str | Path,
    renode_path: str | Path | None = None,
    run_seconds: float = 1.0,
) -> RenodeRunResult:
    uart_capture_path = str(Path(project_path).resolve() / "Renode" / "uart_capture.log") if str(project_path) else ""
    expectations_path = str(Path(project_path).resolve() / "renode_expect.json") if str(project_path) else ""
    doctor = doctor_renode_project(project_path, renode_path=renode_path, run_seconds=run_seconds)
    if not doctor.ready:
        return RenodeRunResult(
            ready=False,
            ran=False,
            project_dir=doctor.project_dir,
            uvprojx_path=doctor.uvprojx_path,
            binary_path=doctor.binary_path,
            renode_path=doctor.renode_path,
            chip=doctor.chip,
            family=doctor.family,
            board=doctor.board,
            platform_key=doctor.platform_key,
            platform_path=doctor.platform_path,
            script_path=doctor.script_path,
            run_seconds=doctor.run_seconds,
            uart_analyzers=list(doctor.uart_analyzers),
            applied_patches=[],
            attached_simulation=[],
            scheduled_interactions=[],
            command=[],
            exit_code=None,
            timed_out=False,
            log_path=str(Path(doctor.project_dir) / "Renode" / "renode.log"),
            uart_capture_path=str(Path(doctor.project_dir) / "Renode" / "uart_capture.log"),
            uart_output={},
            expectations_path=str(Path(doctor.project_dir) / "renode_expect.json"),
            expectations={},
            expected_uart_contains=[],
            matched_uart_contains=[],
            missing_uart_contains=[],
            validation_details={},
            validation_passed=None,
            summary_lines=[],
            warnings=list(doctor.warnings),
            errors=list(doctor.errors),
        )

    script_path = Path(doctor.script_path)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = script_path.parent / "renode.log"
    uart_capture_path = str(script_path.parent / "uart_capture.log")
    project_ir_path = Path(doctor.project_dir) / "project_ir.json"
    project_ir = _load_project_ir(project_ir_path)
    expectation_file = Path(doctor.project_dir) / "renode_expect.json"
    expectations_path = str(expectation_file)
    generated_expectations, expectation_warnings = ensure_runtime_expectations(
        Path(doctor.project_dir),
        project_ir=project_ir,
    )
    terminals = _allocate_socket_terminals(doctor.uart_analyzers)
    overlay_commands, timed_actions, simulation_entities, scheduled_interactions, simulation_warnings = (
        _plan_simulation_artifacts(project_ir_path)
    )
    memory_patches, patch_warnings = _plan_runtime_patches(
        project_dir=Path(doctor.project_dir),
        uvprojx_path=Path(doctor.uvprojx_path),
        platform_key=doctor.platform_key,
    )
    script_text = render_renode_script(
        binary_path=Path(doctor.binary_path),
        platform_path=doctor.platform_path,
        uart_analyzers=doctor.uart_analyzers,
        run_seconds=doctor.run_seconds,
        uart_terminals=terminals,
        memory_patches=memory_patches,
        overlay_commands=overlay_commands,
        timed_actions=timed_actions,
    )
    script_path.write_text(script_text, encoding="utf-8")

    command = [
        doctor.renode_path,
        "--disable-gui",
        "--plain",
        "--hide-monitor",
        str(script_path),
    ]
    try:
        execution = _run_renode_command(
            command,
            cwd=doctor.project_dir,
            terminals=terminals,
            run_seconds=doctor.run_seconds,
        )
    except OSError as exc:
        return RenodeRunResult(
            ready=True,
            ran=False,
            project_dir=doctor.project_dir,
            uvprojx_path=doctor.uvprojx_path,
            binary_path=doctor.binary_path,
            renode_path=doctor.renode_path,
            chip=doctor.chip,
            family=doctor.family,
            board=doctor.board,
            platform_key=doctor.platform_key,
            platform_path=doctor.platform_path,
            script_path=str(script_path),
            run_seconds=doctor.run_seconds,
            uart_analyzers=list(doctor.uart_analyzers),
            applied_patches=[patch.summary for patch in memory_patches if patch.summary],
            attached_simulation=simulation_entities,
            scheduled_interactions=scheduled_interactions,
            command=command,
            exit_code=None,
            timed_out=False,
            log_path=str(log_path),
            uart_capture_path=uart_capture_path,
            uart_output={},
            expectations_path=expectations_path,
            expectations={},
            expected_uart_contains=[],
            matched_uart_contains=[],
            missing_uart_contains=[],
            validation_details={},
            validation_passed=None,
            summary_lines=[],
            warnings=[*doctor.warnings, *expectation_warnings, *simulation_warnings, *patch_warnings],
            errors=[f"Failed to launch Renode: {exc}"],
        )

    combined_output = execution.output_text.strip()
    log_path.write_text(combined_output + ("\n" if combined_output else ""), encoding="utf-8")
    _write_uart_capture_log(Path(uart_capture_path), execution.uart_output)

    summary_lines = _extract_summary_lines(combined_output)
    summary_lines.extend(_extract_uart_summary_lines(execution.uart_output))
    errors = list(doctor.errors)
    warnings = list(doctor.warnings)
    warnings.extend(expectation_warnings)
    warnings.extend(simulation_warnings)
    warnings.extend(patch_warnings)
    warnings.extend(execution.warnings)
    summary_lines.extend(simulation_entities)
    summary_lines.extend(scheduled_interactions)
    run_errors = _detect_run_errors(summary_lines)
    errors.extend(run_errors)
    errors.extend(execution.errors)
    ran = (execution.exit_code == 0 or execution.timed_out) and not run_errors and not execution.errors
    if execution.timed_out:
        warnings.append("Renode reached the validation time window and was terminated after collecting output.")
    elif execution.exit_code != 0 and not run_errors:
        errors.append(f"Renode exited with code {execution.exit_code}.")
    if ran and not doctor.uart_analyzers:
        warnings.append("No UART analyzer was configured for this project, so console output may stay empty.")
    elif doctor.uart_analyzers and not any(text.strip() for text in execution.uart_output.values()):
        warnings.append("Renode socket capture completed, but no UART text was observed.")

    expectations, validation_warnings = _load_runtime_expectations(expectation_file)
    if not expectations and generated_expectations:
        expectations = dict(generated_expectations)
    warnings.extend(validation_warnings)
    validation_details = _evaluate_runtime_expectations(
        combined_output,
        execution.uart_output,
        execution.exit_code,
        expectations,
    )
    contains_details = validation_details.get("checks", {}).get("uart_contains", {})
    expected_uart_contains = [str(item) for item in contains_details.get("expected", []) if str(item).strip()]
    matched_uart_contains = [str(item) for item in contains_details.get("matched", []) if str(item).strip()]
    missing_uart_contains = [str(item) for item in contains_details.get("missing", []) if str(item).strip()]
    validation_passed: bool | None = None
    if expectations:
        validation_passed = validation_details.get("passed")
        validation_errors = _render_runtime_validation_failures(validation_details)
        if validation_errors:
            ran = False
            errors.extend(validation_errors)
        elif validation_passed is True:
            summary_lines.append("Renode runtime validation matched all configured rules.")

    return RenodeRunResult(
        ready=True,
        ran=ran,
        project_dir=doctor.project_dir,
        uvprojx_path=doctor.uvprojx_path,
        binary_path=doctor.binary_path,
        renode_path=doctor.renode_path,
        chip=doctor.chip,
        family=doctor.family,
        board=doctor.board,
        platform_key=doctor.platform_key,
        platform_path=doctor.platform_path,
        script_path=str(script_path),
        run_seconds=doctor.run_seconds,
        uart_analyzers=list(doctor.uart_analyzers),
        applied_patches=[patch.summary for patch in memory_patches if patch.summary],
        attached_simulation=simulation_entities,
        scheduled_interactions=scheduled_interactions,
        command=command,
        exit_code=execution.exit_code,
        timed_out=execution.timed_out,
        log_path=str(log_path),
        uart_capture_path=uart_capture_path,
        uart_output=dict(execution.uart_output),
        expectations_path=expectations_path,
        expectations=expectations,
        expected_uart_contains=expected_uart_contains,
        matched_uart_contains=matched_uart_contains,
        missing_uart_contains=missing_uart_contains,
        validation_details=validation_details,
        validation_passed=validation_passed,
        summary_lines=summary_lines,
        warnings=warnings,
        errors=errors,
    )


def find_renode(explicit_path: str | Path | None = None) -> Path | None:
    candidates: List[Path] = []
    if explicit_path is not None:
        candidates.append(Path(explicit_path))

    configured_path, _source = resolve_configured_path("renode_exe_path")
    if configured_path:
        candidates.append(Path(configured_path))

    candidates.extend(
        [
            Path(r"D:\Renode\renode.exe"),
            Path(r"C:\Renode\renode.exe"),
            Path(r"C:\Program Files\Renode\renode.exe"),
            Path(r"C:\Program Files (x86)\Renode\renode.exe"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def ensure_runtime_expectations(
    project_dir: str | Path,
    request_payload: Dict[str, object] | None = None,
    project_ir: Dict[str, object] | None = None,
) -> tuple[Dict[str, object], List[str]]:
    expectation_path = Path(project_dir) / "renode_expect.json"
    if expectation_path.exists():
        return {}, []

    resolved_project_ir = project_ir if isinstance(project_ir, dict) else _load_project_ir(Path(project_dir) / "project_ir.json")
    resolved_request_payload = request_payload if isinstance(request_payload, dict) else {}
    expectation_payload = derive_runtime_expectation_payload(
        request_payload=resolved_request_payload,
        project_ir=resolved_project_ir,
    )
    if not expectation_payload:
        return {}, []

    try:
        expectation_path.write_text(
            json.dumps(expectation_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return expectation_payload, [f"Renode could not write the auto-generated expectation file: {exc}"]

    expected_lines = [str(item) for item in expectation_payload.get("uart_contains", []) if str(item).strip()]
    if not expected_lines:
        expected_lines = [str(item) for item in expectation_payload.get("uart_sequence", []) if str(item).strip()]
    expected_log_lines = [str(item) for item in expectation_payload.get("log_contains", []) if str(item).strip()]
    if expectation_payload.get("uart_sequence"):
        return expectation_payload, [f"Generated ordered Renode UART expectations from app logic: {', '.join(expected_lines[:2])}"]
    if expected_lines:
        return expectation_payload, [f"Generated Renode UART expectations from app logic: {', '.join(expected_lines[:2])}"]
    return expectation_payload, [f"Generated Renode monitor expectations from simulation metadata: {', '.join(expected_log_lines[:2])}"]


def derive_runtime_expectation_payload(
    request_payload: Dict[str, object] | None = None,
    project_ir: Dict[str, object] | None = None,
) -> Dict[str, object]:
    structured = _collect_structured_runtime_expectations(request_payload, project_ir)
    expected_lines = [str(item) for item in structured.get("uart_contains", []) if str(item).strip()]
    expected_any_lines = [str(item) for item in structured.get("uart_any_contains", []) if str(item).strip()]
    forbidden_uart = [str(item) for item in structured.get("uart_not_contains", []) if str(item).strip()]
    expected_sequence = [str(item) for item in structured.get("uart_sequence", []) if str(item).strip()]
    expected_log_lines = [str(item) for item in structured.get("log_contains", []) if str(item).strip()]
    forbidden_logs = [str(item) for item in structured.get("log_not_contains", []) if str(item).strip()]

    if not expected_lines:
        expected_lines = derive_runtime_uart_expectations(request_payload=request_payload, project_ir=project_ir)
        if not expected_sequence and len(expected_lines) > 1:
            expected_sequence = list(expected_lines)
    if not expected_log_lines:
        expected_log_lines = derive_runtime_log_expectations(project_ir or {})

    payload: Dict[str, object] = {}
    if expected_lines:
        payload["uart_contains"] = expected_lines
    if expected_any_lines:
        payload["uart_any_contains"] = expected_any_lines
    if forbidden_uart:
        payload["uart_not_contains"] = forbidden_uart
    if expected_sequence:
        payload["uart_sequence"] = expected_sequence
    if expected_log_lines:
        payload["log_contains"] = expected_log_lines
    if forbidden_logs:
        payload["log_not_contains"] = forbidden_logs
    return payload


def derive_runtime_log_expectations(project_ir: Dict[str, object] | None) -> List[str]:
    if not isinstance(project_ir, dict):
        return []

    modules = project_ir.get("modules", [])
    if not isinstance(modules, list):
        return []

    expectations: List[str] = []
    for module in modules:
        if not isinstance(module, dict):
            continue
        simulation = module.get("simulation", {})
        if not isinstance(simulation, dict):
            continue
        renode = simulation.get("renode", {})
        if not isinstance(renode, dict):
            continue
        attach_items = renode.get("attach", [])
        if not isinstance(attach_items, list):
            continue
        for attach in attach_items:
            if not isinstance(attach, dict):
                continue
            if str(attach.get("kind", "")).strip().lower() != "led":
                continue
            probes = attach.get("probes", [])
            if not isinstance(probes, list):
                continue
            attach_name = str(attach.get("name", "") or module.get("name", "") or "led").strip()
            for raw_probe in probes:
                if not isinstance(raw_probe, dict):
                    continue
                expected_state = raw_probe.get("expect")
                if expected_state is None:
                    continue
                label = str(raw_probe.get("label") or raw_probe.get("name") or attach_name).strip()
                normalized_state = _normalize_expected_probe_state(expected_state)
                if not label or normalized_state is None:
                    continue
                marker = f"[SIM][LED] {label}={normalized_state}"
                if marker not in expectations:
                    expectations.append(marker)
    return expectations


def derive_runtime_uart_expectations(
    request_payload: Dict[str, object] | None = None,
    project_ir: Dict[str, object] | None = None,
) -> List[str]:
    candidates: List[str] = []
    for block in _iter_app_logic_blocks(request_payload, project_ir):
        candidates.extend(_extract_debug_uart_expectations(str(block)))

    unique: List[str] = []
    for item in candidates:
        text = str(item).strip()
        if not text or text in unique:
            continue
        unique.append(text)
        if len(unique) >= 4:
            break
    return unique


def _collect_structured_runtime_expectations(
    request_payload: Dict[str, object] | None,
    project_ir: Dict[str, object] | None,
) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {}
    sources: List[object] = []
    normalized_request_payload = request_payload if isinstance(request_payload, dict) else {}
    normalized_project_ir = project_ir if isinstance(project_ir, dict) else {}

    sources.append(normalized_request_payload.get("runtime_expectations"))
    sources.append(normalized_request_payload.get("acceptance"))
    sources.append(_extract_ir_acceptance(normalized_request_payload.get("app_logic_ir")))

    request_build = normalized_request_payload.get("build", {})
    if isinstance(request_build, dict):
        sources.append(request_build.get("runtime_expectations"))
        sources.append(_extract_ir_acceptance(request_build.get("app_logic_ir")))

    project_build = normalized_project_ir.get("build", {})
    if isinstance(project_build, dict):
        sources.append(project_build.get("runtime_expectations"))
        sources.append(_extract_ir_acceptance(project_build.get("app_logic_ir")))

    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in (
            "uart_contains",
            "uart_any_contains",
            "uart_not_contains",
            "uart_sequence",
            "log_contains",
            "log_not_contains",
        ):
            items = _normalize_expectation_text_list(source.get(key))
            if not items:
                continue
            bucket = merged.setdefault(key, [])
            for item in items:
                if item not in bucket:
                    bucket.append(item)
    return merged


def _extract_ir_acceptance(value: object) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}
    acceptance = value.get("acceptance", {})
    return acceptance if isinstance(acceptance, dict) else {}


def render_renode_script(
    binary_path: Path,
    platform_path: str,
    uart_analyzers: List[str],
    run_seconds: float,
    uart_terminals: List[RenodeSocketTerminal] | None = None,
    memory_patches: List[RenodeMemoryPatch] | None = None,
    overlay_commands: List[str] | None = None,
    timed_actions: List[RenodeTimedAction] | None = None,
) -> str:
    lines = [
        "using sysbus",
        "",
        'mach create "stm32_agent"',
        f"machine LoadPlatformDescription @{platform_path}",
    ]
    lines.extend(command for command in (overlay_commands or []) if str(command).strip())
    if uart_terminals:
        for terminal in uart_terminals:
            lines.append(f'emulation CreateServerSocketTerminal {terminal.port} "{terminal.name}" false')
            lines.append(f"connector Connect sysbus.{terminal.uart_name} {terminal.name}")
    else:
        for uart_name in uart_analyzers:
            lines.append(f"showAnalyzer {uart_name}")
    lines.extend(
        [
            f'sysbus LoadELF "{binary_path.resolve().as_posix()}"',
        ]
    )
    for patch in memory_patches or []:
        lines.append(_render_memory_patch_command(patch))
    elapsed_seconds = 0.0
    for action in sorted(timed_actions or [], key=lambda item: float(item.at_seconds)):
        action_time = max(0.0, float(action.at_seconds))
        if action_time > float(run_seconds):
            continue
        if action_time > elapsed_seconds:
            lines.append('emulation RunFor "' + _format_run_seconds(action_time - elapsed_seconds) + '"')
        lines.append(action.command)
        elapsed_seconds = action_time
    remaining = max(0.0, float(run_seconds) - elapsed_seconds)
    if remaining > 0.0 or not timed_actions:
        lines.append('emulation RunFor "' + _format_run_seconds(remaining if timed_actions else run_seconds) + '"')
    lines.extend(["quit", ""])
    return "\n".join(lines)


def _allocate_socket_terminals(uart_analyzers: List[str]) -> List[RenodeSocketTerminal]:
    terminals: List[RenodeSocketTerminal] = []
    for index, uart_name in enumerate(uart_analyzers, start=1):
        normalized_uart = str(uart_name).strip().lower()
        if not normalized_uart:
            continue
        terminals.append(
            RenodeSocketTerminal(
                name=f"uart_capture_{index}",
                uart_name=normalized_uart,
                port=_reserve_tcp_port(),
            )
        )
    return terminals


def _reserve_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _run_renode_command(
    command: List[str],
    cwd: str,
    terminals: List[RenodeSocketTerminal],
    run_seconds: float,
) -> RenodeExecutionCapture:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    warnings: List[str] = []
    errors: List[str] = []
    timed_out = False
    socket_map = _connect_uart_terminals(terminals, process, warnings, run_seconds)
    uart_output = _collect_uart_output(socket_map, process, run_seconds)

    try:
        stdout_text, _ = process.communicate(timeout=max(10.0, run_seconds + 10.0))
    except subprocess.TimeoutExpired:
        process.kill()
        stdout_text, _ = process.communicate()
        timed_out = True
        warnings.append("Renode did not exit within the expected timeout window and was terminated after collecting output.")

    return RenodeExecutionCapture(
        exit_code=process.returncode,
        output_text=stdout_text or "",
        uart_output=uart_output,
        warnings=warnings,
        errors=errors,
        timed_out=timed_out,
    )


def _connect_uart_terminals(
    terminals: List[RenodeSocketTerminal],
    process: subprocess.Popen[str],
    warnings: List[str],
    run_seconds: float,
) -> Dict[str, socket.socket]:
    connected: Dict[str, socket.socket] = {}
    pending = list(terminals)
    deadline = time.monotonic() + max(5.0, run_seconds + 5.0)

    while pending and time.monotonic() < deadline:
        for terminal in list(pending):
            try:
                sock = socket.create_connection(("127.0.0.1", terminal.port), timeout=0.2)
            except OSError:
                continue
            sock.setblocking(False)
            connected[terminal.uart_name] = sock
            pending.remove(terminal)
        if not pending:
            break
        if process.poll() is not None:
            break
        time.sleep(0.05)

    for terminal in pending:
        warnings.append(
            f"Renode UART socket for {terminal.uart_name} did not accept a connection on port {terminal.port}."
        )
    return connected


def _collect_uart_output(
    socket_map: Dict[str, socket.socket],
    process: subprocess.Popen[str],
    run_seconds: float,
) -> Dict[str, str]:
    if not socket_map:
        return {}

    buffers = {
        uart_name: bytearray()
        for uart_name in socket_map
    }
    sockets = dict(socket_map)
    deadline = time.monotonic() + max(5.0, run_seconds + 5.0)

    try:
        while sockets and time.monotonic() < deadline:
            readable, _, _ = select.select(list(sockets.values()), [], [], 0.1)
            for sock in readable:
                uart_name = next((name for name, candidate in sockets.items() if candidate is sock), "")
                if not uart_name:
                    continue
                try:
                    data = sock.recv(4096)
                except OSError:
                    data = b""
                if data:
                    buffers[uart_name].extend(data)
                    continue
                try:
                    sock.close()
                finally:
                    sockets.pop(uart_name, None)
            if process.poll() is not None and not readable:
                break
    finally:
        for sock in sockets.values():
            try:
                sock.close()
            except OSError:
                pass

    return {
        uart_name: _decode_uart_bytes(bytes(data))
        for uart_name, data in buffers.items()
    }


def _decode_uart_bytes(data: bytes) -> str:
    if not data:
        return ""
    # Filter common telnet negotiation bytes in case a terminal falls back to telnet mode.
    filtered = bytearray()
    index = 0
    while index < len(data):
        value = data[index]
        if value == 0xFF and index + 2 < len(data):
            index += 3
            continue
        filtered.append(value)
        index += 1
    text = filtered.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _write_uart_capture_log(path: Path, uart_output: Dict[str, str]) -> None:
    sections: List[str] = []
    for uart_name, text in sorted(uart_output.items()):
        sections.append(f"[{uart_name}]")
        sections.append(text)
        sections.append("")
    path.write_text("\n".join(sections), encoding="utf-8")


def _extract_uart_summary_lines(uart_output: Dict[str, str], limit: int = 4) -> List[str]:
    summary: List[str] = []
    for uart_name, text in sorted(uart_output.items()):
        for line in text.splitlines():
            clean = line.strip()
            if not clean:
                continue
            summary.append(f"UART[{uart_name}] {clean}")
            if len(summary) >= limit:
                return summary
    return summary


def _normalize_expectation_text_list(value: object) -> List[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _iter_app_logic_blocks(
    request_payload: Dict[str, object] | None,
    project_ir: Dict[str, object] | None,
) -> List[str]:
    blocks: List[str] = []
    normalized_request_payload = request_payload if isinstance(request_payload, dict) else {}
    normalized_project_ir = project_ir if isinstance(project_ir, dict) else {}
    sources = [
        normalized_request_payload.get("app_logic"),
    ]
    project_build = normalized_project_ir.get("build", {})
    if isinstance(project_build, dict):
        sources.append(project_build.get("app_logic"))
    request_build = normalized_request_payload.get("build", {})
    if isinstance(request_build, dict):
        sources.append(request_build.get("app_logic"))

    for candidate in sources:
        if not isinstance(candidate, dict):
            continue
        for value in candidate.values():
            text = str(value or "").strip()
            if text:
                blocks.append(text)
    return blocks


def _extract_debug_uart_expectations(code_text: str) -> List[str]:
    patterns = (
        re.compile(r'DebugUart_WriteLine\s*\(\s*[^,]+,\s*"((?:\\.|[^"\\])*)"', re.S),
        re.compile(r'DebugUart_Write\s*\(\s*[^,]+,\s*\(const\s+uint8_t\s*\*\)\s*"((?:\\.|[^"\\])*)"', re.S),
    )
    lines: List[str] = []
    for pattern in patterns:
        for match in pattern.finditer(code_text):
            text = _decode_c_string_literal(match.group(1)).strip()
            if text:
                lines.append(text)
    return lines


def _decode_c_string_literal(value: str) -> str:
    text = str(value)
    try:
        return bytes(text, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return text.replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\t", "\t").replace(r"\\", "\\")


def _normalize_expected_probe_state(value: object) -> str | None:
    if isinstance(value, bool):
        return "1" if value else "0"
    text = str(value).strip().lower()
    if text in {"1", "true", "on", "high"}:
        return "1"
    if text in {"0", "false", "off", "low"}:
        return "0"
    return None


def _load_runtime_expectations(expectation_file: Path) -> tuple[Dict[str, object], List[str]]:
    if not expectation_file.exists():
        return {}, []
    try:
        payload = json.loads(expectation_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"Renode expectation file could not be parsed: {exc}"]
    if not isinstance(payload, dict):
        return {}, ["Renode expectation file must contain a JSON object."]

    warnings: List[str] = []
    expectations: Dict[str, object] = {}

    uart_contains = _normalize_expectation_text_list(payload.get("uart_contains"))
    if uart_contains:
        expectations["uart_contains"] = uart_contains

    uart_any_contains = _normalize_expectation_text_list(payload.get("uart_any_contains"))
    if uart_any_contains:
        expectations["uart_any_contains"] = uart_any_contains

    uart_not_contains = _normalize_expectation_text_list(payload.get("uart_not_contains"))
    if uart_not_contains:
        expectations["uart_not_contains"] = uart_not_contains

    uart_sequence = _normalize_expectation_text_list(payload.get("uart_sequence"))
    if uart_sequence:
        expectations["uart_sequence"] = uart_sequence

    log_contains = _normalize_expectation_text_list(payload.get("log_contains"))
    if log_contains:
        expectations["log_contains"] = log_contains

    log_not_contains = _normalize_expectation_text_list(payload.get("log_not_contains"))
    if log_not_contains:
        expectations["log_not_contains"] = log_not_contains

    raw_exit_code = payload.get("exit_code")
    if raw_exit_code is not None:
        try:
            expectations["exit_code"] = int(raw_exit_code)
        except (TypeError, ValueError):
            warnings.append(f"Renode expectation exit_code is invalid and was ignored: {raw_exit_code!r}")

    return expectations, warnings


def _evaluate_runtime_expectations(
    log_output: str,
    uart_output: Dict[str, str],
    exit_code: int | None,
    expectations: Dict[str, object],
) -> Dict[str, object]:
    combined_output = "\n".join(uart_output.values())
    details: Dict[str, object] = {}

    expected_uart_contains = [str(item) for item in expectations.get("uart_contains", []) if str(item).strip()]
    if expected_uart_contains:
        matched = [text for text in expected_uart_contains if text in combined_output]
        missing = [text for text in expected_uart_contains if text not in combined_output]
        details["uart_contains"] = {
            "expected": expected_uart_contains,
            "matched": matched,
            "missing": missing,
            "passed": not missing,
        }

    expected_uart_any = [str(item) for item in expectations.get("uart_any_contains", []) if str(item).strip()]
    if expected_uart_any:
        matched_any = [text for text in expected_uart_any if text in combined_output]
        details["uart_any_contains"] = {
            "expected": expected_uart_any,
            "matched": matched_any,
            "passed": bool(matched_any),
        }

    forbidden_uart = [str(item) for item in expectations.get("uart_not_contains", []) if str(item).strip()]
    if forbidden_uart:
        forbidden_matched = [text for text in forbidden_uart if text in combined_output]
        details["uart_not_contains"] = {
            "expected": forbidden_uart,
            "matched": forbidden_matched,
            "passed": not forbidden_matched,
        }

    sequence_uart = [str(item) for item in expectations.get("uart_sequence", []) if str(item).strip()]
    if sequence_uart:
        search_start = 0
        matched_sequence: List[str] = []
        missing_sequence: List[str] = []
        for item in sequence_uart:
            index = combined_output.find(item, search_start)
            if index < 0:
                missing_sequence.append(item)
                break
            matched_sequence.append(item)
            search_start = index + len(item)
        if missing_sequence:
            missing_sequence.extend(sequence_uart[len(matched_sequence) + 1 :])
        details["uart_sequence"] = {
            "expected": sequence_uart,
            "matched": matched_sequence,
            "missing": missing_sequence,
            "passed": not missing_sequence,
        }

    expected_log_contains = [str(item) for item in expectations.get("log_contains", []) if str(item).strip()]
    if expected_log_contains:
        matched_log = [text for text in expected_log_contains if text in log_output]
        missing_log = [text for text in expected_log_contains if text not in log_output]
        details["log_contains"] = {
            "expected": expected_log_contains,
            "matched": matched_log,
            "missing": missing_log,
            "passed": not missing_log,
        }

    forbidden_log = [str(item) for item in expectations.get("log_not_contains", []) if str(item).strip()]
    if forbidden_log:
        forbidden_log_matched = [text for text in forbidden_log if text in log_output]
        details["log_not_contains"] = {
            "expected": forbidden_log,
            "matched": forbidden_log_matched,
            "passed": not forbidden_log_matched,
        }

    if "exit_code" in expectations:
        expected_exit_code = expectations.get("exit_code")
        details["exit_code"] = {
            "expected": expected_exit_code,
            "actual": exit_code,
            "passed": exit_code == expected_exit_code,
        }

    passed_checks = [
        bool(item.get("passed"))
        for item in details.values()
        if isinstance(item, dict) and "passed" in item
    ]
    overall_passed = all(passed_checks) if passed_checks else None
    return {
        "combined_uart_output": combined_output,
        "checks": details,
        "passed": overall_passed,
    }


def _render_runtime_validation_failures(validation_details: Dict[str, object]) -> List[str]:
    checks = validation_details.get("checks", {})
    if not isinstance(checks, dict):
        return []

    errors: List[str] = []
    contains = checks.get("uart_contains", {})
    if isinstance(contains, dict):
        missing = [str(item) for item in contains.get("missing", []) if str(item).strip()]
        if missing:
            errors.append("Renode UART validation did not observe expected text: " + "; ".join(missing))

    any_contains = checks.get("uart_any_contains", {})
    if isinstance(any_contains, dict) and any_contains.get("passed") is False:
        expected = [str(item) for item in any_contains.get("expected", []) if str(item).strip()]
        if expected:
            errors.append("Renode UART validation did not observe any allowed text: " + "; ".join(expected))

    not_contains = checks.get("uart_not_contains", {})
    if isinstance(not_contains, dict):
        matched = [str(item) for item in not_contains.get("matched", []) if str(item).strip()]
        if matched:
            errors.append("Renode UART validation observed forbidden text: " + "; ".join(matched))

    sequence = checks.get("uart_sequence", {})
    if isinstance(sequence, dict):
        missing_sequence = [str(item) for item in sequence.get("missing", []) if str(item).strip()]
        if missing_sequence:
            errors.append("Renode UART validation did not match the expected sequence: " + " -> ".join(missing_sequence))

    log_contains = checks.get("log_contains", {})
    if isinstance(log_contains, dict):
        missing_log = [str(item) for item in log_contains.get("missing", []) if str(item).strip()]
        if missing_log:
            errors.append("Renode log validation did not observe expected text: " + "; ".join(missing_log))

    log_not_contains = checks.get("log_not_contains", {})
    if isinstance(log_not_contains, dict):
        matched_log = [str(item) for item in log_not_contains.get("matched", []) if str(item).strip()]
        if matched_log:
            errors.append("Renode log validation observed forbidden text: " + "; ".join(matched_log))

    exit_code = checks.get("exit_code", {})
    if isinstance(exit_code, dict) and exit_code.get("passed") is False:
        errors.append(
            f"Renode exited with code {exit_code.get('actual')}, expected {exit_code.get('expected')}."
        )

    return errors


def _plan_runtime_patches(
    project_dir: Path,
    uvprojx_path: Path,
    platform_key: str,
) -> tuple[List[RenodeMemoryPatch], List[str]]:
    if platform_key != "stm32f103":
        return [], []
    if not _project_uses_external_clock(project_dir / "project_ir.json"):
        return [], []

    patch_address = _find_generated_main_clock_call_patch(project_dir, uvprojx_path)
    if patch_address is None:
        return [], [
            "Renode detected an STM32F103 external-clock project but could not locate the generated "
            "SystemClock_Config call site, so no simulation-only clock workaround was applied."
        ]

    return (
        [
            RenodeMemoryPatch(
                address=patch_address,
                value=0xBF00BF00,
                width="doubleword",
                summary=(
                    "Applied a Renode-only STM32F103 workaround that skips SystemClock_Config; "
                    "UART/logic validation is available, but simulated clocks and timers may differ from hardware."
                ),
            )
        ],
        [],
    )


def _project_uses_external_clock(project_ir_path: Path) -> bool:
    if not project_ir_path.exists():
        return False
    try:
        payload = json.loads(project_ir_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False

    constraints = payload.get("constraints", {})
    if not isinstance(constraints, dict):
        return False
    clock_plan = constraints.get("clock_plan", {})
    if not isinstance(clock_plan, dict):
        return False

    lines = clock_plan.get("system_clock_config", [])
    if not isinstance(lines, list):
        return False
    clock_text = "\n".join(str(line) for line in lines)
    return "RCC_OSCILLATORTYPE_HSE" in clock_text or "RCC_PLL_" in clock_text or "PLLSOURCE_HSE" in clock_text


def _find_generated_main_clock_call_patch(project_dir: Path, uvprojx_path: Path) -> int | None:
    main_source = project_dir / "Core" / "Src" / "main.c"
    if not _generated_main_calls_system_clock_config(main_source):
        return None

    map_path = uvprojx_path.parent / "Objects" / f"{uvprojx_path.stem}.map"
    main_symbol = _read_thumb_symbol_address(map_path, "main")
    if main_symbol is None:
        return None
    return (main_symbol & ~1) + 4


def _generated_main_calls_system_clock_config(main_source: Path) -> bool:
    if not main_source.exists():
        return False
    try:
        text = main_source.read_text(encoding="utf-8")
    except OSError:
        return False

    hal_init_index = text.find("HAL_Init();")
    clock_index = text.find("SystemClock_Config();")
    gpio_init_index = text.find("MX_GPIO_Init();")
    return hal_init_index >= 0 and clock_index > hal_init_index and gpio_init_index > clock_index


def _read_thumb_symbol_address(map_path: Path, symbol_name: str) -> int | None:
    if not map_path.exists():
        return None
    pattern = re.compile(
        rf"^\s*{re.escape(symbol_name)}\s+0x([0-9A-Fa-f]+)\s+Thumb Code\b",
        re.MULTILINE,
    )
    try:
        content = map_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = pattern.search(content)
    if not match:
        return None
    try:
        return int(match.group(1), 16)
    except ValueError:
        return None


def _render_memory_patch_command(patch: RenodeMemoryPatch) -> str:
    normalized_width = patch.width.strip().lower()
    if normalized_width == "byte":
        command_name = "WriteByte"
        value_mask = 0xFF
        hex_width = 2
    elif normalized_width == "word":
        command_name = "WriteWord"
        value_mask = 0xFFFF
        hex_width = 4
    else:
        command_name = "WriteDoubleWord"
        value_mask = 0xFFFFFFFF
        hex_width = 8
    return (
        f"sysbus {command_name} 0x{patch.address:08X} "
        f"0x{patch.value & value_mask:0{hex_width}X}"
    )


def _select_platform_profile(chip: str) -> RenodePlatformProfile | None:
    normalized_chip = str(chip).strip().upper()
    for profile in RENODE_PLATFORM_PROFILES:
        if any(normalized_chip.startswith(prefix) for prefix in profile.chip_prefixes):
            return profile
    return None


def _collect_uart_analyzers(project_ir_path: Path, profile: RenodePlatformProfile) -> List[str]:
    payload = _load_project_ir(project_ir_path)
    if not payload:
        return list(profile.default_uart_analyzers)

    analyzers: List[str] = []
    modules = payload.get("modules", [])
    if isinstance(modules, list):
        for module in modules:
            if not isinstance(module, dict):
                continue
            interfaces = module.get("interfaces", {})
            if not isinstance(interfaces, dict):
                continue
            uart_instance = str(interfaces.get("uart", "")).strip().lower()
            if uart_instance and uart_instance not in analyzers:
                analyzers.append(uart_instance)

    if analyzers:
        return analyzers
    return list(profile.default_uart_analyzers)


def _load_project_target(project_ir_path: Path) -> Dict[str, object]:
    payload = _load_project_ir(project_ir_path)
    target = payload.get("target", {})
    return target if isinstance(target, dict) else {}


def _load_project_ir(project_ir_path: Path) -> Dict[str, object]:
    if not project_ir_path.exists():
        return {}
    try:
        payload = json.loads(project_ir_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _plan_simulation_artifacts(
    project_ir_path: Path,
) -> tuple[List[str], List[RenodeTimedAction], List[str], List[str], List[str]]:
    if not project_ir_path.exists():
        return [], [], [], [], []
    try:
        payload = json.loads(project_ir_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], [], [], [], ["project_ir.json could not be parsed for Renode simulation metadata."]
    if not isinstance(payload, dict):
        return [], [], [], [], []

    signal_map = _collect_module_signal_pins(payload)
    i2c_devices = _collect_i2c_device_map(payload)
    overlay_commands: List[str] = []
    timed_actions: List[RenodeTimedAction] = []
    attached_simulation: List[str] = []
    scheduled_interactions: List[str] = []
    warnings: List[str] = []

    modules = payload.get("modules", [])
    if not isinstance(modules, list):
        return [], [], [], [], []

    for module in modules:
        if not isinstance(module, dict):
            continue
        module_name = str(module.get("name", "")).strip()
        simulation = module.get("simulation", {})
        renode = simulation.get("renode", {}) if isinstance(simulation, dict) else {}
        attach_items = renode.get("attach", []) if isinstance(renode, dict) else []
        if not isinstance(attach_items, list):
            continue
        for attach in attach_items:
            if not isinstance(attach, dict):
                continue
            kind = str(attach.get("kind", "")).strip().lower()
            if kind == "led":
                command, summary, warning, actions, action_summaries = _build_led_overlay_command(
                    module_name,
                    attach,
                    signal_map,
                )
                if command:
                    overlay_commands.append(command)
                    attached_simulation.append(summary)
                    timed_actions.extend(actions)
                    scheduled_interactions.extend(action_summaries)
                if warning:
                    warnings.append(warning)
            elif kind == "button":
                command, summary, warning, actions, action_summaries = _build_button_overlay_commands(
                    module_name,
                    attach,
                    signal_map,
                )
                if command:
                    overlay_commands.append(command)
                    attached_simulation.append(summary)
                    timed_actions.extend(actions)
                    scheduled_interactions.extend(action_summaries)
                if warning:
                    warnings.append(warning)
            elif kind == "i2c_mock":
                commands, summary, warning = _build_i2c_mock_overlay_commands(module_name, attach, module, i2c_devices)
                if commands:
                    overlay_commands.extend(commands)
                    attached_simulation.append(summary)
                if warning:
                    warnings.append(warning)

    return overlay_commands, timed_actions, attached_simulation, scheduled_interactions, warnings


def _collect_module_signal_pins(project_ir: Dict[str, object]) -> Dict[str, Dict[str, str]]:
    peripherals = project_ir.get("peripherals", {})
    if not isinstance(peripherals, dict):
        return {}
    raw_signals = peripherals.get("signals", [])
    if not isinstance(raw_signals, list):
        return {}
    signal_map: Dict[str, Dict[str, str]] = {}
    for item in raw_signals:
        if not isinstance(item, dict):
            continue
        module_name = str(item.get("module", "")).strip()
        signal_name = str(item.get("signal", "")).strip().lower()
        pin = str(item.get("pin", "")).strip().upper()
        if not module_name or not signal_name or not pin:
            continue
        signal_map.setdefault(module_name, {})
        signal_map[module_name][signal_name] = pin
    return signal_map


def _collect_i2c_device_map(project_ir: Dict[str, object]) -> Dict[str, Dict[str, str]]:
    peripherals = project_ir.get("peripherals", {})
    if not isinstance(peripherals, dict):
        return {}
    raw_buses = peripherals.get("buses", [])
    if not isinstance(raw_buses, list):
        return {}
    device_map: Dict[str, Dict[str, str]] = {}
    for bus in raw_buses:
        if not isinstance(bus, dict):
            continue
        if str(bus.get("kind", "")).strip().lower() != "i2c":
            continue
        bus_name = str(bus.get("bus", "")).strip().upper()
        devices = bus.get("devices", [])
        if not isinstance(devices, list):
            continue
        for device in devices:
            if not isinstance(device, dict):
                continue
            module_name = str(device.get("module", "")).strip()
            address = str(device.get("address", "")).strip().lower()
            if not module_name or not bus_name or not address:
                continue
            device_map[module_name] = {
                "bus": bus_name,
                "address": address,
            }
    return device_map


def _build_led_overlay_command(
    module_name: str,
    attach: Dict[str, object],
    signal_map: Dict[str, Dict[str, str]],
) -> tuple[str, str, str, List[RenodeTimedAction], List[str]]:
    signal_name = str(attach.get("signal", "control")).strip().lower() or "control"
    pin = signal_map.get(module_name, {}).get(signal_name, "")
    if not pin:
        return "", "", f"Renode simulation metadata for {module_name} requested LED signal {signal_name}, but no GPIO pin was planned.", [], []
    gpio_name, pin_number = _renode_gpio_parts(pin)
    if not gpio_name:
        return "", "", f"Renode could not map pin {pin} for module {module_name}.", [], []
    led_name = _sanitize_identifier(attach.get("name") or f"{module_name}_{signal_name}_led")
    invert = bool(attach.get("invert", False))
    body = f"{led_name}: Miscellaneous.LED @ {gpio_name} {pin_number}"
    if invert:
        body += " { invert: true }"
    summary = f"Renode attached LED {led_name} on {pin} for module {module_name}."
    actions: List[RenodeTimedAction] = []
    action_summaries: List[str] = []
    raw_probes = attach.get("probes", [])
    if isinstance(raw_probes, list):
        led_path = f"sysbus.{gpio_name}.{led_name}"
        for index, raw_probe in enumerate(raw_probes, start=1):
            if not isinstance(raw_probe, dict):
                continue
            at_seconds = _coerce_float(raw_probe.get("at"), default=1.0)
            label = _sanitize_identifier(raw_probe.get("label") or raw_probe.get("name") or led_name or f"led_probe_{index}")
            actions.append(
                RenodeTimedAction(
                    at_seconds=at_seconds,
                    command=_render_led_probe_command(led_path=led_path, label=label),
                    summary=f"Renode scheduled LED probe {label} at {at_seconds:g}s.",
                )
            )
            action_summaries.append(f"Renode scheduled LED probe {label} at {at_seconds:g}s.")
    return f'machine LoadPlatformDescriptionFromString "{body}"', summary, "", actions, action_summaries


def _build_button_overlay_commands(
    module_name: str,
    attach: Dict[str, object],
    signal_map: Dict[str, Dict[str, str]],
) -> tuple[str, str, str, List[RenodeTimedAction], List[str]]:
    signal_name = str(attach.get("signal", "input")).strip().lower() or "input"
    pin = signal_map.get(module_name, {}).get(signal_name, "")
    if not pin:
        return "", "", f"Renode simulation metadata for {module_name} requested button signal {signal_name}, but no GPIO pin was planned.", [], []
    gpio_name, pin_number = _renode_gpio_parts(pin)
    if not gpio_name:
        return "", "", f"Renode could not map pin {pin} for module {module_name}.", [], []
    button_name = _sanitize_identifier(attach.get("name") or f"{module_name}_{signal_name}_button")
    invert = bool(attach.get("invert", False))
    property_lines = ["-> " + gpio_name + "@" + pin_number]
    if invert:
        property_lines.insert(0, "invert: true")
    body = f"{button_name}: Miscellaneous.Button @ {gpio_name} {pin_number} {{ " + "; ".join(property_lines) + " }"
    command = f'machine LoadPlatformDescriptionFromString "{body}"'
    summary = f"Renode attached button {button_name} on {pin} for module {module_name}."

    actions: List[RenodeTimedAction] = []
    action_summaries: List[str] = []
    raw_actions = attach.get("actions", [])
    if isinstance(raw_actions, list):
        for raw_action in raw_actions:
            if not isinstance(raw_action, dict):
                continue
            at_seconds = _coerce_float(raw_action.get("at"), default=1.0)
            action_name = str(raw_action.get("action", "press_and_release")).strip().lower()
            monitor_command = _button_action_command(
                gpio_name=gpio_name,
                button_name=button_name,
                action_name=action_name,
            )
            if not monitor_command:
                continue
            actions.append(
                RenodeTimedAction(
                    at_seconds=at_seconds,
                    command=monitor_command,
                    summary=f"Renode scheduled {action_name} for button {button_name} at {at_seconds:g}s.",
                )
            )
            action_summaries.append(f"Renode scheduled {action_name} for button {button_name} at {at_seconds:g}s.")
    return command, summary, "", actions, action_summaries


def _build_i2c_mock_overlay_commands(
    module_name: str,
    attach: Dict[str, object],
    module: Dict[str, object],
    i2c_devices: Dict[str, Dict[str, str]],
) -> tuple[List[str], str, str]:
    module_i2c = i2c_devices.get(module_name, {})
    bus_name = str(module_i2c.get("bus", "")).strip().lower()
    address = str(module_i2c.get("address", "")).strip().lower()
    if not bus_name:
        interfaces = module.get("interfaces", {})
        if isinstance(interfaces, dict):
            bus_name = str(interfaces.get("i2c", "")).strip().lower()
    if not address:
        options = module.get("options", {})
        if isinstance(options, dict):
            raw_address = options.get("address")
            if raw_address is not None:
                try:
                    address = hex(int(str(raw_address), 0)).lower()
                except (TypeError, ValueError):
                    address = ""
    if not bus_name or not address:
        return [], "", f"Renode simulation metadata for {module_name} requested an I2C mock, but the planned I2C bus/address was incomplete."
    model = str(attach.get("model", "echo")).strip().lower() or "echo"
    mock_name = _sanitize_identifier(attach.get("name") or f"{module_name}_{model}")

    if model in {"at24c02", "at24c32"}:
        size_bytes = 256 if model == "at24c02" else 4096
        address_width_bytes = 1 if model == "at24c02" else 2
        fill_byte = _coerce_int(attach.get("fill_byte"), default=0xFF) & 0xFF
        commands = [
            f'machine LoadPlatformDescriptionFromString "{mock_name}: Mocks.DummyI2CSlave @ {bus_name} {address}"',
            _render_at24_i2c_python_setup(
                mock_path=f"sysbus.{bus_name}.{mock_name}",
                address_width_bytes=address_width_bytes,
                size_bytes=size_bytes,
                fill_byte=fill_byte,
            ),
        ]
        summary = (
            f"Renode attached memory-backed {model.upper()} I2C mock {mock_name} "
            f"on {bus_name} {address} for module {module_name}."
        )
        return commands, summary, ""

    peripheral_type = "Mocks.EchoI2CDevice" if model == "echo" else "Mocks.DummyI2CSlave"
    commands = [f'machine LoadPlatformDescriptionFromString "{mock_name}: {peripheral_type} @ {bus_name} {address}"']
    summary = f"Renode attached {model} I2C mock {mock_name} on {bus_name} {address} for module {module_name}."
    return commands, summary, ""


def _render_at24_i2c_python_setup(
    mock_path: str,
    address_width_bytes: int,
    size_bytes: int,
    fill_byte: int,
) -> str:
    python_lines = [
        "python",
        '"""',
        "class At24CxxI2CPeripheral:",
        "    def __init__(self, dummy, address_width_bytes, size_bytes, fill_byte):",
        "        self.dummy = dummy",
        "        self.address_width_bytes = max(1, int(address_width_bytes))",
        "        self.size_bytes = max(1, int(size_bytes))",
        "        self.pointer = 0",
        "        self.memory = bytearray([int(fill_byte) & 0xFF] * self.size_bytes)",
        "",
        "    def write(self, data):",
        "        if data is None:",
        "            return",
        "        payload = [int(item) & 0xFF for item in data]",
        "        if len(payload) < self.address_width_bytes:",
        "            return",
        "        address = 0",
        "        for item in payload[: self.address_width_bytes]:",
        "            address = ((address << 8) | item) % self.size_bytes",
        "        body = payload[self.address_width_bytes :]",
        "        if body:",
        "            for offset, value in enumerate(body):",
        "                self.memory[(address + offset) % self.size_bytes] = value",
        "            self.pointer = (address + len(body)) % self.size_bytes",
        "            return",
        "        self.pointer = address",
        "        self.dummy.EnqueueResponseBytes(",
        "            [self.memory[(self.pointer + offset) % self.size_bytes] for offset in range(self.size_bytes)]",
        "        )",
        "",
        "def mc_setup_at24_i2c_peripheral(path, address_width_bytes, size_bytes, fill_byte):",
        "    dummy = monitor.Machine[path]",
        "    dummy.DataReceived += At24CxxI2CPeripheral(",
        "        dummy,",
        "        address_width_bytes=address_width_bytes,",
        "        size_bytes=size_bytes,",
        "        fill_byte=fill_byte,",
        "    ).write",
        '"""',
        (
            f'setup_at24_i2c_peripheral "{mock_path}" '
            f"{int(address_width_bytes)} {int(size_bytes)} {int(fill_byte)}"
        ),
    ]
    return "\n".join(python_lines)


def _render_led_probe_command(led_path: str, label: str) -> str:
    escaped_path = led_path.replace("\\", "\\\\").replace('"', '\\"')
    escaped_label = str(label).replace("\\", "\\\\").replace('"', '\\"')
    return (
        f'python "state = bool(monitor.Machine[\\"{escaped_path}\\"].State); '
        f'print(\\"[SIM][LED] {escaped_label}=\\" + (\\"1\\" if state else \\"0\\"))"'
    )


def _renode_gpio_parts(pin: str) -> tuple[str, str]:
    normalized = str(pin).strip().upper()
    match = re.match(r"^P([A-Z])(\d+)$", normalized)
    if not match:
        return "", ""
    return f"gpioPort{match.group(1)}", match.group(2)


def _sanitize_identifier(value: object) -> str:
    text = re.sub(r"[^0-9A-Za-z_]+", "_", str(value).strip()).strip("_").lower()
    if not text:
        return "sim_device"
    if text[0].isdigit():
        return f"sim_{text}"
    return text


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return int(default)


def _button_action_command(gpio_name: str, button_name: str, action_name: str) -> str:
    normalized = action_name.strip().lower()
    if normalized == "press":
        suffix = "Press"
    elif normalized == "release":
        suffix = "Release"
    else:
        suffix = "PressAndRelease"
    return f"sysbus.{gpio_name}.{button_name} {suffix}"


def _format_run_seconds(value: float) -> str:
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text or "1"


def _extract_summary_lines(output_text: str, limit: int = 40) -> List[str]:
    lines: List[str] = []
    for raw_line in output_text.splitlines():
        clean_line = _ANSI_ESCAPE_RE.sub("", raw_line).strip()
        if not clean_line:
            continue
        lines.append(clean_line)
        if len(lines) >= limit:
            break
    return lines


def _detect_run_errors(lines: List[str]) -> List[str]:
    errors: List[str] = []
    for line in lines:
        lower = line.lower()
        if "there was an error executing command" in lower:
            errors.append(line)
        elif "[error]" in lower:
            errors.append(line)
        elif "unexpected options detected" in lower:
            errors.append(line)
        elif "parameters did not match the signature" in lower:
            errors.append(line)
    return errors
