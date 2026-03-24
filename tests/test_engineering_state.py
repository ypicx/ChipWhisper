from __future__ import annotations

import unittest

from stm32_agent.desktop.engineering_state import ThreadEngineeringState


class ThreadEngineeringStateTests(unittest.TestCase):
    def test_merge_updates_preserves_nonempty_values_and_clears_empty_fields(self) -> None:
        state = ThreadEngineeringState.from_dict(
            {
                "status_text": "编译通过",
                "status_kind": "success",
                "build_summary": ["0 Error(s), 0 Warning(s)"],
                "error_excerpt": ["old error"],
            }
        )

        updated = state.merge_updates(
            status_text="仿真通过",
            simulate_summary="通过",
            error_excerpt=[],
        )

        payload = updated.to_dict()
        self.assertEqual(payload["status_text"], "仿真通过")
        self.assertEqual(payload["simulate_summary"], "通过")
        self.assertNotIn("error_excerpt", payload)

    def test_append_timeline_event_keeps_recent_slice(self) -> None:
        state = ThreadEngineeringState()
        for index in range(15):
            state = state.append_timeline_event(
                stage="提案",
                status="进行中",
                detail=f"step-{index}",
                timestamp=f"03-22 10:{index:02d}",
            )

        payload = state.to_dict()
        timeline = payload["timeline"]
        self.assertEqual(len(timeline), 12)
        self.assertEqual(timeline[0]["detail"], "step-3")
        self.assertEqual(timeline[-1]["detail"], "step-14")


if __name__ == "__main__":
    unittest.main()
