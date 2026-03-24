from __future__ import annotations

import unittest

from stm32_agent.llm_config import _profile_from_payload


class LlmConfigTests(unittest.TestCase):
    def test_profile_from_payload_normalizes_gemini_aliases(self) -> None:
        profile = _profile_from_payload(
            {
                "name": "Gemini alias",
                "provider_type": "google",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
            }
        )

        self.assertEqual(profile.provider_type, "gemini")

    def test_profile_from_payload_normalizes_openai_compatible_aliases(self) -> None:
        profile = _profile_from_payload(
            {
                "name": "DeepSeek alias",
                "provider_type": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
            }
        )

        self.assertEqual(profile.provider_type, "openai_compatible")


if __name__ == "__main__":
    unittest.main()
