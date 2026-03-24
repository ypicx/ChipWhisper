from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stm32_agent.desktop.chat_threads import (
    DEFAULT_THREAD_TITLE,
    build_thread_context_summary,
    build_thread_followup_context,
    create_chat_thread,
    derive_thread_title,
    derive_thread_status,
    format_thread_timeline,
    format_thread_list_label,
    format_thread_timestamp,
    load_chat_thread_store,
    load_chat_threads,
    sanitize_model_messages_for_storage,
    save_chat_thread_store,
    save_chat_threads,
    summarize_thread,
)


class ChatThreadPersistenceTests(unittest.TestCase):
    def test_derive_thread_title_prefers_project_name_then_first_user_message(self) -> None:
        self.assertEqual(
            derive_thread_title([], project_dir=r"D:\work\demo_project"),
            "demo_project",
        )
        self.assertEqual(
            derive_thread_title(
                [
                    {"role": "assistant", "text": "hello"},
                    {"role": "user", "text": "做一个 STM32 流水灯工程\n带按键"},
                ]
            ),
            "做一个 STM32 流水灯工程",
        )
        self.assertEqual(derive_thread_title([], project_dir=""), DEFAULT_THREAD_TITLE)

    def test_save_and_load_chat_threads_round_trip(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "threads.json"
            thread = create_chat_thread(project_dir=r"D:\work\demo_project")
            thread.model_messages.append({"role": "user", "content": "hello"})
            thread.display_messages.append({"role": "user", "text": "hello"})
            thread.proposal_state = {"proposal_text": "待确认方案", "confirm_enabled": True}
            thread.engineering_state = {"status_text": "编译通过", "status_kind": "success"}
            thread.summary_text = "当前工程: demo_project"
            save_chat_threads([thread], path)

            loaded = load_chat_threads(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].project_dir, r"D:\work\demo_project")
        self.assertEqual(loaded[0].model_messages[0]["content"], "hello")
        self.assertEqual(loaded[0].display_messages[0]["text"], "hello")
        self.assertEqual(loaded[0].proposal_state["proposal_text"], "待确认方案")
        self.assertEqual(loaded[0].engineering_state["status_text"], "编译通过")
        self.assertEqual(loaded[0].summary_text, "当前工程: demo_project")

    def test_sanitize_model_messages_for_storage_strips_data_urls_and_keeps_recent_slice(self) -> None:
        messages = [
            {"role": "assistant", "content": f"message-{index}"}
            for index in range(30)
        ]
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "请参考这张图片继续修改工程"},
                    {"type": "input_image", "image_url": "data:image/png;base64," + ("A" * 4096)},
                ],
            }
        )

        sanitized = sanitize_model_messages_for_storage(messages)

        self.assertEqual(len(sanitized), 24)
        self.assertEqual(sanitized[0]["content"], "message-7")
        self.assertIsInstance(sanitized[-1]["content"], str)
        self.assertIn("请参考这张图片继续修改工程", sanitized[-1]["content"])
        self.assertIn("图片附件已省略", sanitized[-1]["content"])
        self.assertNotIn("data:image/png;base64", sanitized[-1]["content"])

    def test_save_and_load_chat_thread_store_preserves_selected_thread(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "threads.json"
            first = create_chat_thread(title="线程一")
            second = create_chat_thread(title="线程二")
            save_chat_thread_store([first, second], current_thread_id=second.thread_id, path=path)
            loaded, current_thread_id = load_chat_thread_store(path)

        self.assertEqual(len(loaded), 2)
        self.assertEqual(current_thread_id, second.thread_id)

    def test_summarize_thread_uses_project_name_or_message_count(self) -> None:
        thread = create_chat_thread(project_dir=r"D:\repo\demo")
        self.assertEqual(summarize_thread(thread), "demo")
        thread.project_dir = ""
        thread.display_messages = [{"role": "user", "text": "hi"}]
        self.assertEqual(summarize_thread(thread), "1 条消息")

    def test_derive_thread_status_prefers_pending_proposal_then_project_context(self) -> None:
        thread = create_chat_thread(project_dir=r"D:\repo\demo")
        thread.proposal_state = {
            "proposal_status_text": "等待确认",
            "proposal_status_kind": "warning",
            "confirm_enabled": True,
        }
        self.assertEqual(derive_thread_status(thread), ("等待确认", "warning"))
        thread.proposal_state = {}
        thread.engineering_state = {"status_text": "编译失败", "status_kind": "error"}
        self.assertEqual(derive_thread_status(thread), ("编译失败", "error"))
        thread.engineering_state = {}
        thread.display_messages = [{"role": "assistant", "text": "hello"}]
        self.assertEqual(derive_thread_status(thread), ("进行中", "success"))

    def test_format_thread_list_label_contains_status_and_summary(self) -> None:
        thread = create_chat_thread(project_dir=r"D:\repo\demo")
        thread.proposal_state = {"proposal_status_text": "已生成", "proposal_status_kind": "success"}
        thread.updated_at = "2026-03-18T12:34:56"
        label = format_thread_list_label(thread)
        self.assertIn("已生成", label)
        self.assertIn("demo", label)
        self.assertIn("03-18 12:34", label)

    def test_format_thread_timestamp_formats_iso_string(self) -> None:
        thread = create_chat_thread()
        thread.updated_at = "2026-03-18T08:09:10"
        self.assertEqual(format_thread_timestamp(thread), "03-18 08:09")

    def test_build_thread_context_summary_includes_project_status_and_recent_user_intents(self) -> None:
        thread = create_chat_thread(project_dir=r"D:\repo\demo")
        thread.display_messages = [
            {"role": "user", "text": "做一个带 OLED 的工程"},
            {"role": "assistant", "text": "好的"},
            {"role": "user", "text": "再加 EEPROM 参数保存"},
        ]
        thread.proposal_state = {
            "proposal_status_text": "等待确认",
            "proposal_status_kind": "warning",
            "confirm_enabled": True,
            "request_payload": {"target": {"chip": "stm32f103c8t6", "board": "blue_pill_f103c8"}},
            "plan_summary": {"modules": [{"key": "lcd1602_i2c"}, {"key": "at24c32_i2c"}]},
            "change_preview": ["新增 EEPROM 模块", "保留原 OLED 显示"],
        }
        thread.engineering_state = {
            "status_text": "编译通过",
            "status_kind": "success",
            "action": "confirm_generation",
            "build_summary": ["0 Error(s), 0 Warning(s)"],
            "simulate_summary": "通过",
            "repair_count": 1,
        }
        summary = build_thread_context_summary(thread)
        self.assertIn("当前工程: demo", summary)
        self.assertIn("线程状态: 等待确认", summary)
        self.assertIn("目标芯片: stm32f103c8t6", summary)
        self.assertIn("工程状态: 编译通过", summary)
        self.assertIn("最近动作: confirm_generation", summary)
        self.assertIn("最近构建:", summary)
        self.assertIn("最近仿真: 通过", summary)
        self.assertIn("自动修复: 1 次", summary)
        self.assertIn("当前模块: lcd1602_i2c, at24c32_i2c", summary)
        self.assertIn("待应用变更:", summary)
        self.assertIn("做一个带 OLED 的工程", summary)
        self.assertIn("好的", summary)

    def test_build_thread_followup_context_uses_summary_and_recent_messages(self) -> None:
        thread = create_chat_thread(project_dir=r"D:\repo\demo")
        thread.display_messages = [
            {"role": "user", "text": "先做一个 OLED 菜单"},
            {"role": "assistant", "text": "好的，我先规划 I2C 和显示模块"},
            {"role": "user", "text": "再加 EEPROM 参数保存"},
        ]
        thread.proposal_state = {
            "proposal_status_text": "等待确认",
            "proposal_status_kind": "warning",
            "confirm_enabled": True,
            "plan_summary": {"modules": [{"key": "lcd1602_i2c"}, {"key": "at24c32_i2c"}]},
        }

        context = build_thread_followup_context(thread, exclude_latest_user_message=True)

        self.assertIn("Existing desktop project thread summary:", context)
        self.assertIn("当前模块: lcd1602_i2c, at24c32_i2c", context)
        self.assertIn("Recent dialogue in this thread:", context)
        self.assertIn("User: 先做一个 OLED 菜单", context)
        self.assertIn("Assistant: 好的，我先规划 I2C 和显示模块", context)
        self.assertNotIn("再加 EEPROM 参数保存", context)

    def test_format_thread_timeline_renders_recent_engineering_events(self) -> None:
        thread = create_chat_thread(project_dir=r"D:\repo\demo")
        thread.engineering_state = {
            "timeline": [
                {"timestamp": "03-18 10:00", "stage": "提案", "status": "进行中", "detail": "开始整理方案"},
                {"timestamp": "03-18 10:01", "stage": "提案", "status": "待确认", "detail": "方案已整理完成"},
                {"timestamp": "03-18 10:02", "stage": "编译", "status": "通过", "detail": "0 Error(s), 0 Warning(s)"},
            ]
        }

        text = format_thread_timeline(thread)

        self.assertIn("03-18 10:00 · 提案 · 进行中", text)
        self.assertIn("方案已整理完成", text)
        self.assertIn("03-18 10:02 · 编译 · 通过", text)


if __name__ == "__main__":
    unittest.main()
