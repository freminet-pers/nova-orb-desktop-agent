import io
import json
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coco.agent_tools import AgentExecutor, TOOL_SCHEMAS, local_agent_request
from coco.assistant import ModelRequestCancelled, build_agent_payload, list_models, model_agent
from coco.state import ROOT


SCRATCH = ROOT / "10_临时文件_确认后可删除" / "coco_test"
SCRATCH.mkdir(parents=True, exist_ok=True)


class SequenceOpener:
    def __init__(self, values):
        self.values = list(values)
        self.payloads = []

    def open(self, request, timeout=0):
        if request.data:
            self.payloads.append(json.loads(request.data))
        return io.BytesIO(json.dumps(self.values.pop(0), ensure_ascii=False).encode("utf-8"))


class Catalog:
    def __init__(self):
        self.started = []

    def find(self, name):
        return [type("Entry", (), {"name": name})()]

    def launch(self, entry):
        self.started.append(entry.name)
        return f"已请求 Windows 启动「{entry.name}」。"


class AgentTests(unittest.TestCase):
    def test_schema_contains_only_named_safe_tools(self):
        names = {item["function"]["name"] for item in TOOL_SCHEMAS}
        self.assertIn("open_application", names)
        self.assertIn("type_text", names)
        self.assertIn("write_new_text_file", names)
        self.assertNotIn("run_shell", names)
        self.assertNotIn("delete_file", names)

    def test_model_tool_call_round_trip_preserves_tool_id(self):
        path = Path(tempfile.mkdtemp(prefix="agent_", dir=SCRATCH)) / "result.txt"
        first = {
            "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_write_1", "type": "function", "function": {
                    "name": "write_new_text_file",
                    "arguments": json.dumps({"path": str(path), "content": "Saturday agent"}, ensure_ascii=False),
                },
            }]}}]
        }
        second = {"choices": [{"message": {"role": "assistant", "content": "已创建并验证新文件。"}}]}
        opener = SequenceOpener([first, second])
        result = model_agent(
            {"base_url": "http://127.0.0.1:9/v1", "model": "local"}, "fake-key",
            [{"role": "user", "content": "创建一个文本文件"}], {"behavior": "idle"}, [],
            AgentExecutor(), opener=opener,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.text, "已创建并验证新文件。")
        self.assertEqual(path.read_text(encoding="utf-8"), "Saturday agent")
        self.assertEqual(opener.payloads[1]["messages"][-1]["tool_call_id"], "call_write_1")
        self.assertEqual(opener.payloads[1]["messages"][-2]["tool_calls"][0]["id"], "call_write_1")

    def test_cancel_stops_before_network(self):
        event = threading.Event()
        event.set()

        class Never:
            def open(self, *_args, **_kwargs):
                raise AssertionError("cancelled agent touched network")

        with self.assertRaises(ModelRequestCancelled):
            model_agent({"base_url": "http://127.0.0.1:9/v1", "model": "local"}, "key", [], {"behavior": "idle"}, [], AgentExecutor(), opener=Never(), cancel_event=event)

    def test_path_guard_rejects_existing_and_outside_files(self):
        executor = AgentExecutor()
        outside = Path(tempfile.gettempdir()) / "saturday-agent-secret.txt"
        result = executor.execute("write_new_text_file", {"path": str(outside), "content": "x"})
        self.assertFalse(result.ok)
        existing = SCRATCH / "existing_agent.txt"
        existing.write_text("old", encoding="utf-8")
        result = executor.execute("write_new_text_file", {"path": str(existing), "content": "new"})
        self.assertFalse(result.ok)
        self.assertEqual(existing.read_text(encoding="utf-8"), "old")

    def test_type_text_rejects_shell_browser_and_unknown_windows(self):
        executor = AgentExecutor()
        for title in ("Windows PowerShell", "Google Chrome", "Settings", "Project Editor"):
            with patch("coco.agent_tools._find_window", return_value={"title": title, "pid": 1, "hwnd": 1}):
                result = executor.execute("type_text", {"title": title, "text": "unsafe"})
            self.assertFalse(result.ok)
            self.assertIn("只允许", result.message)

    def test_type_text_requires_real_notepad_process_and_edit_control(self):
        executor = AgentExecutor()
        row = {"title": "无标题 - 记事本", "pid": 1, "hwnd": 1}
        with patch("coco.agent_tools._find_window", return_value=row), patch("coco.agent_tools._window_process_path", return_value=r"C:\Windows\System32\evil.exe"), patch("coco.agent_tools._has_edit_control", return_value=True):
            result = executor.execute("type_text", {"title": row["title"], "text": "unsafe"})
        self.assertFalse(result.ok)
        with patch("coco.agent_tools._find_window", return_value=row), patch("coco.agent_tools._window_process_path", return_value=r"C:\Windows\System32\notepad.exe"), patch("coco.agent_tools._has_edit_control", return_value=False):
            result = executor.execute("type_text", {"title": row["title"], "text": "unsafe"})
        self.assertFalse(result.ok)

    def test_open_path_rejects_executable(self):
        executor = AgentExecutor()
        executable = SCRATCH / "not-a-tool.exe"
        executable.write_bytes(b"MZ")
        result = executor.execute("open_path", {"path": str(executable)})
        self.assertFalse(result.ok)
        self.assertIn("文本文件", result.message)

    def test_local_open_and_type_reports_real_result(self):
        catalog = Catalog()
        executor = AgentExecutor(catalog)
        row = {"title": "无标题 - 记事本", "pid": 123, "hwnd": 456}
        with patch("coco.agent_tools._find_window", return_value=row), patch("coco.agent_tools._focus_window", return_value=row), patch("coco.agent_tools._window_process_path", return_value=r"C:\Windows\System32\notepad.exe"), patch("coco.agent_tools._has_edit_control", return_value=True), patch("coco.agent_tools._send_unicode", return_value=5) as sender, patch("coco.agent_tools.time.sleep"):
            result = local_agent_request("打开记事本并写入：Saturday", executor)
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "application_started_and_typed")
        sender.assert_called_once_with("Saturday")
        self.assertEqual(catalog.started, ["记事本"])

    def test_model_list_preserves_custom_model(self):
        opener = SequenceOpener([{"object": "list", "data": [{"id": "deepseek-v4-flash"}, {"id": "custom-local"}]}])
        models = list_models({"base_url": "http://127.0.0.1:9/v1"}, "fake-key", opener=opener)
        self.assertEqual(models, ["deepseek-v4-flash", "custom-local"])

    def test_agent_payload_disables_thinking_for_tool_calls(self):
        _, payload = build_agent_payload({"base_url": "https://api.deepseek.com", "model": "deepseek-v4-pro", "thinking": True}, [], {"behavior": "idle"}, [])
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertTrue(payload["tools"])

    def test_normal_thinking_setting_is_scoped_to_official_deepseek(self):
        from coco.assistant import build_chat_payload
        _, official = build_chat_payload({"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "thinking": True, "reasoning_effort": "max"}, [], {"behavior": "idle"}, [])
        self.assertEqual(official["thinking"], {"type": "enabled"})
        self.assertEqual(official["reasoning_effort"], "max")
        _, custom = build_chat_payload({"base_url": "https://example.test/v1", "model": "custom", "thinking": True}, [], {"behavior": "idle"}, [])
        self.assertNotIn("thinking", custom)


if __name__ == "__main__":
    unittest.main()
