from __future__ import annotations

import html
import os
import re
import threading
import time
import random
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QProgressBar, QTextBrowser, QLineEdit, QTabWidget, QListWidget,
    QListWidgetItem, QCheckBox, QFormLayout, QFileDialog, QMenu, QSystemTrayIcon,
    QInputDialog, QMessageBox, QComboBox, QScrollArea, QLayout,
)

from PySide6.QtMultimedia import QMediaDevices

from .behavior import interaction_scene, PHASES, STATE_RULES, scene_duration, scene_rule
from .desktop import DesktopPet
from .voice import VoiceInput
from .wake import WakeListener, WAKE_PHRASES, canonical_phrases, normalize_wake_text, is_wake_phrase
from .speaker_verification import SpeakerRecorder, SpeakerTask, SpeakerVerificationError, delete_profile, profile_exists
from .assistant import Assistant, AppCatalog, list_models, model_agent, model_reply, validate_endpoint, route_intent
from .agent_tools import AgentExecutor, local_agent_request, is_agent_request, ToolCancelled
from .online import OnlineCancelled, SearchConfig, classify_online_request, fetch_online
from .search_providers import normalize_provider, provider_key_scope
from .paths import ICON_FILE, SPEAKER_PROFILE_FILE, credential_file
from .secure_store import SecureStoreError, available as secure_store_available, save as save_api_key, load as load_api_key, clear as clear_api_key
from . import __version__

ANIMATIONS = [
    ("弹跳", "bouncing", "bounce"), ("转一圈", "playful", "spin"), ("庆祝", "celebrate", "burst"),
    ("开心", "happy", ""), ("兴奋", "excited", ""), ("害羞", "shy", ""),
    ("大笑", "laughing", ""), ("惊讶", "surprised", ""), ("好奇", "curious", ""),
    ("骄傲", "proud", ""), ("困惑", "confused", ""), ("怀疑", "suspicious", ""),
    ("生气", "angry", ""), ("难过", "sad", ""), ("害怕", "scared", ""),
    ("无聊", "bored", ""), ("犯困", "drowsy", ""), ("睡觉", "sleeping", ""),
    ("醒来", "waking", ""), ("待机", "idle", ""), ("听你说", "listening", ""),
    ("思考", "thinking", ""), ("搜索", "searching", ""), ("工作", "working", ""),
    ("玩闹", "playful", ""), ("轨道", "orbit", ""), ("雷达", "radar", ""),
    ("进度", "progress", ""), ("登场", "spawning", ""), ("轻哼", "humming", ""),
    ("加载", "loading", ""), ("听写", "dictating", ""), ("书写", "writing", ""),
    ("发送", "sending", ""), ("接收", "receiving", ""), ("上传", "uploading", ""),
    ("通知", "notifying", ""), ("提醒", "alerting", ""), ("拖拽", "dragging", ""),
    ("关机", "powering-down", ""),
]

SPEAKER_EXAMPLES = (
    "我今天在家里安静地工作，下午想喝一杯热茶。",
    "请帮我打开记事本，写下今天要完成的三件小事。",
    "我喜欢清楚、简短、自然的电脑助手回复。",
)

STYLE = """
QWidget { color: #35463c; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
QWidget#home { background: #f8f7f2; }
QFrame#garden { background: #eef1eb; border-radius: 18px; }
QLabel#eyebrow { color: #71816c; font-size: 11px; letter-spacing: 2px; }
QLabel#title { font-family: 'Segoe UI'; font-size: 36px; font-weight: 600; color: #354d3e; }
QLabel#muted { color: #7b8478; font-size: 12px; }
QLabel#status { background: #f8faf0; border-radius: 12px; padding: 6px 12px; color: #5b7753; }
QPushButton { min-height: 18px; background: #eeeee5; border: 1px solid #dfe3d7; border-radius: 10px; padding: 9px 13px; }
QPushButton:hover { background: #e2e8d8; border-color: #a1b499; }
QPushButton:pressed { background: #cad8c0; }
QPushButton:disabled { color: #9ba195; background: #eeeee9; }
QPushButton#primary { color: white; background: #536f52; border: 0; }
QPushButton#primary:hover { background: #415e40; }
QPushButton#small { padding: 5px 9px; font-size: 12px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { color: #7c857a; padding: 12px 11px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #3d583e; border-bottom: 2px solid #65845d; }
QTextBrowser, QListWidget { border: 1px solid #e6e8df; border-radius: 12px; background: #fffefa; padding: 12px; }
QListWidget::item { padding: 9px; border-bottom: 1px solid #eff0e9; }
QListWidget::item:selected { background: #e0e9d8; color: #344d37; border-radius: 6px; }
QLineEdit { padding: 11px; border-radius: 9px; border: 1px solid #dbe0d3; background: #fffefa; selection-background-color: #7e9670; }
QLineEdit:focus { border-color: #7e9670; }
QProgressBar { border: 0; border-radius: 4px; background: #d9dfd0; min-height: 7px; max-height: 7px; }
QProgressBar::chunk { border-radius: 4px; background: #879e75; }
QCheckBox { spacing: 8px; padding: 6px 0; }
QMenu { background: #fffefa; border: 1px solid #d8dfd0; padding: 6px; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #e0e9d8; }
"""


def label(text, name=None, wrap=False):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    item.setWordWrap(wrap)
    if "<a " in str(text):
        item.setOpenExternalLinks(True)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName("primary")
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.clicked.connect(callback)
    return item


_REPLY_ERROR_MARKERS = (
    "失败", "超时", "API 返回", "连不上", "密钥无效", "响应不是", "参数不正确",
    "请先填写", "余额不足", "服务拒绝", "请求格式", "不受支持", "没有返回", "请求发生错误",
)


def reply_is_error(text):
    return any(marker in str(text or "") for marker in _REPLY_ERROR_MARKERS)


class ReplyBridge(QObject):
    ready = Signal(object)


class CatalogBridge(QObject):
    ready = Signal(object)


class OnlineBridge(QObject):
    ready = Signal(object)


class ModelsBridge(QObject):
    ready = Signal(object)


class AgentBridge(QObject):
    ready = Signal(object)
    progress = Signal(object)


class CompactionBridge(QObject):
    ready = Signal(object)


class ModelCombo(QComboBox):
    """Editable model selector with QLineEdit-compatible test/access methods."""
    def text(self):
        return self.currentText()

    def setText(self, value):
        self.setCurrentText(str(value))


