from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .catalog import BOARDS, CHIPS, MODULES, BoardProfile, ChipDefinition, ClockProfile, InterfaceOption, ModuleSpec


PACK_SCHEMA_VERSION = "1.0"
PACKS_ENV_VAR = "STM32_AGENT_PACKS_DIR"
IMPORTABLE_SOURCE_EXTENSIONS = {".c", ".h"}


@dataclass(frozen=True)
class CatalogRegistry:
    packs_dir: str
    chips: Dict[str, ChipDefinition]
    boards: Dict[str, BoardProfile]
    modules: Dict[str, ModuleSpec]
    loaded_files: Tuple[str, ...]
    warnings: Tuple[str, ...]
    errors: Tuple[str, ...]

    def to_dict(self) -> Dict[str, object]:
        return {
            "packs_dir": self.packs_dir,
            "chip_count": len(self.chips),
            "board_count": len(self.boards),
            "module_count": len(self.modules),
            "loaded_files": list(self.loaded_files),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "chips": sorted(self.chips),
            "boards": sorted(self.boards),
            "modules": sorted(self.modules),
        }


@dataclass(frozen=True)
class ModuleFileImportResult:
    module_key: str
    module_pack_dir: str
    manifest_path: str
    imported_files: Tuple[str, ...]
    template_files: Tuple[str, ...]

    def to_dict(self) -> Dict[str, object]:
        return {
            "module_key": self.module_key,
            "module_pack_dir": self.module_pack_dir,
            "manifest_path": self.manifest_path,
            "imported_files": list(self.imported_files),
            "template_files": list(self.template_files),
        }


def get_default_packs_dir() -> Path:
    env_value = os.environ.get(PACKS_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "packs").resolve()


def load_catalog(packs_dir: str | Path | None = None) -> CatalogRegistry:
    resolved_packs_dir = Path(packs_dir).expanduser().resolve() if packs_dir else get_default_packs_dir()
    chips: Dict[str, ChipDefinition] = {
        name: _clone_chip(chip) for name, chip in CHIPS.items()
    }
    boards: Dict[str, BoardProfile] = {
        key: _clone_board(board) for key, board in BOARDS.items()
    }
    modules: Dict[str, ModuleSpec] = {
        key: _clone_module(spec) for key, spec in MODULES.items()
    }
    loaded_files: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []

    source_roots = _catalog_source_roots(resolved_packs_dir)
    if not source_roots:
        return CatalogRegistry(
            packs_dir=str(resolved_packs_dir),
            chips=chips,
            boards=boards,
            modules=modules,
            loaded_files=tuple(loaded_files),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    for source_root in source_roots:
        for file_path in _iter_chip_files(source_root / "chips"):
            try:
                chip = _load_chip_file(file_path)
                chips[chip.name.upper()] = chip
                loaded_files.append(str(file_path))
            except Exception as exc:  # pragma: no cover - defensive path
                errors.append(f"Failed to load chip pack {file_path}: {exc}")

        for file_path in _iter_board_files(source_root / "boards"):
            try:
                board = _load_board_file(file_path)
                boards[board.key] = board
                loaded_files.append(str(file_path))
            except Exception as exc:  # pragma: no cover - defensive path
                errors.append(f"Failed to load board pack {file_path}: {exc}")

        for file_path in _iter_module_files(source_root / "modules"):
            try:
                module = _load_module_file(file_path)
                modules[module.key] = module
                loaded_files.append(str(file_path))
            except Exception as exc:  # pragma: no cover - defensive path
                errors.append(f"Failed to load module pack {file_path}: {exc}")

    return CatalogRegistry(
        packs_dir=str(resolved_packs_dir),
        chips=chips,
        boards=boards,
        modules=modules,
        loaded_files=tuple(loaded_files),
        warnings=tuple(warnings),
        errors=tuple(errors),
    )


def _catalog_source_roots(resolved_packs_dir: Path) -> List[Path]:
    roots: List[Path] = []
    default_root = get_default_packs_dir()
    if default_root.exists():
        roots.append(default_root)
    if resolved_packs_dir.exists() and resolved_packs_dir not in roots:
        roots.append(resolved_packs_dir)
    return roots


def doctor_packs(packs_dir: str | Path | None = None) -> CatalogRegistry:
    return load_catalog(packs_dir)


# ---------------------------------------------------------------------------
# Scenario templates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioTemplate:
    scenario_id: str
    display_name: str
    tags: Tuple[str, ...]
    description: str
    recommended_boards: Tuple[str, ...]
    modules: Tuple[Dict[str, str], ...]
    app_logic_goal: str
    requirements: Tuple[str, ...]
    assumptions: Tuple[str, ...]
    definition_path: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "display_name": self.display_name,
            "tags": list(self.tags),
            "description": self.description,
            "recommended_boards": list(self.recommended_boards),
            "modules": [dict(m) for m in self.modules],
            "app_logic_goal": self.app_logic_goal,
            "requirements": list(self.requirements),
            "assumptions": list(self.assumptions),
        }


