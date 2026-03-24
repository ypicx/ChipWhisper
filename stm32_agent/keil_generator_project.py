from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Mapping

from .catalog import ChipDefinition
from .generated_files import normalize_generated_file_path, normalize_generated_files, resolve_generated_file_output_path
from .keil_generator_app import APP_LOGIC_PLACEHOLDERS
from .keil_generator_context import CodegenContext
from .keil_generator_units import (
    _render_app_header,
    _render_app_source,
    _render_module_header,
    _render_module_source,
)
from .pack_plugins import collect_module_generate_hook_files
from .planner import PlanResult

USER_CODE_BLOCK_RE = re.compile(
    r"/\* USER CODE BEGIN (?P<name>[A-Za-z0-9_]+) \*/(?P<body>.*?)/\* USER CODE END (?P=name) \*/",
    re.S,
)


def project_directories(root: Path) -> List[Path]:
    return [
        root / "Core" / "Inc",
        root / "Core" / "Src",
        root / "App" / "Inc",
        root / "App" / "Src",
        root / "Modules" / "Inc",
        root / "Modules" / "Src",
        root / "Drivers",
        root / "MDK-ARM",
    ]


def collect_custom_template_roots(plan: PlanResult) -> Dict[str, List[str]]:
    template_roots: Dict[str, List[str]] = {}
    for module in plan.project_ir.get("modules", []):
        if not isinstance(module, dict):
            continue
        root = str(module.get("template_root", "")).strip()
        if not root:
            continue
        for target in module.get("template_files", []):
            normalized = str(target).replace("\\", "/")
            normalized = normalize_generated_file_path(normalized) or normalized
            template_roots.setdefault(normalized, [])
            if root not in template_roots[normalized]:
                template_roots[normalized].append(root)
    return template_roots


def resolve_template_content(
    template_roots: Dict[str, List[str]],
    template_path: str,
    default_content: str,
) -> str:
    normalized = template_path.replace("\\", "/")
    for root in template_roots.get(normalized, []):
        root_path = Path(root)
        basename = Path(normalized).name
        for candidate in (
            root_path / normalized,
            root_path / f"{normalized}.tpl",
            root_path / basename,
            root_path / f"{basename}.tpl",
        ):
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")
    return default_content


def merge_preserved_user_code(path: Path, generated_content: str) -> str:
    if not path.exists():
        return generated_content

    try:
        existing_text = path.read_text(encoding="utf-8")
    except OSError:
        return generated_content

    existing_blocks = {
        match.group("name"): match.group("body")
        for match in USER_CODE_BLOCK_RE.finditer(existing_text)
    }
    if not existing_blocks:
        return generated_content

    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        old_body = existing_blocks.get(name)
        if old_body is None:
            return match.group(0)

        new_body = match.group("body")
        placeholder = APP_LOGIC_PLACEHOLDERS.get(name)
        if placeholder is not None:
            if placeholder not in new_body:
                return match.group(0)
            if old_body.strip() == placeholder:
                return match.group(0)
        return f"/* USER CODE BEGIN {name} */{old_body}/* USER CODE END {name} */"

    return USER_CODE_BLOCK_RE.sub(_replace, generated_content)


def assemble_project_files_to_write(
    plan: PlanResult,
    root: Path,
    context: CodegenContext,
    rendered_files: Mapping[str, str],
    _chip: ChipDefinition | None = None,
) -> Dict[Path, str]:
    files_to_write: Dict[Path, str] = {
        root / relative_path: content
        for relative_path, content in rendered_files.items()
    }

    template_roots = collect_custom_template_roots(plan)
    for header in context.app_headers:
        template_path = f"app/{header}"
        files_to_write[root / "App" / "Inc" / header] = resolve_template_content(
            template_roots,
            template_path,
            default_content=_render_app_header(header),
        )
    for source in context.app_sources:
        template_path = f"app/{source}"
        files_to_write[root / "App" / "Src" / source] = resolve_template_content(
            template_roots,
            template_path,
            default_content=_render_app_source(source),
        )
    for header in context.module_headers:
        template_path = f"modules/{header}"
        files_to_write[root / "Modules" / "Inc" / header] = resolve_template_content(
            template_roots,
            template_path,
            default_content=_render_module_header(header),
        )
    for source in context.module_sources:
        template_path = f"modules/{source}"
        files_to_write[root / "Modules" / "Src" / source] = resolve_template_content(
            template_roots,
            template_path,
            default_content=_render_module_source(source),
        )

    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    build = project_ir.get("build", {}) if isinstance(project_ir, dict) else {}
    for normalized_path, content in normalize_generated_files(build.get("generated_files", {})).items():
        files_to_write[resolve_generated_file_output_path(root, normalized_path)] = content

    for module in project_ir.get("modules", []) if isinstance(project_ir.get("modules", []), list) else []:
        if not isinstance(module, dict):
            continue
        try:
            generated_from_hook = collect_module_generate_hook_files(module, project_ir)
        except Exception as exc:
            module_name = str(module.get("name", "")).strip() or str(module.get("kind", "")).strip() or "unknown"
            raise ValueError(f"Module plugin on_generate failed for {module_name}: {exc}") from exc
        for normalized_path, content in generated_from_hook.items():
            files_to_write[resolve_generated_file_output_path(root, normalized_path)] = content

    for path, content in list(files_to_write.items()):
        files_to_write[path] = merge_preserved_user_code(path, content)
    return files_to_write
