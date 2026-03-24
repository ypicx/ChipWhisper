from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Callable, Iterable, List
from urllib.parse import urlparse

import requests

from ..llm_config import LlmProfile


ChatMessage = dict[str, object]
ChatMessageList = List[ChatMessage]


@dataclass(frozen=True)
class ProviderAdapter:
    provider_type: str
    label: str
    complete_fn: Callable[[LlmProfile, ChatMessageList], str]
    stream_fn: Callable[[LlmProfile, ChatMessageList, Callable[[str], None]], None]
    list_models_fn: Callable[[LlmProfile], List[str]]
    requires_api_key: bool = True


_KNOWN_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/responses",
    "/models",
    "/messages",
    "/api/chat",
    "/api/tags",
    ":generateContent",
    ":streamGenerateContent",
)

_DEFAULT_ANTHROPIC_MAX_TOKENS = 4096
_ANTHROPIC_API_VERSION = "2023-06-01"
_OPENAI_COMPATIBLE_ALIASES = {
    "openai_compatible",
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
}


def get_supported_provider_types() -> List[str]:
    return list(_PROVIDER_ADAPTERS.keys())


def complete_chat_completion(
    profile: LlmProfile,
    messages: ChatMessageList,
) -> str:
    adapter = _get_provider_adapter(profile)
    return adapter.complete_fn(profile, messages)


def stream_chat_completion(
    profile: LlmProfile,
    messages: ChatMessageList,
    on_chunk: Callable[[str], None],
) -> None:
    adapter = _get_provider_adapter(profile)
    adapter.stream_fn(profile, messages, on_chunk)


def test_profile_connection(profile: LlmProfile) -> tuple[bool, str]:
    adapter = _get_provider_adapter(profile)
    if adapter.requires_api_key and not profile.api_key.strip():
        return False, "API key is empty."
    if not profile.base_url.strip():
        return False, "Base URL is empty."

    try:
        models = adapter.list_models_fn(profile)
    except Exception as exc:
        return False, f"{adapter.label} model discovery failed: {exc}"

    detail = f"{adapter.label} reachable: {_describe_models_url(profile, adapter.provider_type)}"
    if models:
        detail += "\nAvailable models: " + ", ".join(models[:20])
        if not profile.model.strip():
            detail += "\nModel is empty; please copy one of the model IDs above."
    else:
        detail += "\nNo models were returned by the endpoint."
    return True, detail


test_profile_connection.__test__ = False


def _complete_openai_responses(
    profile: LlmProfile,
    messages: ChatMessageList,
) -> str:
    _require_base_url(profile)
    _require_api_key(profile)
    model = _resolve_model(profile)
    response = requests.post(
        _build_url(profile.base_url, "/responses"),
        headers=_build_openai_headers(profile),
        json={
            "model": model,
            "input": _build_responses_input(messages),
            "temperature": profile.temperature,
            "stream": False,
        },
        timeout=(15, 600),
    )
    response.raise_for_status()
    return _normalize_message_content(_load_json_response(response))


def _stream_openai_responses(
    profile: LlmProfile,
    messages: ChatMessageList,
    on_chunk: Callable[[str], None],
) -> None:
    _require_base_url(profile)
    _require_api_key(profile)
    model = _resolve_model(profile)
    payload = {
        "model": model,
        "input": _build_responses_input(messages),
        "temperature": profile.temperature,
        "stream": True,
    }
    with requests.post(
        _build_url(profile.base_url, "/responses"),
        headers=_build_openai_headers(profile),
        json=payload,
        timeout=(15, 600),
        stream=True,
    ) as response:
        response.raise_for_status()
        for line in _iter_stream_lines(response.iter_lines(decode_unicode=False)):
            if line == "[DONE]":
                return
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            event_type = str(payload.get("type", "")).strip()
            if event_type == "response.output_text.delta":
                delta = payload.get("delta")
                if isinstance(delta, str) and delta:
                    on_chunk(delta)
                continue
            if event_type in {"response.completed", "response.done"}:
                return
            if event_type == "error":
                message = payload.get("message") or payload.get("error") or "streaming error"
                raise RuntimeError(str(message))


def _complete_openai_compatible_chat(
    profile: LlmProfile,
    messages: ChatMessageList,
) -> str:
    _require_base_url(profile)
    model = _resolve_model(profile)
    response = requests.post(
        _build_url(profile.base_url, "/chat/completions"),
        headers=_build_openai_headers(profile),
        json={
            "model": model,
            "messages": _build_openai_compatible_messages(messages),
            "temperature": profile.temperature,
            "stream": False,
        },
        timeout=(15, 600),
    )
    response.raise_for_status()
    data = _load_json_response(response)
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return _normalize_message_content(message.get("content"))


