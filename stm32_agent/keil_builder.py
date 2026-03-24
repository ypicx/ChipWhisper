from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from .family_support import collect_hal_sources, get_family_support
from .path_config import resolve_configured_path

_TEXT_DECODE_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk")


@dataclass
class KeilDoctorResult:
    ready: bool
    project_dir: str
    uvprojx_path: str
    uv4_path: str
    fromelf_path: str
    device_pack_path: str
    build_log_path: str
    checked_paths: List[Dict[str, object]]
    warnings: List[str]
    errors: List[str]
    builder_kind: str = "keil"

    def to_dict(self) -> Dict[str, object]:
        return {
            "builder_kind": self.builder_kind,
            "ready": self.ready,
            "project_dir": self.project_dir,
            "uvprojx_path": self.uvprojx_path,
            "uv4_path": self.uv4_path,
            "fromelf_path": self.fromelf_path,
            "device_pack_path": self.device_pack_path,
            "build_log_path": self.build_log_path,
            "checked_paths": self.checked_paths,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class KeilBuildResult:
    ready: bool
    built: bool
    hex_generated: bool
    project_dir: str
    uvprojx_path: str
    uv4_path: str
    fromelf_path: str
    device_pack_path: str
    build_log_path: str
    hex_file: str
    command: List[str]
    hex_command: List[str]
    exit_code: int | None
    summary_lines: List[str]
    warnings: List[str]
    errors: List[str]
    builder_kind: str = "keil"

    def to_dict(self) -> Dict[str, object]:
        return {
            "builder_kind": self.builder_kind,
            "ready": self.ready,
            "built": self.built,
            "hex_generated": self.hex_generated,
            "project_dir": self.project_dir,
            "uvprojx_path": self.uvprojx_path,
            "uv4_path": self.uv4_path,
            "fromelf_path": self.fromelf_path,
            "device_pack_path": self.device_pack_path,
            "build_log_path": self.build_log_path,
            "hex_file": self.hex_file,
            "command": self.command,
            "hex_command": self.hex_command,
            "exit_code": self.exit_code,
            "summary_lines": self.summary_lines,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def doctor_keil_project(
    project_path: str | Path,
    uv4_path: str | Path | None = None,
    fromelf_path: str | Path | None = None,
) -> KeilDoctorResult:
    project_dir, uvprojx_path, errors = _resolve_project_paths(project_path)
    warnings: List[str] = []
    checked_paths: List[Dict[str, object]] = []
    build_log_path = ""
    resolved_uv4 = ""
    resolved_fromelf = ""
    resolved_device_pack = ""

    if errors:
        return KeilDoctorResult(
            ready=False,
            project_dir=str(project_dir),
            uvprojx_path=str(uvprojx_path),
            uv4_path="",
            fromelf_path="",
            device_pack_path="",
            build_log_path="",
            checked_paths=[],
            warnings=[],
            errors=errors,
        )

    try:
        family = _load_target_family(project_dir / "project_ir.json")
        support = get_family_support(family)
    except ValueError as exc:
        return KeilDoctorResult(
            ready=False,
            project_dir=str(project_dir),
            uvprojx_path=str(uvprojx_path),
            uv4_path="",
            fromelf_path="",
            device_pack_path="",
            build_log_path="",
            checked_paths=[],
            warnings=[],
            errors=[str(exc)],
        )

    build_log_path = str(uvprojx_path.parent / "build.log")

    resolved_uv4_path = find_uv4(uv4_path)
    if resolved_uv4_path is None:
        errors.append("Keil UV4.exe was not found. Pass the path explicitly or configure KEIL_UV4_PATH / UV4_PATH.")
    else:
        resolved_uv4 = str(resolved_uv4_path)
        resolved_fromelf_path = find_fromelf(fromelf_path, resolved_uv4_path)
        resolved_device_pack_path = find_device_family_pack(support.family, resolved_uv4_path)
        if resolved_fromelf_path is not None:
            resolved_fromelf = str(resolved_fromelf_path)
        else:
            warnings.append("fromelf.exe was not found, so HEX export will be skipped after a successful build.")

        if resolved_device_pack_path is not None:
            resolved_device_pack = str(resolved_device_pack_path)
            checked_paths.append(
                {
                    "path": resolved_device_pack,
                    "kind": "device family pack",
                    "exists": True,
                }
            )
        else:
            warnings.append(
                f"{support.device_pack_dir} was not found. Keil device recognition, download, or debug support may be incomplete."
            )

    for path, kind in _required_project_paths(project_dir, support):
        exists = path.exists()
        checked_paths.append(
            {
                "path": str(path),
                "kind": kind,
                "exists": exists,
            }
        )
        if not exists:
            errors.append(f"Missing {kind}: {path}")

    if Path(build_log_path).exists():
        warnings.append(f"Detected an existing build.log that will be overwritten: {build_log_path}")

    return KeilDoctorResult(
        ready=not errors,
        project_dir=str(project_dir),
        uvprojx_path=str(uvprojx_path),
        uv4_path=resolved_uv4,
        fromelf_path=resolved_fromelf,
        device_pack_path=resolved_device_pack,
        build_log_path=build_log_path,
        checked_paths=checked_paths,
        warnings=warnings,
        errors=errors,
    )


def build_keil_project(
    project_path: str | Path,
    uv4_path: str | Path | None = None,
    fromelf_path: str | Path | None = None,
) -> KeilBuildResult:
    doctor = doctor_keil_project(project_path, uv4_path, fromelf_path)
    if not doctor.ready:
        return KeilBuildResult(
            ready=False,
            built=False,
            hex_generated=False,
            project_dir=doctor.project_dir,
            uvprojx_path=doctor.uvprojx_path,
            uv4_path=doctor.uv4_path,
            fromelf_path=doctor.fromelf_path,
            device_pack_path=doctor.device_pack_path,
            build_log_path=doctor.build_log_path,
            hex_file="",
            command=[],
            hex_command=[],
            exit_code=None,
            summary_lines=[],
            warnings=doctor.warnings,
            errors=doctor.errors,
        )

    uvprojx_path = Path(doctor.uvprojx_path)
    build_log_path = Path(doctor.build_log_path)
    command = [
        doctor.uv4_path,
        "-b",
        uvprojx_path.name,
        "-j0",
        "-o",
        build_log_path.name,
    ]

    if build_log_path.exists():
        build_log_path.unlink()

    try:
        completed = subprocess.run(
            command,
            cwd=str(uvprojx_path.parent),
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return KeilBuildResult(
            ready=True,
            built=False,
            hex_generated=False,
            project_dir=doctor.project_dir,
            uvprojx_path=doctor.uvprojx_path,
            uv4_path=doctor.uv4_path,
            fromelf_path=doctor.fromelf_path,
            device_pack_path=doctor.device_pack_path,
            build_log_path=doctor.build_log_path,
            hex_file="",
            command=command,
            hex_command=[],
            exit_code=None,
            summary_lines=[],
            warnings=list(doctor.warnings),
            errors=[f"Failed to launch UV4.exe: {exc}"],
        )

    stdout = _decode_text_output(completed.stdout)
    stderr = _decode_text_output(completed.stderr)
    summary_lines = _extract_build_summary(build_log_path, stdout, stderr)
    warnings = list(doctor.warnings)
    errors: List[str] = []
    error_count, warning_count = _parse_error_warning_counts(summary_lines)
    built = completed.returncode == 0

    if error_count is not None:
        built = error_count == 0
        if warning_count and warning_count > 0:
            warnings.append(f"Keil build completed with {warning_count} warning(s).")
    elif completed.returncode != 0:
        errors.append("Keil command-line build failed. Check build.log or summary_lines for details.")

    if error_count is not None and error_count > 0:
        errors.append(f"Keil build failed with {error_count} error(s).")

    hex_generated = False
    hex_file = ""
    hex_command: List[str] = []

    if built and doctor.fromelf_path:
        axf_path = _find_axf_output(uvprojx_path)
        if axf_path is None:
            errors.append("Keil build succeeded, but no .axf output was found for HEX export.")
        else:
            hex_path = axf_path.with_suffix(".hex")
            hex_command = [
                doctor.fromelf_path,
                "--i32",
                "--output",
                hex_path.name,
                axf_path.name,
            ]
            if hex_path.exists():
                hex_path.unlink()
            try:
                hex_completed = subprocess.run(
                    hex_command,
                    cwd=str(axf_path.parent),
                    capture_output=True,
                    check=False,
                )
            except OSError as exc:
                errors.append(f"Failed to launch fromelf.exe: {exc}")
            else:
                if hex_completed.returncode == 0 and hex_path.exists():
                    hex_generated = True
                    hex_file = str(hex_path)
                else:
                    hex_stdout = _decode_text_output(hex_completed.stdout)
                    hex_stderr = _decode_text_output(hex_completed.stderr)
                    details = "\n".join(
                        part.strip() for part in [hex_stdout, hex_stderr] if part.strip()
                    )
                    if details:
                        errors.append(f"HEX export failed: {details}")
                    else:
                        errors.append("HEX export failed, but fromelf.exe returned no readable output.")

    return KeilBuildResult(
        ready=True,
        built=built,
        hex_generated=hex_generated,
        project_dir=doctor.project_dir,
        uvprojx_path=doctor.uvprojx_path,
        uv4_path=doctor.uv4_path,
        fromelf_path=doctor.fromelf_path,
        device_pack_path=doctor.device_pack_path,
        build_log_path=doctor.build_log_path,
        hex_file=hex_file,
        command=command,
        hex_command=hex_command,
        exit_code=completed.returncode,
        summary_lines=summary_lines,
        warnings=warnings,
        errors=errors,
    )


def find_uv4(explicit_path: str | Path | None = None) -> Path | None:
    candidates: List[Path] = []
    if explicit_path is not None:
        candidates.append(Path(explicit_path))

    configured_path, _source = resolve_configured_path("keil_uv4_path")
    if configured_path:
        candidates.append(Path(configured_path))

    candidates.extend(
        [
            Path(r"D:\Keil_v5\UV4\UV4.exe"),
            Path(r"D:\Keil_v5\ARM\UV4\UV4.exe"),
            Path(r"C:\Keil_v5\UV4\UV4.exe"),
            Path(r"C:\Keil_v5\ARM\UV4\UV4.exe"),
            Path(r"C:\Program Files\Keil_v5\UV4\UV4.exe"),
            Path(r"C:\Program Files (x86)\Keil_v5\UV4\UV4.exe"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    from_where = _find_uv4_from_path()
    if from_where is not None:
        return from_where

    for root in [
        Path(r"D:\Keil_v5"),
        Path(r"C:\Keil_v5"),
        Path(r"C:\Program Files\Keil_v5"),
        Path(r"C:\Program Files (x86)\Keil_v5"),
    ]:
        if not root.exists():
            continue
        matches = list(root.rglob("UV4.exe"))
        if matches:
            return matches[0]

    return None


def find_fromelf(explicit_path: str | Path | None = None, uv4_path: str | Path | None = None) -> Path | None:
    candidates: List[Path] = []
    if explicit_path is not None:
        candidates.append(Path(explicit_path))

    configured_path, _source = resolve_configured_path("keil_fromelf_path")
    if configured_path:
        candidates.append(Path(configured_path))

    if uv4_path is not None:
        uv4 = Path(uv4_path)
        if uv4.exists():
            keil_root = uv4.parent.parent
            candidates.extend(
                [
                    keil_root / "ARM" / "ARMCLANG" / "bin" / "fromelf.exe",
                    keil_root / "ARM" / "ARMCC" / "bin" / "fromelf.exe",
                ]
            )

    candidates.extend(
        [
            Path(r"D:\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe"),
            Path(r"D:\Keil_v5\ARM\ARMCC\bin\fromelf.exe"),
            Path(r"C:\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe"),
            Path(r"C:\Keil_v5\ARM\ARMCC\bin\fromelf.exe"),
            Path(r"C:\Program Files\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe"),
            Path(r"C:\Program Files\Keil_v5\ARM\ARMCC\bin\fromelf.exe"),
            Path(r"C:\Program Files (x86)\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe"),
            Path(r"C:\Program Files (x86)\Keil_v5\ARM\ARMCC\bin\fromelf.exe"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def find_device_family_pack(family: str, uv4_path: str | Path | None = None) -> Path | None:
    support = get_family_support(family)
    candidates: List[Path] = []

    if uv4_path is not None:
        uv4 = Path(uv4_path)
        if uv4.exists():
            parent = uv4.parent
            for root in (parent.parent, parent.parent.parent):
                if root.exists():
                    candidates.append(root / "ARM" / "PACK" / "Keil" / support.device_pack_dir)

    candidates.extend(
        [
            Path(rf"D:\Keil_v5\ARM\PACK\Keil\{support.device_pack_dir}"),
            Path(rf"C:\Keil_v5\ARM\PACK\Keil\{support.device_pack_dir}"),
            Path(rf"C:\Program Files\Keil_v5\ARM\PACK\Keil\{support.device_pack_dir}"),
            Path(rf"C:\Program Files (x86)\Keil_v5\ARM\PACK\Keil\{support.device_pack_dir}"),
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        if not candidate.exists() or not candidate.is_dir():
            continue

        version_dirs = sorted([item for item in candidate.iterdir() if item.is_dir()], reverse=True)
        for version_dir in version_dirs:
            pdsc_files = sorted(version_dir.glob("*.pdsc"))
            if pdsc_files:
                return pdsc_files[0]

        pdsc_files = sorted(candidate.glob("*.pdsc"))
        if pdsc_files:
            return pdsc_files[0]

    return None


def find_stm32f1xx_dfp(uv4_path: str | Path | None = None) -> Path | None:
    return find_device_family_pack("STM32F1", uv4_path)


def find_stm32g4xx_dfp(uv4_path: str | Path | None = None) -> Path | None:
    return find_device_family_pack("STM32G4", uv4_path)


def _find_uv4_from_path() -> Path | None:
    try:
        completed = subprocess.run(
            ["where.exe", "UV4.exe"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    for line in _decode_text_output(completed.stdout).splitlines():
        candidate = Path(line.strip())
        if candidate.exists():
            return candidate
    return None


def _resolve_project_paths(project_path: str | Path) -> tuple[Path, Path, List[str]]:
    path = Path(project_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    errors: List[str] = []

    if not path.exists():
        return path, path, [f"Project path does not exist: {path}"]

    if path.is_file():
        if path.suffix.lower() != ".uvprojx":
            return path.parent, path, [f"File is not a .uvprojx project: {path}"]
        project_dir = path.parent.parent if path.parent.name.upper() == "MDK-ARM" else path.parent
        return project_dir, path, []

    uvprojx_candidates: List[Path] = []
    if path.name.upper() == "MDK-ARM":
        uvprojx_candidates = sorted(path.glob("*.uvprojx"))
        project_dir = path.parent
    else:
        mdk_arm = path / "MDK-ARM"
        if mdk_arm.exists():
            uvprojx_candidates = sorted(mdk_arm.glob("*.uvprojx"))
            project_dir = path
        else:
            uvprojx_candidates = sorted(path.glob("*.uvprojx"))
            project_dir = path

    if not uvprojx_candidates:
        errors.append(f"No .uvprojx project file was found under: {path}")
        return project_dir, path, errors
    if len(uvprojx_candidates) > 1:
        errors.append(f"Multiple .uvprojx files were found. Specify one explicitly: {path}")
        return project_dir, uvprojx_candidates[0], errors

    return project_dir, uvprojx_candidates[0], []


def _required_project_paths(project_dir: Path, support=None) -> List[tuple[Path, str]]:
    project_ir_path = project_dir / "project_ir.json"
    if support is None:
        family = _load_target_family(project_ir_path)
        support = get_family_support(family)
    hal_components = _load_hal_components(project_ir_path)
    required_hal_sources = _required_hal_sources(hal_components, support.family)

    required: List[tuple[Path, str]] = [
        (project_dir / "Core" / "Src" / "main.c", "generated source"),
        (project_dir / "Core" / "Src" / "peripherals.c", "generated source"),
        (project_dir / "App" / "Src" / "app_main.c", "generated source"),
        (project_dir / "Drivers" / "CMSIS" / "Include", "CMSIS include dir"),
        (
            project_dir / "Drivers" / "CMSIS" / "Device" / "ST" / support.cmsis_device_dir / "Include",
            "device include dir",
        ),
        (
            project_dir
            / "Drivers"
            / "CMSIS"
            / "Device"
            / "ST"
            / support.cmsis_device_dir
            / "Source"
            / "Templates"
            / support.system_source,
            "CMSIS system source",
        ),
        (
            project_dir
            / "Drivers"
            / "CMSIS"
            / "Device"
            / "ST"
            / support.cmsis_device_dir
            / "Source"
            / "Templates"
            / "arm"
            / support.startup_source,
            "startup source",
        ),
        (project_dir / "Drivers" / support.hal_driver_dir / "Inc", "HAL include dir"),
        (project_dir / "Drivers" / support.hal_driver_dir / "Src", "HAL source dir"),
    ]

    for source in required_hal_sources:
        required.append((project_dir / "Drivers" / support.hal_driver_dir / "Src" / source, "HAL source"))

    return required


def _load_hal_components(project_ir_path: Path) -> List[str]:
    if not project_ir_path.exists():
        return ["RCC", "GPIO"]
    try:
        payload = json.loads(read_text_with_fallback(project_ir_path))
    except (OSError, ValueError):
        return ["RCC", "GPIO"]
    components = payload.get("hal_components")
    if components is None and isinstance(payload.get("build"), dict):
        components = payload["build"].get("hal_components", [])
    if not isinstance(components, list):
        return ["RCC", "GPIO"]
    return [str(item) for item in components]


def _required_hal_sources(components: Iterable[str], family: str) -> List[str]:
    return collect_hal_sources(components, family)


def _load_target_family(project_ir_path: Path) -> str:
    if not project_ir_path.exists():
        raise ValueError(f"Missing project_ir.json, cannot determine target family: {project_ir_path}")
    try:
        payload = json.loads(read_text_with_fallback(project_ir_path))
    except (OSError, ValueError) as exc:
        raise ValueError(f"project_ir.json could not be parsed, cannot determine target family: {exc}") from exc

    target = payload.get("target", {})
    if isinstance(target, dict):
        family = str(target.get("family", "")).strip()
        if family:
            return family
    raise ValueError(f"project_ir.json did not declare target.family: {project_ir_path}")


def _find_axf_output(uvprojx_path: Path) -> Path | None:
    objects_dir = uvprojx_path.parent / "Objects"
    expected = objects_dir / f"{uvprojx_path.stem}.axf"
    if expected.exists():
        return expected
    if not objects_dir.exists():
        return None
    candidates = sorted(objects_dir.glob("*.axf"))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _extract_build_summary(build_log_path: Path, stdout: str, stderr: str) -> List[str]:
    content = ""
    if build_log_path.exists():
        content = read_text_with_fallback(build_log_path)
    elif stdout or stderr:
        content = "\n".join(part for part in [stdout, stderr] if part)

    if not content:
        return []

    interesting: List[str] = []
    for line in content.splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        lower = normalized.lower()
        if "error" in lower or "warning" in lower or "build time elapsed" in lower or "target not created" in lower:
            interesting.append(normalized)

    if interesting:
        return interesting[-20:]
    return content.splitlines()[-10:]


def _parse_error_warning_counts(summary_lines: List[str]) -> tuple[int | None, int | None]:
    pattern = re.compile(r"(\d+)\s+Error\(s\),\s+(\d+)\s+Warning\(s\)\.")
    for line in reversed(summary_lines):
        match = pattern.search(line)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def read_text_with_fallback(path: str | Path) -> str:
    resolved = Path(path)
    last_error: Exception | None = None
    for encoding in _TEXT_DECODE_ENCODINGS:
        try:
            return resolved.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        return resolved.read_text(encoding="utf-8", errors="replace")
    return resolved.read_text(encoding="utf-8", errors="replace")


def _decode_text_output(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, (bytes, bytearray)):
        return str(raw)
    payload = bytes(raw)
    if not payload:
        return ""
    for encoding in _TEXT_DECODE_ENCODINGS:
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")
