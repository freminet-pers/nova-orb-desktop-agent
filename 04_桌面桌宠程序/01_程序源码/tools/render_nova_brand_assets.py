"""Render the authored Nova Orb SVG into the packaged PNG and ICO assets.

This is a local, deterministic build helper. It deliberately uses Qt's SVG
renderer and Pillow only; no online asset service or third-party avatar
geometry is involved.
"""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402


SOURCE_ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = SOURCE_ROOT.parent / "02_角色图片与动画" / "品牌图标"
SVG_FILE = BRAND_DIR / "Nova_Orb.svg"
PREVIEW_FILE = BRAND_DIR / "Nova_Orb_preview.png"
ICO_FILE = BRAND_DIR / "Nova_Orb.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    return image


def pil_image(image: QImage) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    image.save(buffer, "PNG")
    return Image.open(BytesIO(bytes(buffer.data()))).convert("RGBA")


def main() -> None:
    if not SVG_FILE.is_file():
        raise FileNotFoundError(SVG_FILE)
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(SVG_FILE))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {SVG_FILE}")

    preview = render(renderer, 512)
    if not preview.save(str(PREVIEW_FILE), "PNG"):
        raise RuntimeError(f"Could not write {PREVIEW_FILE}")

    icon_images = {size: pil_image(render(renderer, size)) for size in ICO_SIZES}
    icon_images[256].save(str(ICO_FILE), format="ICO", sizes=[(size, size) for size in ICO_SIZES])
    print(f"rendered {PREVIEW_FILE}")
    print(f"rendered {ICO_FILE} sizes={','.join(str(size) for size in ICO_SIZES)}")
    app.quit()


if __name__ == "__main__":
    main()