def _stream_openai_compatible_chat(
    profile: LlmProfile,
    messages: ChatMessageList,
    on_chunk: Callable[[str], None],
) -> None:
    _require_base_url(profile)
    model = _resolve_model(profile)
    payload = {
        "model": model,
        "messages": _build_openai_compatible_messages(messages),
        "temperature": profile.temperature,
        "stream": True,
    }
    with requests.post(
        _build_url(profile.base_url, "/chat/completions"),
        headers=_build_openai_headers(profile),
        json=payload,
        timeout=(15, 600),
        stream=True,
    ) as response:
        response.raise_for_status()
        for line in _iter_stream_lines(response.iter_lines(decode_unicode=False)):
            if line == "[DONE]":
                return
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            choice = (payload.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                on_chunk(content)


def _complete_ollama_chat(
    profile: LlmProfile,
    messages: ChatMessageList,
) -> str:
    _require_base_url(profile)
    model = _resolve_model(profile)
    response = requests.post(
        _build_url(profile.base_url, "/api/chat"),
        json={
            "model": model,
            "messages": _build_ollama_messages(messages),
            "stream": False,
        },
        timeout=(15, 600),
    )
    response.raise_for_status()
    data = _load_json_response(response)
    message = data.get("message") or {}
    return _normalize_message_content(message.get("content"))


def _stream_ollama_chat(
    profile: LlmProfile,
    messages: ChatMessageList,
    on_chunk: Callable[[str], None],
) -> None:
    _require_base_url(profile)
    model = _resolve_model(profile)
    payload = {
        "model": model,
        "messages": _build_ollama_messages(messages),
        "stream": True,
    }
    with requests.post(
        _build_url(profile.base_url, "/api/chat"),
        json=payload,
        timeout=(15, 600),
        stream=True,
    ) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=False):
            line = _decode_text(raw_line).strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            message = payload.get("message") or {}
            content = message.get("content")
            if isinstance(content, str) and content:
                on_chunk(content)
            if payload.get("done"):
                return


def _complete_anthropic_messages(
    profile: LlmProfile,
    messages: ChatMessageList,
) -> str:
    _require_base_url(profile)
    _require_api_key(profile)
    payload = _build_anthropic_payload(profile, messages, stream=False)
    response = requests.post(
        _build_url(profile.base_url, "/messages"),
        headers=_build_anthropic_headers(profile),
        json=payload,
        timeout=(15, 600),
    )
    response.raise_for_status()
    return _normalize_message_content(_load_json_response(response))


def _stream_anthropic_messages(
    profile: LlmProfile,
    messages: ChatMessageList,
    on_chunk: Callable[[str], None],
) -> None:
    _require_base_url(profile)
    _require_api_key(profile)
    payload = _build_anthropic_payload(profile, messages, stream=True)
    with requests.post(
        _build_url(profile.base_url, "/messages"),
        headers=_build_anthropic_headers(profile),
        json=payload,
        timeout=(15, 600),
        stream=True,
    ) as response:
        response.raise_for_status()
        for line in _iter_stream_lines(response.iter_lines(decode_unicode=False)):
            if line == "[DONE]":
                return
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            event_type = str(payload.get("type", "")).strip()
            if event_type == "content_block_delta":
                delta = payload.get("delta") or {}
                text = delta.get("text")
                if isinstance(text, str) and text:
                    on_chunk(text)
                continue
            if event_type in {"message_stop", "message_delta"}:
                continue
            if event_type == "error":
                error = payload.get("error") or {}
                message = error.get("message") or payload.get("message") or "streaming error"
                raise RuntimeError(str(message))


def _complete_gemini_generate_content(
    profile: LlmProfile,
    messages: ChatMessageList,
) -> str:
    _require_base_url(profile)
    _require_api_key(profile)
    model_path = _normalize_gemini_model_path(_resolve_model(profile))
    response = _gemini_post(
        _build_url(profile.base_url, f"/{model_path}:generateContent"),
        profile,
        json=_build_gemini_payload(profile, messages),
        timeout=(15, 600),
    )
    response.raise_for_status()
    return _normalize_message_content(_load_json_response(response))