class HomeWindow(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Window)
        self.c = controller
        self.setObjectName("home")
        self.setWindowTitle(f"Nova · 聊天与设置 · {__version__}")
        # The desktop character owns the always-on-top behavior.  The settings
        # panel is a normal top-level window so another Windows app can take
        # focus and cover it until the user explicitly opens the panel again.
        self.resize(920, 700)
        self.setMinimumSize(850, 650)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 18, 26, 18)
        top = QHBoxLayout()
        top.addWidget(label("NOVA  /  电脑端 AI 助理", "eyebrow"))
        top.addStretch()
        top.addWidget(button("回到桌面", self.hide))
        outer.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(22)
        outer.addLayout(row, 1)
        garden = QFrame()
        garden.setObjectName("garden")
        garden.setMinimumWidth(252)
        left = QVBoxLayout(garden)
        left.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        left.setContentsMargins(22, 24, 22, 24)
        left.addWidget(label("Nova.", "title"))
        left.addWidget(label("电脑端 AI 助理", "muted"))
        left.addSpacing(24)
        self.status = label("●  随时帮你处理电脑上的小事", "status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.status)
        left.addSpacing(12)
        left.addWidget(label("聊天 · 语音 · 应用 · 记忆", "muted", True))
        left.addStretch()
        garden_scroll = QScrollArea()
        garden_scroll.setWidgetResizable(True)
        garden_scroll.setFrameShape(QFrame.Shape.NoFrame)
        garden_scroll.setFixedWidth(286)
        garden_scroll.setWidget(garden)
        row.addWidget(garden_scroll)
        self.tabs = QTabWidget()
        row.addWidget(self.tabs, 1)
        self.build_chat()
        self.build_apps()
        self.build_diary()
        self.build_settings()
        self.build_voice()

        footer = QHBoxLayout()
        footer.addWidget(label("聊天、语音与应用启动。", "muted"))
        footer.addStretch()
        self.mode = label("本地互动 · 记忆已开启", "muted")
        footer.addWidget(self.mode)
        outer.addLayout(footer)

    def build_chat(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 17, 0, 0)
        layout.addWidget(label("和 Nova 说说话", None))
        layout.addWidget(label("聊聊今天，或让我帮你打开一个应用。", "muted"))
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        self.chat.setOpenLinks(True)
        layout.addWidget(self.chat, 1)
        quick = QHBoxLayout()
        for text in ("你好", "你能做什么"):
            item = button(text, lambda checked=False, t=text: self.c.send(t))
            item.setObjectName("small")
            quick.addWidget(item)
        quick.addStretch()
        layout.addLayout(quick)
        compose = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setMaxLength(2000)
        self.input.setPlaceholderText("说点什么…  例如：打开计算器")
        self.input.returnPressed.connect(self.submit)
        self.input.textEdited.connect(self.c.on_typing)
        compose.addWidget(self.input, 1)
        self.send_button = button("发送", self.submit, True)
        compose.addWidget(self.send_button)
        self.cancel_button = button("停止", self.c.cancel_request)
        self.cancel_button.setEnabled(False)
        compose.addWidget(self.cancel_button)
        layout.addLayout(compose)
        self.chat_hint = label("自由聊天：在设置中填入你的 DeepSeek API Key；明确说“打开记事本写入……”可使用受限本地工具。", "muted", True)
        layout.addWidget(self.chat_hint)
        self.tabs.addTab(page, "聊天")

    def build_voice(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("说给我听，回复写给你"))
        layout.addWidget(label("本地 Whisper 中文识别。桌宠上按鼠标中键开始，说完停顿即可；此页也能开始或手动完成。最长录音 30 秒。", "muted", True))
        self.microphones = QComboBox()
        self.populate_microphones()
        self.microphones.currentIndexChanged.connect(lambda: self.c.service.set_setting("voice_device", self.microphones.currentData() or ""))
        layout.addWidget(label("麦克风"))
        layout.addWidget(self.microphones)
        layout.addWidget(button("刷新麦克风列表", self.populate_microphones))
        self.voice_meter = QProgressBar()
        self.voice_meter.setRange(0, 100)
        self.voice_meter.setTextVisible(False)
        layout.addWidget(self.voice_meter)
        layout.addWidget(label("开始说话后，音量条应随声音跳动。没有变化就换一个麦克风。", "muted", True))
        self.voice_button = button("开始说话", self.c.toggle_voice, True)
        layout.addWidget(self.voice_button)
        layout.addWidget(button("取消本次录音／识别", self.c.cancel_voice))
        self.voice_hint = label("麦克风未开启。识别出的文字可修改后发送。", "muted", True)
        layout.addWidget(self.voice_hint)
        self.wake_enabled = QCheckBox("启用唤醒词（本机监听系统默认麦克风）")
        self.wake_enabled.setChecked(self.c.service.setting("wake_enabled", False))
        layout.addWidget(self.wake_enabled)
        self.wake_phrase = QLineEdit(self.c.service.setting("wake_phrase", "hey nova"))
        self.wake_phrase.setMaxLength(32)
        self.wake_phrase.setPlaceholderText("hey Nova")
        layout.addWidget(self.wake_phrase)
        layout.addWidget(button("应用唤醒词", self.c.apply_wake))
        self.wake_hint = label("默认关闭。仅识别完整呼叫：Nova、hey/hi/hello Nova、are you there Nova、Nova can you help 等有限句式；录音期间暂停监听。", "muted", True)
        layout.addWidget(self.wake_hint)
        layout.addSpacing(12)
        layout.addWidget(label("Nova 声纹（可选）"))
        layout.addWidget(label("声纹只在识别出完整 Nova 呼叫后做本地二次校验，不负责识别词语，也不是高风险身份认证。原始录音只在内存中处理，保存的是当前 Windows 用户加密的声纹。", "muted", True))
        self.speaker_guidance = label("录入前：在安静房间，距离麦克风约 20–40 厘米，用正常音量自然说话；每段约 5–8 秒，不要刻意喊叫，也不要让环境空录。", "muted", True)
        self.speaker_guidance.setWordWrap(True)
        layout.addWidget(self.speaker_guidance)
        self.speaker_example = label("第 1 段示例：" + SPEAKER_EXAMPLES[0], "status", True)
        self.speaker_example.setWordWrap(True)
        layout.addWidget(self.speaker_example)
        self.speaker_status = label("声纹未录入 · 默认关闭", "muted", True)
        layout.addWidget(self.speaker_status)
        self.speaker_enabled = QCheckBox("只响应已录入的声音（可随时关闭）")
        self.speaker_enabled.setChecked(bool(self.c.service.setting("speaker_enabled", False)) and profile_exists())
        self.speaker_enabled.setEnabled(profile_exists())
        self.speaker_enabled.toggled.connect(self.c.apply_speaker_setting)
        layout.addWidget(self.speaker_enabled)
        self.speaker_record_button = button("开始录入第 1/3 段", self.c.toggle_speaker_record, True)
        layout.addWidget(self.speaker_record_button)
        speaker_actions = QHBoxLayout()
        self.speaker_cancel_button = button("取消录入", self.c.cancel_speaker_enrollment)
        self.speaker_cancel_button.setEnabled(False)
        speaker_actions.addWidget(self.speaker_cancel_button)
        self.speaker_test_button = button("测试已录入声纹", self.c.start_speaker_test)
        self.speaker_test_button.setEnabled(profile_exists())
        speaker_actions.addWidget(self.speaker_test_button)
        self.speaker_delete_button = button("删除本地声纹", self.c.delete_speaker_profile)
        self.speaker_delete_button.setEnabled(profile_exists())
        speaker_actions.addWidget(self.speaker_delete_button)
        layout.addLayout(speaker_actions)
        self.speaker_hint = label("未录入时不改变原有唤醒流程。点开始后会先倒数 5 秒，再开始收音；完成每段后点同一个按钮停止。录入完成后仍可保持关闭。", "muted", True)
        self.speaker_hint.setWordWrap(True)
        layout.addWidget(self.speaker_hint)
        self.wake_enabled.toggled.connect(self.c.apply_wake)
        self.auto_voice = QCheckBox("手动录音识别后自动发送（唤醒后的语音单独处理）")
        self.auto_voice.setChecked(self.c.service.setting("voice_auto_send", False))
        self.auto_voice.toggled.connect(lambda value: self.c.service.set_setting("voice_auto_send", value))
        layout.addWidget(self.auto_voice)
        self.wake_review_text = QCheckBox("唤醒后的语音先让我确认文字（高级）")
        self.wake_review_text.setChecked(bool(self.c.service.setting("wake_review_text", False)))
        self.wake_review_text.toggled.connect(lambda value: self.c.service.set_setting("wake_review_text", value))
        layout.addWidget(self.wake_review_text)
        layout.addWidget(label("默认：完整呼叫 Nova 后，下一段清晰语音会自动处理一次；勾选上项可先修改识别文字。未命中唤醒词不会发送任务。", "muted", True))
        layout.addWidget(label("回复只显示在角色旁的小框和聊天记录中，不播放声音。语音在本机识别，不保存录音；开启自由聊天后，识别出的文字按聊天设置发送给模型服务。", "muted", True))
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "语音")

    def populate_microphones(self):
        chosen = self.c.service.setting("voice_device", "")
        self.microphones.blockSignals(True)
        self.microphones.clear()
        self.microphones.addItem("跟随 Windows 默认输入", "")
        for device in QMediaDevices.audioInputs():
            self.microphones.addItem(device.description(), bytes(device.id()).hex())
        index = self.microphones.findData(chosen)
        self.microphones.setCurrentIndex(max(0, index))
        self.microphones.blockSignals(False)

    def build_animations(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("试试它会什么"))
        layout.addWidget(label("点击动作，让桌面上的角色演示；全部调用原项目动画。", "muted", True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        actions = QGridLayout(content)
        for index, (name, state, trick) in enumerate(ANIMATIONS):
            actions.addWidget(button(name, lambda checked=False, n=name, st=state, tr=trick: self.c.animate(n, st, tr)), index // 3, index % 3)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.tabs.addTab(page, "动作")

    def submit(self):
        text = self.input.text().strip()
        if text and not self.c.busy:
            self.input.clear()
            self.c.send(text)

    def append(self, role, text):
        name = "你" if role == "user" else "Nova"
        color = "#8a755d" if role == "user" else "#607e50"
        safe = html.escape(text).replace("\n", "<br>")
        safe = re.sub(r"(https://[^\s<]+)", lambda match: f'<a href="{html.escape(match.group(1), quote=True)}">{match.group(1)}</a>', safe)
        self.chat.append(f'<p style="color:{color};font-size:11px;margin-top:16px;"><b>{name}</b></p><p style="color:#35463c;line-height:150%;margin-bottom:16px;">{safe}</p>')
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def build_apps(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 17, 0, 0)
        layout.addWidget(label("你电脑上的应用"))
        layout.addWidget(label("自动发现开始菜单应用；便携程序可手动添加。", "muted", True))
        self.search = QLineEdit()
        self.search.setPlaceholderText("按名称搜索应用")
        self.search.textChanged.connect(self.populate_apps)
        layout.addWidget(self.search)
        self.apps = QListWidget()
        self.apps.itemDoubleClicked.connect(self.launch_selected)
        layout.addWidget(self.apps, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("添加程序", self.add_app))
        self.refresh_apps_button = button("刷新", self.refresh_apps)
        actions.addWidget(self.refresh_apps_button)
        actions.addWidget(button("打开选中应用", self.launch_selected, True))
        layout.addLayout(actions)
        self.app_hint = label("", "muted", True)
        layout.addWidget(self.app_hint)
        self.tabs.addTab(page, "应用")
        self.populate_apps()

    def populate_apps(self):
        self.apps.clear()
        for entry in self.c.catalog.search(self.search.text()):
            item = QListWidgetItem(entry.name)
            item.setToolTip(entry.path)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.apps.addItem(item)
        self.app_hint.setText(f"发现 {len(self.c.catalog.entries)} 个入口 · 双击打开，悬停查看路径")

    def refresh_apps(self):
        self.c.refresh_catalog()

    def add_app(self):
        if self.c.catalog_loading:
            self.app_hint.setText("正在刷新应用列表，请稍等。")
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择要交给 Nova 打开的应用", "", "Windows 程序 (*.exe)")
        if not path:
            return
        name, ok = QInputDialog.getText(self, "给应用起个好叫的名字", "以后说“打开 这个名字”即可：", text=Path(path).stem)
        if ok and name.strip():
            self.c.catalog.custom.append({"name": name.strip()[:100], "path": path})
            self.c.service.set_setting("custom_apps", self.c.catalog.custom)
            self.refresh_apps()

    def launch_selected(self, *_):
        item = self.apps.currentItem()
        if not item:
            self.app_hint.setText("先选中一个应用。")
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        try:
            result = self.c.catalog.launch(entry)
            self.c.service.record("app_launch", {"name": entry.name})
            self.app_hint.setText(result)
            self.c.scene("launched")
        except (OSError, ValueError):
            self.app_hint.setText("启动失败：请检查路径或重新添加这个应用。")
            self.c.scene("error")

    def build_diary(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 17, 0, 0)
        layout.addWidget(label("我们的小日记"))
        layout.addWidget(label("记得那些小小的互动，也记得你的叮嘱。", "muted"))
        self.diary = QTextBrowser()
        layout.addWidget(self.diary, 1)
        layout.addWidget(label("可追溯的个人记忆（候选不会自动当成事实）", "muted", True))
        self.memory_list = QListWidget()
        self.memory_list.setMaximumHeight(150)
        layout.addWidget(self.memory_list)
        memory_actions = QHBoxLayout()
        memory_actions.addWidget(button("确认选中", self.confirm_memory))
        memory_actions.addWidget(button("更正选中", self.correct_memory))
        memory_actions.addWidget(button("删除选中", self.delete_memory))
        layout.addLayout(memory_actions)
        actions = QHBoxLayout()
        actions.addWidget(button("刷新日记", self.update_diary))
        actions.addWidget(button("导出记忆", lambda: self.save_data(False)))
        actions.addWidget(button("备份数据", lambda: self.save_data(True)))
        layout.addLayout(actions)
        self.diary_hint = label("说“记住：……”来添加一条长期备注。", "muted", True)
        layout.addWidget(self.diary_hint)
        self.tabs.addTab(page, "记忆")

    def update_diary(self):
        lines = ["<h3>你让我记住的事</h3>"]
        notes = self.c.service.notes()
        lines += ["<p>" + html.escape(n["content"]) + "</p>" for n in notes] or ["<p>还没有备注。</p>"]
        lines.append("<h3>最近的助手活动</h3>")
        event_labels = {
            "app_launch": "帮你启动应用",
            "app_failed": "应用启动失败",
            "voice_transcript": "完成一次语音识别",
            "chat": "完成一次对话",
            "agent_run": "完成一次受限电脑操作",
        }
        for event in self.c.service.events():
            name = event_labels.get(event["kind"])
            if not name:
                continue
            lines.append(f'<p style="color:#7b8478">{time.strftime("%m-%d %H:%M", time.localtime(event["at"]))}　{html.escape(name)}</p>')
        self.diary.setHtml("".join(lines))
        if hasattr(self, "memory_list"):
            self.memory_list.clear()
            status_labels = {"active": "已确认", "candidate": "待确认", "superseded": "已更正", "deleted": "已删除", "rejected": "已拒绝"}
            for item in self.c.service.memories(limit=80):
                status = status_labels.get(item.get("status"), str(item.get("status", "")))
                content = html.escape(str(item.get("content_text", ""))[:240])
                row = QListWidgetItem(f"[{status}] {content}")
                row.setData(Qt.ItemDataRole.UserRole, item.get("memory_id"))
                row.setToolTip(f"来源：{item.get('source_kind', '')} · 置信度：{float(item.get('confidence', 0)):.2f}")
                self.memory_list.addItem(row)

    def _selected_memory_id(self):
        item = self.memory_list.currentItem() if hasattr(self, "memory_list") else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def confirm_memory(self):
        memory_id = self._selected_memory_id()
        if not memory_id:
            self.diary_hint.setText("先选中一条候选记忆。")
            return
        try:
            self.c.service.confirm_memory(memory_id, True)
            self.diary_hint.setText("已确认这条记忆；仍可随时更正或删除。")
            self.update_diary()
        except Exception:
            self.diary_hint.setText("这条记忆暂时无法确认。")

    def correct_memory(self):
        memory_id = self._selected_memory_id()
        if not memory_id:
            self.diary_hint.setText("先选中一条记忆。")
            return
        item = self.memory_list.currentItem()
        current = str(item.text()).split("] ", 1)[-1] if item else ""
        content, ok = QInputDialog.getText(self, "更正个人记忆", "更正后的内容：", text=current)
        if not ok or not content.strip():
            return
        try:
            self.c.service.correct_memory(memory_id, content.strip()[:4000])
            self.diary_hint.setText("已保存更正，并保留原记忆的修订记录。")
            self.update_diary()
        except Exception:
            self.diary_hint.setText("更正未保存，请检查内容。")

    def delete_memory(self):
        memory_id = self._selected_memory_id()
        if not memory_id:
            self.diary_hint.setText("先选中一条记忆。")
            return
        try:
            self.c.service.delete_memory(memory_id)
            self.diary_hint.setText("已删除这条记忆；审计记录仍保留。")
            self.update_diary()
        except Exception:
            self.diary_hint.setText("删除未完成，请稍后再试。")

    def save_data(self, backup):
        try:
            path = self.c.service.backup() if backup else self.c.service.export()
            self.diary_hint.setText("已保存到：" + str(path))
            self.c.scene("backup" if backup else "export")
        except OSError:
            self.diary_hint.setText("保存失败，请检查数据目录是否可写。")
            self.c.scene("error")

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 17, 0, 0)
        layout.addWidget(label("让 Nova 更懂你"))
        layout.addWidget(label("DeepSeek · 兼容 OpenAI 的聊天接口", "muted"))
        form = QFormLayout()
        form.setVerticalSpacing(12)
        config = self.c.service.setting("model_config", {})
        if not isinstance(config, dict):
            config = {}
        self.base = QLineEdit(config.get("base_url", "https://api.deepseek.com"))
        self.model = ModelCombo()
        self.model.setEditable(True)
        model_value = str(config.get("model", "deepseek-flash") or "deepseek-flash")
        self.model.addItems([model_value, "deepseek-flash", "deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"])
        self.model.setCurrentText(model_value)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("已保存（留空保持）" if self.c.api_key_saved else "输入 API Key（默认加密保存）")
        form.addRow("API 地址", self.base)
        form.addRow("模型名称", self.model)
        form.addRow("API Key", self.key)
        self.search_provider = QComboBox()
        for provider, title in (("deepseek_native", "DeepSeek 原生联网搜索（复用上方 Key）"),
                                ("auto", "自动（旧 Brave Key→Brave；无 Key→DDG 摘要）"),
                                ("tavily", "Tavily 网页搜索"), ("brave", "Brave 网页搜索"),
                                ("ddg", "DuckDuckGo 即时摘要"), ("searxng", "自托管 SearXNG")):
            self.search_provider.addItem(title, provider)
        provider_index = self.search_provider.findData(self.c.search_provider)
        self.search_provider.setCurrentIndex(max(0, provider_index))
        self.search_provider.currentIndexChanged.connect(self._search_provider_changed)
        form.addRow("联网搜索服务", self.search_provider)
        self.search_endpoint = QLineEdit(self.c.search_endpoint)
        self.search_endpoint.setPlaceholderText("仅 SearXNG：例如 https://你的实例/search")
        form.addRow("SearXNG 地址", self.search_endpoint)
        self.search_key = QLineEdit()
        self.search_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._search_provider_changed()
        form.addRow("联网搜索 Key", self.search_key)
        layout.addLayout(form)
        model_actions = QHBoxLayout()
        self.refresh_models_button = button("从当前 API 刷新模型", self.c.refresh_models)
        model_actions.addWidget(self.refresh_models_button)
        self.models_hint = label("可直接手填自定义模型；刷新不会覆盖当前选择。", "muted", True)
        model_actions.addWidget(self.models_hint, 1)
        layout.addLayout(model_actions)
        self.cloud = QCheckBox("启用 API 自由聊天")
        self.cloud.setChecked(config.get("enabled", False))
        layout.addWidget(self.cloud)
        self.agent_enabled = QCheckBox("允许 Nova 使用受限电脑工具（只响应明确请求）")
        self.agent_enabled.setChecked(config.get("agent_enabled", True))
        layout.addWidget(self.agent_enabled)
        self.thinking = QCheckBox("手动启用 DeepSeek Thinking（关闭自动路由后生效；工具 Agent 仍使用安全的非 Thinking 回合）")
        self.thinking.setChecked(bool(config.get("thinking", False)))
        layout.addWidget(self.thinking)
        self.auto_route = QCheckBox("自动选择轻量聊天、深度分析或受限工具（本地判断，不额外调用模型）")
        # Existing users who explicitly enabled thinking keep that advanced
        # preference; new configurations use the cheaper local router.
        self.auto_route.setChecked(bool(config.get("auto_route", not config.get("thinking", False))))
        layout.addWidget(self.auto_route)
        effort_row = QHBoxLayout()
        effort_row.addWidget(label("Thinking 强度", "muted"))
        self.reasoning_effort = QComboBox()
        self.reasoning_effort.addItems(["low", "high", "max"])
        effort = str(config.get("reasoning_effort", "high") or "high")
        self.reasoning_effort.setCurrentText(effort if effort in {"low", "high", "max"} else "high")
        effort_row.addWidget(self.reasoning_effort)
        effort_row.addStretch()
        layout.addLayout(effort_row)
        self.remember_key = QCheckBox("使用 Windows 账户加密保存 API Key")
        can_store_key = secure_store_available()
        # A typed key should survive restart by default.  The previous default
        # was unchecked whenever no key had been saved yet, which silently made
        # a first successful setup session-only.  Keep an explicit opt-out in
        # settings without ever storing the secret itself in SQLite.
        remember_default = bool(self.c.service.setting("remember_cloud_credential", can_store_key))
        self.remember_key.setChecked(self.c.api_key_saved or remember_default)
        self.remember_key.setEnabled(can_store_key)
        layout.addWidget(self.remember_key)
        self.remember_search_key = QCheckBox("使用 Windows 账户加密保存联网搜索 Key")
        self.remember_search_key.setChecked(self.c.search_api_key_saved)
        self.remember_search_key.setEnabled(secure_store_available())
        layout.addWidget(self.remember_search_key)
        layout.addWidget(label("启用后，会把最近 16 条对话和最多 12 条备注发送给所填服务；不发送照片、录音或屏幕。", "muted", True))
        layout.addWidget(label("DeepSeek 官方注册与密钥：<a href='https://platform.deepseek.com/api_keys'>platform.deepseek.com/api_keys</a>；Tavily 注册：<a href='https://app.tavily.com'>app.tavily.com</a>；Brave Key：<a href='https://api-dashboard.search.brave.com/app/keys'>Brave API Keys</a>。", "muted", True))
        layout.addWidget(label("DeepSeek 原生搜索复用上方 Key：一次明确搜索最多 3 次服务端检索、只显示来源与引文，不执行网页文字；结果仅本次可见，不写进后续模型历史。自动/无 Key 只提供 DuckDuckGo 即时摘要；其他 provider 的 Key 不会交叉发送。", "muted", True))
        self.on_top = QCheckBox("桌宠保持置顶")
        self.on_top.setChecked(self.c.service.setting("on_top", True))
        layout.addWidget(self.on_top)
        layout.addWidget(button("应用设置", self.apply_settings, True))
        layout.addWidget(button("发送一句问候，测试连接", self.test_model))
        self.clear_key_button = button("清除本机保存的 API Key", self.clear_saved_key)
        self.clear_key_button.setEnabled(self.c.api_key_saved)
        layout.addWidget(self.clear_key_button)
        self.clear_search_key_button = button("清除本机保存的联网搜索 Key", self.clear_saved_search_key)
        self.clear_search_key_button.setEnabled(self.c.search_api_key_saved)
        layout.addWidget(self.clear_search_key_button)
        key_hint = "已启用 Windows 用户加密保存。留空会保留当前密钥；如需删除请点‘清除’。" if self.c.api_key_saved else "新输入的密钥默认使用 Windows 用户加密保存；取消勾选才只保留本次运行。也可从 COCO_API_KEY 或 DEEPSEEK_API_KEY 环境变量读取。"
        if self.c.api_key_store_error:
            key_hint = "本机加密密钥读取失败，请重新输入；不会显示或记录原密钥。"
        self.settings_hint = label(key_hint, "muted", True)
        layout.addWidget(self.settings_hint)
        layout.addStretch()
        layout.addWidget(button("把 Nova 带回屏幕右下角", self.c.pet.home))
        layout.addWidget(button("退出 Nova", self.c.quit))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "设置")

    def _search_provider_changed(self):
        if not hasattr(self, "search_key"):
            return
        provider = str(self.search_provider.currentData() or "auto")
        if provider == "deepseek_native":
            hint = "复用上方的 DeepSeek API Key（不另存搜索 Key）"
        elif provider == "tavily":
            hint = "已保存（Tavily，留空保持）" if self.c.search_api_key_saved and self.c.search_provider == provider else "可选：Tavily API Key"
        elif provider == "brave" or provider == "auto":
            hint = "已保存（Brave，留空保持）" if self.c.search_api_key_saved and self.c.search_provider in {"auto", "brave"} else "可选：Brave Search API Key"
        else:
            hint = "此服务不使用 API Key"
        self.search_key.setPlaceholderText(hint)
        self.search_key.setEnabled(provider in {"auto", "tavily", "brave"})
        self.search_endpoint.setEnabled(provider == "searxng")
        if hasattr(self, "remember_search_key"):
            self.remember_search_key.setEnabled(provider in {"auto", "tavily", "brave"} and secure_store_available())
        if hasattr(self, "clear_search_key_button"):
            self.clear_search_key_button.setEnabled(provider in {"auto", "tavily", "brave"} and self.c.search_api_key_saved)

    def apply_settings(self):
        config = {
            "base_url": self.base.text().strip(), "model": self.model.currentText().strip(),
            "enabled": self.cloud.isChecked(), "agent_enabled": self.agent_enabled.isChecked(),
            "thinking": self.thinking.isChecked(),
            "auto_route": self.auto_route.isChecked(),
            "reasoning_effort": self.reasoning_effort.currentText().strip(),
        }
        try:
            validate_endpoint(config["base_url"])
            if not config["model"]:
                raise ValueError("请输入模型名称")
        except ValueError as exc:
            self.settings_hint.setText(str(exc))
            return False
        entered_key = self.key.text().strip()
        new_scope = validate_endpoint(config["base_url"])
        scope_changed = new_scope != self.c.api_key_scope
        old_key_file = self.c.api_key_file
        old_key_saved = self.c.api_key_saved
        if scope_changed and not entered_key and not self.c.api_key_from_env:
            # Never send a key protected for one provider to a different
            # endpoint.  Endpoint-specific ciphertext remains available if
            # the user returns to it; the current request gets no key.
            self.c.api_key = ""
            self.c.api_key_saved = False
        self.c.api_key_scope = new_scope
        self.c.api_key_file = credential_file(new_scope)
        if scope_changed and not entered_key and not self.c.api_key_from_env:
            try:
                scoped_key = load_api_key(self.c.api_key_file, scope=self.c.api_key_scope)
            except SecureStoreError:
                scoped_key = None
                self.c.api_key_store_error = True
            if scoped_key:
                self.c.api_key = scoped_key
                self.c.api_key_saved = True
        if entered_key:
            self.c.api_key = entered_key
        selected_provider = str(self.search_provider.currentData() or "auto")
        selected_endpoint = self.search_endpoint.text().strip()
        scope_provider = "brave" if selected_provider == "auto" else selected_provider
        new_search_scope = provider_key_scope(scope_provider, selected_endpoint)
        old_search_file = self.c.search_api_key_file
        old_search_saved = self.c.search_api_key_saved
        search_scope_changed = (new_search_scope != self.c.search_api_key_scope)
        if search_scope_changed:
            self.c.search_api_key = ""
            self.c.search_api_key_saved = False
            env_names = {"auto": "NOVA_BRAVE_SEARCH_API_KEY", "brave": "NOVA_BRAVE_SEARCH_API_KEY", "tavily": "NOVA_TAVILY_SEARCH_API_KEY"}
            env_name = env_names.get(selected_provider, "")
            self.c.search_api_key_from_env = bool(env_name and os.environ.get(env_name, ""))
            if self.c.search_api_key_from_env:
                self.c.search_api_key = os.environ.get(env_name, "")
            elif new_search_scope:
                try:
                    scoped_key = load_api_key(credential_file(new_search_scope), scope=new_search_scope)
                except SecureStoreError:
                    scoped_key = None
                if scoped_key:
                    self.c.search_api_key = scoped_key
                    self.c.search_api_key_saved = True
        self.c.search_provider = selected_provider
        self.c.search_endpoint = selected_endpoint
        self.c.search_api_key_scope = new_search_scope
        self.c.search_api_key_file = credential_file(new_search_scope) if new_search_scope else None
        if selected_provider in {"ddg", "searxng", "deepseek_native"}:
            self.c.search_api_key = ""
            self.c.search_api_key_saved = False
        entered_search_key = self.search_key.text().strip()
        if entered_search_key and selected_provider in {"auto", "tavily", "brave"}:
            self.c.search_api_key = entered_search_key
        if self.c.search_api_key_file is not None and self.remember_search_key.isChecked() and self.c.search_api_key:
            try:
                save_api_key(self.c.search_api_key_file, self.c.search_api_key, scope=self.c.search_api_key_scope)
                self.c.search_api_key_saved = True
            except SecureStoreError:
                self.settings_hint.setText("联网搜索 Key 加密保存失败；本次运行仍可使用，密钥未写入明文文件。")
                return False
        elif self.c.search_api_key_file is not None and not self.remember_search_key.isChecked() and self.c.search_api_key_saved:
            try:
                clear_api_key(self.c.search_api_key_file)
                self.c.search_api_key_saved = False
            except SecureStoreError as exc:
                self.settings_hint.setText(str(exc))
                return False
        if search_scope_changed and old_search_saved and old_search_file is not None and not self.remember_search_key.isChecked() and old_search_file != self.c.search_api_key_file:
            try:
                clear_api_key(old_search_file)
            except SecureStoreError:
                self.settings_hint.setText("无法清除旧联网搜索 Key 的本机密文；当前服务不会使用它。")
                return False
        if self.remember_key.isChecked() and self.c.api_key:
            try:
                save_api_key(self.c.api_key_file, self.c.api_key, scope=self.c.api_key_scope)
                self.c.api_key_saved = True
                self.c.api_key_store_error = False
            except SecureStoreError:
                self.c.api_key_store_error = True
                self.settings_hint.setText("Windows 用户加密保存失败；本次运行仍可使用，密钥未写入明文文件。")
                return False
        elif not self.remember_key.isChecked() and self.c.api_key_saved:
            try:
                clear_api_key(self.c.api_key_file)
                self.c.api_key_saved = False
            except SecureStoreError as exc:
                self.settings_hint.setText(str(exc))
                return False
        if scope_changed and old_key_saved and not self.remember_key.isChecked() and old_key_file != self.c.api_key_file:
            try:
                clear_api_key(old_key_file)
            except SecureStoreError:
                self.settings_hint.setText("无法清除旧 API Key 的本机密文；当前端点不会使用它。")
                return False
        self.key.clear()
        self.key.setPlaceholderText("已保存（留空保持）" if self.c.api_key_saved else "输入 API Key（默认仅本次运行）")
        self.clear_key_button.setEnabled(self.c.api_key_saved)
        self.search_key.clear()
        self.search_provider.blockSignals(True)
        provider_index = self.search_provider.findData(self.c.search_provider)
        self.search_provider.setCurrentIndex(max(0, provider_index))
        self.search_provider.blockSignals(False)
        self.search_endpoint.setText(self.c.search_endpoint)
        self._search_provider_changed()
        self.clear_search_key_button.setEnabled(self.c.search_api_key_saved)
        self.c.service.set_setting("model_config", config)
        self.c.service.set_setting("remember_cloud_credential", self.remember_key.isChecked())
        self.c.service.set_setting("search_provider", self.c.search_provider)
        self.c.service.set_setting("search_endpoint", self.c.search_endpoint)
        self.c.service.set_setting("on_top", self.on_top.isChecked())
        self.c.pet.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.on_top.isChecked())
        self.c.pet.show()
        if self.c.api_key_saved:
            self.settings_hint.setText("设置已应用。密钥已由当前 Windows 账户加密保存；留空会保留，清除请点下方按钮。")
        else:
            self.settings_hint.setText("设置已应用。密钥仅保留在本次运行内；勾选 Windows 用户加密保存可跨次启动保留。")
        self.c.update_mode()
        return True

    def clear_saved_search_key(self):
        if self.c.search_api_key_file is None:
            self.settings_hint.setText("当前联网搜索服务不使用 API Key。")
            return False
        try:
            clear_api_key(self.c.search_api_key_file)
        except SecureStoreError as exc:
            self.settings_hint.setText(str(exc))
            return False
        self.c.search_api_key_saved = False
        self.clear_search_key_button.setEnabled(False)
        if not self.c.search_api_key_from_env:
            self.c.search_api_key = ""
        self._search_provider_changed()
        self.settings_hint.setText("已清除本机保存的联网搜索 Key；当前运行的 Key 仍会保留到退出。")
        return True

    def clear_saved_key(self):
        try:
            clear_api_key(self.c.api_key_file)
        except SecureStoreError as exc:
            self.settings_hint.setText(str(exc))
            return False
        self.c.api_key_saved = False
        self.clear_key_button.setEnabled(False)
        # An environment variable remains available for this process; the
        # explicit button only removes the optional local DPAPI copy.
        if not self.c.api_key_from_env:
            self.c.api_key = ""
        self.key.setPlaceholderText("输入 API Key（默认加密保存）")
        self.settings_hint.setText("已清除本机保存的 API Key；当前运行的密钥仍会保留到退出。")
        return True

    def test_model(self):
        if self.c.busy:
            self.settings_hint.setText("上一条消息还在等待回复。")
            return
        if self.apply_settings():
            self.cloud.setChecked(True)
            config = self.c.service.setting("model_config")
            if not isinstance(config, dict):
                config = {}
            config["enabled"] = True
            self.c.service.set_setting("model_config", config)
            self.c.update_mode()
            self.tabs.setCurrentIndex(0)
            self.c.send("请用一句话和我打个招呼。", force_model=True, persist=False, probe=True)

    def closeEvent(self, event):
        event.ignore()
        self.hide()