def load_scenarios(packs_dir: str | Path | None = None) -> List[ScenarioTemplate]:
    """Load all scenario templates from packs/scenarios/*.json."""
    resolved = Path(packs_dir).expanduser().resolve() if packs_dir else get_default_packs_dir()
    scenarios: List[ScenarioTemplate] = []
    for source_root in _catalog_source_roots(resolved):
        scenario_dir = source_root / "scenarios"
        if not scenario_dir.exists():
            continue
        for file_path in sorted(scenario_dir.glob("*.json")):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                if str(payload.get("kind", "")).strip() != "scenario":
                    continue
                scenarios.append(ScenarioTemplate(
                    scenario_id=str(payload.get("scenario_id", "")).strip(),
                    display_name=str(payload.get("display_name", "")).strip(),
                    tags=_tuple_of_str(payload.get("tags", [])),
                    description=str(payload.get("description", "")).strip(),
                    recommended_boards=_tuple_of_str(payload.get("recommended_boards", [])),
                    modules=tuple(dict(m) for m in payload.get("modules", []) if isinstance(m, dict)),
                    app_logic_goal=str(payload.get("app_logic_goal", "")).strip(),
                    requirements=_tuple_of_str(payload.get("requirements", [])),
                    assumptions=_tuple_of_str(payload.get("assumptions", [])),
                    definition_path=str(file_path),
                ))
            except Exception:
                continue
    return scenarios


def match_scenarios(
    user_input: str,
    packs_dir: str | Path | None = None,
    *,
    max_results: int = 3,
) -> List[ScenarioTemplate]:
    """Match user input against scenario templates using keyword overlap."""
    if not user_input.strip():
        return []
    scenarios = load_scenarios(packs_dir)
    if not scenarios:
        return []

    input_lower = user_input.lower()
    scored: List[tuple[float, ScenarioTemplate]] = []
    for scenario in scenarios:
        score = 0.0
        searchable = " ".join([
            scenario.display_name,
            scenario.description,
            scenario.app_logic_goal,
            " ".join(scenario.tags),
        ]).lower()
        # Score by keyword overlap
        for word in input_lower.split():
            if len(word) >= 2 and word in searchable:
                score += 1.0
        # Bonus for tag matches
        for tag in scenario.tags:
            if tag.lower() in input_lower:
                score += 2.0
        if score > 0:
            scored.append((score, scenario))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:max_results]]