def _stream_gemini_generate_content(
    profile: LlmProfile,
    messages: ChatMessageList,
    on_chunk: Callable[[str], None],
) -> None:
    _require_base_url(profile)
    _require_api_key(profile)
    model_path = _normalize_gemini_model_path(_resolve_model(profile))
    response = _gemini_post(
        _build_url(profile.base_url, f"/{model_path}:streamGenerateContent"),
        profile,
        json=_build_gemini_payload(profile, messages),
        params={"alt": "sse"},
        timeout=(15, 600),
        stream=True,
    )
    with response:
        response.raise_for_status()
        for line in _iter_stream_lines(response.iter_lines(decode_unicode=False)):
            if line == "[DONE]":
                return
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            text = _extract_gemini_chunk_text(payload)
            if text:
                on_chunk(text)


def _list_openai_models(profile: LlmProfile) -> List[str]:
    response = requests.get(
        _build_url(profile.base_url, "/models"),
        headers=_build_openai_headers(profile),
        timeout=10,
    )
    response.raise_for_status()
    data = _load_json_response(response)
    raw_items = data.get("data", []) if isinstance(data, dict) else []
    return _dedupe_preserve_order(
        str(item.get("id", "")).strip()
        for item in raw_items
        if isinstance(item, dict)
    )


def _list_ollama_models(profile: LlmProfile) -> List[str]:
    response = requests.get(_build_url(profile.base_url, "/api/tags"), timeout=10)
    response.raise_for_status()
    data = _load_json_response(response)
    raw_items = data.get("models", []) if isinstance(data, dict) else []
    return _dedupe_preserve_order(
        str(item.get("name", "")).strip()
        for item in raw_items
        if isinstance(item, dict)
    )


def _list_anthropic_models(profile: LlmProfile) -> List[str]:
    response = requests.get(
        _build_url(profile.base_url, "/models"),
        headers=_build_anthropic_headers(profile),
        timeout=10,
    )
    response.raise_for_status()
    data = _load_json_response(response)
    raw_items = data.get("data", []) if isinstance(data, dict) else []
    return _dedupe_preserve_order(
        str(item.get("id", "")).strip()
        for item in raw_items
        if isinstance(item, dict)
    )


def _list_gemini_models(profile: LlmProfile) -> List[str]:
    response = _gemini_get(
        _build_url(profile.base_url, "/models"),
        profile,
        timeout=10,
    )
    response.raise_for_status()
    data = _load_json_response(response)
    raw_items = data.get("models", []) if isinstance(data, dict) else []
    return _dedupe_preserve_order(
        str(item.get("name", "")).strip()
        for item in raw_items
        if isinstance(item, dict)
    )


def _require_base_url(profile: LlmProfile) -> None:
    if not profile.base_url.strip():
        raise RuntimeError("base_url is empty")


def _require_api_key(profile: LlmProfile) -> None:
    if not profile.api_key.strip():
        raise RuntimeError("api_key is empty")


def _resolve_model(profile: LlmProfile) -> str:
    model = profile.model.strip()
    if model:
        return model
    models = _get_provider_adapter(profile).list_models_fn(profile)
    if len(models) == 1:
        return models[0]
    if models:
        raise RuntimeError(f"model is empty; available models: {', '.join(models[:20])}")
    raise RuntimeError("model is empty and the endpoint did not return any available models")


def _build_openai_headers(profile: LlmProfile) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if profile.api_key.strip():
        headers["Authorization"] = f"Bearer {profile.api_key}"
    return headers


def _build_anthropic_headers(profile: LlmProfile) -> dict[str, str]:
    return {
        "x-api-key": profile.api_key,
        "anthropic-version": _ANTHROPIC_API_VERSION,
        "Content-Type": "application/json",
    }


def _build_gemini_headers(profile: LlmProfile) -> dict[str, str]:
    return {
        "x-goog-api-key": profile.api_key,
        "Content-Type": "application/json",
    }


def _gemini_get(
    url: str,
    profile: LlmProfile,
    **kwargs: object,
) -> requests.Response:
    response = requests.get(
        url,
        headers=_build_gemini_headers(profile),
        **kwargs,
    )
    if _should_retry_gemini_with_query_key(response):
        _close_response(response)
        params = dict(kwargs.get("params") or {})
        params["key"] = profile.api_key
        retry_kwargs = dict(kwargs)
        retry_kwargs["params"] = params
        response = requests.get(
            url,
            headers={"Content-Type": "application/json"},
            **retry_kwargs,
        )
    return response


