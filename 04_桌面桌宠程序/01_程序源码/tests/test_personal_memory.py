import sqlite3
import tempfile
import unittest
from pathlib import Path

from coco.personal_memory import (
    ConversationMessage,
    MemoryCandidate,
    add_candidate,
    commit_compaction,
    compact_session,
    confirm_memory,
    correct_memory,
    delete_memory,
    ensure_schema,
    extract_candidates,
    latest_summary,
    list_memories,
    memory_revisions,
    prepare_compaction,
    render_compacted_context,
    search_relevant,
)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="personal_memory_"))
        self.db = sqlite3.connect(self.directory / "fake.sqlite3")
        self.db.row_factory = sqlite3.Row
        ensure_schema(self.db)

    def tearDown(self):
        self.db.close()

    def test_explicit_owner_extraction_is_conservative(self):
        self.assertEqual(extract_candidates("我喜欢安静的陪伴", message_id="m1")[0].kind, "preference")
        self.assertEqual(extract_candidates("记住：我叫小北", message_id="m2")[0].kind, "fact")
        self.assertEqual(extract_candidates("我的目标是完成一个小项目", message_id="m3")[0].kind, "goal")
        self.assertEqual(extract_candidates("这是一个假设，不是真的", message_id="m4"), [])
        self.assertEqual(extract_candidates("我喜欢安静", source_kind="model_inference", message_id="m5"), [])
        self.assertEqual(extract_candidates("记住：我的 password=super-secret", message_id="m6"), [])

    def test_candidate_confirmation_dedup_and_evidence(self):
        first = add_candidate(
            self.db,
            MemoryCandidate(kind="preference", content="喜欢安静的陪伴", message_id="m1", ingested_at="2026-01-01T00:00:00Z"),
            now="2026-01-01T00:00:00Z",
        )
        duplicate = add_candidate(
            self.db,
            MemoryCandidate(kind="preference", content="喜欢安静的陪伴", message_id="m2", source_device="robot", ingested_at="2026-01-01T00:00:01Z"),
            now="2026-01-01T00:00:01Z",
        )
        self.assertTrue(first.created)
        self.assertFalse(duplicate.created)
        self.assertEqual(first.memory_id, duplicate.memory_id)
        evidence_count = self.db.execute(
            "SELECT COUNT(*) FROM personal_memory_evidence WHERE memory_id=?", (first.memory_id,)
        ).fetchone()[0]
        self.assertEqual(evidence_count, 2)
        self.assertEqual(search_relevant(self.db, "安静"), [])
        confirmed = confirm_memory(self.db, first.memory_id, now="2026-01-01T00:00:02Z")
        self.assertTrue(confirmed["owner_confirmed"])
        self.assertEqual(search_relevant(self.db, "安静")[0]["memory_id"], first.memory_id)

    def test_correction_conflict_history_and_tombstone(self):
        original = add_candidate(
            self.db,
            MemoryCandidate(kind="fact", content="主人叫小北", owner_confirmed=True, message_id="m1"),
        )
        replacement = correct_memory(self.db, original.memory_id, "主人叫小南", now="2026-01-02T00:00:00Z")
        self.assertNotEqual(replacement.memory_id, original.memory_id)
        old = list_memories(self.db, status="superseded")[0]
        self.assertEqual(old["memory_id"], original.memory_id)
        self.assertGreaterEqual(len(memory_revisions(self.db, original.memory_id)), 2)
        deleted = delete_memory(self.db, replacement.memory_id, reason="测试撤回", now="2026-01-02T00:00:01Z")
        self.assertEqual(deleted["status"], "deleted")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM personal_memory_tombstones").fetchone()[0], 1)
        self.assertEqual(search_relevant(self.db, "小南"), [])