class Controller(QObject):
    def __init__(self, service):
        super().__init__()
        self.service = service
        # Migrate the earlier Chinese/Coco wake setting before constructing
        # the settings panel. The stored value and visible field stay aligned
        # with the strict English Whisper listener.
        saved_wake = normalize_wake_text(service.setting("wake_phrase", WAKE_PHRASES[0]))
        allowed_wake = {normalize_wake_text(item) for item in WAKE_PHRASES}
        if saved_wake not in allowed_wake:
            service.set_setting("wake_phrase", WAKE_PHRASES[0])
        self.catalog = AppCatalog(service.setting("custom_apps", []))
        self.catalog_loading = False
        self.models_loading = False
        self.assistant = Assistant(service, self.catalog)
        self.busy = False
        self.stopping = False
        self._request_serial = 0
        self._request_cancel = None
        model_config = service.setting("model_config", {})
        if not isinstance(model_config, dict):
            model_config = {}
        try:
            self.api_key_scope = validate_endpoint(model_config.get("base_url", "https://api.deepseek.com"))
        except ValueError:
            self.api_key_scope = "https://api.deepseek.com/chat/completions"
        self.api_key_file = credential_file(self.api_key_scope)
        self.api_key_from_env = bool(os.environ.get("COCO_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", ""))
        self.api_key = os.environ.get("COCO_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        self.api_key_saved = False
        self.api_key_store_error = False
        if not self.api_key:
            try:
                stored_key = load_api_key(self.api_key_file, scope=self.api_key_scope)
            except SecureStoreError:
                stored_key = None
                self.api_key_store_error = True
            if stored_key:
                self.api_key = stored_key
                self.api_key_saved = True
        # New installs use the user's existing DeepSeek credential for the
        # explicit web-search route.  Saved choices remain untouched so an
        # existing Brave/Tavily/SearXNG setup is never switched behind them.
        saved_provider = str(service.setting("search_provider", "deepseek_native") or "deepseek_native").strip().lower()
        if saved_provider not in {"auto", "tavily", "brave", "ddg", "searxng", "deepseek_native"}:
            saved_provider = "deepseek_native"
        self.search_provider = saved_provider
        self.search_endpoint = str(service.setting("search_endpoint", "") or "").strip()
        # ``auto`` preserves the original install contract: a legacy Brave
        # key remains scoped to Brave; without it the route is DDG Instant
        # Answer. Explicit providers always get their own DPAPI scope.
        scope_provider = "brave" if saved_provider == "auto" else saved_provider
        self.search_api_key_scope = provider_key_scope(scope_provider, self.search_endpoint)
        self.search_api_key_file = credential_file(self.search_api_key_scope) if self.search_api_key_scope else None
        env_names = {"auto": "NOVA_BRAVE_SEARCH_API_KEY", "brave": "NOVA_BRAVE_SEARCH_API_KEY", "tavily": "NOVA_TAVILY_SEARCH_API_KEY"}
        env_name = env_names.get(saved_provider, "")
        self.search_api_key_from_env = bool(env_name and os.environ.get(env_name, ""))
        self.search_api_key = os.environ.get(env_name, "") if env_name else ""
        self.search_api_key_saved = False
        if not self.search_api_key and self.search_api_key_file is not None:
            try:
                stored_search_key = load_api_key(self.search_api_key_file, scope=self.search_api_key_scope)
            except SecureStoreError:
                stored_search_key = None
            if stored_search_key:
                self.search_api_key = stored_search_key
                self.search_api_key_saved = True
        self.voice = VoiceInput(self)
        self.wake = WakeListener(self)
        self.speaker_recorder = SpeakerRecorder(self)
        self.speaker_task = None
        self.speaker_segments = []
        self.speaker_record_mode = "enroll"
        self.speaker_operation_serial = 0
        self.speaker_restore_wake = False
        self.speaker_gate_pending = False
        self.speaker_countdown = 0
        self.speaker_countdown_segment = 0
        self.speaker_countdown_mode = "enroll"
        self.speaker_countdown_timer = QTimer(self)
        self.speaker_countdown_timer.setInterval(1000)
        self.speaker_countdown_timer.timeout.connect(self._speaker_countdown_tick)
        self._quit_poll_timer = QTimer(self)
        self._quit_poll_timer.setInterval(50)
        self._quit_poll_timer.timeout.connect(self._finish_quit)
        self._quit_deadline = 0.0
        self._quit_exit_scheduled = False
        self.wake_command = False
        self.wake_transcript_consumed = False
        self.last_route_mode = "chat"
        # Wake-origin speech has an explicit, separate policy.  A missing
        # value is a migration to the newly authorized default: process one
        # clear command after a full Nova call, while ordinary manual voice
        # remains governed by voice_auto_send.
        if service.setting("wake_review_text", None) is None:
            service.set_setting("wake_review_text", False)
        self.game = None
        self.game_count = 0
        self.game_left = False
        self.game_cooldown_until = 0.0
        self.phase = None
        self.active_scene = None
        self.active_scene_until = 0.0
        # Avoid sending the same persistent state through the WebEngine every
        # refresh tick.  Direct reactions still update immediately; the timer
        # only needs to bridge an actual state change after a transient ends.
        self._last_synced_animation = None
        self._last_status_text = None
        self.drag_active = False
        self.drag_feedback_stage = ""
        self.scene_timer = QTimer(self)
        self.scene_timer.setSingleShot(True)
        self.scene_timer.timeout.connect(self._scene_finished)
        self.pet = DesktopPet(self)
        self.panel = HomeWindow(self)
        self.voice.transcript.connect(self.on_transcript)
        self.voice.status.connect(self.voice_status)
        self.voice.active_changed.connect(self.voice_active)
        self.voice.level.connect(self.panel.voice_meter.setValue)
        self.voice.level.connect(self.voice_level)
        self.wake.awakened.connect(self.on_wake)
        self.wake.status.connect(self.panel.wake_hint.setText)
        self.speaker_recorder.level.connect(self.panel.voice_meter.setValue)
        self.speaker_recorder.finished.connect(self._speaker_segment_ready)
        self.speaker_recorder.failed.connect(self._speaker_record_failed)
        self.speaker_recorder.active_changed.connect(self._speaker_record_active)
        self.wake_timer = QTimer(self)
        self.wake_timer.setSingleShot(True)
        self.wake_timer.timeout.connect(self.resume_wake)
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self.idle_action)
        self.game_timer = QTimer(self)
        self.game_timer.setSingleShot(True)
        self.game_timer.timeout.connect(self.game_expired)
        self.typing_timer = QTimer(self)
        self.typing_timer.setSingleShot(True)
        self.typing_timer.timeout.connect(self.typing_finished)
        self.bridge = ReplyBridge(self)
        self.bridge.ready.connect(self._reply_ready)
        self.catalog_bridge = CatalogBridge(self)
        self.catalog_bridge.ready.connect(self.catalog_ready)
        self.online_bridge = OnlineBridge(self)
        self.online_bridge.ready.connect(self._online_ready)
        self.models_bridge = ModelsBridge(self)
        self.models_bridge.ready.connect(self._models_ready)
        self.agent_bridge = AgentBridge(self)
        self.agent_bridge.ready.connect(self._agent_ready)
        self.agent_bridge.progress.connect(self._agent_progress)
        self.compaction_bridge = CompactionBridge(self)
        self.compaction_bridge.ready.connect(self._compaction_ready)
        self.compaction_active = False
        self.compaction_cancel = None
        self.compaction_retry_after = 0.0
        self.agent_active = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.tray = QSystemTrayIcon(self)
        icon = QIcon(str(ICON_FILE))
        QApplication.setWindowIcon(icon)
        self.tray.setIcon(icon)
        self.tray.setToolTip("Nova · 我在这里呀")
        self.tray_menu = self.menu()
        self.tray_menu.aboutToShow.connect(self.update_tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(lambda reason: self.show_panel() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        history = service.history()
        if history:
            for message in history:
                self.panel.append(message["role"], message["content"])
        else:
            self.panel.append("assistant", "你来啦。我是 Nova。\n\n点一下我，或告诉我今天发生了什么。\n\n想让我帮忙，就说“打开 应用名”。")
        self.refresh()
        self.update_mode()
        self.panel.update_diary()

    def start(self):
        self.pet.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.service.setting("on_top", True))
        position = self.service.setting("pet_position")
        if isinstance(position, list) and len(position) == 2:
            self.pet.move(*position)
            self.pet.clamp()
            self.pet.show()
        else:
            self.pet.home()
        self.pet.enter()
        self.idle_timer.start(14000)
        self.wake_timer.start(2000)

    def menu(self):
        menu = QMenu()
        menu.addAction("打开设置", self.show_settings)
        menu.addAction("和 Nova 聊天", self.show_chat)
        menu.addAction("开始说话 / 完成或取消", self.toggle_voice)
        wake_action = menu.addAction("关闭唤醒监听" if self.service.setting("wake_enabled", False) else "开启唤醒监听", self.toggle_wake)
        wake_action.setObjectName("wake-toggle")
        menu.addSeparator()
        menu.addAction("回到屏幕右下角", self.pet.home)
        menu.addAction("退出 Nova", self.quit)
        return menu

    def _scene_finished(self):
        self.active_scene = None
        self.active_scene_until = 0.0

    def _can_run_random(self):
        behavior = self.service.snapshot()["behavior"]
        return not (self.stopping or self.busy or self.voice.active or self.catalog_loading or self.game
                    or self.drag_active or self.pet.offset is not None or self.typing_timer.isActive()
                    or behavior in {"sleeping", "eating", "snacking", "expectant"})

    def begin_drag(self):
        """Reserve the drag state without interrupting assistant work."""
        if self.stopping or self.busy or self.voice.active or self.panel.isVisible():
            return False
        if self.active_scene and self.active_scene_until > time.monotonic():
            active_rule = STATE_RULES.get(self.active_scene, scene_rule(self.active_scene))
            if not active_rule.interruptible or active_rule.priority >= 80:
                return False
        self.drag_active = True
        self.drag_feedback_stage = ""
        self.active_scene = "dragging"
        self.active_scene_until = float("inf")
        self.scene_timer.stop()
        self.idle_timer.stop()
        self.pet.character.set_state("dragging", transient=False)
        return True

    def drag_feedback(self, stage):
        """Play one short original expression for each rising drag stage."""
        if not self.drag_active or self.stopping or self.busy or self.voice.active or self.panel.isVisible():
            return False
        order = {"curious": 1, "surprised": 2, "suspicious": 3, "confused": 4, "drowsy": 5}
        if stage not in order or order[stage] <= order.get(self.drag_feedback_stage, 0):
            return False
        self.drag_feedback_stage = stage
        duration = {"curious": 500, "surprised": 520, "suspicious": 600,
                    "confused": 720, "drowsy": 900}[stage]
        self.pet.character.react(stage, duration=duration)
        return True

    def finish_drag(self, release):
        """End the drag and choose release motion without claiming a click."""
        was_active = self.drag_active
        self.drag_active = False
        self.drag_feedback_stage = ""
        self.active_scene = None
        self.active_scene_until = 0.0
        self.scene_timer.stop()
        if not was_active or self.stopping or self.busy or self.voice.active or self.panel.isVisible():
            self.refresh()
            return False
        scene = {"bounce": "drag_bounce", "sway": "drag_sway", "settle": "drag_settle"}.get(release.kind, "drag_settle")
        accepted = self.scene(scene, source="drag")
        if accepted:
            self.pet.character.drag_release(release.kind, release.strength)
        return accepted

    def cancel_drag(self):
        self.drag_active = False
        self.drag_feedback_stage = ""
        self.active_scene = None
        self.active_scene_until = 0.0
        self.scene_timer.stop()
        self.refresh()

    def _accept_scene(self, name, source, force=False):
        now = time.monotonic()
        if source == "random" and not self._can_run_random():
            return False
        if self.active_scene and now >= self.active_scene_until:
            self._scene_finished()
        rule = scene_rule(name)
        if self.active_scene and self.active_scene_until > now and not force:
            active_rule = STATE_RULES.get(self.active_scene, scene_rule(self.active_scene))
            if not active_rule.interruptible and rule.priority <= active_rule.priority:
                return False
            if source == "random" and rule.priority <= active_rule.priority:
                return False
        self.active_scene = name
        duration = scene_duration(name)
        self.active_scene_until = now + duration / 1000.0
        self.scene_timer.start(max(1, int(duration)))
        return True

    def scene(self, name, source="task", force=False):
        if self.stopping or not self._accept_scene(name, source, force):
            return False
        self.pet.character.scene(name)
        return True

    def reaction(self, state, trick='', duration=2600, source='user', force=False):
        if self.stopping:
            return False
        if source == 'random' and not self._can_run_random():
            return False
        now = time.monotonic()
        if self.active_scene and now >= self.active_scene_until:
            self._scene_finished()
        if self.active_scene and self.active_scene_until > now and not force:
            active_rule = STATE_RULES.get(self.active_scene, scene_rule(self.active_scene))
            priority = 10 if source == 'random' else 75
            if ((not active_rule.interruptible and priority <= active_rule.priority)
                    or (source == 'random' and priority <= active_rule.priority)):
                return False
        self.active_scene = state
        self.active_scene_until = now + duration / 1000.0
        self.scene_timer.start(max(1, int(duration)))
        self.pet.character.react(state, trick, duration)
        return True

    def refresh_catalog(self):
        if self.catalog_loading:
            return
        self.catalog_loading = True
        self.panel.refresh_apps_button.setEnabled(False)
        self.panel.app_hint.setText("正在查找应用，窗口仍可操作…")
        self.scene("lookup")
        custom = list(self.catalog.custom)
        def run():
            try:
                entries = AppCatalog(custom).entries
            except Exception:
                entries = None
            if not self.stopping:
                self.catalog_bridge.ready.emit(entries)
        threading.Thread(target=run, name="coco-app-list", daemon=True).start()

    def catalog_ready(self, entries):
        if self.stopping:
            return
        self.catalog_loading = False
        self.panel.refresh_apps_button.setEnabled(True)
        if entries is None:
            self.panel.app_hint.setText("刷新失败，保留原来的列表。")
            self.scene("error")
        else:
            self.catalog.entries = entries
            self.panel.populate_apps()
            self.scene("saved")

    def refresh_models(self):
        if self.models_loading or self.stopping:
            return
        try:
            base = self.panel.base.text().strip()
            validate_endpoint(base)
        except ValueError as exc:
            self.panel.models_hint.setText(str(exc))
            return
        self.models_loading = True
        self.panel.refresh_models_button.setEnabled(False)
        self.panel.models_hint.setText("正在读取当前服务的模型列表…")
        base_key = self.api_key
        bridge = self.models_bridge

        def run():
            try:
                models = list_models({"base_url": base}, base_key)
                result = (True, models, "模型列表已刷新；当前手填值仍保留。")
            except Exception as exc:
                result = (False, [], str(exc))
            if not self.stopping:
                bridge.ready.emit(result)

        threading.Thread(target=run, name="nova-model-list", daemon=True).start()

    def _models_ready(self, payload):
        if self.stopping or not isinstance(payload, (tuple, list)) or len(payload) != 3:
            return
        success, models, message = payload
        self.models_loading = False
        self.panel.refresh_models_button.setEnabled(True)
        if not success:
            self.panel.models_hint.setText(str(message))
            return
        current = self.panel.model.currentText().strip()
        self.panel.model.blockSignals(True)
        self.panel.model.clear()
        self.panel.model.addItems([str(item) for item in models])
        if current and self.panel.model.findText(current) < 0:
            self.panel.model.addItem(current)
        self.panel.model.setCurrentText(current or (models[0] if models else ""))
        self.panel.model.blockSignals(False)
        self.panel.models_hint.setText(str(message) + f" 共 {len(models)} 个。")

    def update_tray_menu(self):
        for action in self.tray_menu.actions():
            if action.objectName() == "wake-toggle":
                action.setText("关闭唤醒监听" if self.service.setting("wake_enabled", False) else "开启唤醒监听")

    def model_waiting(self):
        if self.busy:
            self.phase = "thinking"
            self.refresh()

    def voice_level(self, level):
        if level > 4 and self.voice.phase == 'recording':
            self.pet.character.set_state('dictating')

    def on_typing(self, text):
        if text and not self.busy and not self.voice.active:
            self.typing_timer.start(1400)
            self.pet.character.set_state('writing')

    def typing_finished(self):
        self.refresh()

    def start_game(self, kind):
        if self.stopping or self.busy or self.voice.active or self.catalog_loading:
            return False
        now = time.monotonic()
        if now < self.game_cooldown_until:
            self.pet.say("刚玩过一轮，歇一会儿再来找我吧。")
            return False
        self.game, self.game_count, self.game_left = kind, 0, False
        self.scene(kind, source="user")
        self.pet.say("先把鼠标移开，再靠近我，让我找到你。" if kind == 'seek' else "和我击掌三次，每次单击停半秒。")
        self.game_timer.start(15000)
        return True

    def cancel_game(self, cooldown=False):
        if cooldown and self.game:
            self.game_cooldown_until = time.monotonic() + 4.0
        self.game = None
        self.game_timer.stop()

    def game_expired(self):
        if self.game:
            self.cancel_game(cooldown=True)
            self.scene('game_timeout', source='task')

    def pointer_presence(self, entered):
        if self.game == 'seek':
            if not entered:
                self.game_left = True
            elif self.game_left:
                self.cancel_game(cooldown=True)
                self.scene('found', source='task')
                self.pet.say("找到你啦！")

    def body_click(self):
        self.light_touch()

    def light_touch(self):
        """Give a small pointer response without invoking legacy pet-care state."""
        if self.stopping or self.busy or self.voice.active:
            return
        self.pet.last_activity = time.monotonic()
        self.reaction("happy", duration=1800, source="pointer")

    def show_panel(self):
        self.panel.showNormal()
        screen = QApplication.screenAt(self.pet.frameGeometry().center()) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        if not bounds.contains(self.panel.frameGeometry()):
            self.panel.move(bounds.center() - self.panel.rect().center())
        self.panel.raise_()
        self.panel.activateWindow()
        if self.panel.windowHandle():
            self.panel.windowHandle().requestActivate()

    def show_chat(self):
        self.panel.tabs.setCurrentIndex(0)
        self.show_panel()

    def toggle_voice(self):
        if self.voice.phase == "recording":
            self.voice.finish_recording()
        elif self.voice.active:
            self.cancel_voice()
        elif self.busy:
            self.pet.say("正在等上一条回复，稍后再说吧。")
        else:
            self.wake.stop()
            self.wake_command = False
            self.wake_transcript_consumed = False
            self.voice.start(self.service.setting("voice_device", ""), auto_finish=True)

    def apply_wake(self):
        if not self.panel.wake_enabled.isChecked():
            self.service.set_setting("wake_enabled", False)
            self.wake_timer.stop()
            self.wake.stop()
            self.panel.wake_hint.setText("唤醒监听已关闭。")
            return
        phrase = normalize_wake_text(self.panel.wake_phrase.text())
        if phrase not in {normalize_wake_text(item) for item in WAKE_PHRASES}:
            self.service.set_setting("wake_phrase", WAKE_PHRASES[0])
            self.panel.wake_phrase.setText("hey Nova")
            self.panel.wake_hint.setText("只接受完整呼叫：Nova、hey/hi/hello Nova、are you there Nova、Nova can you help 等有限句式。陈述句或夹在长句中的 Nova 不会触发。")
            return
        self.service.set_setting("wake_phrase", phrase)
        self.service.set_setting("wake_enabled", self.panel.wake_enabled.isChecked())
        self.wake.stop()
        self.wake.reset_failures()
        self.panel.wake_hint.setText("正在准备英文唤醒…" if self.panel.wake_enabled.isChecked() else "唤醒监听已关闭。")
        self.resume_wake()

    def toggle_wake(self):
        self.panel.wake_enabled.setChecked(not self.service.setting("wake_enabled", False))

    def _update_speaker_panel(self, status=None):
        if not hasattr(self.panel, "speaker_status"):
            return
        enrolled = profile_exists()
        enabled = bool(self.service.setting("speaker_enabled", False)) and enrolled
        self.panel.speaker_enabled.blockSignals(True)
        self.panel.speaker_enabled.setChecked(enabled)
        self.panel.speaker_enabled.setEnabled(enrolled)
        self.panel.speaker_enabled.blockSignals(False)
        if enrolled:
            self.panel.speaker_status.setText(status or ("声纹已录入 · " + ("二次校验已开启" if enabled else "默认关闭")))
        else:
            self.panel.speaker_status.setText(status or "声纹未录入 · 默认关闭")
        self.panel.speaker_test_button.setEnabled(enrolled and self.speaker_task is None and not self.speaker_recorder.active)
        self.panel.speaker_delete_button.setEnabled(enrolled and self.speaker_task is None and not self.speaker_recorder.active)

    def apply_speaker_setting(self, enabled):
        if enabled and not profile_exists():
            self.service.set_setting("speaker_enabled", False)
            self._update_speaker_panel("还没有本地声纹，请先完成三段录入；本次保持关闭。")
            return
        self.service.set_setting("speaker_enabled", bool(enabled))
        self._update_speaker_panel()

    def _pause_for_speaker(self):
        self.speaker_restore_wake = bool(self.service.setting("wake_enabled", False))
        self.wake.stop()
        self.wake_timer.stop()
        self.voice.stop(quiet=True)

    def toggle_speaker_record(self):
        if self.speaker_task is not None:
            return
        if self.speaker_countdown_timer.isActive():
            self.cancel_speaker_enrollment()
            return
        if self.speaker_recorder.active:
            self.speaker_recorder.finish()
            return
        if len(self.speaker_segments) >= 3:
            self.speaker_segments = []
        if not self.speaker_segments:
            self._pause_for_speaker()
            self.speaker_record_mode = "enroll"
        number = len(self.speaker_segments) + 1
        self._start_speaker_countdown("enroll", number)

    def _start_speaker_countdown(self, mode, number):
        """Give the user a visible preparation window before opening the mic."""
        self.speaker_countdown_mode = str(mode)
        self.speaker_countdown_segment = int(number)
        self.speaker_countdown = 5
        self.panel.speaker_cancel_button.setEnabled(True)
        self.panel.speaker_record_button.setEnabled(True)
        self.panel.speaker_record_button.setText("取消准备")
        prompt = "准备测试声纹" if mode == "test" else f"准备录第 {number}/3 段"
        self.panel.speaker_hint.setText(f"{prompt}，{self.speaker_countdown} 秒后开始收音；请保持安静并准备好自然说话。")
        self.speaker_countdown_timer.start()

    def _speaker_countdown_tick(self):
        if self.speaker_countdown <= 1:
            self.speaker_countdown_timer.stop()
            mode = self.speaker_countdown_mode
            number = self.speaker_countdown_segment
            self.panel.speaker_record_button.setText("完成声纹测试" if mode == "test" else f"完成第 {number}/3 段")
            self.panel.speaker_hint.setText(
                "正在测试，请自然说 5–8 秒；完成后点同一个按钮结束。" if mode == "test"
                else f"正在录第 {number}/3 段。请说示例句或同样时长的自然内容；完成后点同一个按钮结束。"
            )
            started = self.speaker_recorder.start(self.service.setting("voice_device", ""), maximum_ms=12000)
            if not started:
                self.panel.speaker_record_button.setText("开始录入第 1/3 段" if not self.speaker_segments else f"开始录入第 {len(self.speaker_segments) + 1}/3 段")
                self._restore_wake_after_speaker()
            return
        self.speaker_countdown -= 1
        mode = "测试" if self.speaker_countdown_mode == "test" else f"第 {self.speaker_countdown_segment}/3 段"
        self.panel.speaker_hint.setText(f"{mode}准备中，还剩 {self.speaker_countdown} 秒；请保持安静。")

    def _speaker_record_active(self, active):
        if not active and self.speaker_task is None and not self.speaker_segments:
            self.panel.speaker_record_button.setText("开始录入第 1/3 段")

    def _speaker_record_failed(self, message):
        self.panel.speaker_hint.setText(str(message))
        if self.speaker_record_mode == "test":
            self._restore_wake_after_speaker()
        self._update_speaker_panel()

    def _speaker_segment_ready(self, samples):
        if self.speaker_record_mode == "test":
            self.panel.speaker_hint.setText("正在本机校验声纹，请稍候…")
            self._start_speaker_task("verify", samples=samples)
            return
        self.speaker_segments.append(samples)
        count = len(self.speaker_segments)
        if count < 3:
            self.panel.speaker_record_button.setText(f"开始录入第 {count + 1}/3 段")
            self.panel.speaker_example.setText(f"第 {count + 1} 段示例：{SPEAKER_EXAMPLES[count]}")
            self.panel.speaker_hint.setText(f"第 {count}/3 段已收到。请换一句自然中文，再开始第 {count + 1} 段；不要朗读同一句。")
            return
        self.panel.speaker_record_button.setEnabled(False)
        self.panel.speaker_hint.setText("三段已收到，正在本机生成加密声纹；不会上传录音…")
        self._start_speaker_task("enroll", segments=list(self.speaker_segments))

    def _start_speaker_task(self, operation, segments=None, samples=None):
        self.speaker_operation_serial += 1
        serial = self.speaker_operation_serial
        task = SpeakerTask(operation, segments=segments, samples=samples, parent=self)
        self.speaker_task = task
        task.completed.connect(lambda result, s=serial: self._speaker_task_done(s, result))
        task.failed.connect(lambda message, s=serial: self._speaker_task_failed(s, message))
        task.finished.connect(lambda t=task: self._speaker_task_finished(t))
        task.finished.connect(task.deleteLater)
        task.start()
        self._update_speaker_panel("正在本机处理声纹…")

    def _speaker_task_finished(self, task):
        """Release a finished worker even when shutdown invalidated its serial."""
        if self.stopping and self.speaker_task is task:
            self.speaker_task = None

    def _speaker_task_done(self, serial, result):
        if serial != self.speaker_operation_serial:
            return
        self.speaker_task = None
        operation = result.get("operation") if isinstance(result, dict) else ""
        if operation == "enroll":
            self.service.set_setting("speaker_enrolled", True)
            self.service.set_setting("speaker_enabled", False)
            self.speaker_segments = []
            self.panel.speaker_record_button.setEnabled(True)
            self.panel.speaker_record_button.setText("重新录入三段声纹")
            self.panel.speaker_example.setText("录入完成。若要重录，请用三句不同的自然内容；也可单独测试 Hey Nova。")
            self.panel.speaker_hint.setText("已保存为当前 Windows 用户的加密声纹；默认仍关闭。可先点“测试”，确认后再开启二次校验。")
        elif operation == "verify":
            score = float(result.get("score", 0.0))
            if result.get("accepted"):
                self.panel.speaker_hint.setText(f"声纹匹配（分数 {score:.2f}），本次测试通过。")
            else:
                self.panel.speaker_hint.setText(f"声纹未匹配（分数 {score:.2f}），请换安静环境或重新录入。")
            gate_pending = self.speaker_gate_pending
            self.speaker_gate_pending = False
            if gate_pending:
                if result.get("accepted"):
                    self.panel.wake_hint.setText("Nova 呼叫已通过本地声纹，正在听下一句…")
                    self.on_wake()
                elif not self.stopping:
                    self.panel.wake_hint.setText(
                        f"已听到 Nova，但声纹未匹配（分数 {score:.2f}）；请完整说 Hey Nova，唤醒监听已恢复。"
                    )
                    self.wake_timer.start(500)
        self._update_speaker_panel()
        self._restore_wake_after_speaker()

    def _speaker_task_failed(self, serial, message):
        if serial != self.speaker_operation_serial:
            return
        self.speaker_task = None
        self.panel.speaker_record_button.setEnabled(True)
        self.panel.speaker_hint.setText(str(message))
        gate_pending = self.speaker_gate_pending
        self.speaker_gate_pending = False
        self._update_speaker_panel()
        self._restore_wake_after_speaker()
        if gate_pending and not self.stopping:
            self.panel.wake_hint.setText(
                "已听到 Nova，但声纹校验没有完成；请在安静环境完整说 Hey Nova，唤醒监听已恢复。"
            )
            self.wake_timer.start(700)

    def cancel_speaker_enrollment(self):
        self.speaker_operation_serial += 1
        self.speaker_countdown_timer.stop()
        self.speaker_countdown = 0
        self.speaker_segments = []
        self.speaker_record_mode = "enroll"
        self.speaker_recorder.stop(quiet=True)
        task = self.speaker_task
        self.speaker_task = None
        if task is not None:
            task.requestInterruption()
        self.panel.speaker_record_button.setEnabled(True)
        self.panel.speaker_record_button.setText("开始录入第 1/3 段")
        self.panel.speaker_cancel_button.setEnabled(False)
        self.panel.speaker_example.setText("第 1 段示例：" + SPEAKER_EXAMPLES[0])
        self.panel.speaker_hint.setText("录入已取消，原始录音没有保存。")
        self._restore_wake_after_speaker()

    def start_speaker_test(self):
        if self.speaker_task is not None or self.speaker_recorder.active:
            return
        if not profile_exists():
            self._update_speaker_panel("还没有本地声纹，请先录入三段。")
            return
        self._pause_for_speaker()
        self.speaker_record_mode = "test"
        self._start_speaker_countdown("test", 0)

    def delete_speaker_profile(self):
        if self.speaker_task is not None or self.speaker_recorder.active:
            return
        try:
            delete_profile()
        except SpeakerVerificationError as exc:
            self._update_speaker_panel(str(exc))
            return
        self.service.set_setting("speaker_enabled", False)
        self.service.set_setting("speaker_enrolled", False)
        self.speaker_segments = []
        self.speaker_countdown_timer.stop()
        self.panel.speaker_record_button.setText("开始录入第 1/3 段")
        self.panel.speaker_example.setText("第 1 段示例：" + SPEAKER_EXAMPLES[0])
        self.panel.speaker_hint.setText("本地声纹已删除，原始录音没有保存。")
        self._update_speaker_panel()

    def _restore_wake_after_speaker(self):
        restore = self.speaker_restore_wake
        self.speaker_restore_wake = False
        if restore and not self.stopping:
            self.wake_timer.start(400)

    def resume_wake(self):
        if self.stopping or not self.service.setting("wake_enabled", False):
            return
        if self.voice.active or self.busy:
            self.wake_timer.start(1500)
            return
        phrase = self.service.setting("wake_phrase", "hey nova")
        self.wake.start(phrase, self.service.setting("voice_device", ""))

    def on_wake(self):
        if self.busy or self.voice.active:
            self.wake_timer.start(1500)
            return
        self.wake_command = True
        self.wake_transcript_consumed = False
        self.voice.start(self.service.setting("voice_device", ""), auto_finish=True)
        if not self.voice.active:
            self.wake_command = False
            self.wake_transcript_consumed = False
            self.wake_timer.start(2000)

    def handle_wake_candidate(self, samples):
        """Receive one complete ASR-matched wake window in memory."""
        if self.stopping:
            return
        enabled = bool(self.service.setting("speaker_enabled", False))
        if not enabled or not profile_exists() or samples is None:
            self.on_wake()
            return
        if self.busy or self.voice.active:
            self.wake_timer.start(1500)
            return
        self.panel.wake_hint.setText("Nova 呼叫已识别，正在做本地声纹二次校验…")
        self.speaker_gate_pending = True
        self._start_speaker_task("verify", samples=samples)

    def idle_action(self):
        if self.stopping:
            return
        state = self.service.snapshot()
        if (self._can_run_random() and time.monotonic() - self.pet.last_activity > 6
                and state["behavior"] == "idle"):
            choices = [("curious", ""), ("happy", ""), ("shy", ""), ("idle", ""), ("playful", "bounce")]
            name, trick = random.choice(choices)
            self.reaction(name, trick, random.randint(2000, 3800), source='random')
        self.idle_timer.start(random.randint(12000, 28000))

    def cancel_voice(self):
        self.wake_command = False
        self.voice.stop()

    def voice_status(self, text):
        if not self.voice.active:
            self.wake_command = False
            self.wake_timer.start(1800)
        self.panel.voice_hint.setText(text)
        self.pet.say(text)

    def voice_active(self, active):
        recording = self.voice.phase == "recording"
        self.panel.voice_button.setText("说完了，开始识别" if recording else "取消识别" if active else "开始说话")
        if not active:
            self.wake_timer.start(1800)
        self.refresh()

    def on_transcript(self, text):
        text = str(text or "").strip()[:2000]
        self.panel.voice_hint.setText("识别：" + text if text else "没有识别到可处理的语音。")
        from_wake, self.wake_command = self.wake_command, False
        if from_wake:
            if self.wake_transcript_consumed:
                return
            self.wake_transcript_consumed = True
            # A recognizer can return the wake phrase itself or an empty final
            # after the one-shot recording.  Neither is a user task.
            if not text or is_wake_phrase(text):
                self.panel.voice_hint.setText("只听到唤醒词；请在下一次呼叫 Nova 后说出要处理的内容。")
                self.wake_timer.start(500)
                return
            if not self.service.setting("wake_review_text", False) and not self.busy:
                self.send(text)
                return
            if self.service.setting("wake_review_text", False):
                self.panel.input.setText(text)
                self.pet.say("听到：" + text + "\n请确认或修改后发送。")
                self.show_chat()
                self.panel.input.setFocus()
                return
        if self.service.setting("voice_auto_send", False) and text and not self.busy:
            self.send(text)
        elif text:
            self.panel.input.setText(text)
            self.pet.say("听到：" + text + "\n可在聊天框修改后发送。")
            self.show_chat()
            self.panel.input.setFocus()
        else:
            self.wake_timer.start(500)

    def show_settings(self):
        self.panel.tabs.setCurrentIndex(3)
        self.show_panel()

    def refresh(self):
        state = self.service.snapshot()
        status = {"idle": "安静地待在桌面上", "relaxed": "轻轻回应你的鼠标",
                  "curious": "正在听你说", "backing": "在这里等你", "grooming": "安静陪着你",
                  "sleeping": "暂时保持安静"}
        status_text = "●  " + status.get(state["behavior"], "准备帮你处理事情")
        if status_text != self._last_status_text:
            self.panel.status.setText(status_text)
            self._last_status_text = status_text
        if self.drag_active:
            return
        mapped = {"relaxed": "happy", "curious": "curious", "backing": "shy", "grooming": "idle",
                  "sleeping": "idle"}
        phase_animation = PHASES.get(self.phase, self.phase or "thinking")
        animation = ("dictating" if getattr(self.voice, "speech_seen", False) else "listening") if self.voice.phase == "recording" else "loading" if self.voice.active else phase_animation if self.busy else "writing" if self.typing_timer.isActive() else mapped.get(state["behavior"], "idle")
        if animation != self._last_synced_animation:
            applied = self.pet.character.sync_state(animation)
            if applied:
                self._last_synced_animation = animation

    def preview_entrance(self):
        self.pet.enter()

    def update_mode(self):
        config = self.service.setting("model_config", {})
        enabled = config.get("enabled", False) if isinstance(config, dict) else False
        agent_enabled = config.get("agent_enabled", True) if isinstance(config, dict) else True
        self.panel.mode.setText(("API 聊天与受限 Agent 已启用 · 本地备注" if agent_enabled else "API 聊天已启用 · Agent 已关闭") if enabled else ("本地助手与受限 Agent · 备注已开启" if agent_enabled else "本地助手 · Agent 已关闭"))
        self.panel.chat_hint.setText(("普通对话会发送到设置中的 API 服务；明确电脑操作会进入受限 Agent。" if enabled else "自由聊天：在设置中填入你的 DeepSeek API Key") + ("" if agent_enabled else " Agent 当前已关闭。"))

    def interact(self, kind, silent=False):
        if self.busy or self.voice.active:
            if not silent:
                self.pet.say("我正在处理你刚才的话，稍等一下。")
            return
        if kind == "pet":
            self.light_touch()
            return "我在这里。"
        self.cancel_game()
        self.typing_timer.stop()
        self.pet.last_activity = time.monotonic()
        outcome = self.service.interact_outcome(kind)
        if not silent:
            self.pet.say(outcome["reply"])
        self.refresh()
        self.panel.update_diary()
        scene = interaction_scene(kind, outcome)
        if outcome["before"]["behavior"] == "sleeping" and kind not in ("sleep",):
            scene = "wake"
        self.scene(scene, source="interaction")
        return outcome["reply"]

    def animate(self, name, state, trick=''):
        if self.voice.active or self.busy:
            self.pet.say("等我处理完这句话，再给你表演。")
            return
        self.pet.say(name + "！")
        self.reaction(state, trick, 4500, source='user', force=True)

    def send(self, text, force_model=False, persist=True, probe=False):
        if self.busy or not text.strip():
            return
        self.cancel_game()
        self.typing_timer.stop()
        self.wake.stop()
        self.voice.stop(quiet=True)
        text = text.strip()[:2000]
        config = self.service.setting("model_config", {})
        if not isinstance(config, dict):
            config = {}
        online_intent = None if force_model else classify_online_request(text)
        deterministic_tool = (not force_model and is_agent_request(text))
        decision = route_intent(
            text,
            online=online_intent is not None,
            deterministic_tool=deterministic_tool,
            auto=bool(config.get("auto_route", not config.get("thinking", False))),
            manual_thinking=bool(config.get("thinking", False)),
        )
        self.last_route_mode = decision.mode
        if persist:
            self.service.message("user", text)
            self.panel.append("user", text)
        if online_intent is not None:
            self._start_online(online_intent, persist=persist)
            return
        if deterministic_tool:
            self._start_agent(text, persist=persist)
            return
        reply = None if force_model else self.assistant.local_reply(text)
        if reply is not None:
            self.finish_reply(reply, persist=persist, probe=probe)
            return
        if not config.get("enabled"):
            self.finish_reply("我在听呢。现在还处于本地助手模式，自由聊天需要在“设置”里接上 API。你可以说“打开 应用名”或“记住：……”。",
                              persist=persist, probe=probe)
            return
        self._request_serial += 1
        request_serial = self._request_serial
        request_cancel = threading.Event()
        self._request_cancel = request_cancel
        self.busy = True
        self.phase = "sending"
        self.refresh()
        QTimer.singleShot(450, self.model_waiting)
        self.panel.send_button.setEnabled(False)
        self.panel.cancel_button.setEnabled(True)
        self.panel.chat_hint.setText("Nova 正在想怎么回答… 最多等待约 25 秒")
        if probe:
            # A connection check must not disclose private chat or notes; it
            # is a minimal one-message request handled by the same endpoint.
            history, state, notes = [{"role": "user", "content": text}], {"behavior": "idle"}, []
        else:
            history, notes = self.service.model_context(text, history_limit=16)
            state = self.service.snapshot()
        api_key = self.api_key
        bridge = self.bridge
        request_config = dict(config)
        if not force_model and bool(config.get("auto_route", not config.get("thinking", False))):
            # DeepSeek's thinking field is selected once, locally, for this
            # request.  Agent requests returned above never enter this path.
            request_config["thinking"] = bool(decision.thinking)

        def run():
            success = True
            try:
                answer = model_reply(request_config, api_key, history, state, notes, cancel_event=request_cancel)
            except Exception as exc:
                # Import lazily so a patched model_reply in the native smoke
                # remains compatible while cancellation stays silent.
                from .assistant import ModelRequestCancelled
                if isinstance(exc, ModelRequestCancelled):
                    return
                if isinstance(exc, ValueError):
                    answer = str(exc)
                else:
                    answer = "模型请求发生错误，请检查设置后再试。"
                success = False
            if not self.stopping:
                bridge.ready.emit((request_serial, answer, persist, probe, success))

        threading.Thread(target=run, name="coco-chat", daemon=True).start()

    @staticmethod
    def _redact_compaction_input(value):
        """Remove obvious credential-shaped text before an optional summary call."""
        text = str(value or "")[:24000]
        text = re.sub(r"(?i)(sk-[A-Za-z0-9]{8,})", "[redacted-key]", text)
        text = re.sub(r"(?i)((?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret)\s*[:=]\s*)\S+", r"\1[redacted]", text)
        text = re.sub(r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----).*?(-----END [A-Z ]*PRIVATE KEY-----)", r"\1[redacted]\2", text, flags=re.S)
        return text

    def _maybe_start_compaction(self):
        """Start one bounded rolling-summary request after a threshold is hit.

        Planning and the eventual SQLite commit stay on the StateService/UI
        thread.  The worker receives only an immutable redacted prompt; if it
        fails or the source range changes, the original messages remain.
        """
        if self.stopping or self.compaction_active or time.monotonic() < self.compaction_retry_after:
            return
        config = self.service.setting("model_config", {})
        if not isinstance(config, dict) or not config.get("enabled"):
            return
        try:
            plan = self.service.compaction_plan()
        except Exception:
            return
        if plan is None:
            return
        self.compaction_active = True
        cancel_event = threading.Event()
        self.compaction_cancel = cancel_event
        summary_config = dict(config)
        summary_config["auto_route"] = False
        summary_config["thinking"] = False
        summary_input = self._redact_compaction_input(plan.summary_input)
        bridge = self.compaction_bridge

        def run():
            success = False
            summary = ""
            try:
                summary = model_reply(
                    summary_config, self.api_key,
                    [{"role": "user", "content": summary_input}],
                    {"behavior": "idle"}, [], cancel_event=cancel_event,
                )
                success = bool(str(summary).strip())
            except Exception:
                success = False
            if not self.stopping:
                bridge.ready.emit((plan, summary, success))

        threading.Thread(target=run, name="nova-compaction", daemon=True).start()

    def _compaction_ready(self, payload):
        if not isinstance(payload, (tuple, list)) or len(payload) != 3:
            return
        plan, summary, success = payload
        self.compaction_active = False
        self.compaction_cancel = None
        if self.stopping or not success:
            self.compaction_retry_after = time.monotonic() + 60.0
            return
        try:
            result = self.service.commit_compaction(plan, summary)
            if result is not None and not getattr(result, "committed", False):
                self.compaction_retry_after = time.monotonic() + 15.0
        except Exception:
            # A stale/edited source range is expected to be rejected without
            # deleting or rewriting the original messages.
            self.compaction_retry_after = time.monotonic() + 15.0
            return

    def _start_online(self, intent, persist=True):
        self._request_serial += 1
        request_serial = self._request_serial
        request_cancel = threading.Event()
        self._request_cancel = request_cancel
        self.busy = True
        self.phase = "searching"
        self.refresh()
        self.panel.send_button.setEnabled(False)
        self.panel.cancel_button.setEnabled(True)
        self.panel.chat_hint.setText("Nova 正在联网查询；不会发送聊天历史或 API Key…")
        bridge = self.online_bridge
        search_key = self.search_api_key
        model_config = self.service.setting("model_config", {})
        if not isinstance(model_config, dict):
            model_config = {}
        search_config = SearchConfig(
            provider=self.search_provider,
            api_key=search_key,
            endpoint=self.search_endpoint,
            model=str(model_config.get("model", "deepseek-flash") or "deepseek-flash"),
            deepseek_api_key=self.api_key,
        )

        def run():
            try:
                result = fetch_online(intent, search_config=search_config, cancel_event=request_cancel)
            except OnlineCancelled:
                return
            except Exception:
                result = type("OnlineFallback", (), {
                    "success": False, "text": "联网查询发生错误，请稍后再试。", "kind": intent.kind,
                })()
            if not self.stopping:
                bridge.ready.emit((request_serial, result.text, persist, bool(result.success), result.kind))

        threading.Thread(target=run, name="coco-online", daemon=True).start()

    def _start_agent(self, text, persist=True):
        self._request_serial += 1
        request_serial = self._request_serial
        request_cancel = threading.Event()
        self._request_cancel = request_cancel
        self.agent_active = True
        self.busy = True
        self.phase = "planning"
        self.refresh()
        self.panel.send_button.setEnabled(False)
        self.panel.cancel_button.setEnabled(True)
        self.panel.chat_hint.setText("Nova 正在制定有限步骤；只会使用允许的电脑工具…")
        bridge = self.agent_bridge
        executor = AgentExecutor(self.catalog)
        config = self.service.setting("model_config", {})
        if not isinstance(config, dict):
            config = {}
        history, notes = self.service.model_context(text, history_limit=16)
        state = self.service.snapshot()
        api_key = self.api_key

        def progress(event):
            if not self.stopping:
                bridge.progress.emit((request_serial, event))

        def run():
            try:
                local = None if not config.get("agent_enabled", True) else local_agent_request(text, executor, cancel_event=request_cancel)
                if not config.get("agent_enabled", True):
                    from .assistant import AgentResult
                    result = AgentResult("受限电脑工具已在设置中关闭；可重新打开 Agent 开关后再试。", False, ({"phase": "failure"},))
                elif local is not None:
                    from .assistant import AgentResult
                    result = AgentResult(local.message, bool(local.ok), tuple(
                        [{"phase": "working", "tool": item.get("tool"), "ok": item.get("ok")} for item in executor.history] +
                        [{"phase": "success" if local.ok else "failure"}]
                    ))
                elif not config.get("enabled"):
                    from .assistant import AgentResult
                    result = AgentResult("这项电脑操作需要先在设置里启用 API Agent；本地明确的打开应用、窗口和新文本文件操作无需 API。", False, ({"phase": "failure"},))
                else:
                    result = model_agent(config, api_key, history, state, notes, executor,
                                         cancel_event=request_cancel, on_event=progress)
            except ToolCancelled:
                return
            except Exception as exc:
                from .assistant import AgentResult
                result = AgentResult(str(exc) if isinstance(exc, ValueError) else "Agent 操作没有完成，请检查设置或目标窗口。", False, ({"phase": "failure"},))
            if not self.stopping:
                bridge.ready.emit((request_serial, result.text, persist, result.success, result.events))

        threading.Thread(target=run, name="nova-agent", daemon=True).start()

    def _agent_progress(self, payload):
        if self.stopping or not isinstance(payload, (tuple, list)) or len(payload) != 2:
            return
        serial, event = payload
        if serial != self._request_serial or not isinstance(event, dict):
            return
        phase = str(event.get("phase", "working"))
        self.phase = phase
        labels = {
            "planning": "正在制定步骤…",
            "working": "正在执行允许的电脑操作…",
            "success": "操作已返回真实结果。",
            "failure": "操作没有完成。",
            "cancel": "正在停止操作…",
        }
        self.panel.chat_hint.setText("Nova " + labels.get(phase, "正在处理…"))
        self.refresh()

    def _agent_ready(self, payload):
        if not isinstance(payload, (tuple, list)) or len(payload) != 5:
            return
        request_serial, reply, persist, success, events = payload
        if self.stopping or request_serial != self._request_serial:
            return
        self.agent_active = False
        tool_names = []
        for event in events or ():
            if isinstance(event, dict) and event.get("tool") and event["tool"] not in tool_names:
                tool_names.append(str(event["tool"]))
        self.service.record("agent_run", {"success": bool(success), "tools": tool_names[:8], "steps": len(events or ())})
        self.finish_reply(reply, persist=bool(persist), success=bool(success))

    def cancel_request(self):
        if self._request_cancel is None or not self.busy:
            return
        self._request_cancel.set()
        self._request_serial += 1
        self._request_cancel = None
        self.agent_active = False
        self.busy = False
        self.phase = None
        self.panel.send_button.setEnabled(True)
        self.panel.cancel_button.setEnabled(False)
        self.panel.chat_hint.setText("已停止本次操作；没有继续执行后续工具。")
        self.scene("idle", source="task", force=True)
        self.refresh()

    def _online_ready(self, payload):
        if not isinstance(payload, (tuple, list)) or len(payload) != 5:
            return
        request_serial, reply, persist, success, kind = payload
        if self.stopping or request_serial != self._request_serial:
            return
        # Search snippets are untrusted external content.  Show them for this
        # turn, but do not write them to the conversation store that becomes a
        # later model prompt.  The user's short query was already persisted.
        self.finish_reply(reply, persist=False, success=bool(success), online_kind=str(kind or ""))

    def _reply_ready(self, payload):
        if not isinstance(payload, (tuple, list)) or len(payload) != 5:
            return
        request_serial, reply, persist, probe, success = payload
        if self.stopping or request_serial != self._request_serial:
            return
        self.finish_reply(reply, persist=bool(persist), probe=bool(probe), success=bool(success))

    def finish_reply(self, reply, animate=True, persist=True, probe=False, success=True, online_kind=""):
        if self.stopping:
            return
        reply = str(reply or "模型没有返回文字，请稍后再试。")
        self.busy = False
        self._request_cancel = None
        self.agent_active = False
        self.phase = None
        self.panel.send_button.setEnabled(True)
        self.panel.cancel_button.setEnabled(False)
        if persist:
            self.service.message("assistant", reply)
        if persist or online_kind:
            self.panel.append("assistant", reply)
            if success and not probe:
                self._maybe_start_compaction()
        if probe:
            if not success:
                self.panel.settings_hint.setText("连接未成功：" + str(reply))
            else:
                self.panel.settings_hint.setText("连接成功：模型已返回文字；这次测试没有写入聊天记录。")
        else:
            self.pet.say(reply)
        self.refresh()
        self.panel.update_diary()
        self.update_mode()
        if animate and not probe:
            self.scene("error" if not success or reply_is_error(reply) else "missing" if "还没找到" in reply or "同名" in reply else "launched" if "已请求启动" in reply else "saved" if "记住啦" in reply else "reply")
        self.wake_timer.start(1800)

    def quit(self):
        if self.stopping:
            return
        if self._request_cancel is not None:
            self._request_cancel.set()
        if self.compaction_cancel is not None:
            self.compaction_cancel.set()
        self.compaction_active = False
        self._request_serial += 1
        self.stopping = True
        self.game_timer.stop()
        self.typing_timer.stop()
        self.idle_timer.stop()
        self.wake_timer.stop()
        self.wake.stop()
        self.pet.bubble_window.hide()
        self.voice.stop(quiet=True)
        self.speaker_operation_serial += 1
        self.speaker_recorder.stop(quiet=True)
        if self.speaker_task is not None:
            self.speaker_task.requestInterruption()
        self.timer.stop()
        self.tray.hide()
        self.panel.hide()
        self.pet.character.scene("exit")
        self._quit_deadline = time.monotonic() + 5.0
        self._quit_poll_timer.start()
        self._finish_quit()

    def _finish_quit(self):
        """Wait briefly for speaker cancellation before leaving Qt's event loop."""
        if self._quit_exit_scheduled:
            return
        task = self.speaker_task
        running = False
        if task is not None:
            try:
                running = task.isRunning()
            except RuntimeError:
                self.speaker_task = None
        if running and time.monotonic() < self._quit_deadline:
            return
        if running:
            # The normal CAM++ path is short; this bounded wait is only a
            # safety valve so a broken native worker cannot keep the app alive
            # forever.  We never terminate the QThread or write a profile here.
            task.requestInterruption()
            try:
                task.wait(250)
            except RuntimeError:
                pass
        self._quit_poll_timer.stop()
        self._quit_exit_scheduled = True
        QTimer.singleShot(900, QApplication.quit)
