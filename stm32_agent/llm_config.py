from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = (
    "You are an STM32 development assistant. Stay grounded in the current project, "
    "the user request, and the available files."
)


@dataclass
class LlmProfile:
    profile_id: str
    name: str
    provider_type: str
    base_url: str
    api_key: str
    model: str
    system_prompt: str
    temperature: float
    enabled: bool = True

    def to_dict(self, *, mask_api_key: bool = True) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "provider_type": self.provider_type,
            "base_url": self.base_url,
            "api_key": _mask_key(self.api_key) if mask_api_key else self.api_key,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "enabled": self.enabled,
        }


@dataclass
class LlmConfig:
    config_path: str
    config_exists: bool
    default_profile_id: str
    profiles: list[LlmProfile]
    warnings: list[str]
    errors: list[str]

    def to_dict(self, *, mask_api_key: bool = True) -> dict[str, object]:
        return {
            "config_path": self.config_path,
            "config_exists": self.config_exists,
            "default_profile_id": self.default_profile_id,
            "profiles": [profile.to_dict(mask_api_key=mask_api_key) for profile in self.profiles],
            "warnings": self.warnings,
            "errors": self.errors,
        }


def get_default_llm_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "stm32_agent.llm.json"


def get_example_llm_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "stm32_agent.llm.example.json"


def load_llm_config(config_path: str | Path | None = None) -> LlmConfig:  # noqa: C901
    resolved_path = Path(config_path) if config_path is not None else get_default_llm_config_path()
    if not resolved_path.exists():
        return LlmConfig(
            config_path=str(resolved_path),
            config_exists=False,
            default_profile_id="",
            profiles=[],
            warnings=[f"LLM config file does not exist yet: {resolved_path}"],
            errors=[],
        )

    warnings: list[str] = []
    errors: list[str] = []

    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return LlmConfig(
            config_path=str(resolved_path),
            config_exists=True,
            default_profile_id="",
            profiles=[],
            warnings=[],
            errors=[f"Failed to read LLM config: {exc}"],
        )

    if not isinstance(payload, dict):
        return LlmConfig(
            config_path=str(resolved_path),
            config_exists=True,
            default_profile_id="",
            profiles=[],
            warnings=[],
            errors=["LLM config root must be a JSON object."],
        )

    profiles_payload = payload.get("profiles", [])
    profiles: list[LlmProfile] = []
    if not isinstance(profiles_payload, list):
        errors.append("profiles must be a JSON array.")
        profiles_payload = []

    for item in profiles_payload:
        if not isinstance(item, dict):
            warnings.append("Skipped one invalid profile entry because it was not an object.")
            continue
        try:
            profiles.append(_profile_from_payload(item))
        except ValueError as exc:
            warnings.append(str(exc))

    default_profile_id = str(payload.get("default_profile_id", "")).strip()
    if default_profile_id and all(profile.profile_id != default_profile_id for profile in profiles):
        warnings.append("default_profile_id does not match any current profile.")

    return LlmConfig(
        config_path=str(resolved_path),
        config_exists=True,
        default_profile_id=default_profile_id,
        profiles=profiles,
        warnings=warnings,
        errors=errors,
    )


def save_llm_config(
    profiles: list[LlmProfile],
    default_profile_id: str = "",
    config_path: str | Path | None = None,
) -> Path:
    resolved_path = Path(config_path) if config_path is not None else get_default_llm_config_path()
    payload = {
        "default_profile_id": default_profile_id,
        "profiles": [profile.to_dict(mask_api_key=False) for profile in profiles],
    }
    resolved_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved_path


def write_llm_config_template(
    config_path: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    resolved_path = Path(config_path) if config_path is not None else get_default_llm_config_path()
    if resolved_path.exists() and not overwrite:
        return resolved_path

    example_profiles = [
        LlmProfile(
            profile_id=_new_profile_id(),
            name="OpenAI",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="",
            model="gpt-4.1-mini",
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            temperature=0.2,
            enabled=True,
        ),
        LlmProfile(
            profile_id=_new_profile_id(),
            name="OpenAI Compatible",
            provider_type="openai_compatible",
            base_url="https://api.example.com/v1",
            api_key="",
            model="",
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            temperature=0.2,
            enabled=False,
        ),
        LlmProfile(
            profile_id=_new_profile_id(),
            name="Anthropic",
            provider_type="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key="",
            model="claude-3-5-sonnet-latest",
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            temperature=0.2,
            enabled=False,
        ),
        LlmProfile(
            profile_id=_new_profile_id(),
            name="Gemini",
            provider_type="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key="",
            model="gemini-2.0-flash",
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            temperature=0.2,
            enabled=False,
        ),
        LlmProfile(
            profile_id=_new_profile_id(),
            name="Ollama Local",
            provider_type="ollama",
            base_url="http://127.0.0.1:11434",
            api_key="",
            model="qwen2.5-coder:7b",
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            temperature=0.2,
            enabled=False,
        ),
    ]
    default_profile_id = example_profiles[0].profile_id if example_profiles else ""
    return save_llm_config(example_profiles, default_profile_id, resolved_path)


def _profile_from_payload(payload: dict[str, object]) -> LlmProfile:
    profile_id = str(payload.get("profile_id", "")).strip() or _new_profile_id()
    name = str(payload.get("name", "")).strip()
    provider_type = str(payload.get("provider_type", "")).strip() or "openai_compatible"
    normalized_provider = provider_type.lower()
    if normalized_provider == "openai_responses":
        provider_type = "openai"
    elif normalized_provider == "claude":
        provider_type = "anthropic"
    elif normalized_provider in {"google", "google_ai_studio", "generativelanguage"}:
        provider_type = "gemini"
    elif normalized_provider in {
        "deepseek",
        "openrouter",
        "groq",
        "siliconflow",
        "together",
        "fireworks",
        "moonshot",
        "kimi",
        "qwen",
        "dashscope",
        "zhipu",
        "yi",
        "mistral",
        "doubao",
        "minimax",
    }:
        provider_type = "openai_compatible"
    base_url = str(payload.get("base_url", "")).strip()
    model = str(payload.get("model", "")).strip()
    if not name:
        raise ValueError("Skipped one profile because name is empty.")
    return LlmProfile(
        profile_id=profile_id,
        name=name,
        provider_type=provider_type,
        base_url=base_url,
        api_key=str(payload.get("api_key", "")),
        model=model,
        system_prompt=str(payload.get("system_prompt", DEFAULT_SYSTEM_PROMPT)),
        temperature=float(payload.get("temperature", 0.2)),
        enabled=bool(payload.get("enabled", True)),
    )


def _mask_key(key: str) -> str:
    """Mask an API key for safe display, showing only the last 4 characters."""
    stripped = key.strip()
    if len(stripped) <= 4:
        return "****" if stripped else ""
    return "****" + stripped[-4:]


def _new_profile_id() -> str:
    return uuid.uuid4().hex
