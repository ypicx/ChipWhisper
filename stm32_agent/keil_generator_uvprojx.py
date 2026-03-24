from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Tuple

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .catalog import ChipDefinition
from .family_support import get_family_support
from .planner import PlanResult


_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent / "templates")),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


def render_uvprojx_v2(
    plan: PlanResult,
    project_name: str,
    chip: ChipDefinition,
    hal_sources: List[str],
    app_sources: List[str],
    module_sources: List[str],
) -> str:
    support = get_family_support(chip.family)
    clock_hz = _clock_hz_for_plan(plan, support.cpu_clock_hz)
    template = _TEMPLATE_ENV.get_template("keil_uvprojx/project.uvprojx.jinja")
    context = _build_uvprojx_context(
        plan=plan,
        project_name=project_name,
        chip=chip,
        hal_sources=hal_sources,
        app_sources=app_sources,
        module_sources=module_sources,
        clock_hz=clock_hz,
    )
    return template.render(**context)


def _build_uvprojx_context(
    plan: PlanResult,
    project_name: str,
    chip: ChipDefinition,
    hal_sources: List[str],
    app_sources: List[str],
    module_sources: List[str],
    clock_hz: int,
) -> Dict[str, object]:
    support = get_family_support(chip.family)
    include_path = ";".join(
        [
            "../Core/Inc",
            "../App/Inc",
            "../Modules/Inc",
            "../Drivers/CMSIS/Include",
            f"../Drivers/CMSIS/Device/ST/{support.cmsis_device_dir}/Include",
            f"../Drivers/{support.hal_driver_dir}/Inc",
            f"../Drivers/{support.hal_driver_dir}/Inc/Legacy",
        ]
    )
    defines = ["USE_HAL_DRIVER", chip.c_define]
    groups = _build_group_context(
        support=support,
        app_sources=app_sources,
        hal_sources=hal_sources,
        module_sources=module_sources,
    )
    return {
        "project_name": project_name,
        "chip": chip,
        "support": support,
        "cpu": _cpu_string_v2(
            flash_start=chip.irom_start,
            flash_kb=chip.flash_kb,
            ram_start=chip.iram_start,
            ram_kb=chip.ram_kb,
            cpu_type=chip.cpu_type,
            clock_hz=clock_hz,
        ),
        "chip_cpu_type_quoted": f'"{chip.cpu_type}"',
        "include_path": include_path,
        "defines_csv": ",".join(defines),
        "iram_start_hex": f"0x{chip.iram_start:08X}",
        "iram_size_hex": f"0x{chip.ram_kb * 1024:X}",
        "irom_start_hex": f"0x{chip.irom_start:08X}",
        "irom_size_hex": f"0x{chip.flash_kb * 1024:X}",
        "groups": groups,
    }


def _build_group_context(
    support: object,
    app_sources: List[str],
    hal_sources: List[str],
    module_sources: List[str],
) -> List[Dict[str, object]]:
    core_sources = [
        ("../Core/Src/main.c", 1),
        ("../Core/Src/peripherals.c", 1),
        (f"../Core/Src/{support.it_source}", 1),
        (f"../Core/Src/{support.hal_msp_source}", 1),
    ]
    groups = [
        _group_dict(
            f"Drivers/{support.hal_driver_dir}",
            [(f"../Drivers/{support.hal_driver_dir}/Src/" + name, 1) for name in hal_sources],
        ),
        _group_dict("Core/Src", core_sources),
    ]
    groups.extend(_build_source_groups("App/Src", "../App/Src", ["app_main.c", *app_sources]))
    if module_sources:
        groups.extend(_build_source_groups("Modules/Src", "../Modules/Src", module_sources))
    groups.append(
        _group_dict(
            "Drivers/CMSIS",
            [(f"../Drivers/CMSIS/Device/ST/{support.cmsis_device_dir}/Source/Templates/{support.system_source}", 1)],
        )
    )
    groups.append(
        _group_dict(
            "Startup",
            [(f"../Drivers/CMSIS/Device/ST/{support.cmsis_device_dir}/Source/Templates/arm/{support.startup_source}", 2)],
        )
    )
    return groups


def _build_source_groups(group_root: str, file_root: str, sources: List[str]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Tuple[str, int]]] = {}
    for source in sources:
        normalized = str(source).replace("\\", "/").strip().strip("/")
        if not normalized:
            continue
        parent = PurePosixPath(normalized).parent
        group_name = group_root if str(parent) in {"", "."} else f"{group_root}/{parent.as_posix()}"
        grouped.setdefault(group_name, []).append((f"{file_root}/{normalized}", 1))

    return [
        _group_dict(group_name, grouped[group_name])
        for group_name in sorted(grouped, key=lambda item: (item.count("/"), item))
    ]


def _group_dict(group_name: str, files: Iterable[Tuple[str, int]]) -> Dict[str, object]:
    file_items = []
    for file_path, file_type in files:
        file_items.append(
            {
                "name": Path(file_path).name,
                "type": int(file_type),
                "path": file_path,
            }
        )
    return {
        "name": group_name,
        "files": file_items,
    }


def _cpu_string_v2(
    flash_start: int,
    flash_kb: int,
    ram_start: int,
    ram_kb: int,
    cpu_type: str,
    clock_hz: int,
) -> str:
    flash_end = flash_start + flash_kb * 1024 - 1
    ram_end = ram_start + ram_kb * 1024 - 1
    return f'IRAM(0x{ram_start:08X}-0x{ram_end:08X}) IROM(0x{flash_start:08X}-0x{flash_end:08X}) CLOCK({clock_hz}) CPUTYPE("{cpu_type}")'


def _clock_hz_for_plan(plan: PlanResult, default_clock_hz: int) -> int:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    constraints = project_ir.get("constraints", {}) if isinstance(project_ir, dict) else {}
    clock_plan = constraints.get("clock_plan", {}) if isinstance(constraints, dict) else {}
    if not isinstance(clock_plan, dict):
        return default_clock_hz
    value = clock_plan.get("cpu_clock_hz", default_clock_hz)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_clock_hz