def _gemini_post(
    url: str,
    profile: LlmProfile,
    **kwargs: object,
) -> requests.Response:
    response = requests.post(
        url,
        headers=_build_gemini_headers(profile),
        **kwargs,
    )
    if _should_retry_gemini_with_query_key(response):
        _close_response(response)
        params = dict(kwargs.get("params") or {})
        params["key"] = profile.api_key
        retry_kwargs = dict(kwargs)
        retry_kwargs["params"] = params
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            **retry_kwargs,
        )
    return response


def _should_retry_gemini_with_query_key(response: requests.Response) -> bool:
    status_code = int(getattr(response, "status_code", 200) or 200)
    return status_code in {400, 401, 403}


def _close_response(response: object) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _build_anthropic_payload(
    profile: LlmProfile,
    messages: ChatMessageList,
    stream: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": _resolve_model(profile),
        "messages": _build_anthropic_messages(messages),
        "max_tokens": _DEFAULT_ANTHROPIC_MAX_TOKENS,
        "temperature": profile.temperature,
        "stream": stream,
    }
    system_text = _extract_system_text(messages)
    if system_text:
        payload["system"] = system_text
    return payload


def _build_gemini_payload(profile: LlmProfile, messages: ChatMessageList) -> dict[str, object]:
    payload: dict[str, object] = {
        "contents": _build_gemini_contents(messages),
        "generationConfig": {"temperature": profile.temperature},
    }
    system_text = _extract_system_text(messages)
    if system_text:
        payload["system_instruction"] = {"parts": [{"text": system_text}]}
    return payload


