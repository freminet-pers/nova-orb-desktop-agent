import time

from PySide6.QtCore import Qt, QTimer, QEvent, QPoint, QRect
from PySide6.QtGui import QCursor, QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QPushButton, QApplication

from .nova import NovaCanvas
from .gestures import HeadStrokes
from .drag_motion import DragMotionTracker
from . import __version__


class PetHitSurface(QWidget):
    """Native input surface: Windows layered hit testing must see nonzero alpha."""
    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip('靠近时 Nova 会看向鼠标 · 双击设置 · 中键说话 · 右键菜单')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 1))
        painter.drawEllipse(self.rect().adjusted(22, 22, -22, -22))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pet.controller.toggle_voice()
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.pet.web_action('press', event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        self.pet.character.gaze(event.position().toPoint())
        # The native hit surface owns the inside-pointer path. Mark the
        # diagnostic path active so the nearby-gaze timer can clear it again
        # when the cursor returns to the body or leaves the surface.
        self.pet._gaze_active = True
        self.pet.hover_stroke(event.position().toPoint())
        self.pet.web_action('move', event.globalPosition().toPoint())

    def enterEvent(self, event):
        self.pet.controller.pointer_presence(True)

    def leaveEvent(self, event):
        self.pet.controller.pointer_presence(False)
        self.pet.character.clear_gaze()
        self.pet._gaze_active = False
        self.pet._gaze_target = None
        self.pet._last_gaze_sent = None

    def wheelEvent(self, event):
        now = time.monotonic()
        if now - self.pet.last_activity > .7 and not self.pet.controller.busy and not self.pet.controller.voice.active:
            self.pet.last_activity = now
            self.pet.controller.scene('tickle')
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pet.web_action('release', event.globalPosition().toPoint())
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pet.open_settings()
            event.accept()

    def contextMenuEvent(self, event):
        self.pet.controller.menu().exec(event.globalPos())


class DesktopPet(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle(f'Nova · {__version__}')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(220, 220)
        self.strokes = HeadStrokes()
        self.last_activity = time.monotonic()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.character = NovaCanvas(self)
        self.character.action.connect(self.web_action)
        layout.addWidget(self.character)
        self.hit_surface = PetHitSurface(self)
        self.character.installEventFilter(self)
        self.bubble_window = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.bubble_window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.bubble_window.setFixedSize(270, 110)
        bubble_layout = QVBoxLayout(self.bubble_window)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        self.bubble = QTextBrowser()
        self.bubble.setOpenLinks(False)
        self.bubble.setStyleSheet('QTextBrowser {background:#f3efe6;color:#242321;border:1px solid #d5d0c6;border-radius:12px;padding:8px;font-size:12px;}')
        bubble_layout.addWidget(self.bubble)
        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self.bubble_window.hide)
        self.offset = None
        self.dragged = False
        self.last_click = None
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.controller.body_click)
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self.long_press)
        self.motion = DragMotionTracker()
        self.drag_timer = QTimer(self)
        self.drag_timer.setInterval(40)
        self.drag_timer.timeout.connect(self.sample_drag)
        self.drag_feedback_active = False
        self._gaze_target = None
        self._gaze_active = False
        self._last_gaze_sent = None
        self.gaze_timer = QTimer(self)
        self.gaze_timer.setInterval(30)
        self.gaze_timer.timeout.connect(self.update_global_gaze)
        self.gaze_timer.start()

    def update_global_gaze(self):
        """Map the global cursor to WebEngine CSS coordinates with smoothing."""
        if not self.isVisible() or not self.character.ready:
            return
        origin = self.character.mapToGlobal(QPoint(0, 0))
        rect = QRect(origin, self.character.size())
        # The WebEngine surface already receives the native pointer event when
        # the cursor is over the character.  Let that path own the inside case
        # and reserve this timer for the nearby outside ring; this also avoids
        # leaving the diagnostic gaze input active after returning to the body.
        if rect.contains(QCursor.pos()):
            if self._gaze_active:
                self.character.clear_gaze()
                self._gaze_active = False
                self._gaze_target = None
                self._last_gaze_sent = None
            return
        # Keep the eyes responsive in a bounded elliptical approach field. The
        # radius is expressed in logical pixels, so Windows scaling does not
        # change the gesture distance; farther-away pointers return smoothly.
        center = rect.center()
        radius_x = max(1.0, rect.width() * 1.5)
        radius_y = max(1.0, rect.height() * 1.5)
        distance_x = (QCursor.pos().x() - center.x()) / radius_x
        distance_y = (QCursor.pos().y() - center.y()) / radius_y
        if distance_x * distance_x + distance_y * distance_y > 1.0:
            if self._gaze_active:
                self.character.clear_gaze()
                self._gaze_active = False
                self._gaze_target = None
                self._last_gaze_sent = None
            return
        local = self.character.mapFromGlobal(QCursor.pos())
        local.setX(max(0, min(self.character.width() - 1, local.x())))
        local.setY(max(0, min(self.character.height() - 1, local.y())))
        if self._gaze_target is None:
            self._gaze_target = local
        else:
            self._gaze_target = QPoint(
                round(self._gaze_target.x() * 0.55 + local.x() * 0.45),
                round(self._gaze_target.y() * 0.55 + local.y() * 0.45),
            )
        if (self._last_gaze_sent is None
                or (self._last_gaze_sent - self._gaze_target).manhattanLength() >= 2):
            self.character.gaze(self._gaze_target)
            self._last_gaze_sent = QPoint(self._gaze_target)
        self._gaze_active = True

    def long_press(self):
        if self.offset is not None and not self.dragged:
            self.held = True
            self.click_timer.stop()
            self.controller.light_touch()

    def sample_drag(self):
        """Sample a held pointer so velocity and emotion decay use real time."""
        if self.offset is None or not self.dragged:
            self.drag_timer.stop()
            return
        point = QCursor.pos()
        snapshot = self.motion.update(point.x(), point.y(), time.monotonic())
        if self.drag_feedback_active:
            self.controller.drag_feedback(snapshot.stage)

    def _clamp_drag_target(self, target, point):
        screen = QApplication.screenAt(point) or QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        return QPoint(
            max(bounds.left(), min(target.x(), bounds.right() - self.width() + 1)),
            max(bounds.top(), min(target.y(), bounds.bottom() - self.height() + 1)),
        )

    def eventFilter(self, watched, event):
        if watched is self.character and event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            self.hit_surface.setGeometry(self.character.geometry())
            self.hit_surface.raise_()
            self.hit_surface.show()
        return super().eventFilter(watched, event)

    def enter(self):
        self.clamp()
        self.show()
        self.character.enter()
        return True

    def say(self, text):
        self.bubble.setPlainText(text)
        self.bubble.verticalScrollBar().setValue(0)
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        x = max(bounds.left(), min(self.x() - 25, bounds.right() - self.bubble_window.width()))
        y = self.y() - self.bubble_window.height() + 15
        if y < bounds.top():
            y = min(bounds.bottom() - self.bubble_window.height(), self.y() + self.height() - 15)
        self.bubble_window.move(x, y)
        self.bubble_window.show()
        self.bubble_timer.start(min(22000, max(6000, len(text) * 170)))

    def hover_stroke(self, point):
        if self.offset is not None or self.controller.busy or self.controller.voice.active:
            return
        now = time.monotonic()
        if self.strokes.move(point.x(), point.y(), self.width(), self.height(), now):
            self.last_activity = now
            self.controller.light_touch()


    def home(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 32, screen.bottom() - self.height() - 25)
        self.show()

    def clamp(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        self.move(max(bounds.left(), min(self.x(), bounds.right() - self.width() + 1)),
                  max(bounds.top(), min(self.y(), bounds.bottom() - self.height() + 1)))

    def web_action(self, action, point=None):
        point = QCursor.pos() if point is None else point
        if action == 'press':
            self.last_activity = time.monotonic()
            self.bubble_window.hide()
            self.drag_distance = 0
            self.held = False
            self.last_drag_point = point
            self.last_drag_time = time.monotonic()
            self.motion.begin(point.x(), point.y(), self.last_drag_time)
            self.drag_timer.stop()
            self.drag_feedback_active = False
            self.hold_timer.start(800)
            self.offset = point - self.pos()
            self.start = point
            self.dragged = False
        elif action == 'move' and self.offset is not None:
            now = time.monotonic()
            snapshot = self.motion.update(point.x(), point.y(), now)
            if (point - self.start).manhattanLength() > QApplication.startDragDistance():
                if not self.dragged:
                    self.hold_timer.stop()
                    self.controller.cancel_game()
                    self.dragged = True
                    self.drag_feedback_active = self.controller.begin_drag()
                    if self.drag_feedback_active:
                        self.character.set_state('dragging', transient=False)
                        self.drag_timer.start()
            if self.dragged:
                self.click_timer.stop()
                target = self._clamp_drag_target(point - self.offset, point)
                delta = point - self.last_drag_point
                self.last_drag_point, self.last_drag_time = point, now
                self.drag_distance += (target - self.pos()).manhattanLength()
                self.move(target)
                if self.drag_feedback_active:
                    self.controller.drag_feedback(snapshot.stage)
        elif action == 'release' and self.offset is not None:
            self.hold_timer.stop()
            was_dragged = self.dragged
            release = self.motion.finish(time.monotonic()) if was_dragged else None
            self.drag_timer.stop()
            self.offset = None
            self.clamp()
            self.controller.service.set_setting('pet_position', [self.x(), self.y()])
            if was_dragged:
                self.last_activity = time.monotonic()
                if release is not None:
                    self.controller.finish_drag(release)
            if not was_dragged and not self.held:
                if self.click_timer.isActive() and self.last_click is not None and (point - self.last_click).manhattanLength() <= QApplication.startDragDistance():
                    self.open_settings()
                else:
                    self.last_click = point
                    self.click_timer.start(QApplication.doubleClickInterval())
            self.dragged = False
            self.drag_feedback_active = False
        elif action == 'settings':
            self.open_settings()
        elif action == 'cancel':
            self.hold_timer.stop()
            was_dragged = self.dragged
            self.drag_timer.stop()
            self.motion.cancel()
            self.offset = None
            self.click_timer.stop()
            self.dragged = False
            self.drag_feedback_active = False
            if was_dragged:
                self.controller.cancel_drag()
        elif action == 'menu':
            self.controller.menu().exec(point)

    def open_settings(self):
        self.hold_timer.stop()
        self.click_timer.stop()
        self.offset = None
        self.last_click = None
        self.controller.show_settings()
