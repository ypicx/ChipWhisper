from __future__ import annotations

import unittest
from pathlib import Path

from stm32_agent.graph.nodes import (
    GraphRuntime,
    _build_change_preview_lines,
    _render_proposal_message,
    make_plan_node,
    route_after_plan,
    route_after_review,
)
from stm32_agent.llm_config import LlmProfile
from stm32_agent.planner import plan_request


class GraphNegotiationTests(unittest.TestCase):
    def test_route_after_plan_enters_review_for_negotiation(self) -> None:
        next_node = route_after_plan(
            {
                "request_payload": {"chip": "STM32F103C8T6"},
                "review_kind": "negotiate",
                "errors": ["Unsupported board"],
                "project_ir": {"status": {"feasible": False}},
            }
        )

        self.assertEqual(next_node, "review")

    def test_route_after_review_restarts_draft_for_negotiation_feedback(self) -> None:
        next_node = route_after_review(
            {
                "review_kind": "negotiate",
                "is_approved": True,
                "user_feedback": "请改成 board=chip_only 后重新规划。",
            }
        )

        self.assertEqual(next_node, "draft")

    def test_plan_node_builds_negotiation_options_for_unsupported_board(self) -> None:
        runtime = GraphRuntime(profile=_dummy_profile(), repo_root=Path("."))
        node = make_plan_node(runtime)

        update = node(
            {
                "request_payload": {
                    "chip": "STM32F103C8T6",
                    "board": "missing_board_profile",
                    "modules": [{"kind": "led", "name": "status_led", "options": {}}],
                },
                "user_input": "做一个最简单的 LED 工程",
                "active_project_dir": "",
                "warnings": [],
            }
        )

        self.assertEqual(update["review_kind"], "negotiate")
        self.assertTrue(update["negotiation_options"])
        self.assertIn("折中方案", update["proposal_text"])
        self.assertIn("auto_board", {item["id"] for item in update["negotiation_options"]})

    def test_proposal_message_surfaces_request_constraints(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "modules": [{"kind": "led", "name": "status_led", "options": {}}],
            "requirements": ["Power on with a visible LED startup state."],
            "assumptions": ["The LED is active high unless the board pack says otherwise."],
            "open_questions": ["Should the LED stay on after boot or keep blinking?"],
            "app_logic_goal": "Show a visible startup state over the onboard LED.",
        }
        plan = plan_request(payload)

        self.assertTrue(plan.feasible, msg=plan.errors)
        proposal = _render_proposal_message(payload, plan, "out/demo", "create", [], [])
        change_preview = _build_change_preview_lines(payload, plan, "out/demo", "create", [])

        self.assertIn("需求画像:", proposal)
        self.assertIn("业务目标:", proposal)
        self.assertIn("关键需求:", proposal)
        self.assertIn("当前假设:", proposal)
        self.assertIn("待确认问题:", proposal)
        self.assertTrue(any("业务约束" in item for item in change_preview))


def _dummy_profile() -> LlmProfile:
    return LlmProfile(
        profile_id="test",
        name="Test",
        provider_type="openai_compatible",
        base_url="http://localhost",
        api_key="test",
        model="test-model",
        system_prompt="",
        temperature=0.0,
        enabled=True,
    )


if __name__ == "__main__":
    unittest.main()