def _build_responses_input(messages: ChatMessageList) -> List[dict[str, object]]:
    items: List[dict[str, object]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        content_items = _build_responses_message_parts(message)
        if not content_items:
            content_items = [{"type": "input_text", "text": ""}]
        items.append({"type": "message", "role": role, "content": content_items})
    return items


def _build_responses_message_parts(message: ChatMessage) -> List[dict[str, object]]:
    parts: List[dict[str, object]] = []
    for item in _iter_message_parts(message):
        kind = str(item.get("type", "")).strip()
        if kind == "text":
            text = str(item.get("text", ""))
            if text:
                parts.append({"type": "input_text", "text": text})
        elif kind == "image":
            image_url = str(item.get("image_url", "")).strip()
            if image_url:
                payload = {"type": "input_image", "image_url": image_url}
                detail = str(item.get("detail", "")).strip()
                if detail:
                    payload["detail"] = detail
                parts.append(payload)
    return parts


def _build_openai_compatible_messages(messages: ChatMessageList) -> List[dict[str, object]]:
    normalized: List[dict[str, object]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        parts = list(_iter_message_parts(message))
        if not parts:
            normalized.append({"role": role, "content": ""})
            continue
        if all(str(item.get("type", "")).strip() == "text" for item in parts):
            text = "\n".join(str(item.get("text", "")) for item in parts if str(item.get("text", "")))
            normalized.append({"role": role, "content": text})
            continue
        content_parts: List[dict[str, object]] = []
        for item in parts:
            kind = str(item.get("type", "")).strip()
            if kind == "text":
                text = str(item.get("text", ""))
                if text:
                    content_parts.append({"type": "text", "text": text})
            elif kind == "image":
                image_url = str(item.get("image_url", "")).strip()
                if image_url:
                    payload = {"url": image_url}
                    detail = str(item.get("detail", "")).strip()
                    if detail:
                        payload["detail"] = detail
                    content_parts.append({"type": "image_url", "image_url": payload})
        normalized.append({"role": role, "content": content_parts or ""})
    return normalized


def _build_ollama_messages(messages: ChatMessageList) -> List[dict[str, object]]:
    normalized: List[dict[str, object]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        normalized.append({"role": role, "content": _message_to_plain_text(message)})
    return normalized


def _build_anthropic_messages(messages: ChatMessageList) -> List[dict[str, object]]:
    normalized: List[dict[str, object]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        if role == "system":
            continue
        anthropic_role = "assistant" if role == "assistant" else "user"
        content: List[dict[str, object]] = []
        for item in _iter_message_parts(message):
            kind = str(item.get("type", "")).strip()
            if kind == "text":
                text = str(item.get("text", ""))
                if text:
                    content.append({"type": "text", "text": text})
            elif kind == "image":
                image_part = _build_anthropic_image_part(item)
                if image_part is not None:
                    content.append(image_part)
                else:
                    content.append({"type": "text", "text": _image_fallback_text(item)})
        if not content:
            content = [{"type": "text", "text": ""}]
        normalized.append({"role": anthropic_role, "content": content})
    return normalized


def _build_gemini_contents(messages: ChatMessageList) -> List[dict[str, object]]:
    contents: List[dict[str, object]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        if role == "system":
            continue
        gemini_role = "model" if role == "assistant" else "user"
        parts: List[dict[str, object]] = []
        for item in _iter_message_parts(message):
            kind = str(item.get("type", "")).strip()
            if kind == "text":
                text = str(item.get("text", ""))
                if text:
                    parts.append({"text": text})
            elif kind == "image":
                image_part = _build_gemini_image_part(item)
                if image_part is not None:
                    parts.append(image_part)
                else:
                    parts.append({"text": _image_fallback_text(item)})
        if not parts:
            parts = [{"text": ""}]
        contents.append({"role": gemini_role, "parts": parts})
    if not contents:
        contents.append({"role": "user", "parts": [{"text": ""}]})
    return contents


def _extract_system_text(messages: ChatMessageList) -> str:
    parts: List[str] = []
    for message in messages:
        if str(message.get("role", "user")).strip() != "system":
            continue
        text = _message_to_plain_text(message).strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _build_anthropic_image_part(item: dict[str, object]) -> dict[str, object] | None:
    image_url = str(item.get("image_url", "")).strip()
    parsed = _parse_inline_image(image_url)
    if parsed is None:
        return None
    media_type, data = parsed
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        },
    }


def _build_gemini_image_part(item: dict[str, object]) -> dict[str, object] | None:
    image_url = str(item.get("image_url", "")).strip()
    parsed = _parse_inline_image(image_url)
    if parsed is None:
        return None
    media_type, data = parsed
    return {
        "inline_data": {
            "mime_type": media_type,
            "data": data,
        }
    }


def _parse_inline_image(image_url: str) -> tuple[str, str] | None:
    if not image_url.startswith("data:"):
        return None
    header, separator, data = image_url.partition(",")
    if separator != "," or not data:
        return None
    meta = header[5:]
    if ";base64" not in meta:
        return None
    media_type = meta.split(";", 1)[0].strip() or "application/octet-stream"
    try:
        base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None
    return media_type, data


def _image_fallback_text(item: dict[str, object]) -> str:
    name = str(item.get("name", "")).strip() or "image"
    return f"[Image omitted: {name}] Visual input is unavailable for this provider."


def _message_to_plain_text(message: ChatMessage) -> str:
    lines: List[str] = []
    for item in _iter_message_parts(message):
        kind = str(item.get("type", "")).strip()
        if kind == "text":
            text = str(item.get("text", "")).strip()
            if text:
                lines.append(text)
        elif kind == "image":
            lines.append(_image_fallback_text(item))
    return "\n\n".join(lines)


def _iter_message_parts(message: ChatMessage) -> Iterable[dict[str, object]]:
    content = message.get("content", "")
    if isinstance(content, str):
        yield {"type": "text", "text": content}
        return
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type", "")).strip()
        if kind == "text":
            yield {"type": "text", "text": str(item.get("text", ""))}
        elif kind == "image":
            payload = {"type": "image", "image_url": str(item.get("image_url", ""))}
            if item.get("detail") is not None:
                payload["detail"] = item.get("detail")
            if item.get("name") is not None:
                payload["name"] = item.get("name")
            yield payload


def _iter_stream_lines(lines: Iterable[str | bytes]) -> Iterable[str]:
    for raw_line in lines:
        line = _decode_text(raw_line).strip()
        if not line:
            continue
        if line.startswith("data:"):
            yield line[5:].strip()


def _load_json_response(response: requests.Response) -> object:
    return json.loads(_decode_text(response.content))


def _decode_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _normalize_message_content(content: object) -> str:
    if isinstance(content, dict):
        if "choices" in content:
            choice = (content.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            return _normalize_message_content(message.get("content"))
        if "output_text" in content and isinstance(content.get("output_text"), str):
            return str(content.get("output_text"))
        if "output" in content and isinstance(content.get("output"), list):
            parts: List[str] = []
            for item in content.get("output", []):
                if not isinstance(item, dict):
                    continue
                text = _normalize_message_content(item.get("content"))
                if text:
                    parts.append(text)
            if parts:
                return "".join(parts)
        content_items = content.get("content")
        if isinstance(content_items, list):
            text = _normalize_message_content(content_items)
            if text:
                return text
        message = content.get("message")
        if isinstance(message, dict):
            text = _normalize_message_content(message.get("content"))
            if text:
                return text
        candidates = content.get("candidates")
        if isinstance(candidates, list):
            parts: List[str] = []
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                candidate_content = candidate.get("content") or {}
                text = _normalize_message_content(candidate_content)
                if text:
                    parts.append(text)
            if parts:
                return "".join(parts)
        parts = content.get("parts")
        if isinstance(parts, list):
            return _normalize_message_content(parts)
        text = content.get("text")
        if isinstance(text, str):
            return text
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
                inner_parts = item.get("parts")
                if isinstance(inner_parts, list):
                    nested = _normalize_message_content(inner_parts)
                    if nested:
                        parts.append(nested)
        return "".join(parts)
    if isinstance(content, str):
        return content
    return ""


def _extract_gemini_chunk_text(payload: object) -> str:
    text = _normalize_message_content(payload)
    return text if isinstance(text, str) else ""


def _dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_gemini_model_path(model: str) -> str:
    model = model.strip()
    if model.startswith("models/"):
        return model
    return f"models/{model}"


def _normalize_provider_type(provider_type: str, base_url: str = "") -> str:
    normalized = provider_type.strip().lower()
    if normalized in {"openai", "openai_responses"}:
        return "openai"
    if normalized in _OPENAI_COMPATIBLE_ALIASES:
        return "openai_compatible"
    if normalized == "ollama":
        return "ollama"
    if normalized in {"anthropic", "claude"}:
        return "anthropic"
    if normalized in {"gemini", "google", "google_ai_studio", "generativelanguage"}:
        return "gemini"

    host = urlparse(base_url.strip()).netloc.lower()
    if host == "api.openai.com":
        return "openai"
    if "anthropic.com" in host:
        return "anthropic"
    if "generativelanguage.googleapis.com" in host:
        return "gemini"
    if host in {"localhost:11434", "127.0.0.1:11434"}:
        return "ollama"
    return "openai_compatible"


def _build_url(base_url: str, suffix: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        return suffix
    parsed = urlparse(normalized)
    if parsed.path.endswith(suffix):
        return normalized
    for known_suffix in _KNOWN_ENDPOINT_SUFFIXES:
        if parsed.path.endswith(known_suffix):
            normalized = normalized[: -len(known_suffix)]
            break
    return normalized + suffix


def _describe_models_url(profile: LlmProfile, provider_type: str) -> str:
    if provider_type == "ollama":
        return _build_url(profile.base_url, "/api/tags")
    return _build_url(profile.base_url, "/models")


def _get_provider_adapter(profile: LlmProfile) -> ProviderAdapter:
    provider_type = _normalize_provider_type(profile.provider_type, profile.base_url)
    adapter = _PROVIDER_ADAPTERS.get(provider_type)
    if adapter is None:
        raise RuntimeError(f"Unsupported provider type: {provider_type}")
    return adapter


_PROVIDER_ADAPTERS: dict[str, ProviderAdapter] = {
    "openai": ProviderAdapter(
        provider_type="openai",
        label="OpenAI endpoint",
        complete_fn=_complete_openai_responses,
        stream_fn=_stream_openai_responses,
        list_models_fn=_list_openai_models,
        requires_api_key=True,
    ),
    "openai_compatible": ProviderAdapter(
        provider_type="openai_compatible",
        label="OpenAI-compatible endpoint",
        complete_fn=_complete_openai_compatible_chat,
        stream_fn=_stream_openai_compatible_chat,
        list_models_fn=_list_openai_models,
        requires_api_key=False,
    ),
    "ollama": ProviderAdapter(
        provider_type="ollama",
        label="Ollama endpoint",
        complete_fn=_complete_ollama_chat,
        stream_fn=_stream_ollama_chat,
        list_models_fn=_list_ollama_models,
        requires_api_key=False,
    ),
    "anthropic": ProviderAdapter(
        provider_type="anthropic",
        label="Anthropic endpoint",
        complete_fn=_complete_anthropic_messages,
        stream_fn=_stream_anthropic_messages,
        list_models_fn=_list_anthropic_models,
        requires_api_key=True,
    ),
    "gemini": ProviderAdapter(
        provider_type="gemini",
        label="Gemini endpoint",
        complete_fn=_complete_gemini_generate_content,
        stream_fn=_stream_gemini_generate_content,
        list_models_fn=_list_gemini_models,
        requires_api_key=True,
    ),
}
