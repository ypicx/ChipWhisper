from __future__ import annotations

import unittest

from stm32_agent.desktop.attachments import AttachmentDigest, compose_multimodal_user_content


class AttachmentPromptTests(unittest.TestCase):
    def test_prompt_block_uses_readable_labels(self) -> None:
        digest = AttachmentDigest(
            path="demo.txt",
            name="demo.txt",
            suffix=".txt",
            media_kind="text",
            mime_type="text/plain",
            extracted_text="hello world",
        )

        block = digest.prompt_block()

        self.assertIn("文件: demo.txt", block)
        self.assertIn("类型: text", block)
        self.assertIn("提取内容:", block)

    def test_compose_multimodal_user_content_uses_clean_attachment_manifest(self) -> None:
        digest = AttachmentDigest(
            path="demo.txt",
            name="demo.txt",
            suffix=".txt",
            media_kind="text",
            mime_type="text/plain",
            extracted_text="hello world",
        )

        content = compose_multimodal_user_content("请根据附件起草", [digest])

        self.assertIsInstance(content, list)
        text_blocks = [item["text"] for item in content if item.get("type") == "text"]
        joined = "\n".join(text_blocks)
        self.assertIn("以下是用户额外提供的需求附件", joined)
        self.assertIn("[附件 1]", joined)


if __name__ == "__main__":
    unittest.main()
