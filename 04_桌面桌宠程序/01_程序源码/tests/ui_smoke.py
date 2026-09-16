"""Render own app and exercise Qt widgets; no desktop capture or external app control."""
import os
if not os.environ.get("COCO_UI_NATIVE"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFontDatabase, QFont, QCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from coco.state import StateService, ROOT
from coco.paths import ICON_FILE
from coco.ui import Controller, STYLE

app = QApplication([])
for filename in ("msyh.ttc", "msyhbd.ttc", "georgia.ttf", "segoeui.ttf"):
    font = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / filename
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
app.setFont(QFont("Microsoft YaHei UI", 10))
app.setStyleSheet(STYLE)
scratch = ROOT / "10_临时文件_确认后可删除" / "coco_test"
run = Path(tempfile.mkdtemp(prefix="ui_", dir=scratch))
service = StateService(run / "ui.sqlite3")
c = Controller(service)
c.start()
assert ICON_FILE.is_file()
assert not QApplication.windowIcon().isNull()
assert not c.tray.icon().isNull()
assert c.pet.isVisible() and not c.panel.isVisible()
assert "Nova" in c.pet.windowTitle()
assert "Nova" in c.panel.windowTitle()
assert not c.pet.bubble_window.isVisible()
from PySide6.QtWidgets import QPushButton, QProgressBar
assert not c.pet.findChildren(QPushButton)
for _ in range(150):
    QTest.qWait(100)
    if c.pet.character.ready:
        break
assert c.pet.character.ready, "Nova renderer did not initialize"
assert not c.voice.active

def js(code):
    result = []
    c.pet.character.page().runJavaScript(code, lambda value: result.append(value))
    for _ in range(100):
        QTest.qWait(20)
        if result:
            return result[0]
    raise AssertionError("JavaScript timeout")

assert js("typeof window.coco.snapshot") == "function"
assert js("typeof window.coco.gazeSnapshot") == "function"
assert js("typeof window.coco.renderSnapshot") == "function"

def render_snapshot():
    value = js("JSON.stringify(window.coco.renderSnapshot())")
    assert isinstance(value, str) and value.startswith("{")
    snapshot = json.loads(value)
    assert len(snapshot["eyes"]) == 2
    return snapshot

def eye_translation(snapshot):
    points = []
    for eye in snapshot["eyes"]:
        match = re.search(r"translate\(\s*([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)", eye["transform"] or "")
        assert match, snapshot
        points.append((float(match.group(1)), float(match.group(2))))
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )

def eye_relative(snapshot):
    body = snapshot["body"]
    body_center = (body["x"] + body["width"] / 2, body["y"] + body["height"] / 2)
    assert all(eye["width"] > 1 and eye["height"] > 1 for eye in snapshot["eyes"]), snapshot
    eye_center = (
        sum(eye["x"] + eye["width"] / 2 for eye in snapshot["eyes"]) / 2,
        sum(eye["y"] + eye["height"] / 2 for eye in snapshot["eyes"]) / 2,
    )
    return (eye_center[0] - body_center[0], eye_center[1] - body_center[1])

def visible_render_snapshot():
    # A blink can briefly hide a path; sample until both rendered eye paths
    # are visible so direction assertions describe the picture, not a blink.
    for _ in range(12):
        snapshot = render_snapshot()
        if all(eye["width"] > 1 and eye["height"] > 1 for eye in snapshot["eyes"]):
            return snapshot
        QTest.qWait(100)
    raise AssertionError("eye paths stayed hidden")

def release_render_snapshot(kind, strength, wait_ms=180):
    c.pet.character.set_state("idle", transient=False)
    QTest.qWait(850)
    js("window.coco.dragRelease(%r, %s)" % (kind, float(strength)))
    QTest.qWait(wait_ms)
    return render_snapshot()

# Release feedback is measured from rendered geometry, rather than only from
# the selected scene name.  A stronger vertical release lifts the body more;
# a horizontal release applies a visible but bounded tilt.  The original
# upstream renderer still supplies the face and its normal bounce trick.
light_bounce = release_render_snapshot("bounce", 0.12)
strong_bounce = release_render_snapshot("bounce", 0.90)
assert strong_bounce["body"]["y"] < light_bounce["body"]["y"] - 1, (light_bounce, strong_bounce)
light_sway = release_render_snapshot("sway", 0.12)
strong_sway = release_render_snapshot("sway", 0.90)
assert light_sway["groupTransform"] != strong_sway["groupTransform"]
assert "rotate(" in strong_sway["groupTransform"]
c.pet.grab().save(str(run / "drag_release_strong.png"))

