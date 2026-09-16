import tempfile
import unittest
from pathlib import Path

from coco.state import StateService


class StateMemoryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="memory_bridge_"))
        self.service = StateService(self.root / "state.sqlite3")

    def tearDown(self):
        self.service.close()

    def test_stable_statement_is_active_and_candidate_is_not(self):
        self.service.message("user", "我喜欢简短的回复")
        self.service.message("user", "也许我明天会喜欢另一种风格")
        rows = self.service.memories()
        statuses = {row["content_text"]: row["status"] for row in rows}
        self.assertEqual(statuses["我喜欢简短的回复"], "active")
        # Ambiguous/speculative language is conservatively not persisted.
        self.assertNotIn("也许我明天会喜欢另一种风格", statuses)

    def test_explicit_note_is_not_injected_twice_as_memory(self):
        self.service.message("user", "记住：我喜欢简洁标题")
        self.service.remember("我喜欢简洁标题")
        _, notes = self.service.model_context("简洁标题")
        memory_notes = [item for item in notes if "本地长期记忆" in str(item.get("content", ""))]
        self.assertEqual(memory_notes, [])

    def test_memory_correction_retrieval_and_deletion(self):
        self.service.message("user", "我喜欢简短的回复")
        original = next(
            item for item in self.service.memories()
            if item["content_text"] == "我喜欢简短的回复"
        )
        replacement = self.service.correct_memory(
            original["memory_id"], "我喜欢详细但清楚的回复"
        )
        self.assertEqual(replacement.status, "active")
        _, notes = self.service.model_context("详细 清楚")
        rendered = "\n".join(str(item.get("content", "")) for item in notes)
        self.assertIn("我喜欢详细但清楚的回复", rendered)
        self.assertNotIn("我喜欢简短的回复", rendered)

        self.service.delete_memory(replacement.memory_id, reason="test delete")
        _, notes = self.service.model_context("详细 清楚")
        rendered = "\n".join(str(item.get("content", "")) for item in notes)
        self.assertNotIn("我喜欢详细但清楚的回复", rendered)

    def test_compaction_is_two_phase_and_keeps_recent_messages(self):
        for index in range(6):
            self.service.message("user", f"目标 {index} " + ("u" * 1600))
            self.service.message("assistant", f"回复 {index} " + ("a" * 1600))
        plan = self.service.compaction_plan(char_budget=12000, recent_turns=2, min_compact_chars=6000)
        self.assertIsNotNone(plan)
        result = self.service.commit_compaction(plan, "Intent: 保留用户目标\nPending tasks: 继续处理")
        self.assertTrue(result.committed)
        history, notes = self.service.model_context("目标", history_limit=4)
        self.assertEqual(len(history), 4)
        self.assertTrue(any("滚动对话摘要" in str(item.get("content", "")) for item in notes))
        # A failed/edited source must not erase the durable original rows.
        self.service.message("user", "新增用户更正")
        self.assertGreaterEqual(len(self.service.history(20)), 13)


if __name__ == "__main__":
    unittest.main()