def _conversation_messages():
    messages = [
        {"seq": 1, "message_id": "m1", "role": "user", "content": "开始处理旧任务。" * 8},
        {"seq": 2, "message_id": "m2", "role": "assistant", "content": "我要调用工具", "tool_calls": [{"id": "call-1"}]},
        {"seq": 3, "message_id": "m3", "role": "tool", "content": "工具返回旧结果。" * 5, "tool_result_for": "call-1"},
        {"seq": 4, "message_id": "m4", "role": "assistant", "content": "旧任务完成。" * 6},
        {"seq": 5, "message_id": "m5", "role": "user", "content": "第二轮问题。" * 8},
        {"seq": 6, "message_id": "m6", "role": "assistant", "content": "第二轮回答。" * 8},
        {"seq": 7, "message_id": "m7", "role": "user", "content": "第三轮问题。" * 8},
        {"seq": 8, "message_id": "m8", "role": "assistant", "content": "第三轮回答。" * 8},
        {"seq": 9, "message_id": "m9", "role": "user", "content": "最新问题。" * 8},
        {"seq": 10, "message_id": "m10", "role": "assistant", "content": "最新回答。" * 8},
    ]
    return messages


class CompactionTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="compaction_"))
        self.db = sqlite3.connect(self.directory / "fake.sqlite3")
        self.db.row_factory = sqlite3.Row
        ensure_schema(self.db)

    def tearDown(self):
        self.db.close()

    def test_plan_keeps_recent_turns_and_balances_tool_group(self):
        messages = _conversation_messages()
        plan = prepare_compaction(messages, char_budget=500, recent_turns=2, min_compact_chars=40, conversation_id="fake")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.conversation_id, "fake")
        # The first assistant tool call and its result are both in the source,
        # and the plan ends after the assistant's final response.
        self.assertIn("m2", plan.source_message_ids)
        self.assertIn("m3", plan.source_message_ids)
        self.assertEqual(plan.source_end_seq, "6")
        self.assertIn("Pending tasks", plan.summary_input)
        self.assertIn("Tool results and decisions", plan.summary_input)

    def test_two_phase_commit_allows_appended_message_but_rejects_source_edit(self):
        messages = _conversation_messages()
        plan = prepare_compaction(messages, char_budget=500, recent_turns=2, min_compact_chars=40, conversation_id="fake")
        self.assertIsNotNone(plan)
        appended = messages + [{"seq": 11, "message_id": "m11", "role": "user", "content": "追加消息"}]
        committed = commit_compaction(self.db, plan, "Intent\n- old work\nPending tasks\n- continue", appended, now="2026-01-03T00:00:00Z")
        self.assertTrue(committed.committed)
        self.assertEqual(latest_summary(self.db, "fake")["summary_version"], 1)
        rendered = render_compacted_context(self.db, "fake", appended)
        self.assertNotIn("开始处理旧任务", rendered)
        self.assertIn("追加消息", rendered)

        edited = list(appended)
        edited[1] = dict(edited[1], content="改写了工具调用")
        next_plan = prepare_compaction(messages, char_budget=500, recent_turns=2, min_compact_chars=40, conversation_id="other")
        # The source range is not silently replaced if a worker returns late.
        if next_plan is not None:
            result = commit_compaction(self.db, next_plan, "small", edited)
            self.assertIn(result.reason, {"source_range_changed", "summary_not_smaller", "summary_parent_changed"})

    def test_failures_leave_no_summary_and_wrapper_calls_model_once(self):
        messages = _conversation_messages()
        plan = prepare_compaction(messages, char_budget=500, recent_turns=2, min_compact_chars=40, conversation_id="failed")
        self.assertIsNotNone(plan)
        failed = commit_compaction(self.db, plan, "", messages)
        self.assertFalse(failed.committed)
        self.assertIsNone(latest_summary(self.db, "failed"))
        calls = []

        def fake_summarizer(prompt):
            calls.append(prompt)
            return "short checkpoint"

        result = compact_session(
            self.db,
            messages,
            fake_summarizer,
            conversation_id="wrapped",
            char_budget=500,
            recent_turns=2,
            min_compact_chars=40,
        )
        self.assertTrue(result.committed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(latest_summary(self.db, "wrapped")["summary_version"], 1)


if __name__ == "__main__":
    unittest.main()
