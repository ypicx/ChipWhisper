from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from stm32_agent.desktop.llm_client import (
    _normalize_provider_type,
    complete_chat_completion,
    get_supported_provider_types,
    stream_chat_completion,
    test_profile_connection,
)
from stm32_agent.llm_config import LlmProfile


class _FakeResponse:
    def __init__(
        self,
        payload: object | None = None,
        lines: list[bytes] | None = None,
        status_code: int = 200,
    ) -> None:
        if payload is None:
            self.content = b"{}"
        else:
            self.content = json.dumps(payload).encode("utf-8")
        self._lines = list(lines or [])
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
        return None

    def iter_lines(self, decode_unicode: bool = False):  # noqa: ANN001
        return iter(self._lines)

    def close(self) -> None:
        return None

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False


def _profile(
    provider_type: str,
    base_url: str,
    api_key: str = "test-key",
    model: str = "test-model",
) -> LlmProfile:
    return LlmProfile(
        profile_id="test-profile",
        name="test",
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt="",
        temperature=0.2,
        enabled=True,
    )


class LlmClientProviderTests(unittest.TestCase):
    def test_supported_provider_types_include_anthropic_and_gemini(self) -> None:
        providers = get_supported_provider_types()

        self.assertIn("anthropic", providers)
        self.assertIn("gemini", providers)

    def test_normalize_provider_type_recognizes_aliases_and_hosts(self) -> None:
        self.assertEqual(_normalize_provider_type("claude"), "anthropic")
        self.assertEqual(_normalize_provider_type("google"), "gemini")
        self.assertEqual(_normalize_provider_type("deepseek"), "openai_compatible")
        self.assertEqual(
            _normalize_provider_type("", "https://api.anthropic.com/v1"),
            "anthropic",
        )
        self.assertEqual(
            _normalize_provider_type("", "https://generativelanguage.googleapis.com/v1beta"),
            "gemini",
        )

    @patch("stm32_agent.desktop.llm_client.requests.post")
    def test_complete_anthropic_messages_returns_text(self, mock_post) -> None:
        mock_post.return_value = _FakeResponse({"content": [{"type": "text", "text": "hello"}]})

        result = complete_chat_completion(
            _profile("anthropic", "https://api.anthropic.com/v1", model="claude-3-5-sonnet-latest"),
            [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "Say hi."},
            ],
        )

        self.assertEqual(result, "hello")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["x-api-key"], "test-key")
        self.assertEqual(kwargs["json"]["system"], "You are concise.")
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "user")

    @patch("stm32_agent.desktop.llm_client.requests.post")
    def test_stream_anthropic_messages_emits_text_deltas(self, mock_post) -> None:
        mock_post.return_value = _FakeResponse(
            lines=[
                b'data: {"type":"content_block_delta","delta":{"text":"hel"}}',
                b'data: {"type":"content_block_delta","delta":{"text":"lo"}}',
            ]
        )
        chunks: list[str] = []

        stream_chat_completion(
            _profile("anthropic", "https://api.anthropic.com/v1", model="claude-3-5-sonnet-latest"),
            [{"role": "user", "content": "Say hello."}],
            chunks.append,
        )

        self.assertEqual(chunks, ["hel", "lo"])

    @patch("stm32_agent.desktop.llm_client.requests.post")
    def test_complete_gemini_returns_text(self, mock_post) -> None:
        mock_post.return_value = _FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "ok"}],
                        }
                    }
                ]
            }
        )

        result = complete_chat_completion(
            _profile("gemini", "https://generativelanguage.googleapis.com/v1beta", model="gemini-2.0-flash"),
            [
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "ping"},
            ],
        )

        self.assertEqual(result, "ok")
        args, kwargs = mock_post.call_args
        self.assertTrue(str(args[0]).endswith("/models/gemini-2.0-flash:generateContent"))
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(kwargs["json"]["system_instruction"]["parts"][0]["text"], "Be helpful.")

    @patch("stm32_agent.desktop.llm_client.requests.post")
    def test_stream_gemini_emits_sse_chunks(self, mock_post) -> None:
        mock_post.return_value = _FakeResponse(
            lines=[
                b'data: {"candidates":[{"content":{"parts":[{"text":"he"}]}}]}',
                b'data: {"candidates":[{"content":{"parts":[{"text":"llo"}]}}]}',
            ]
        )
        chunks: list[str] = []

        stream_chat_completion(
            _profile("gemini", "https://generativelanguage.googleapis.com/v1beta", model="gemini-2.0-flash"),
            [{"role": "user", "content": "Say hello."}],
            chunks.append,
        )

        self.assertEqual(chunks, ["he", "llo"])
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["params"], {"alt": "sse"})

    @patch("stm32_agent.desktop.llm_client.requests.post")
    def test_gemini_complete_retries_with_query_key_on_auth_failure(self, mock_post) -> None:
        mock_post.side_effect = [
            _FakeResponse(status_code=403),
            _FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": "fallback-ok"}],
                            }
                        }
                    ]
                }
            ),
        ]

        result = complete_chat_completion(
            _profile("gemini", "https://generativelanguage.googleapis.com/v1beta", model="gemini-2.0-flash"),
            [{"role": "user", "content": "ping"}],
        )

        self.assertEqual(result, "fallback-ok")
        self.assertEqual(mock_post.call_count, 2)
        _, retry_kwargs = mock_post.call_args
        self.assertEqual(retry_kwargs["params"], {"key": "test-key"})
        self.assertNotIn("x-goog-api-key", retry_kwargs["headers"])

    @patch("stm32_agent.desktop.llm_client.requests.get")
    def test_gemini_model_discovery_retries_with_query_key_on_auth_failure(self, mock_get) -> None:
        mock_get.side_effect = [
            _FakeResponse(status_code=401),
            _FakeResponse({"models": [{"name": "models/gemini-2.0-flash"}]}),
        ]

        ok, detail = test_profile_connection(
            _profile(
                "gemini",
                "https://generativelanguage.googleapis.com/v1beta",
                model="",
            )
        )

        self.assertTrue(ok)
        self.assertIn("models/gemini-2.0-flash", detail)
        self.assertEqual(mock_get.call_count, 2)
        _, retry_kwargs = mock_get.call_args
        self.assertEqual(retry_kwargs["params"], {"key": "test-key"})

    @patch("stm32_agent.desktop.llm_client.requests.get")
    def test_openai_compatible_connection_allows_empty_api_key(self, mock_get) -> None:
        mock_get.return_value = _FakeResponse({"data": [{"id": "deepseek-chat"}]})

        ok, detail = test_profile_connection(
            _profile(
                "openai_compatible",
                "https://api.deepseek.com/v1",
                api_key="",
                model="",
            )
        )

        self.assertTrue(ok)
        self.assertIn("deepseek-chat", detail)


if __name__ == "__main__":
    unittest.main()
