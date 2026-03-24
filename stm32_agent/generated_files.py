from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Dict

HEADER_SUFFIXES = {".h", ".hpp", ".hh", ".hxx"}


def normalize_generated_file_path(value: object) -> str:
    raw = str(value or "").replace("\\", "/").strip().strip("/")
    if not raw:
        return ""
    parts = [part for part in PurePosixPath(raw).parts if part not in ("", ".")]
    if len(parts) < 2:
        return ""
    prefix = parts[0].lower()
    if prefix not in {"app", "modules"}:
        return ""
    relative_parts = list(parts[1:])
    if relative_parts and relative_parts[0].lower() in {"src", "inc"}:
        relative_parts = relative_parts[1:]
    if not relative_parts or any(part in {"", ".", ".."} for part in relative_parts):
        return ""
    return f"{prefix}/{'/'.join(relative_parts)}"


def is_generated_header_path(value: object) -> bool:
    normalized = normalize_generated_file_path(value)
    if normalized:
        relative = normalized.split("/", 1)[1]
    else:
        relative = str(value or "").replace("\\", "/").strip().strip("/")
    return Path(relative).suffix.lower() in HEADER_SUFFIXES


def generated_file_project_relative_path(normalized_path: str) -> str:
    normalized = normalize_generated_file_path(normalized_path)
    if not normalized:
        raise ValueError(f"Unsupported generated file path: {normalized_path!r}")
    prefix, relative = normalized.split("/", 1)
    root_name = "App" if prefix == "app" else "Modules"
    leaf_type = "Inc" if is_generated_header_path(normalized) else "Src"
    return str(PurePosixPath(root_name, leaf_type, relative))


def generated_file_uvprojx_source_path(normalized_path: str) -> str:
    if is_generated_header_path(normalized_path):
        return ""
    return "../" + generated_file_project_relative_path(normalized_path).replace("\\", "/")


def generated_file_include_path(normalized_path: str) -> str:
    normalized = normalize_generated_file_path(normalized_path)
    if not normalized or not is_generated_header_path(normalized):
        return ""
    return normalized.split("/", 1)[1]


def generated_file_source_path(normalized_path: str) -> str:
    normalized = normalize_generated_file_path(normalized_path)
    if not normalized or is_generated_header_path(normalized):
        return ""
    return normalized.split("/", 1)[1]


def generated_file_group_key(normalized_path: str) -> str:
    normalized = normalize_generated_file_path(normalized_path)
    if not normalized:
        return ""
    return "App" if normalized.startswith("app/") else "Modules"


def generated_file_group_name(normalized_path: str) -> str:
    normalized = normalize_generated_file_path(normalized_path)
    if not normalized:
        return ""
    group_root = "App" if normalized.startswith("app/") else "Modules"
    relative = normalized.split("/", 1)[1]
    parts = list(PurePosixPath(relative).parts[:-1])
    if not parts:
        return f"{group_root}/Src"
    return f"{group_root}/Src/" + "/".join(parts)


def collect_generated_source_groups(value: object) -> Dict[str, list[str]]:
    groups: Dict[str, list[str]] = {"App": [], "Modules": []}
    for normalized_path in normalize_generated_files(value):
        if is_generated_header_path(normalized_path):
            continue
        group_key = generated_file_group_key(normalized_path)
        if group_key:
            groups.setdefault(group_key, []).append(normalized_path)
    for key in list(groups):
        groups[key] = sorted(set(groups[key]))
    return groups


def normalize_generated_files(value: object) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}

    normalized: Dict[str, str] = {}
    for raw_path, raw_content in value.items():
        normalized_path = normalize_generated_file_path(raw_path)
        if not normalized_path:
            continue
        text = str(raw_content or "").replace("\r\n", "\n").strip()
        if not text:
            continue
        normalized[normalized_path] = text + ("\n" if not text.endswith("\n") else "")
    return normalized


def resolve_generated_file_output_path(root: Path, normalized_path: str) -> Path:
    return root / Path(generated_file_project_relative_path(normalized_path))