def init_packs_dir(packs_dir: str | Path | None = None) -> Path:
    root = Path(packs_dir).expanduser().resolve() if packs_dir else get_default_packs_dir()
    for directory in (
        root,
        root / "chips",
        root / "boards",
        root / "modules",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    readme_path = root / "README.md"
    if not readme_path.exists():
        readme_path.write_text(_render_packs_readme(), encoding="utf-8")
    return root


def scaffold_module_pack(module_key: str, packs_dir: str | Path | None = None) -> Path:
    key = module_key.strip()
    if not key:
        raise ValueError("module_key must not be empty")

    root = init_packs_dir(packs_dir)
    module_root = root / "modules" / key
    templates_root = module_root / "templates" / "modules"
    templates_root.mkdir(parents=True, exist_ok=True)

    manifest_path = module_root / "module.json"
    header_name = f"{key}.h"
    source_name = f"{key}.c"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": PACK_SCHEMA_VERSION,
                    "kind": "module",
                    "key": key,
                    "display_name": key,
                    "summary": "Describe this module based on the user manual and example code.",
                    "hal_components": ["GPIO"],
                    "template_files": [f"modules/{source_name}", f"modules/{header_name}"],
                    "resource_requests": ["gpio_out"],
                    "depends_on": [],
                    "init_priority": 0,
                    "loop_priority": 0,
                    "irqs": [],
                    "dma_requests": [],
                    "c_top_template": [],
                    "c_init_template": [
                        "/* Optional: add App_Init lines here using [[signal_port_macro]] / [[signal_pin_macro]] placeholders. */"
                    ],
                    "c_loop_template": [],
                    "c_callbacks_template": [],
                    "simulation": {
                        "renode": {
                            "attach": []
                        }
                    },
                    "notes": [
                        "Supported resource request forms: gpio_out, gpio_in, pwm_out, timer_ic, timer_oc, adc_in, dac_out, uart_port, i2c_device, spi_bus, spi_device, encoder, advanced_timer, can_port, usb_device, onewire_gpio.",
                        "Named signals can use kind:signal or kind:signal:optional, for example gpio_in:int:optional.",
                        "Template placeholders support defaults such as [[option_active_low|1]].",
                        "Use depends_on when this module requires another middleware or transport pack to be present.",
                        "Use init_priority / loop_priority to make shared App_Init() or App_Loop() injections deterministic.",
                        "Optional DMA requests can use symbolic names like uart_rx, uart_tx, i2c_rx, i2c_tx, or exact chip request names.",
                        "Append :shared_bus for bus-shared resources such as I2C DMA, for example i2c_rx:optional:shared_bus.",
                        "Use simulation.renode.attach to describe optional Renode-only button injections, LEDs, or I2C mocks.",
                    ],
                    "sources": ["Add the real datasheet or user-manual citation here."],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    header_path = templates_root / f"{header_name}.tpl"
    if not header_path.exists():
        header_path.write_text(_render_module_header_template(key), encoding="utf-8")

    source_path = templates_root / f"{source_name}.tpl"
    if not source_path.exists():
        source_path.write_text(_render_module_source_template(key), encoding="utf-8")

    plugin_path = module_root / "plugin.py"
    if not plugin_path.exists():
        plugin_path.write_text(_render_module_plugin_template(), encoding="utf-8")

    return module_root


def import_module_files(
    module_key: str,
    source_files: Iterable[str | Path],
    packs_dir: str | Path | None = None,
) -> ModuleFileImportResult:
    key = module_key.strip()
    if not key:
        raise ValueError("module_key must not be empty")

    source_paths = [Path(item).expanduser().resolve() for item in source_files]
    if not source_paths:
        raise ValueError("at least one source file is required")

    module_root = scaffold_module_pack(key, packs_dir)
    manifest_path = module_root / "module.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_common_manifest(manifest, expected_kind="module", path=manifest_path)

    templates_root = module_root / "templates" / "modules"
    templates_root.mkdir(parents=True, exist_ok=True)

    imported_targets: List[str] = []
    copied_paths: List[str] = []
    for source_path in source_paths:
        if not source_path.exists():
            raise FileNotFoundError(f"Source file does not exist: {source_path}")
        if not source_path.is_file():
            raise ValueError(f"Source path must be a file: {source_path}")
        if source_path.suffix.lower() not in IMPORTABLE_SOURCE_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type {source_path.suffix!r}; supported types: {sorted(IMPORTABLE_SOURCE_EXTENSIONS)}"
            )

        destination = templates_root / source_path.name
        shutil.copyfile(source_path, destination)
        copied_paths.append(str(destination))
        imported_targets.append(f"modules/{source_path.name}")

    template_files = [str(item).replace("\\", "/").strip() for item in manifest.get("template_files", [])]
    template_files = _replace_default_scaffold_templates(key, module_root, template_files, imported_targets)
    if not template_files:
        _remove_default_scaffold_files(key, module_root)
    for target in imported_targets:
        if target not in template_files:
            template_files.append(target)

    manifest["template_files"] = template_files
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return ModuleFileImportResult(
        module_key=key,
        module_pack_dir=str(module_root),
        manifest_path=str(manifest_path),
        imported_files=tuple(copied_paths),
        template_files=tuple(template_files),
    )


