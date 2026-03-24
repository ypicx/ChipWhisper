from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Tuple

from .catalog import ChipDefinition, ModuleSpec
from .generated_files import normalize_generated_files

_PLUGIN_CACHE: Dict[str, ModuleType | None] = {}


def apply_module_plan_hook(
    spec: ModuleSpec,
    *,
    module_name: str,
    module_options: Dict[str, object],
    chip: ChipDefinition,
    board: str,
) -> tuple[ModuleSpec, Dict[str, str], List[str]]:
    plugin = _load_module_plugin(spec.plugin_path)
    if plugin is None or not hasattr(plugin, "on_plan"):
        return spec, {}, []

    payload = plugin.on_plan(
        {
            "module": {
                "name": module_name,
                "kind": spec.key,
                "options": dict(module_options),
            },
            "spec": {
                "key": spec.key,
                "display_name": spec.display_name,
                "summary": spec.summary,
                "template_files": list(spec.template_files),
                "resource_requests": list(spec.resource_requests),
                "depends_on": list(spec.depends_on),
                "hal_components": list(spec.hal_components),
            },
            "target": {
                "chip": chip.name,
                "family": chip.family,
                "board": board,
            },
        }
    )
    if payload is None:
        return spec, {}, []
    if not isinstance(payload, dict):
        raise ValueError(f"module plugin on_plan must return a dict, got {type(payload).__name__}")

    generated_files = normalize_generated_files(payload.get("generated_files", {}))
    extra_template_files = _merge_unique(spec.template_files, payload.get("template_files", ()), tuple(generated_files))
    updated_spec = replace(
        spec,
        hal_components=_merge_unique(spec.hal_components, payload.get("hal_components", ())),
        template_files=extra_template_files,
        resource_requests=_merge_unique(spec.resource_requests, payload.get("resource_requests", ())),
        depends_on=_merge_unique(spec.depends_on, payload.get("depends_on", ())),
        c_top_template=_merge_unique(spec.c_top_template, payload.get("c_top_template", ())),
        c_init_template=_merge_unique(spec.c_init_template, payload.get("c_init_template", ())),
        c_loop_template=_merge_unique(spec.c_loop_template, payload.get("c_loop_template", ())),
        c_callbacks_template=_merge_unique(spec.c_callbacks_template, payload.get("c_callbacks_template", ())),
        dma_requests=_merge_unique(spec.dma_requests, payload.get("dma_requests", ())),
        notes=_merge_unique(spec.notes, payload.get("notes", ())),
    )
    warnings = [str(item).strip() for item in payload.get("warnings", []) if str(item).strip()]
    return updated_spec, generated_files, warnings


def collect_module_generate_hook_files(module: Dict[str, object], plan_project_ir: Dict[str, object]) -> Dict[str, str]:
    plugin = _load_module_plugin(str(module.get("plugin_path", "")).strip())
    if plugin is None or not hasattr(plugin, "on_generate"):
        return {}

    payload = plugin.on_generate(
        {
            "module": dict(module),
            "project_ir": dict(plan_project_ir),
        }
    )
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"module plugin on_generate must return a dict, got {type(payload).__name__}")
    return normalize_generated_files(payload.get("generated_files", {}))


def _load_module_plugin(plugin_path: str) -> ModuleType | None:
    normalized = str(plugin_path or "").strip()
    if not normalized:
        return None
    if normalized in _PLUGIN_CACHE:
        return _PLUGIN_CACHE[normalized]

    path = Path(normalized)
    if not path.exists():
        _PLUGIN_CACHE[normalized] = None
        return None

    spec = importlib.util.spec_from_file_location(f"stm32_agent_pack_plugin_{abs(hash(path))}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load plugin module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _PLUGIN_CACHE[normalized] = module
    return module


def _merge_unique(existing: Tuple[str, ...], *iterables: object) -> Tuple[str, ...]:
    merged = [str(item).strip() for item in existing if str(item).strip()]
    for iterable in iterables:
        if isinstance(iterable, (str, bytes)) or iterable is None:
            continue
        try:
            iterator = iter(iterable)
        except TypeError:
            continue
        for item in iterator:
            text = str(item).strip()
            if text and text not in merged:
                merged.append(text)
    return tuple(merged)
