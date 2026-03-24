from __future__ import annotations

import unittest

from stm32_agent.desktop.proposal_state import PendingProposalState


class PendingProposalStateTests(unittest.TestCase):
    def test_round_trip_normalizes_collections_and_metadata(self) -> None:
        payload = {
            "proposal_text": "待确认方案",
            "request_payload": {"chip": "STM32F103C8T6"},
            "plan_summary": {"modules": [{"key": "led"}]},
            "review_kind": "negotiate",
            "negotiation_options": [{"id": "chip_only", "feedback": "改成 chip_only"}],
            "change_preview": ["新增 led"],
            "file_change_preview": [{"status": "create", "relative_path": "Core/Src/main.c"}],
            "graph_thread_id": "graph-1",
            "graph_profile_id": "profile-1",
            "graph_runtime_validation_enabled": True,
        }

        state = PendingProposalState.from_dict(payload)
        round_trip = state.to_dict()

        self.assertEqual(round_trip["proposal_text"], "待确认方案")
        self.assertEqual(round_trip["request_payload"]["chip"], "STM32F103C8T6")
        self.assertEqual(round_trip["review_kind"], "negotiate")
        self.assertEqual(round_trip["negotiation_options"][0]["id"], "chip_only")
        self.assertTrue(round_trip["graph_runtime_validation_enabled"])

    def test_preferred_feedback_uses_first_negotiation_option_when_empty(self) -> None:
        state = PendingProposalState.from_dict(
            {
                "review_kind": "negotiate",
                "negotiation_options": [
                    {"id": "chip_only", "feedback": "请改成 chip_only"},
                    {"id": "auto_board", "feedback": "请自动选兼容板卡"},
                ],
            }
        )

        self.assertEqual(state.preferred_feedback(), "请改成 chip_only")


if __name__ == "__main__":
    unittest.main()
