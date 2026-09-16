"""Focused native Qt smoke for Phase M settings and model-request boundaries."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from coco.state import ROOT, StateService
from coco.ui import Controller, STYLE


app = QApplication.instance() or QApplication([])
app.setStyleSheet(STYLE)
scratch = ROOT / "10_临时文件_确认后可删除" / "coco_test"
run = Path(tempfile.mkdtemp(prefix="assistant_ui_", dir=scratch))
service = StateService(run / "assistant.sqlite3")
credential = run / "api_key.dpapi"
captured = {}
online_captured = {}


def fake_model(config, api_key, history, state, notes, **kwargs):
    captured.update({"config": config, "api_key": api_key, "history": history, "state": state, "notes": notes})
    return "测试连接已收到"


def fake_online(intent, **kwargs):
    online_captured.update({"kind": intent.kind, "query": intent.query, "kwargs": kwargs})
    return SimpleNamespace(success=True, text="北京天气测试结果\n来源：https://open-meteo.com/en/docs", kind=intent.kind)


with patch("coco.ui.credential_file", side_effect=lambda _scope: credential), \
     patch("coco.ui.model_reply", side_effect=fake_model), \
     patch("coco.ui.fetch_online", side_effect=fake_online):
    controller = Controller(service)
    controller.start()
    controller.show_settings()
    QTest.qWait(350)
    assert controller.panel.isVisible()
    assert not bool(controller.panel.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert controller.panel.key.echoMode().name == "Password"

    service.remember("这是私人备注")
    service.message("user", "历史私人聊天")
    service.set_setting("model_config", {"base_url": "http://127.0.0.1:9", "model": "local", "enabled": True})
    history_before = len(service.history())
    controller.send("最小连接探测", force_model=True, persist=False, probe=True)
    for _ in range(50):
        QTest.qWait(20)
        if not controller.busy:
            break
    assert not controller.busy
    assert len(service.history()) == history_before
    assert captured["history"] == [{"role": "user", "content": "最小连接探测"}]
    assert captured["notes"] == []
    assert "连接成功" in controller.panel.settings_hint.text()

    controller.send("查北京明天天气")
    for _ in range(50):
        QTest.qWait(20)
        if not controller.busy:
            break
    assert not controller.busy
    assert online_captured["kind"] == "weather"
    assert online_captured["query"] == "北京"
    assert service.history()[-1]["content"] == "查北京明天天气"
    assert all("北京天气测试结果" not in item["content"] for item in service.history())
    assert "北京天气测试结果" in controller.panel.chat.toPlainText()

    controller.panel.base.setText("http://127.0.0.1:9")
    controller.panel.model.setText("local")
    controller.panel.cloud.setChecked(True)
    assert controller.panel.remember_key.isChecked()
    controller.panel.key.setText("phase-m-fake-key")
    controller.panel.remember_key.setChecked(True)
    assert controller.panel.apply_settings()
    assert credential.is_file()
    assert b"phase-m-fake-key" not in credential.read_bytes()
    assert service.setting("remember_cloud_credential") is True
    controller.panel.key.clear()
    controller.panel.remember_key.setChecked(False)
    assert controller.panel.apply_settings()
    assert not credential.exists()
    assert service.setting("remember_cloud_credential") is False
    assert controller.api_key == "phase-m-fake-key"

    assert controller.panel.agent_enabled.isChecked()
    assert controller.panel.model.currentText() == "local"
    with patch("coco.ui.list_models", return_value=["remote-a", "remote-b"]):
        controller.refresh_models()
        for _ in range(50):
            QTest.qWait(20)
            if not controller.models_loading:
                break
    assert controller.panel.model.findText("remote-a") >= 0
    assert controller.panel.model.currentText() == "local"

    with patch("coco.ui.is_agent_request", return_value=True), patch(
        "coco.ui.local_agent_request",
        return_value=SimpleNamespace(ok=True, message="已创建并验证临时文件。"),
    ):
        controller.send("创建一个临时文本文件")
        for _ in range(50):
            QTest.qWait(20)
            if not controller.busy:
                break
    assert not controller.busy
    assert "已创建并验证临时文件" in service.history()[-1]["content"]
    assert any(event["kind"] == "agent_run" for event in service.events())

    controller.quit()
    QTest.qWait(950)
    controller.pet.character.close()
    service.close()

print("assistant_ui_smoke: PASS")
