from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .family_support import collect_hal_sources, get_family_support
from .keil_builder import KeilBuildResult, KeilDoctorResult, read_text_with_fallback
from .path_config import resolve_configured_path

GccDoctorResult = KeilDoctorResult
GccBuildResult = KeilBuildResult

_GCC_SEARCH_DIRS = [
    Path(r"D:\Arm GNU Toolchain arm-none-eabi\14.3 rel1\bin"),
    Path(r"D:\arm-gnu-toolchain\bin"),
    Path(r"D:\arm-gcc\bin"),
    Path(r"C:\Program Files\Arm GNU Toolchain arm-none-eabi\bin"),
    Path(r"C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi\bin"),
]


def find_arm_gcc(explicit_path: str | Path | None = None) -> Path | None:
    candidates: List[Path] = []
    if explicit_path is not None:
        candidates.append(Path(explicit_path))

    configured_path, _source = resolve_configured_path("arm_gcc_path")
    if configured_path:
        candidates.append(Path(configured_path))

    for search_dir in _GCC_SEARCH_DIRS:
        candidates.append(search_dir / "arm-none-eabi-gcc.exe")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    found = _find_arm_gcc_from_path()
    if found is not None:
        return found

    for search_dir in _GCC_SEARCH_DIRS:
        parent = search_dir.parent
        if not parent.exists():
            continue
        for child in parent.iterdir():
            if child.is_dir():
                gcc = child / "bin" / "arm-none-eabi-gcc.exe"
                if gcc.exists():
                    return gcc

    return None


