"""Transparent Qt host for the original, offline Nova Orb renderer."""
import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QUrl, Qt
from PySide6.QtGui import QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


EVENTS = frozenset({'press', 'move', 'release', 'cancel', 'settings', 'menu', 'ready'})


class DesktopBridge(QObject):
    event = Signal(str)

    @Slot(str)
    def action(self, name):
        if name in EVENTS:
            self.event.emit(name)


class LocalPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main_frame):
        return url == QUrl.fromLocalFile(str(Path(__file__).parent / 'web/nova.html'))


class NovaCanvas(QWebEngineView):
    """Qt-side protocol adapter; visual state is owned by the local web view."""

    action = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ready = False
        self.pending_state = 'idle'
        self.pending_enter = False
        self.transient_until = 0.0
        self.last_scene = ''
        self._last_gaze_payload = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet('background:transparent;border:0;')
        page = LocalPage(self)
        self.setPage(page)
        page.setBackgroundColor(QColor(0, 0, 0, 0))
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.channel = QWebChannel(page)
        self.bridge = DesktopBridge(self.channel)
        self.channel.registerObject('desktop', self.bridge)
        page.setWebChannel(self.channel)
        self.bridge.event.connect(self.on_action)
        self.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'web/nova.html')))

    def on_action(self, name):
        if name == 'ready':
            self.ready = True
            self.set_state(self.pending_state, transient=False)
            if self.pending_enter:
                self.pending_enter = False
                self.enter()
        self.action.emit(name)

    def set_state(self, state, transient=True):
        self.pending_state = state
        if transient:
            self.transient_until = max(self.transient_until, time.monotonic() + 1.2)
        if self.ready:
            self.page().runJavaScript('window.coco.setState(' + json.dumps(state, ensure_ascii=False) + ')')

    def sync_state(self, state):
        """Apply the persistent state unless a direct interaction is visible."""
        if time.monotonic() < self.transient_until:
            return False
        self.set_state(state, transient=False)
        return True

    def enter(self):
        self.pending_enter = not self.ready
        if self.ready:
            self.page().runJavaScript('window.coco.enter()')

    def handoff_enter(self, source='desktop', context=None):
        """Start the shared entrance choreography with future handoff metadata."""
        if self.ready:
            args = ','.join(json.dumps(value, ensure_ascii=False) for value in (source, context))
            self.page().runJavaScript('window.coco.handoff_enter(' + args + ')')

    def react(self, state, trick='', duration=2600):
        if self.ready:
            args = ','.join(json.dumps(value, ensure_ascii=False) for value in (state, trick, duration))
            self.page().runJavaScript('window.coco.react(' + args + ')')

    def gaze(self, point):
        payload = (point.x(), point.y(), self.width(), self.height())
        if payload == self._last_gaze_payload:
            return
        self._last_gaze_payload = payload
        if self.ready:
            self.page().runJavaScript(
                f'window.coco.gaze({payload[0]}, {payload[1]}, {payload[2]}, {payload[3]})'
            )

    def scene(self, name):
        from .behavior import payload
        self.last_scene = name
        if self.ready:
            self.page().runJavaScript('window.coco.sequence(' + json.dumps(payload(name), ensure_ascii=False) + ')')

    def clear_gaze(self):
        self._last_gaze_payload = None
        if self.ready:
            self.page().runJavaScript('window.coco.clearGaze()')

    def drag_release(self, kind, strength):
        if self.ready:
            self.page().runJavaScript(
                'window.coco.dragRelease(' + ','.join(json.dumps(value) for value in (kind, float(strength))) + ')'
            )