def scaffold_chip_pack(chip_name: str, packs_dir: str | Path | None = None) -> Path:
    name = chip_name.strip().upper()
    if not name:
        raise ValueError("chip_name must not be empty")

    root = init_packs_dir(packs_dir)
    file_path = root / "chips" / f"{name.lower()}.json"
    if not file_path.exists():
        file_path.write_text(
            json.dumps(
                {
                    "schema_version": PACK_SCHEMA_VERSION,
                    "kind": "chip",
                    "name": name,
                    "device_name": name,
                    "vendor": "Fill vendor",
                    "family": "Fill family",
                    "cpu_type": "Fill CPU core",
                    "package": "Fill package",
                    "flash_kb": 0,
                    "ram_kb": 0,
                    "irom_start": "0x08000000",
                    "iram_start": "0x20000000",
                    "c_define": "FILL_DEVICE_DEFINE",
                    "reserved_pins": [],
                    "gpio_preference": [],
                    "adc_pins": [],
                    "adc_channels": {},
                    "interfaces": {
                        "i2c": [],
                        "uart": [],
                        "spi": [],
                        "dac": [],
                        "can": [],
                        "usb": [],
                        "pwm": [],
                        "timer_ic": [],
                    },
                    "dma_channels": [],
                    "dma_request_map": {},
                    "sources": [
                        "Add the real datasheet and reference-manual citations here."
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return file_path


def scaffold_board_pack(board_key: str, packs_dir: str | Path | None = None) -> Path:
    key = board_key.strip().lower()
    if not key:
        raise ValueError("board_key must not be empty")

    root = init_packs_dir(packs_dir)
    file_path = root / "boards" / f"{key}.json"
    if not file_path.exists():
        file_path.write_text(
            json.dumps(
                {
                    "schema_version": PACK_SCHEMA_VERSION,
                    "kind": "board",
                    "key": key,
                    "display_name": key,
                    "summary": "Describe the real board and its on-board peripherals.",
                    "chip": "STM32F103C8T6",
                    "reserved_pins": [],
                    "avoid_pins": [],
                    "preferred_signals": {
                        "led.control": [],
                        "button.input": [],
                    },
                    "clock_profile": {
                        "summary": "Describe the board clock tree used by generated projects.",
                        "cpu_clock_hz": 8000000,
                        "hse_value": 8000000,
                        "hsi_value": 8000000,
                        "lsi_value": 40000,
                        "lse_value": 32768,
                        "external_clock_value": 48000,
                        "system_clock_config": [
                            "RCC_OscInitTypeDef RCC_OscInitStruct = {0};",
                            "RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};",
                            "",
                            "RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;",
                            "RCC_OscInitStruct.HSEState = RCC_HSE_ON;",
                            "RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;",
                            "RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;",
                            "RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;",
                            "RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;",
                            "if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {",
                            "    Error_Handler();",
                            "}",
                            "",
                            "RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK",
                            "                             | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;",
                            "RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;",
                            "RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;",
                            "RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;",
                            "RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;",
                            "if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) {",
                            "    Error_Handler();",
                            "}"
                        ],
                        "notes": [
                            "Move board-specific crystal, PLL, and flash-latency settings here instead of hard-coding them in Python."
                        ]
                    },
                    "capabilities": [
                        {
                            "key": "board_led",
                            "display_name": "On-board LED",
                            "summary": "Document a board-side reusable capability here.",
                            "module_kind": "led",
                            "recommended_name": "status_led",
                            "category": "indicator",
                        }
                    ],
                    "notes": [
                        "Use preferred_signals to steer modules such as led/button to known on-board resources.",
                        "Keep reserved_pins for signals that should never be auto-allocated on this board.",
                    ],
                    "sources": ["Add the real board user manual or schematic citation here."],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return file_path


def export_builtin_catalog(packs_dir: str | Path | None = None) -> Path:
    root = init_packs_dir(packs_dir)

    for chip in CHIPS.values():
        chip_path = root / "chips" / f"{chip.name.lower()}.json"
        chip_path.write_text(
            json.dumps(_chip_to_manifest(chip), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    for board in BOARDS.values():
        board_path = root / "boards" / f"{board.key}.json"
        board_path.write_text(
            json.dumps(_board_to_manifest(board), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    for module in MODULES.values():
        module_root = root / "modules" / module.key
        module_root.mkdir(parents=True, exist_ok=True)
        module_path = module_root / "module.json"
        module_path.write_text(
            json.dumps(_module_to_manifest(module), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return root


def _clone_board(board: BoardProfile) -> BoardProfile:
    return BoardProfile(
        key=board.key,
        display_name=board.display_name,
        summary=board.summary,
        chip=board.chip,
        reserved_pins=tuple(board.reserved_pins),
        avoid_pins=tuple(board.avoid_pins),
        preferred_signals={key: tuple(value) for key, value in (board.preferred_signals or {}).items()},
        clock_profile=_clone_clock_profile(board.clock_profile),
        capabilities=tuple(dict(item) for item in board.capabilities),
        notes=tuple(board.notes),
        sources=tuple(board.sources),
        definition_path=board.definition_path,
    )


def _clone_chip(chip: ChipDefinition) -> ChipDefinition:
    return ChipDefinition(
        name=chip.name,
        device_name=chip.device_name,
        vendor=chip.vendor,
        family=chip.family,
        cpu_type=chip.cpu_type,
        package=chip.package,
        flash_kb=chip.flash_kb,
        ram_kb=chip.ram_kb,
        irom_start=chip.irom_start,
        iram_start=chip.iram_start,
        c_define=chip.c_define,
        reserved_pins=tuple(chip.reserved_pins),
        gpio_preference=tuple(chip.gpio_preference),
        adc_pins=tuple(chip.adc_pins),
        interfaces={
            kind: tuple(
                InterfaceOption(
                    option_id=item.option_id,
                    kind=item.kind,
                    instance=item.instance,
                    signals=dict(item.signals),
                    shareable=item.shareable,
                    notes=tuple(item.notes),
                )
                for item in options
            )
            for kind, options in chip.interfaces.items()
        },
        adc_channels={
            str(pin): tuple(dict(item) for item in channels)
            for pin, channels in chip.adc_channels.items()
        },
        clock_profile=_clone_clock_profile(chip.clock_profile),
        dma_channels=tuple(chip.dma_channels),
        dma_request_map={
            str(key): tuple(value)
            for key, value in chip.dma_request_map.items()
        },
        sources=tuple(chip.sources),
        definition_path=chip.definition_path,
    )


def _clone_module(spec: ModuleSpec) -> ModuleSpec:
    return ModuleSpec(
        key=spec.key,
        display_name=spec.display_name,
        summary=spec.summary,
        hal_components=tuple(spec.hal_components),
        template_files=tuple(spec.template_files),
        resource_requests=tuple(spec.resource_requests),
        depends_on=tuple(spec.depends_on),
        init_priority=int(spec.init_priority),
        loop_priority=int(spec.loop_priority),
        c_top_template=tuple(spec.c_top_template),
        c_init_template=tuple(spec.c_init_template),
        c_loop_template=tuple(spec.c_loop_template),
        c_callbacks_template=tuple(spec.c_callbacks_template),
        irqs=tuple(spec.irqs),
        dma_requests=tuple(spec.dma_requests),
        address_options=tuple(spec.address_options),
        bus_kind=spec.bus_kind,
        optional_signals=tuple(spec.optional_signals),
        notes=tuple(spec.notes),
        sources=tuple(spec.sources),
        definition_path=spec.definition_path,
        template_root=spec.template_root,
        plugin_path=spec.plugin_path,
        simulation=_clone_json_object(spec.simulation),
        app_logic_snippets=_clone_json_object(spec.app_logic_snippets),
    )


def _iter_chip_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()
    return sorted(root.glob("*.json"))


def _iter_board_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()
    return sorted(root.glob("*.json"))


def _iter_module_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()

    top_level = sorted(root.glob("*.json"))
    nested = sorted(root.glob("*/module.json"))
    return [*top_level, *nested]


def _load_chip_file(path: Path) -> ChipDefinition:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _validate_common_manifest(payload, expected_kind="chip", path=path)
    interfaces = {
        kind: tuple(_parse_interface_option(item, default_kind=kind) for item in payload.get("interfaces", {}).get(kind, []))
        for kind in payload.get("interfaces", {})
    }
    return ChipDefinition(
        name=str(payload["name"]).upper(),
        device_name=str(payload["device_name"]),
        vendor=str(payload["vendor"]),
        family=str(payload["family"]),
        cpu_type=str(payload["cpu_type"]),
        package=str(payload["package"]),
        flash_kb=int(payload["flash_kb"]),
        ram_kb=int(payload["ram_kb"]),
        irom_start=_parse_int_value(payload["irom_start"]),
        iram_start=_parse_int_value(payload["iram_start"]),
        c_define=str(payload["c_define"]),
        reserved_pins=_tuple_of_str(payload.get("reserved_pins", [])),
        gpio_preference=_tuple_of_str(payload.get("gpio_preference", [])),
        adc_pins=_tuple_of_str(payload.get("adc_pins", [])),
        interfaces=interfaces,
        adc_channels=_parse_adc_channels(payload.get("adc_channels", {})),
        clock_profile=_parse_clock_profile(payload.get("clock_profile")),
        dma_channels=_tuple_of_str(payload.get("dma_channels", [])),
        dma_request_map={
            str(key).strip().upper(): _tuple_of_str(value)
            for key, value in dict(payload.get("dma_request_map", {})).items()
        },
        sources=_tuple_of_str(payload.get("sources", [])),
        definition_path=str(path),
    )


def _load_board_file(path: Path) -> BoardProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _validate_common_manifest(payload, expected_kind="board", path=path)
    return BoardProfile(
        key=str(payload["key"]).strip().lower(),
        display_name=str(payload["display_name"]).strip(),
        summary=str(payload["summary"]).strip(),
        chip=str(payload["chip"]).strip().upper(),
        reserved_pins=_tuple_of_str(payload.get("reserved_pins", [])),
        avoid_pins=_tuple_of_str(payload.get("avoid_pins", [])),
        preferred_signals={
            str(key).strip(): _tuple_of_str(value)
            for key, value in dict(payload.get("preferred_signals", {})).items()
        },
        clock_profile=_parse_clock_profile(payload.get("clock_profile")),
        capabilities=tuple(_normalize_board_capability(item) for item in list(payload.get("capabilities", []))),
        notes=_tuple_of_str(payload.get("notes", [])),
        sources=_tuple_of_str(payload.get("sources", [])),
        definition_path=str(path),
    )


def _load_module_file(path: Path) -> ModuleSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _validate_common_manifest(payload, expected_kind="module", path=path)
    template_root = path.parent / "templates"
    plugin_path = path.parent / "plugin.py"
    return ModuleSpec(
        key=str(payload["key"]).strip(),
        display_name=str(payload["display_name"]).strip(),
        summary=str(payload["summary"]).strip(),
        hal_components=_tuple_of_str(payload.get("hal_components", [])),
        template_files=_tuple_of_str(payload.get("template_files", [])),
        resource_requests=_tuple_of_str(payload.get("resource_requests", [])),
        depends_on=_tuple_of_str(payload.get("depends_on", [])),
        init_priority=int(payload.get("init_priority", 0) or 0),
        loop_priority=int(payload.get("loop_priority", 0) or 0),
        c_top_template=_tuple_of_code_lines(payload.get("c_top_template", [])),
        c_init_template=_tuple_of_code_lines(payload.get("c_init_template", [])),
        c_loop_template=_tuple_of_code_lines(payload.get("c_loop_template", [])),
        c_callbacks_template=_tuple_of_code_lines(payload.get("c_callbacks_template", [])),
        irqs=_tuple_of_str(payload.get("irqs", [])),
        dma_requests=_tuple_of_str(payload.get("dma_requests", [])),
        address_options=tuple(int(item) for item in payload.get("address_options", [])),
        bus_kind=str(payload.get("bus_kind", "")).strip(),
        optional_signals=_tuple_of_str(payload.get("optional_signals", [])),
        notes=_tuple_of_str(payload.get("notes", [])),
        sources=_tuple_of_str(payload.get("sources", [])),
        definition_path=str(path),
        template_root=str(template_root) if template_root.exists() else "",
        plugin_path=str(plugin_path) if plugin_path.exists() else "",
        simulation=_normalize_json_object(payload.get("simulation", {}), field_name="simulation"),
        app_logic_snippets=_normalize_json_object(payload.get("app_logic_snippets", {}), field_name="app_logic_snippets"),
    )


def _validate_common_manifest(payload: Dict[str, object], expected_kind: str, path: Path) -> None:
    kind = str(payload.get("kind", "")).strip()
    if kind != expected_kind:
        raise ValueError(f"{path} kind must be {expected_kind!r}, got {kind!r}")

    schema_version = str(payload.get("schema_version", "")).strip()
    if schema_version and schema_version != PACK_SCHEMA_VERSION:
        raise ValueError(
            f"{path} schema_version {schema_version!r} is unsupported, expected {PACK_SCHEMA_VERSION!r}"
        )


def _parse_interface_option(payload: Dict[str, object], default_kind: str) -> InterfaceOption:
    signals = payload.get("signals", {})
    if not isinstance(signals, dict) or not signals:
        raise ValueError("interface option signals must be a non-empty object")

    return InterfaceOption(
        option_id=str(payload["option_id"]).strip(),
        kind=str(payload.get("kind", default_kind)).strip(),
        instance=str(payload["instance"]).strip(),
        signals={str(key).strip(): str(value).strip().upper() for key, value in signals.items()},
        shareable=bool(payload.get("shareable", False)),
        notes=_tuple_of_str(payload.get("notes", [])),
    )


def _parse_adc_channels(payload: object) -> Dict[str, Tuple[Dict[str, str], ...]]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("adc_channels must be an object")

    parsed: Dict[str, Tuple[Dict[str, str], ...]] = {}
    for raw_pin, raw_entries in payload.items():
        pin = str(raw_pin).strip().upper()
        if not pin:
            continue
        if not isinstance(raw_entries, list):
            raise ValueError("adc_channels values must be arrays")
        entries: List[Dict[str, str]] = []
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                raise ValueError("adc_channels entries must be objects")
            instance = str(raw_entry.get("instance", "")).strip().upper()
            channel = str(raw_entry.get("channel", "")).strip().upper()
            if not instance or not channel:
                raise ValueError("adc_channels entries require instance and channel")
            entries.append(
                {
                    "instance": instance,
                    "channel": channel,
                }
            )
        if entries:
            parsed[pin] = tuple(entries)
    return parsed


def _clone_clock_profile(profile: ClockProfile | None) -> ClockProfile | None:
    if profile is None:
        return None
    return ClockProfile(
        summary=profile.summary,
        cpu_clock_hz=profile.cpu_clock_hz,
        hse_value=profile.hse_value,
        hsi_value=profile.hsi_value,
        lsi_value=profile.lsi_value,
        lse_value=profile.lse_value,
        external_clock_value=profile.external_clock_value,
        system_clock_config=tuple(profile.system_clock_config),
        notes=tuple(profile.notes),
    )


def _parse_clock_profile(payload: object) -> ClockProfile | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("clock_profile must be an object")
    return ClockProfile(
        summary=str(payload.get("summary", "")).strip(),
        cpu_clock_hz=int(payload.get("cpu_clock_hz", 0) or 0),
        hse_value=int(payload.get("hse_value", 0) or 0),
        hsi_value=int(payload.get("hsi_value", 0) or 0),
        lsi_value=int(payload.get("lsi_value", 0) or 0),
        lse_value=int(payload.get("lse_value", 32768) or 32768),
        external_clock_value=int(payload.get("external_clock_value", 48000) or 48000),
        system_clock_config=_tuple_of_code_lines(payload.get("system_clock_config", [])),
        notes=_tuple_of_str(payload.get("notes", [])),
    )


def _parse_int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    raise ValueError(f"unsupported integer value: {value!r}")


def _tuple_of_str(items: object) -> Tuple[str, ...]:
    if items is None:
        return ()
    if not isinstance(items, list):
        raise ValueError(f"expected list, got {type(items).__name__}")
    return tuple(str(item).strip() for item in items)


def _tuple_of_code_lines(items: object) -> Tuple[str, ...]:
    if items is None:
        return ()
    if not isinstance(items, list):
        raise ValueError(f"expected list, got {type(items).__name__}")
    return tuple(str(item).rstrip("\r\n") for item in items)


def _normalize_board_capability(item: object) -> Dict[str, object]:
    if not isinstance(item, dict):
        raise ValueError("board capability entries must be objects")
    capability = {
        "key": str(item.get("key", "")).strip(),
        "display_name": str(item.get("display_name", "")).strip(),
        "summary": str(item.get("summary", "")).strip(),
        "module_kind": str(item.get("module_kind", "")).strip(),
        "recommended_name": str(item.get("recommended_name", "")).strip(),
        "category": str(item.get("category", "board")).strip() or "board",
        "notes": [str(note).strip() for note in list(item.get("notes", [])) if str(note).strip()],
    }
    if not capability["key"]:
        raise ValueError("board capability key must not be empty")
    return capability


def _chip_to_manifest(chip: ChipDefinition) -> Dict[str, object]:
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "kind": "chip",
        "name": chip.name,
        "device_name": chip.device_name,
        "vendor": chip.vendor,
        "family": chip.family,
        "cpu_type": chip.cpu_type,
        "package": chip.package,
        "flash_kb": chip.flash_kb,
        "ram_kb": chip.ram_kb,
        "irom_start": f"0x{chip.irom_start:08X}",
        "iram_start": f"0x{chip.iram_start:08X}",
        "c_define": chip.c_define,
        "reserved_pins": list(chip.reserved_pins),
        "gpio_preference": list(chip.gpio_preference),
        "adc_pins": list(chip.adc_pins),
        "adc_channels": {
            pin: [dict(item) for item in channels]
            for pin, channels in chip.adc_channels.items()
        },
        "interfaces": {
            kind: [
                {
                    "option_id": option.option_id,
                    "kind": option.kind,
                    "instance": option.instance,
                    "signals": dict(option.signals),
                    "shareable": option.shareable,
                    "notes": list(option.notes),
                }
                for option in options
            ]
            for kind, options in chip.interfaces.items()
        },
        "clock_profile": _clock_profile_to_manifest(chip.clock_profile),
        "dma_channels": list(chip.dma_channels),
        "dma_request_map": {
            key: list(value)
            for key, value in chip.dma_request_map.items()
        },
        "sources": list(chip.sources),
    }


def _board_to_manifest(board: BoardProfile) -> Dict[str, object]:
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "kind": "board",
        "key": board.key,
        "display_name": board.display_name,
        "summary": board.summary,
        "chip": board.chip,
        "reserved_pins": list(board.reserved_pins),
        "avoid_pins": list(board.avoid_pins),
        "preferred_signals": {
            key: list(value)
            for key, value in (board.preferred_signals or {}).items()
        },
        "clock_profile": _clock_profile_to_manifest(board.clock_profile),
        "capabilities": [dict(item) for item in board.capabilities],
        "notes": list(board.notes),
        "sources": list(board.sources),
    }


def _module_to_manifest(spec: ModuleSpec) -> Dict[str, object]:
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "kind": "module",
        "key": spec.key,
        "display_name": spec.display_name,
        "summary": spec.summary,
        "hal_components": list(spec.hal_components),
        "template_files": list(spec.template_files),
        "resource_requests": list(spec.resource_requests),
        "depends_on": list(spec.depends_on),
        "init_priority": spec.init_priority,
        "loop_priority": spec.loop_priority,
        "c_top_template": list(spec.c_top_template),
        "c_init_template": list(spec.c_init_template),
        "c_loop_template": list(spec.c_loop_template),
        "c_callbacks_template": list(spec.c_callbacks_template),
        "irqs": list(spec.irqs),
        "dma_requests": list(spec.dma_requests),
        "address_options": list(spec.address_options),
        "bus_kind": spec.bus_kind,
        "optional_signals": list(spec.optional_signals),
        "simulation": _clone_json_object(spec.simulation),
        "notes": list(spec.notes),
        "sources": list(spec.sources),
    }


def _clone_json_object(value: object) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return json.loads(json.dumps(value, ensure_ascii=False))


def _normalize_json_object(value: object, field_name: str = "object") -> Dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return _clone_json_object(value)


def _clock_profile_to_manifest(profile: ClockProfile | None) -> Dict[str, object] | None:
    if profile is None:
        return None
    return {
        "summary": profile.summary,
        "cpu_clock_hz": profile.cpu_clock_hz,
        "hse_value": profile.hse_value,
        "hsi_value": profile.hsi_value,
        "lsi_value": profile.lsi_value,
        "lse_value": profile.lse_value,
        "external_clock_value": profile.external_clock_value,
        "system_clock_config": list(profile.system_clock_config),
        "notes": list(profile.notes),
    }


def _replace_default_scaffold_templates(
    module_key: str,
    module_root: Path,
    template_files: List[str],
    imported_targets: List[str],
) -> List[str]:
    default_targets = {
        f"modules/{module_key}.c",
        f"modules/{module_key}.h",
    }
    normalized = [item for item in template_files if item]
    if not normalized:
        return []
    if not set(normalized).issubset(default_targets):
        return normalized
    if set(imported_targets) == set(normalized):
        return normalized

    templates_root = module_root / "templates" / "modules"
    for suffix in (".c.tpl", ".h.tpl", ".c", ".h"):
        candidate = templates_root / f"{module_key}{suffix}"
        if candidate.exists():
            candidate.unlink()
    return []


def _remove_default_scaffold_files(module_key: str, module_root: Path) -> None:
    templates_root = module_root / "templates" / "modules"
    for suffix in (".c.tpl", ".h.tpl", ".c", ".h"):
        candidate = templates_root / f"{module_key}{suffix}"
        if candidate.exists():
            candidate.unlink()


def _render_packs_readme() -> str:
    return """# Extension Packs

This directory lets users add chips and modules without editing Python source files.

Layout:
- `chips/*.json`
- `modules/<module_key>/module.json`
- `modules/<module_key>/templates/...`
- `modules/<module_key>/plugin.py`

Template rules:
- `template_files` describes the files that the generated Keil project should contain.
- If a matching file exists under `templates/`, the generator copies that file into the project.
- If no template file exists, the generator falls back to a built-in placeholder renderer.
- `c_callbacks_template` can inject reusable code into `AppCallbacks`.
- Template tokens can provide defaults with `[[token|fallback]]`.
- Scalar options also expose `[[option_name_brackets|[32]]]` style tokens for array declarations.
- Dependency-aware tokens can reference the first matching dependent module, such as `[[dep_uart_frame_uart_handle]]`.
- `simulation` can describe optional Renode-only attachments such as buttons, LEDs, and I2C mocks.
- `depends_on` can require another module kind or name to be present before planning succeeds.
- `init_priority` and `loop_priority` control deterministic middleware injection order.
- `plugin.py` can expose optional `on_plan(context)` / `on_generate(context)` hooks to inject extra metadata or generated files.
- If you already have verified vendor `.h` / `.c` files, use `python -m stm32_agent import-module-files <module_key> <file1> [file2 ...]`.

Supported resource request strings:
- `gpio_out`
- `gpio_in`
- `pwm_out`
- `timer_ic`
- `timer_oc`
- `adc_in`
- `dac_out`
- `uart_port`
- `i2c_device`
- `spi_bus`
- `spi_device`
- `encoder`
- `advanced_timer`
- `can_port`
- `usb_device`
- `onewire_gpio`
- Named form: `gpio_out:reset`
- Optional named form: `gpio_in:int:optional`

Middleware packs:
- A pure software middleware pack can leave `resource_requests` empty and only inject reusable code into `App_Init()` / `App_Loop()`.
- A GPIO-aware middleware pack can combine normal pin requests with `depends_on` to share one software time base or event loop.

Renode simulation pattern:
- Use `simulation.renode.attach` for validation-only attachments and scripted interactions.
- Supported first-step kinds are `led`, `button`, and `i2c_mock`.

Future LLM workflow:
- Upload user manual, datasheet, and sample code.
- Ask the agent to draft a pack under `packs/modules/<name>/`.
- Review the generated `module.json` and templates before using it for project generation.
"""


def _render_module_header_template(module_key: str) -> str:
    guard = module_key.upper().replace("-", "_")
    return f"""#ifndef __{guard}_H
#define __{guard}_H

#include "main.h"

HAL_StatusTypeDef {module_key.title().replace("_", "")}_Init(void);

#endif
"""


def _render_module_source_template(module_key: str) -> str:
    symbol = module_key.title().replace("_", "")
    header_name = f"{module_key}.h"
    return f"""#include "{header_name}"

HAL_StatusTypeDef {symbol}_Init(void)
{{
    return HAL_OK;
}}
"""


def _render_module_plugin_template() -> str:
    return """from __future__ import annotations


def on_plan(context: dict) -> dict:
    # Optional: return extra template/resource/generated-file metadata.
    # Example return shape:
    # {
    #   "warnings": ["Plugin added a helper source file."],
    #   "generated_files": {
    #       "app/helper_task.c": "void HelperTask_Run(void) {}\\n",
    #       "app/helper_task.h": "void HelperTask_Run(void);\\n",
    #   },
    #   "template_files": ["app/helper_task.c", "app/helper_task.h"],
    #   "c_init_template": ["    HelperTask_Init();"],
    # }
    return {}


def on_generate(context: dict) -> dict:
    # Optional: return extra generated files after project_ir is finalized.
    # Example:
    # return {
    #   "generated_files": {
    #       "modules/generated_adapter.c": "/* generated by plugin */\\n",
    #   }
    # }
    return {}
"""
