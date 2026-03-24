from __future__ import annotations

import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from stm32_agent.desktop.chat_threads import create_chat_thread, save_chat_thread_store
from stm32_agent.desktop.chat_page import ChatPage
from stm32_agent.graph.workflow import GraphStepResult
from stm32_agent.llm_config import LlmProfile


class ChatPageThreadStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_pending_proposal_state_restores_after_thread_switch(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            page = ChatPage()
            page.chat_threads_path = os.path.join(tmp_dir, "threads.json")
            first = create_chat_thread(title="线程一")
            second = create_chat_thread(title="线程二")
            page.chat_threads = [first, second]
            page.thread_graph_sessions.clear()
            page.thread_graph_thread_ids.clear()
            page._refresh_thread_list(select_thread_id=first.thread_id)
            page._select_thread(first.thread_id, refresh_list=False)

            page.pending_request_payload = {"target": {"chip": "stm32f103c8t6"}}
            page.pending_plan_summary = {"modules": [{"key": "led"}]}
            page.pending_change_preview = ["新增 LED 模块"]
            page.pending_file_change_preview = [{"status": "create", "relative_path": "Core/Src/main.c"}]
            page.pending_output_dir = r"D:\work\out1"
            page.pending_mode = "create"
            page.pending_graph_session = object()
            page.pending_graph_thread_id = "graph-thread-1"
            page.proposal_view.setPlainText("线程一待确认方案")
            page.proposal_status_label.set_status("等待确认", "warning")
            page.proposal_feedback_input.setPlainText("I2C 固定到 PB6/PB7")
            page.confirm_proposal_button.setText("确认方案并开始生成")
            page.confirm_proposal_button.setEnabled(True)
            page.revise_proposal_button.setEnabled(True)
            page.clear_proposal_button.setEnabled(True)
            page._persist_current_thread()

            page._select_thread(second.thread_id)
            self.assertEqual(page.pending_request_payload, {})
            self.assertEqual(page.proposal_view.toPlainText(), page._default_proposal_text())
            self.assertFalse(page.confirm_proposal_button.isEnabled())

            page._select_thread(first.thread_id)
            self.assertEqual(page.proposal_view.toPlainText(), "线程一待确认方案")
            self.assertEqual(page.proposal_feedback_input.toPlainText(), "I2C 固定到 PB6/PB7")
            self.assertEqual(page.pending_request_payload["target"]["chip"], "stm32f103c8t6")
            self.assertEqual(page.pending_change_preview, ["新增 LED 模块"])
            self.assertTrue(page.confirm_proposal_button.isEnabled())
            self.assertEqual(page.pending_graph_thread_id, "graph-thread-1")
            self.assertIsNotNone(page.pending_graph_session)

            page.deleteLater()

    def test_load_chat_threads_restores_last_selected_thread(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            page = ChatPage()
            page.chat_threads_path = os.path.join(tmp_dir, "threads.json")
            first = create_chat_thread(title="线程一", project_dir=r"D:\work\one")
            second = create_chat_thread(title="线程二", project_dir=r"D:\work\two")
            second.display_messages = [{"role": "assistant", "text": "hello"}]
            save_chat_thread_store([first, second], current_thread_id=second.thread_id, path=page.chat_threads_path)

            page._load_chat_threads()

            self.assertEqual(page.current_thread_id, second.thread_id)
            self.assertEqual(page.active_project_dir, r"D:\work\two")
            self.assertEqual(page.thread_list.currentItem().data(0x0100), second.thread_id)
            page.deleteLater()

    def test_load_chat_threads_restores_persisted_graph_runtime(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            page = ChatPage()
            page.chat_threads_path = os.path.join(tmp_dir, "threads.json")
            page.profiles = [_dummy_profile()]
            page.default_profile_id = page.profiles[0].profile_id
            page.profile_combo.clear()
            page.profile_combo.addItem(page.profiles[0].name, page.profiles[0].profile_id)
            page.profile_combo.setCurrentIndex(0)

            thread = create_chat_thread(title="绾跨▼涓€", project_dir=r"D:\work\demo")
            thread.proposal_state = {
                "proposal_text": "绛夊緟纭鐨勬柟妗?",
                "proposal_status_text": "绛夊緟纭",
                "proposal_status_kind": "warning",
                "request_payload": {"target": {"chip": "stm32f103c8t6"}},
                "plan_summary": {"modules": [{"key": "led"}]},
                "confirm_enabled": True,
                "revise_enabled": True,
                "clear_enabled": True,
                "graph_thread_id": "persisted-graph-thread",
                "graph_profile_id": page.profiles[0].profile_id,
                "graph_runtime_validation_enabled": True,
            }
            save_chat_thread_store([thread], current_thread_id=thread.thread_id, path=page.chat_threads_path)

            with patch("stm32_agent.desktop.chat_page.STM32ProjectGraphSession", _FakeGraphSession):
                page._load_chat_threads()

            self.assertEqual(page.pending_graph_thread_id, "persisted-graph-thread")
            self.assertIsInstance(page.pending_graph_session, _FakeGraphSession)
            self.assertTrue(page.confirm_proposal_button.isEnabled())
            self.assertTrue(page.chat_renode_checkbox.isChecked())
            page.deleteLater()

    def test_negotiation_proposal_populates_feedback_and_option_buttons(self) -> None:
        page = ChatPage()
        result = GraphStepResult(
            thread_id="thread-1",
            values={
                "proposal_text": "规划失败后的折中方案",
                "request_payload": {"chip": "STM32F103C8T6"},
                "plan_result": {"modules": []},
                "review_kind": "negotiate",
                "negotiation_options": [
                    {
                        "id": "chip_only",
                        "title": "切到 chip_only",
                        "summary": "先按最小系统重算",
                        "feedback": "请改成 board=chip_only，基于芯片重新规划。",
                    },
                    {
                        "id": "auto_board",
                        "title": "自动选板卡",
                        "summary": "保留芯片，自动挑兼容板卡",
                        "feedback": "请保留芯片，自动选择兼容板卡后重新规划。",
                    },
                ],
                "change_preview": [],
                "file_change_preview": [],
                "project_dir": r"D:\work\demo",
            },
            next_nodes=("review",),
            interrupts=[{"id": "proposal-review", "value": {"approved": False}}],
            raw_output={},
        )

        page._on_proposal_workflow_finished(result)

        self.assertEqual(page.pending_review_kind, "negotiate")
        self.assertEqual(len(page.pending_negotiation_options), 2)
        self.assertEqual(page.confirm_proposal_button.text(), "采纳当前方案并重算")
        self.assertIn("board=chip_only", page.proposal_feedback_input.toPlainText())
        self.assertEqual(len(page.negotiation_option_buttons), 2)
        page.negotiation_option_buttons[1].click()
        self.assertIn("自动选择兼容板卡", page.proposal_feedback_input.toPlainText())
        page.deleteLater()

    def test_build_model_context_messages_uses_summary_plus_recent_window(self) -> None:
        page = ChatPage()
        page.chat_threads = [create_chat_thread(title="线程一", project_dir=r"D:\work\demo")]
        page.current_thread_id = page.chat_threads[0].thread_id
        page.active_project_dir = r"D:\work\demo"
        page.max_context_messages = 4
        page.conversation = [
            {"role": "user", "content": "需求 1"},
            {"role": "assistant", "content": "答复 1"},
            {"role": "user", "content": "需求 2"},
            {"role": "assistant", "content": "答复 2"},
            {"role": "user", "content": "需求 3"},
            {"role": "assistant", "content": "答复 3"},
        ]
        page.display_conversation = [
            {"role": "user", "text": "需求 1"},
            {"role": "assistant", "text": "答复 1"},
            {"role": "user", "text": "需求 2"},
            {"role": "assistant", "text": "答复 2"},
            {"role": "user", "text": "需求 3"},
            {"role": "assistant", "text": "答复 3"},
        ]
        page._persist_current_thread(refresh_list=False)

        messages = page._build_model_context_messages("system prompt")

        self.assertEqual(messages[0]["content"], "system prompt")
        self.assertIn("当前工程线程摘要如下", messages[1]["content"])
        self.assertEqual(len(messages), 6)
        self.assertEqual(messages[-4]["content"], "需求 2")
        self.assertEqual(messages[-1]["content"], "答复 3")
        page.deleteLater()

    def test_current_thread_followup_context_excludes_latest_user_message(self) -> None:
        page = ChatPage()
        thread = create_chat_thread(title="线程一", project_dir=r"D:\work\demo")
        thread.display_messages = [
            {"role": "user", "text": "先做一个 OLED 菜单"},
            {"role": "assistant", "text": "好的，我先规划 I2C 和显示模块"},
            {"role": "user", "text": "再加 EEPROM 参数保存"},
        ]
        thread.proposal_state = {
            "proposal_status_text": "等待确认",
            "proposal_status_kind": "warning",
            "confirm_enabled": True,
        }
        page.chat_threads = [thread]
        page.current_thread_id = thread.thread_id

        context = page._current_thread_followup_context(exclude_latest_user_message=True)

        self.assertIn("Existing desktop project thread summary:", context)
        self.assertIn("User: 先做一个 OLED 菜单", context)
        self.assertIn("Assistant: 好的，我先规划 I2C 和显示模块", context)
        self.assertNotIn("再加 EEPROM 参数保存", context)
        page.deleteLater()

    def test_engineering_state_restores_after_thread_switch(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            page = ChatPage()
            page.chat_threads_path = os.path.join(tmp_dir, "threads.json")
            first = create_chat_thread(title="线程一")
            second = create_chat_thread(title="线程二")
            page.chat_threads = [first, second]
            page._refresh_thread_list(select_thread_id=first.thread_id)
            page._select_thread(first.thread_id, refresh_list=False)

            page.thread_engineering_state = {
                "status_text": "编译通过",
                "status_kind": "success",
                "action": "build",
            }
            page._persist_current_thread()

            page._select_thread(second.thread_id)
            self.assertEqual(page.thread_engineering_state, {})

            page._select_thread(first.thread_id)
            self.assertEqual(page.thread_engineering_state["status_text"], "编译通过")
            self.assertEqual(page.thread_engineering_state["action"], "build")
            page.deleteLater()

    def test_thread_context_panel_shows_summary_and_engineering_state(self) -> None:
        page = ChatPage()
        thread = create_chat_thread(title="线程一", project_dir=r"D:\work\demo")
        thread.display_messages = [
            {"role": "user", "text": "做一个带 OLED 的工程"},
            {"role": "assistant", "text": "好的，先规划 I2C 和显示模块"},
        ]
        thread.proposal_state = {
            "proposal_status_text": "等待确认",
            "proposal_status_kind": "warning",
            "confirm_enabled": True,
            "request_payload": {"target": {"chip": "stm32f103c8t6"}},
        }
        thread.engineering_state = {
            "status_text": "编译通过",
            "status_kind": "success",
            "action": "confirm_generation",
            "build_summary": ["0 Error(s), 0 Warning(s)"],
            "timeline": [
                {"timestamp": "03-18 10:00", "stage": "提案", "status": "待确认", "detail": "方案已整理完成"},
                {"timestamp": "03-18 10:01", "stage": "编译", "status": "通过", "detail": "0 Error(s), 0 Warning(s)"},
            ],
        }
        page.chat_threads = [thread]
        page._refresh_thread_list(select_thread_id=thread.thread_id)
        page._select_thread(thread.thread_id, refresh_list=False)

        self.assertIn("编译通过", page.thread_context_caption.text())
        context_text = page.thread_context_view.toPlainText()
        self.assertIn("当前工程: demo", context_text)
        self.assertIn("工程状态: 编译通过", context_text)
        self.assertIn("最近构建:", context_text)
        timeline_text = page.thread_timeline_view.toPlainText()
        self.assertIn("03-18 10:00 · 提案 · 待确认", timeline_text)
        self.assertIn("03-18 10:01 · 编译 · 通过", timeline_text)
        page.deleteLater()


    def test_ui_state_round_trip_restores_collapsed_panels_and_active_tab(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            settings = QSettings(os.path.join(tmp_dir, "desktop_state.ini"), QSettings.IniFormat)
            page = ChatPage()
            page.sidebar_tabs.setCurrentIndex(2)
            page.workspace_splitter.setSizes([860, 540])
            page.context_splitter.setSizes([190, 120])
            page.proposal_splitter.setSizes([210, 110])
            page.chat_project_explorer.splitter.setSizes([230, 140])
            page._set_thread_panel_collapsed(True)
            page._set_sidebar_panel_collapsed(False)
            page.save_ui_state(settings)
            settings.sync()
            page.deleteLater()

            restored = ChatPage()
            restored.load_ui_state(settings)

            self.assertTrue(restored.thread_panel_collapsed)
            self.assertFalse(restored.sidebar_panel_collapsed)
            self.assertEqual(restored.sidebar_tabs.currentIndex(), 2)
            self.assertTrue(all(size > 0 for size in restored.chat_project_explorer.splitter.sizes()))
            restored.deleteLater()

def _dummy_profile() -> LlmProfile:
    return LlmProfile(
        profile_id="test-profile",
        name="Test Profile",
        provider_type="openai_compatible",
        base_url="http://localhost",
        api_key="test",
        model="test-model",
        system_prompt="",
        temperature=0.0,
        enabled=True,
    )


class _FakeGraphSession:
    def __init__(self, runtime):
        self.runtime = runtime

    def get_state(self, thread_id: str) -> GraphStepResult:
        if thread_id == "persisted-graph-thread":
            return GraphStepResult(
                thread_id=thread_id,
                values={"proposal_text": "restored"},
                next_nodes=(),
                interrupts=[{"id": "proposal-review", "value": {"approved": False}}],
                raw_output={},
            )
        return GraphStepResult(
            thread_id=thread_id,
            values={},
            next_nodes=(),
            interrupts=[],
            raw_output={},
        )


if __name__ == "__main__":
    unittest.main()
