from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .family_support import collect_hal_sources, get_family_support
from .keil_builder import _resolve_project_paths
from .path_config import resolve_configured_path


@dataclass
class CubePackageDoctorResult:
    ready: bool
    family: str
    repository_path: str
    package_path: str
    drivers_path: str
    checked_paths: List[Dict[str, object]]
    warnings: List[str]
    errors: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "ready": self.ready,
            "family": self.family,
            "repository_path": self.repository_path,
            "package_path": self.package_path,
            "drivers_path": self.drivers_path,
            "checked_paths": self.checked_paths,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class CubePackageImportResult:
    ready: bool
    imported: bool
    family: str
    project_dir: str
    repository_path: str
    package_path: str
    copied_paths: List[str]
    warnings: List[str]
    errors: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "ready": self.ready,
            "imported": self.imported,
            "family": self.family,
            "project_dir": self.project_dir,
            "repository_path": self.repository_path,
            "package_path": self.package_path,
            "copied_paths": self.copied_paths,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def doctor_cube_package(
    family: str,
    repository_path: str | Path | None = None,
    package_path: str | Path | None = None,
) -> CubePackageDoctorResult:
    support = get_family_support(family)
    warnings: List[str] = []
    errors: List[str] = []
    checked_paths: List[Dict[str, object]] = []

    repository = find_stm32cube_repository(repository_path)
    if repository is None:
        errors.append("STM32Cube repository was not found. Install STM32CubeMX and download the firmware package first.")
        return CubePackageDoctorResult(
            ready=False,
            family=support.family,
            repository_path="",
            package_path="",
            drivers_path="",
            checked_paths=[],
            warnings=warnings,
            errors=errors,
        )

    package = find_cube_package(support.family, repository, package_path)
    if package is None:
        errors.append(
            f"{support.cube_package_label} firmware package was not found. Download the {support.family} package in STM32CubeMX first."
        )
        return CubePackageDoctorResult(
            ready=False,
            family=support.family,
            repository_path=str(repository),
            package_path="",
            drivers_path="",
            checked_paths=[],
            warnings=warnings,
            errors=errors,
        )

    drivers_root = package / "Drivers"
    required_paths = [
        (drivers_root / "CMSIS", "cube drivers root"),
        (drivers_root / "CMSIS" / "Include", "CMSIS include dir"),
        (drivers_root / "CMSIS" / "Device" / "ST" / support.cmsis_device_dir / "Include", "device include dir"),
        (
            drivers_root
            / "CMSIS"
            / "Device"
            / "ST"
            / support.cmsis_device_dir
            / "Source"
            / "Templates"
            / support.system_source,
            "CMSIS system source",
        ),
        (drivers_root / support.hal_driver_dir / "Inc", "HAL include dir"),
        (drivers_root / support.hal_driver_dir / "Src", "HAL source dir"),
        (
            drivers_root
            / support.hal_driver_dir
            / "Src"
            / next(iter(support.hal_source_map["GPIO"])),
            "HAL source",
        ),
    ]

    # Keil projects use the ARM startup template. Keep it as a separate check because some
    # firmware packages also include gcc/iar variants under the same folder tree.
    arm_startup = (
        drivers_root
        / "CMSIS"
        / "Device"
        / "ST"
        / support.cmsis_device_dir
        / "Source"
        / "Templates"
        / "arm"
        / support.startup_source
    )
    required_paths.append((arm_startup, "startup source"))

    for path, kind in required_paths:
        exists = path.exists()
        checked_paths.append({"path": str(path), "kind": kind, "exists": exists})
        if not exists:
            errors.append(f"Missing {kind}: {path}")

    return CubePackageDoctorResult(
        ready=not errors,
        family=support.family,
        repository_path=str(repository),
        package_path=str(package),
        drivers_path=str(drivers_root),
        checked_paths=checked_paths,
        warnings=warnings,
        errors=errors,
    )


