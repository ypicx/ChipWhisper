from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


CONFIG_KEYS = {
    "keil_uv4_path": ["KEIL_UV4_PATH", "UV4_PATH", "MDK_UV4_PATH"],
    "keil_fromelf_path": ["KEIL_FROMELF_PATH", "FROMELF_PATH"],
    "renode_exe_path": ["RENODE_PATH", "RENODE_EXE_PATH"],
    "stm32cubemx_install_path": ["STM32CUBEMX_PATH", "STM32CUBEMX_INSTALL_PATH"],
    "stm32cube_repository_path": ["STM32CUBE_REPOSITORY", "STM32CUBE_REPO_PATH", "STM32CUBEMX_REPOSITORY"],
    "stm32cube_f1_package_path": ["STM32CUBE_F1_PACKAGE_PATH"],
    "stm32cube_g4_package_path": ["STM32CUBE_G4_PACKAGE_PATH"],
}


@dataclass
class ResolvedPathItem:
    key: str
    value: str
    source: str
    exists: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "exists": self.exists,
        }


@dataclass
class PathConfigResult:
    config_path: str
    config_exists: bool
    paths: list[ResolvedPathItem]
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "config_path": self.config_path,
            "config_exists": self.config_exists,
            "paths": [item.to_dict() for item in self.paths],
            "warnings": self.warnings,
            "errors": self.errors,
        }


def get_default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "stm32_agent.paths.json"


def get_example_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "stm32_agent.paths.example.json"


def load_path_config(config_path: str | Path | None = None) -> tuple[Path, dict[str, str]]:
    resolved_path = Path(config_path) if config_path is not None else get_default_config_path()
    if not resolved_path.exists():
        return resolved_path, {}
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("读取路径配置失败: %s", exc)
        return resolved_path, {}
    if not isinstance(payload, dict):
        return resolved_path, {}
    normalized: dict[str, str] = {}
    for key in CONFIG_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    return resolved_path, normalized


def save_path_config(
    values: dict[str, str],
    config_path: str | Path | None = None,
) -> Path:
    resolved_path = Path(config_path) if config_path is not None else get_default_config_path()
    normalized: dict[str, str] = {}
    for key in CONFIG_KEYS:
        value = values.get(key, "")
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
        else:
            normalized[key] = ""
    resolved_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved_path


def resolve_configured_path(key: str, config_path: str | Path | None = None) -> tuple[str | None, str]:
    if key not in CONFIG_KEYS:
        return None, ""

    for env_name in CONFIG_KEYS[key]:
        env_value = os.environ.get(env_name)
        if env_value:
            return env_value, f"env:{env_name}"

    resolved_config_path, config_values = load_path_config(config_path)
    config_value = config_values.get(key)
    if config_value:
        return config_value, f"config:{resolved_config_path}"

    return None, ""


def doctor_path_config(config_path: str | Path | None = None) -> PathConfigResult:
    resolved_config_path, config_values = load_path_config(config_path)
    warnings: list[str] = []
    errors: list[str] = []
    items: list[ResolvedPathItem] = []

    for key in CONFIG_KEYS:
        value, source = resolve_configured_path(key, resolved_config_path)
        if value is None:
            raw_value = config_values.get(key, "")
            if raw_value:
                items.append(
                    ResolvedPathItem(
                        key=key,
                        value=raw_value,
                        source=f"config:{resolved_config_path}",
                        exists=Path(raw_value).exists(),
                    )
                )
            else:
                items.append(ResolvedPathItem(key=key, value="", source="unset", exists=False))
            continue

        items.append(
            ResolvedPathItem(
                key=key,
                value=value,
                source=source,
                exists=Path(value).exists(),
            )
        )

    if not resolved_config_path.exists():
        warnings.append(f"未发现路径配置文件，可通过 init-paths 生成: {resolved_config_path}")

    return PathConfigResult(
        config_path=str(resolved_config_path),
        config_exists=resolved_config_path.exists(),
        paths=items,
        warnings=warnings,
        errors=errors,
    )


def write_path_config_template(config_path: str | Path | None = None, overwrite: bool = False) -> Path:
    resolved_path = Path(config_path) if config_path is not None else get_default_config_path()
    if resolved_path.exists() and not overwrite:
        return resolved_path

    template = {
        "keil_uv4_path": _best_guess(
            resolve_configured_path("keil_uv4_path", resolved_path)[0],
            r"D:\Keil_v5\UV4\UV4.exe",
        ),
        "keil_fromelf_path": _best_guess(
            resolve_configured_path("keil_fromelf_path", resolved_path)[0],
            r"D:\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe",
        ),
        "renode_exe_path": _best_guess(
            resolve_configured_path("renode_exe_path", resolved_path)[0],
            r"D:\Renode\renode.exe",
        ),
        "stm32cubemx_install_path": _best_guess(
            resolve_configured_path("stm32cubemx_install_path", resolved_path)[0],
            r"D:\STM32CubeMX",
        ),
        "stm32cube_repository_path": _best_guess(
            resolve_configured_path("stm32cube_repository_path", resolved_path)[0],
            str(Path.home() / "STM32Cube" / "Repository"),
        ),
        "stm32cube_f1_package_path": _best_guess(
            resolve_configured_path("stm32cube_f1_package_path", resolved_path)[0],
            str((Path.home() / "STM32Cube" / "Repository" / "STM32Cube_FW_F1_V1.8.7")),
        ),
        "stm32cube_g4_package_path": _best_guess(
            resolve_configured_path("stm32cube_g4_package_path", resolved_path)[0],
            str((Path.home() / "STM32Cube" / "Repository" / "STM32Cube_FW_G4_V1.6.2")),
        ),
    }
    resolved_path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resolved_path


def _best_guess(value: str | None, fallback: str) -> str:
    return value or fallback