c.pet.move(400, 250)
QTest.qWait(300)
c.pet.character.set_state("idle", transient=False)
QTest.qWait(500)
origin = c.pet.character.mapToGlobal(QPoint(0, 0))
inside = origin + QPoint(c.pet.character.width() // 2, c.pet.character.height() // 2)
width, height = c.pet.character.width(), c.pet.character.height()
outside = origin + QPoint(width + width * 2, height + height * 2)
QCursor.setPos(inside)
QTest.qWait(700)
center_pose = eye_relative(visible_render_snapshot())
directions = {
    "left": origin + QPoint(-width // 2, height // 2),
    "right": origin + QPoint(width + width // 2, height // 2),
    "up": origin + QPoint(width // 2, -height // 2),
    "down": origin + QPoint(width // 2, height + height // 2),
    "left_down": origin + QPoint(-width // 2, height + height // 2),
    "right_down": origin + QPoint(width + width // 2, height + height // 2),
    "left_up": origin + QPoint(-width // 2, -height // 2),
    "right_up": origin + QPoint(width + width // 2, -height // 2),
}
poses = {}
for name, position in directions.items():
    QCursor.setPos(position)
    QTest.qWait(500)
    snapshot = visible_render_snapshot()
    poses[name] = eye_relative(snapshot)
    c.pet.grab().save(str(run / ("gaze_" + name + ".png")))
assert poses["left"][0] < poses["right"][0] - 8, poses
assert poses["up"][1] < poses["down"][1] - 4, poses
assert poses["left_down"][0] < poses["right_down"][0] - 8, (center_pose, poses)
assert poses["left_down"][1] > poses["left_up"][1] + 4, (center_pose, poses)
assert poses["right_up"][0] > poses["left_up"][0] + 8, (center_pose, poses)
assert poses["right_up"][1] < poses["right_down"][1] - 4, (center_pose, poses)
QCursor.setPos(inside)
QTest.qWait(700)
center_after_snapshot = visible_render_snapshot()
center_after_pose = eye_relative(center_after_snapshot)
assert not center_after_snapshot["input"]["active"]
assert abs(center_after_snapshot["pointer"]["x"]) < 4
assert abs(center_after_snapshot["pointer"]["y"]) < 4
QCursor.setPos(outside)
QTest.qWait(1200)
reset_snapshot = visible_render_snapshot()
reset_pose = eye_relative(reset_snapshot)
assert not reset_snapshot["input"]["active"]
assert abs(reset_snapshot["pointer"]["x"]) < 4
assert abs(reset_snapshot["pointer"]["y"]) < 4
assert abs(reset_pose[0] - center_after_pose[0]) < 18, (center_after_pose, reset_pose)
assert abs(reset_pose[1] - center_after_pose[1]) < 18, (center_after_pose, reset_pose)
c.pet.grab().save(str(run / "gaze_center_after_leave.png"))
c.pet.grab().save(str(run / "nova_desktop.png"))
js("document.getElementById('bot').dispatchEvent(new MouseEvent('dblclick', {bubbles:true}))")
QTest.qWait(150)
assert c.panel.isVisible() and c.panel.tabs.currentIndex() == 3
c.pet.bubble_window.hide()
for x in (70, 140, 70, 140):
    c.pet.hover_stroke(QPoint(x, 60))
    QTest.qWait(150)
assert js('window.coco.snapshot().state') == 'happy'
assert not c.pet.bubble_window.isVisible(), 'stroking must not show text or buttons'
c.panel.hide()
# Keep the native double-click target fully inside the scaled test screen.
# At 150% Qt exposes a 533px logical offscreen screen; the earlier gaze setup
# intentionally moves the pet to x=400, so the first click would otherwise
# clamp the window and make the second click land at a different global point.
c.pet.clamp()
surface = c.pet.hit_surface
assert surface is not None
QTest.mouseClick(surface, Qt.MouseButton.LeftButton, pos=surface.rect().center())
QTest.qWait(70)
QTest.mouseClick(surface, Qt.MouseButton.LeftButton, pos=surface.rect().center())
QTest.qWait(200)
assert c.panel.isVisible() and c.panel.tabs.currentIndex() == 3, "native double click did not open settings"
c.panel.hide()
QTest.mouseDClick(c.pet.hit_surface, Qt.MouseButton.LeftButton, pos=c.pet.hit_surface.rect().center())
assert c.panel.isVisible() and c.panel.tabs.currentIndex() == 3
c.pet.character.react('celebrate', 'burst')
QTest.qWait(150)
assert js('window.coco.snapshot().state') == 'celebrate'
# A repeated click must restart an original reaction even within game cooldown.
c.interact('pet')
QTest.qWait(100)
assert js('window.coco.snapshot().state') == 'happy'
c.interact('pet')
QTest.qWait(100)
assert js('window.coco.snapshot().state') == 'happy'

c.panel.show()
c.pet.show()
QTest.qWait(300)
c.panel.grab().save(str(run / "home.png"))
button_texts = {item.text() for item in c.panel.findChildren(QPushButton)}
assert not {"喂食", "小零食", "玩耍"}.intersection(button_texts)
assert len(c.panel.findChildren(QProgressBar)) == 1, "only the voice level meter should remain"
c.panel.input.setText("你能做什么")
QTest.keyClick(c.panel.input, Qt.Key.Key_Return)
assert "养成" not in c.panel.chat.toPlainText()
c.send("记住：我喜欢安静的陪伴")
assert service.notes()[0]["content"] == "我喜欢安静的陪伴"
c.panel.tabs.setCurrentIndex(1)
c.panel.search.setText("计算器")
app.processEvents()
assert c.panel.apps.count() >= 1
c.panel.apps.setCurrentRow(0)
with patch.object(c.catalog, "launch", return_value="已请求启动") as launch:
    c.panel.launch_selected()
    launch.assert_called_once()
c.panel.grab().save(str(run / "apps.png"))
c.panel.tabs.setCurrentIndex(3)
app.processEvents()
c.panel.grab().save(str(run / "settings.png"))

# Business progress names must resolve through the Python phase table instead
# of leaking unknown strings into the renderer and silently falling to idle.
for business_phase, visual_state in (("planning", "thinking"), ("working", "working"),
                                     ("success", "saved"), ("failure", "error"),
                                     ("cancel", "idle")):
    c.busy = True
    c.phase = business_phase
    c.refresh()
    QTest.qWait(120)
    assert js("window.coco.snapshot().state") == visual_state, (business_phase, visual_state)
c.busy = False
c.phase = None
c.refresh()

# A new high-priority persistent phase cancels an old transient sequence; its
# timeout must not restore the stale reaction later.
c.pet.character.set_state("idle", transient=False)
js("window.coco.react('happy', '', 1800)")
QTest.qWait(120)
assert js("window.coco.snapshot().state") == "happy"
c.pet.character.set_state("thinking", transient=False)
QTest.qWait(450)
assert js("window.coco.snapshot().state") == "thinking"
QTest.qWait(1500)
assert js("window.coco.snapshot().state") == "thinking"
c.pet.character.set_state("thinking")
QTest.qWait(100)
assert js("window.coco.snapshot().state") == "thinking"
c.pet.character.set_state("idle")
assert js("window.coco.snapshot().mode") == "hold"
assert c.pet.enter()
QTest.qWait(200)
c.pet.grab().save(str(run / "nova_spawning.png"))
QTest.qWait(1800)
c.pet.grab().save(str(run / "nova_idle.png"))
# A transcript is editable by default; opt-in auto-send uses the same command path.
with patch.object(c.catalog, "launch", return_value="已请求启动计算器") as launch:
    c.on_transcript("打开计算器")
    launch.assert_not_called()
    assert c.panel.input.text() == "打开计算器"
    service.set_setting("voice_auto_send", True)
    c.on_transcript("打开计算器")
    for _ in range(50):
        QTest.qWait(20)
        if not c.busy:
            break
    assert not c.busy
    launch.assert_called_once()
    assert "已请求启动计算器" in c.pet.bubble.toPlainText()
c.panel.tabs.setCurrentIndex(4)
app.processEvents()
c.panel.grab().save(str(run / "voice.png"))
with patch("coco.ui.model_reply", return_value="测试模型回复"):
    service.set_setting("model_config", {"base_url": "https://api.deepseek.com", "model": "test", "enabled": True})
    c.send("测试自由聊天")
    for _ in range(30):
        QTest.qWait(20)
        if not c.busy:
            break
    assert not c.busy
    assert "测试模型回复" in c.panel.chat.toPlainText()
    history_before_probe = len(service.history())
    c.send("连接探测", force_model=True, persist=False, probe=True)
    for _ in range(30):
        QTest.qWait(20)
        if not c.busy:
            break
    assert not c.busy
    assert len(service.history()) == history_before_probe
    assert "连接成功" in c.panel.settings_hint.text()
c.panel.close()
assert not c.panel.isVisible() and c.pet.isVisible()
c.quit()
c.pet.character.close()
c.pet.deleteLater()
# quit() deliberately leaves 900 ms for the original powering-down scene.
QTest.qWait(950)
service.close()
print(json.dumps({"result": "PASS", "screenshots": str(run), "discovered_apps": len(c.catalog.entries)}, ensure_ascii=False))
