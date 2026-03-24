from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from stm32_agent.graph.sqlite_checkpointer import SQLiteCheckpointer


class _CheckpointState(TypedDict, total=False):
    message: str
    approved: bool
    final_text: str


def _build_review_graph(checkpointer: SQLiteCheckpointer):
    graph = StateGraph(_CheckpointState)

    def review_node(state: _CheckpointState):
        decision = interrupt({"message": state.get("message", "")})
        return {
            "approved": bool(decision.get("approved", False)),
            "final_text": str(decision.get("note", "")).strip(),
        }

    def finish_node(state: _CheckpointState):
        note = str(state.get("final_text", "")).strip()
        message = str(state.get("message", "")).strip()
        return {"final_text": f"{message} -> {note}".strip()}

    graph.add_node("review", review_node)
    graph.add_node("finish", finish_node)
    graph.add_edge(START, "review")
    graph.add_edge("review", "finish")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)


class GraphCheckpointPersistenceTests(unittest.TestCase):
    def test_sqlite_checkpointer_restores_interrupt_state_across_sessions(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            db_path = f"{tmp_dir}/graph.sqlite3"
            first_saver = SQLiteCheckpointer(db_path)
            second_saver = None
            try:
                first_graph = _build_review_graph(first_saver)
                config = {"configurable": {"thread_id": "resume-thread"}}

                first_graph.invoke({"message": "hello"}, config)
                snapshot = first_graph.get_state(config)
                self.assertTrue(snapshot.interrupts)

                second_saver = SQLiteCheckpointer(db_path)
                second_graph = _build_review_graph(second_saver)
                result = second_graph.invoke(
                    Command(resume={"approved": True, "note": "resume ok"}),
                    config,
                )

                self.assertTrue(result["approved"])
                self.assertEqual(result["final_text"], "hello -> resume ok")
            finally:
                first_saver.close()
                if second_saver is not None:
                    second_saver.close()


if __name__ == "__main__":
    unittest.main()
