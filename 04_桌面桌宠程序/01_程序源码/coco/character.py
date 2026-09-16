"""Coco 2D actor: independent tail, ears, eyes, muzzle and paw drawing layers.

Photo references and behavioral provenance live in coco_profile.json.
This local vector rig is an initial interpretation pending owner visual approval.
"""
import math
from PySide6.QtCore import Qt, QTimer, Signal, QPointF, QRectF, QElapsedTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QFont, QRadialGradient
from PySide6.QtWidgets import QWidget
from .state import PROFILE


class DogCanvas(QWidget):
    """A vector placeholder; original photos and recordings are never read."""
    touched = Signal()

    def __init__(self, parent=None, garden=True):
        super().__init__(parent)
        self.garden = garden
        self.behavior = "idle"
        self.wag = False
        self.pose = (1., 1., 0.)
        self.body_pose = [1., 1., 0., 0., 0.]
        self.last_frame = 0.
        self.elapsed = QElapsedTimer()
        self.elapsed.start()
        self.phase = 0.
        self.setMinimumSize(220, 230)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    def animate(self):
        if self.isVisible():
            self.phase = self.elapsed.elapsed() / 1000 * 2.4
            dt = min(.1, max(0., self.phase - self.last_frame) / 2.4)
            self.last_frame = self.phase
            target = {"sleeping": (1.08, .78, 0., 0., 0.), "belly": (1., .92, 26., -5., 0.),
                      "backing": (.95, .95, -3., 12., 0.), "curious": (1., 1., -4., 0., 0.)}.get(self.behavior, (1., 1., 0., 0., 0.))
            blend = 1 - math.exp(-dt * 9)
            self.body_pose = [a + (b - a) * blend for a, b in zip(self.body_pose, target)]
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.touched.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width() / 320, self.height() / 280)
        p.translate((self.width() - 320 * size) / 2, (self.height() - 280 * size) / 2)
        p.scale(size, size)

        def ellipse(x, y, w, h, color, outline=None):
            if color in ("#fffdf5", "#fffdf4", "#fffefa", "#fffdf6", "#f8f4e8"):
                gradient = QRadialGradient(QPointF(x + w * .42, y + h * .30), max(w, h) * .8)
                gradient.setColorAt(0, QColor("#ffffff"))
                gradient.setColorAt(.65, QColor(PROFILE["appearance"]["fur"]))
                gradient.setColorAt(1, QColor("#dfe1da"))
                p.setBrush(gradient)
            else:
                p.setBrush(QColor(color))
            p.setPen(QPen(QColor(outline), 1.4) if outline else Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x, y, w, h))

        def line(x1, y1, x2, y2, color, width=2):
            p.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        if self.garden:
            ellipse(21, 224, 280, 39, "#d4debf")
            ellipse(33, 229, 253, 21, "#becdaa")
            for x, y in ((37, 215), (270, 201), (284, 231)):
                line(x, y + 17, x + 2, y, "#8eaa78", 2)
                ellipse(x - 5, y - 4, 12, 8, "#fcf9df")
                ellipse(x, y - 2, 4, 4, "#e0b86c")
        ellipse(87, 235, 155, 15, "#b6bda566")
        sleeping = self.behavior == "sleeping"
        active = self.behavior in ("playing", "curious", "eating")
        bounce = abs(math.sin(self.phase * 1.8)) * 10 if self.behavior == "playing" else math.sin(self.phase) * 2
        p.save()
        p.translate(0, -bounce)
        sx, sy, angle = self.pose
        bx, by, ba, dx, dy = self.body_pose
        sx, sy, angle = sx * bx, sy * by, angle + ba
        p.translate(dx, dy)
        if self.behavior == "expectant":
            p.translate(math.sin(self.phase * 2) * 11, 0)
            sx *= .80 + .20 * abs(math.cos(self.phase * 1.5))
        p.translate(160, 235)
        p.rotate(angle)
        p.scale(sx, sy)
        p.translate(-160, -235)
        # Curled plume tail.
        p.save()
        p.translate(226, 170)
        p.rotate(math.sin(self.phase * 3) * 20 if self.wag else 0)
        if self.behavior == "eating":
            p.rotate(65)
        ellipse(-8, -44, 59, 77, "#f5eedc", "#dcd5c4")
        ellipse(-12, -51, 53, 70, "#fffdf5")
        ellipse(2, -31, 24, 35, "#e9e4d4")
        p.restore()
        # Body, ruff and paws.
        ellipse(95, 139, 143, 101, "#f8f4e8", "#d9d4c4")
        ellipse(105, 203, 39, 38, "#fffdf4", "#ddd8c8")
        ellipse(185, 203, 39, 38, "#fffdf4", "#ddd8c8")
        for x, y, w, h in ((78, 119, 66, 76), (175, 118, 67, 75), (104, 150, 51, 60), (148, 151, 54, 61)):
            ellipse(x, y, w, h, "#fffdf6")
        # Pointed cream ears.
        for mirror in (False, True):
            p.save()
            if mirror:
                p.translate(320, 0)
                p.scale(-1, 1)
            ear = QPainterPath(QPointF(86, 97))
            ear.cubicTo(80, 64, 90, 43, 99, 43)
            ear.cubicTo(116, 45, 133, 70, 134, 89)
            ear.closeSubpath()
            p.setBrush(QColor(PROFILE["appearance"]["ear"]))
            p.setPen(QPen(QColor("#d9d0bb"), 1.5))
            p.drawPath(ear)
            inner = QPainterPath(QPointF(94, 82))
            inner.lineTo(99, 57)
            inner.quadTo(117, 63, 121, 82)
            p.setBrush(QColor("#dac4a3"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(inner)
            p.restore()
        ellipse(81, 62, 159, 137, "#fffdf5", "#dfdacb")
        for x, y, w, h in ((70, 97, 55, 53), (67, 123, 59, 45), (198, 99, 49, 52), (194, 127, 57, 42), (117, 60, 46, 35)):
            ellipse(x, y, w, h, "#fffdf5")
        # Fine radial ruff: round, full face with small ears, based on the three frontal photos.
        for i in range(160):
            a = 2 * math.pi * i / 160
            radius = 1 + .025 * math.sin(i * 2.39)
            x, y = 160 + 84 * math.cos(a), 127 + 68 * math.sin(a)
            line(x - 5 * math.cos(a), y - 5 * math.sin(a),
                 160 + 90 * radius * math.cos(a), 127 + 74 * radius * math.sin(a), "#fffefa", 1.1)
        ellipse(132, 137, 32, 30, "#fffefa")
        ellipse(160, 137, 32, 30, "#fffefa")
        blink = sleeping or (int(self.phase * 10) % 67 < 2)
        if blink:
            line(125, 123, 143, 125, "#3e392f", 3)
            line(177, 125, 196, 123, "#3e392f", 3)
        else:
            for x in (123, 174):
                ellipse(x - 2, 109, 25, 29, "#766157")
                ellipse(x, 111, 23, 25, PROFILE["appearance"]["eye"])
                ellipse(x + 4, 113, 5, 6, "#edf2f2")
                ellipse(x + 12, 128, 3, 3, "#597385")
        ellipse(144, 154, 34, 16, "#35302e")
        ellipse(148, 140, 25, 19, PROFILE["appearance"]["nose"], "#4b3939")
        ellipse(151, 148, 6, 7, "#241f24")
        ellipse(165, 148, 6, 7, "#241f24")
        ellipse(155, 142, 6, 3, "#b79594")
        line(160, 153, 160, 160, "#494139", 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#494139"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        mouth = QPainterPath(QPointF(148, 158))
        mouth.quadTo(153, 165, 160, 159)
        mouth.quadTo(167, 165, 174, 158)
        p.drawPath(mouth)
        if not sleeping and self.behavior != "eating":
            ellipse(156, 162, 11, 13, "#dda79a")
        # No invented collar or accessories: recent reference photos show none.
        for i in range(24):
            x = 118 + i * 3.5
            line(x, 183, x + math.sin(i) * 4, 199 + math.sin(i * 1.7) * 6, "#e8e5db", .7)
        if self.behavior == "grooming":
            ellipse(144, 170, 30, 35, "#fffefa", "#ddd8c8")
            ellipse(155, 163, 10, 14 + math.sin(self.phase * 4) * 3, "#dda79a")
        if self.behavior == "eating":
            ellipse(118, 226, 75, 22, "#c59271")
            ellipse(122, 224, 67, 13, "#e6cbb3")
            for x in (135, 149, 163, 176):
                ellipse(x, 226, 7, 5, "#9b704a")
            ellipse(108 + math.sin(self.phase * 4) * 6, 207, 38, 23, "#fffdf4", "#ddd8c8")
        if self.behavior == "playing":
            ellipse(248, 219 - abs(math.sin(self.phase * 2)) * 25, 26, 26, "#d9a379", "#b88c69")
        p.restore()
        if sleeping:
            p.setPen(QColor("#829574"))
            p.setFont(QFont("Georgia", 18))
            p.drawText(QPointF(235, 77 - math.sin(self.phase) * 4), "z z")
        if self.behavior == "relaxed":
            p.setPen(QColor("#c79886"))
            p.setFont(QFont("Segoe UI Symbol", 20))
            p.drawText(QPointF(249, 93 - math.sin(self.phase) * 5), "♡")
        p.end()