def import_cube_drivers(
    project_path: str | Path,
    family: str,
    repository_path: str | Path | None = None,
    package_path: str | Path | None = None,
    overwrite: bool = False,
) -> CubePackageImportResult:
    support = get_family_support(family)
    project_dir, _uvprojx_path, project_errors = _resolve_project_paths(project_path)
    if project_errors:
        return CubePackageImportResult(
            ready=False,
            imported=False,
            family=support.family,
            project_dir=str(project_dir),
            repository_path="",
            package_path="",
            copied_paths=[],
            warnings=[],
            errors=project_errors,
        )

    doctor = doctor_cube_package(support.family, repository_path, package_path)
    if not doctor.ready:
        return CubePackageImportResult(
            ready=False,
            imported=False,
            family=support.family,
            project_dir=str(project_dir),
            repository_path=doctor.repository_path,
            package_path=doctor.package_path,
            copied_paths=[],
            warnings=doctor.warnings,
            errors=doctor.errors,
        )

    drivers_source = Path(doctor.drivers_path)
    drivers_target = project_dir / "Drivers"
    copied_paths: List[str] = []
    warnings = list(doctor.warnings)
    errors: List[str] = []
    project_ir = _load_project_ir(project_dir)
    hal_components = _extract_project_hal_components(project_ir)
    hal_sources = collect_hal_sources(hal_components, support.family)

    cmsis_source = drivers_source / "CMSIS"
    cmsis_target = drivers_target / "CMSIS"
    _copy_tree_target(cmsis_source, cmsis_target, copied_paths, errors, overwrite)

    hal_root_source = drivers_source / support.hal_driver_dir
    hal_root_target = drivers_target / support.hal_driver_dir
    hal_inc_source = hal_root_source / "Inc"
    hal_inc_target = hal_root_target / "Inc"
    hal_src_source = hal_root_source / "Src"
    hal_src_target = hal_root_target / "Src"

    _copy_tree_target(hal_inc_source, hal_inc_target, copied_paths, errors, overwrite)
    _copy_selected_sources(
        hal_src_source,
        hal_src_target,
        hal_sources,
        copied_paths,
        warnings,
        errors,
        overwrite,
    )

    return CubePackageImportResult(
        ready=not errors,
        imported=not errors,
        family=support.family,
        project_dir=str(project_dir),
        repository_path=doctor.repository_path,
        package_path=doctor.package_path,
        copied_paths=copied_paths,
        warnings=warnings,
        errors=errors,
    )


def doctor_cube_f1_package(
    repository_path: str | Path | None = None,
    package_path: str | Path | None = None,
) -> CubePackageDoctorResult:
    return doctor_cube_package("STM32F1", repository_path, package_path)


def import_cube_f1_drivers(
    project_path: str | Path,
    repository_path: str | Path | None = None,
    package_path: str | Path | None = None,
    overwrite: bool = False,
) -> CubePackageImportResult:
    return import_cube_drivers(project_path, "STM32F1", repository_path, package_path, overwrite)


def doctor_cube_g4_package(
    repository_path: str | Path | None = None,
    package_path: str | Path | None = None,
) -> CubePackageDoctorResult:
    return doctor_cube_package("STM32G4", repository_path, package_path)


def import_cube_g4_drivers(
    project_path: str | Path,
    repository_path: str | Path | None = None,
    package_path: str | Path | None = None,
    overwrite: bool = False,
) -> CubePackageImportResult:
    return import_cube_drivers(project_path, "STM32G4", repository_path, package_path, overwrite)


def find_stm32cube_repository(explicit_path: str | Path | None = None) -> Path | None:
    candidates: List[Path] = []
    if explicit_path is not None:
        candidates.append(Path(explicit_path))

    configured_path, _source = resolve_configured_path("stm32cube_repository_path")
    if configured_path:
        candidates.append(Path(configured_path))

    home = Path.home()
    candidates.extend(
        [
            home / "STM32Cube" / "Repository",
            home / ".stm32cubemx" / "repository",
        ]
    )

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def find_cube_package(
    family: str,
    repository_path: str | Path | None = None,
    explicit_package: str | Path | None = None,
) -> Path | None:
    support = get_family_support(family)

    if explicit_package is not None:
        package = Path(explicit_package)
        if package.exists() and package.is_dir():
            return package
        return None

    repository = find_stm32cube_repository(repository_path)
    if repository is None:
        return None

    if repository_path is None:
        configured_path, _source = resolve_configured_path(support.cube_package_config_key)
        if configured_path:
            package = Path(configured_path)
            if package.exists() and package.is_dir():
                return package

    candidates = sorted([path for path in repository.glob(support.cube_package_glob) if path.is_dir()], reverse=True)
    if candidates:
        return candidates[0]
    return None


def _load_project_ir(project_dir: Path) -> Dict[str, object]:
    path = project_dir / "project_ir.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_project_hal_components(project_ir: Dict[str, object]) -> List[str]:
    build = project_ir.get("build", {})
    if not isinstance(build, dict):
        return []
    components = build.get("hal_components", [])
    if not isinstance(components, list):
        return []
    return [str(item).strip() for item in components if str(item).strip()]


def _copy_tree_target(
    source_dir: Path,
    target_dir: Path,
    copied_paths: List[str],
    errors: List[str],
    overwrite: bool,
) -> None:
    if target_dir.exists() and any(target_dir.iterdir()) and not overwrite:
        errors.append(f"Target directory is not empty. Use overwrite to replace it: {target_dir}")
        return
    if target_dir.exists() and overwrite:
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)
    copied_paths.append(str(target_dir))


def _copy_selected_sources(
    source_dir: Path,
    target_dir: Path,
    filenames: List[str],
    copied_paths: List[str],
    warnings: List[str],
    errors: List[str],
    overwrite: bool,
) -> None:
    if target_dir.exists() and any(target_dir.iterdir()) and not overwrite:
        errors.append(f"Target directory is not empty. Use overwrite to replace it: {target_dir}")
        return
    if target_dir.exists() and overwrite:
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    copied_paths.append(str(target_dir))

    for filename in filenames:
        source_path = source_dir / filename
        if not source_path.exists():
            warnings.append(f"Requested HAL source was not found in Cube package: {source_path}")
            continue
        shutil.copy2(source_path, target_dir / filename)
