from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .keil_builder import KeilBuildResult, KeilDoctorResult, build_keil_project, doctor_keil_project

ProjectBuildResult = KeilBuildResult
ProjectDoctorResult = KeilDoctorResult


@dataclass(frozen=True)
class BuilderDescriptor:
    kind: str
    display_name: str
    supported_project_files: tuple[str, ...]


@runtime_checkable
class ProjectBuilderBackend(Protocol):
    descriptor: BuilderDescriptor

    def supports_project(self, project_path: str | Path) -> bool:
        ...

    def doctor_project(self, project_path: str | Path, **kwargs) -> ProjectDoctorResult:
        ...

    def build_project(self, project_path: str | Path, **kwargs) -> ProjectBuildResult:
        ...


class KeilProjectBuilderBackend:
    descriptor = BuilderDescriptor(
        kind="keil",
        display_name="Keil",
        supported_project_files=(".uvprojx",),
    )

    def supports_project(self, project_path: str | Path) -> bool:
        path = Path(str(project_path or "")).expanduser()
        if path.suffix.lower() == ".uvprojx":
            return True
        if path.is_dir():
            return any(path.glob("*.uvprojx"))
        return False

    def doctor_project(self, project_path: str | Path, **kwargs) -> ProjectDoctorResult:
        return doctor_keil_project(project_path, **kwargs)

    def build_project(self, project_path: str | Path, **kwargs) -> ProjectBuildResult:
        return build_keil_project(project_path, **kwargs)


_BUILDERS: Dict[str, ProjectBuilderBackend] = {
    "keil": KeilProjectBuilderBackend(),
}


def list_project_builders() -> list[BuilderDescriptor]:
    return [backend.descriptor for backend in _BUILDERS.values()]


def get_builder_display_name(builder_kind: str) -> str:
    key = str(builder_kind or "").strip().lower()
    backend = _BUILDERS.get(key)
    if backend is not None:
        return backend.descriptor.display_name
    return key or "Project Builder"


def resolve_builder_kind(project_path: str | Path, preferred_kind: str | None = "auto") -> str:
    requested = str(preferred_kind or "auto").strip().lower()
    if requested and requested != "auto":
        return requested if requested in _BUILDERS else ""
    for backend in _BUILDERS.values():
        if backend.supports_project(project_path):
            return backend.descriptor.kind
    if len(_BUILDERS) == 1:
        return next(iter(_BUILDERS))
    return ""


def doctor_project(
    project_path: str | Path,
    builder_kind: str | None = "auto",
    **kwargs,
) -> ProjectDoctorResult:
    resolved_kind = resolve_builder_kind(project_path, builder_kind)
    backend = _BUILDERS.get(resolved_kind)
    if backend is None:
        return _unsupported_doctor_result(project_path, builder_kind)
    return backend.doctor_project(project_path, **kwargs)


def build_project(
    project_path: str | Path,
    builder_kind: str | None = "auto",
    **kwargs,
) -> ProjectBuildResult:
    resolved_kind = resolve_builder_kind(project_path, builder_kind)
    backend = _BUILDERS.get(resolved_kind)
    if backend is None:
        return _unsupported_build_result(project_path, builder_kind)
    return backend.build_project(project_path, **kwargs)


def _unsupported_doctor_result(project_path: str | Path, builder_kind: str | None) -> ProjectDoctorResult:
    path = Path(str(project_path or "")).expanduser()
    project_dir = str(path.parent if path.suffix else path)
    kind = str(builder_kind or "auto").strip().lower() or "auto"
    available = ", ".join(descriptor.kind for descriptor in list_project_builders()) or "none"
    if kind != "auto":
        error = f"Unsupported builder kind '{kind}'. Available builders: {available}."
    else:
        error = f"Could not detect a supported builder for '{project_path}'. Available builders: {available}."
    return ProjectDoctorResult(
        ready=False,
        project_dir=project_dir,
        uvprojx_path="",
        uv4_path="",
        fromelf_path="",
        device_pack_path="",
        build_log_path="",
        checked_paths=[],
        warnings=[],
        errors=[error],
        builder_kind=kind,
    )


def _unsupported_build_result(project_path: str | Path, builder_kind: str | None) -> ProjectBuildResult:
    path = Path(str(project_path or "")).expanduser()
    project_dir = str(path.parent if path.suffix else path)
    kind = str(builder_kind or "auto").strip().lower() or "auto"
    available = ", ".join(descriptor.kind for descriptor in list_project_builders()) or "none"
    if kind != "auto":
        error = f"Unsupported builder kind '{kind}'. Available builders: {available}."
    else:
        error = f"Could not detect a supported builder for '{project_path}'. Available builders: {available}."
    return ProjectBuildResult(
        ready=False,
        built=False,
        hex_generated=False,
        project_dir=project_dir,
        uvprojx_path="",
        uv4_path="",
        fromelf_path="",
        device_pack_path="",
        build_log_path="",
        hex_file="",
        command=[],
        hex_command=[],
        exit_code=None,
        summary_lines=[],
        warnings=[],
        errors=[error],
        builder_kind=kind,
    )