def _find_arm_gcc_from_path() -> Path | None:
    try:
        completed = subprocess.run(
            ["where.exe", "arm-none-eabi-gcc.exe"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.decode("utf-8", errors="replace").splitlines():
        candidate = Path(line.strip())
        if candidate.exists():
            return candidate
    return None


def doctor_gcc_project(
    project_path: str | Path,
    gcc_path: str | Path | None = None,
) -> GccDoctorResult:
    project_dir, makefile_path, errors = _resolve_gcc_project_paths(project_path)
    warnings: List[str] = []
    checked_paths: List[Dict[str, object]] = []
    resolved_gcc = ""

    if errors:
        return GccDoctorResult(
            ready=False,
            project_dir=str(project_dir),
            uvprojx_path="",
            uv4_path="",
            fromelf_path="",
            device_pack_path="",
            build_log_path="",
            checked_paths=[],
            warnings=[],
            errors=errors,
            builder_kind="gcc",
        )

    try:
        family = _load_target_family(project_dir / "project_ir.json")
        support = get_family_support(family)
    except ValueError as exc:
        return GccDoctorResult(
            ready=False,
            project_dir=str(project_dir),
            uvprojx_path="",
            uv4_path="",
            fromelf_path="",
            device_pack_path="",
            build_log_path="",
            checked_paths=[],
            warnings=[],
            errors=[str(exc)],
            builder_kind="gcc",
        )

    resolved_gcc_path = find_arm_gcc(gcc_path)
    if resolved_gcc_path is None:
        errors.append(
            "arm-none-eabi-gcc was not found. "
            "Install the ARM GNU Toolchain and configure ARM_GCC_PATH, "
            "or pass the path explicitly."
        )
    else:
        resolved_gcc = str(resolved_gcc_path)
        checked_paths.append({"path": resolved_gcc, "kind": "arm-none-eabi-gcc", "exists": True})

    checked_paths.append({"path": str(makefile_path), "kind": "Makefile", "exists": makefile_path.exists()})
    if not makefile_path.exists():
        errors.append(f"Missing Makefile: {makefile_path}")

    for path, kind in _required_source_paths(project_dir, support):
        exists = path.exists()
        checked_paths.append({"path": str(path), "kind": kind, "exists": exists})
        if not exists:
            errors.append(f"Missing {kind}: {path}")

    build_log_path = str(project_dir / "build_gcc.log")

    return GccDoctorResult(
        ready=not errors,
        project_dir=str(project_dir),
        uvprojx_path=str(makefile_path),
        uv4_path=resolved_gcc,
        fromelf_path="",
        device_pack_path="",
        build_log_path=build_log_path,
        checked_paths=checked_paths,
        warnings=warnings,
        errors=errors,
        builder_kind="gcc",
    )


def build_gcc_project(
    project_path: str | Path,
    gcc_path: str | Path | None = None,
) -> GccBuildResult:
    doctor = doctor_gcc_project(project_path, gcc_path)
    if not doctor.ready:
        return GccBuildResult(
            ready=False,
            built=False,
            hex_generated=False,
            project_dir=doctor.project_dir,
            uvprojx_path=doctor.uvprojx_path,
            uv4_path=doctor.uv4_path,
            fromelf_path="",
            device_pack_path="",
            build_log_path=doctor.build_log_path,
            hex_file="",
            command=[],
            hex_command=[],
            exit_code=None,
            summary_lines=[],
            warnings=doctor.warnings,
            errors=doctor.errors,
            builder_kind="gcc",
        )

    project_dir = Path(doctor.project_dir)
    gcc_bin_dir = Path(doctor.uv4_path).parent
    make_exe = _find_make(gcc_bin_dir)
    build_log_path = Path(doctor.build_log_path)

    command = [
        str(make_exe),
        "-C", str(project_dir),
        f"GCC_PATH={gcc_bin_dir}",
        "-j4",
    ]

    if build_log_path.exists():
        build_log_path.unlink()

    try:
        completed = subprocess.run(
            command,
            cwd=str(project_dir),
            capture_output=True,
            check=False,
            timeout=300,
        )
    except OSError as exc:
        return GccBuildResult(
            ready=True,
            built=False,
            hex_generated=False,
            project_dir=str(project_dir),
            uvprojx_path=doctor.uvprojx_path,
            uv4_path=doctor.uv4_path,
            fromelf_path="",
            device_pack_path="",
            build_log_path=str(build_log_path),
            hex_file="",
            command=command,
            hex_command=[],
            exit_code=None,
            summary_lines=[],
            warnings=list(doctor.warnings),
            errors=[f"Failed to launch make: {exc}"],
            builder_kind="gcc",
        )
    except subprocess.TimeoutExpired:
        return GccBuildResult(
            ready=True,
            built=False,
            hex_generated=False,
            project_dir=str(project_dir),
            uvprojx_path=doctor.uvprojx_path,
            uv4_path=doctor.uv4_path,
            fromelf_path="",
            device_pack_path="",
            build_log_path=str(build_log_path),
            hex_file="",
            command=command,
            hex_command=[],
            exit_code=None,
            summary_lines=[],
            warnings=list(doctor.warnings),
            errors=["GCC build timed out after 300 seconds."],
            builder_kind="gcc",
        )

    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    combined = stdout + "\n" + stderr
    build_log_path.write_text(combined, encoding="utf-8")

    summary_lines = _extract_gcc_summary(combined)
    warnings = list(doctor.warnings)
    errors: List[str] = []
    built = completed.returncode == 0

    error_count = sum(1 for line in combined.splitlines() if ": error:" in line.lower())
    warning_count = sum(1 for line in combined.splitlines() if ": warning:" in line.lower())

    if warning_count > 0:
        warnings.append(f"GCC build completed with {warning_count} warning(s).")
    if error_count > 0:
        errors.append(f"GCC build failed with {error_count} error(s).")
        built = False
    elif not built:
        errors.append("GCC build failed. Check build_gcc.log for details.")

    hex_file = ""
    hex_generated = False
    build_dir = project_dir / "build"
    if built:
        hex_candidates = sorted(build_dir.glob("*.hex")) if build_dir.exists() else []
        if hex_candidates:
            hex_file = str(hex_candidates[0])
            hex_generated = True

    return GccBuildResult(
        ready=True,
        built=built,
        hex_generated=hex_generated,
        project_dir=str(project_dir),
        uvprojx_path=doctor.uvprojx_path,
        uv4_path=doctor.uv4_path,
        fromelf_path="",
        device_pack_path="",
        build_log_path=str(build_log_path),
        hex_file=hex_file,
        command=command,
        hex_command=[],
        exit_code=completed.returncode,
        summary_lines=summary_lines,
        warnings=warnings,
        errors=errors,
        builder_kind="gcc",
    )


def _find_make(gcc_bin_dir: Path | None = None) -> str:
    candidates: List[Path] = []
    if gcc_bin_dir is not None:
        candidates.append(gcc_bin_dir / "make.exe")
        candidates.append(gcc_bin_dir / "cs-make.exe")
        candidates.append(gcc_bin_dir / "mingw32-make.exe")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    try:
        result = subprocess.run(["where.exe", "make.exe"], capture_output=True, check=False)
        if result.returncode == 0:
            for line in result.stdout.decode("utf-8", errors="replace").splitlines():
                if Path(line.strip()).exists():
                    return line.strip()
    except OSError:
        pass

    try:
        result = subprocess.run(["where.exe", "mingw32-make.exe"], capture_output=True, check=False)
        if result.returncode == 0:
            for line in result.stdout.decode("utf-8", errors="replace").splitlines():
                if Path(line.strip()).exists():
                    return line.strip()
    except OSError:
        pass

    return "make"


def _resolve_gcc_project_paths(project_path: str | Path) -> tuple[Path, Path, List[str]]:
    path = Path(project_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    errors: List[str] = []

    if not path.exists():
        return path, path / "Makefile", [f"Project path does not exist: {path}"]

    if path.is_file():
        if path.name == "Makefile":
            return path.parent, path, []
        if path.suffix.lower() == ".uvprojx":
            project_dir = path.parent.parent if path.parent.name.upper() == "MDK-ARM" else path.parent
            return project_dir, project_dir / "Makefile", []
        return path.parent, path.parent / "Makefile", []

    return path, path / "Makefile", []


def _required_source_paths(project_dir: Path, support) -> List[tuple[Path, str]]:
    return [
        (project_dir / "Core" / "Src" / "main.c", "generated source"),
        (project_dir / "Core" / "Src" / "peripherals.c", "generated source"),
        (project_dir / "App" / "Src" / "app_main.c", "generated source"),
        (project_dir / "Drivers" / "CMSIS" / "Include", "CMSIS include dir"),
        (
            project_dir / "Drivers" / "CMSIS" / "Device" / "ST" / support.cmsis_device_dir / "Include",
            "device include dir",
        ),
        (project_dir / "Drivers" / support.hal_driver_dir / "Inc", "HAL include dir"),
        (project_dir / "Drivers" / support.hal_driver_dir / "Src", "HAL source dir"),
    ]


def _load_target_family(project_ir_path: Path) -> str:
    if not project_ir_path.exists():
        raise ValueError(f"Missing project_ir.json, cannot determine target family: {project_ir_path}")
    try:
        payload = json.loads(read_text_with_fallback(project_ir_path))
    except (OSError, ValueError) as exc:
        raise ValueError(f"project_ir.json could not be parsed: {exc}") from exc

    target = payload.get("target", {})
    if isinstance(target, dict):
        family = str(target.get("family", "")).strip()
        if family:
            return family
    raise ValueError(f"project_ir.json did not declare target.family: {project_ir_path}")


def _extract_gcc_summary(output: str) -> List[str]:
    interesting: List[str] = []
    for line in output.splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        lower = normalized.lower()
        if ": error:" in lower or ": warning:" in lower or "undefined reference" in lower:
            interesting.append(normalized)
        elif "error:" in lower and ("make" in lower or "ld" in lower):
            interesting.append(normalized)

    if interesting:
        return interesting[-30:]

    lines = output.strip().splitlines()
    return lines[-10:] if lines else []
