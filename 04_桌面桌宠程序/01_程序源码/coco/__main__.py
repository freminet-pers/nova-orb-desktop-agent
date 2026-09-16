from .lifecycle import in_job
STARTUP_IN_JOB = in_job()

import logging
import sys
import json
import os
import importlib
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from .paths import DATA, PACKAGE_SIGNATURE, migrate_legacy, instance_namespace, instance_server_name
from .state import StateService, canonical_wake_phrase
from .ui import Controller, STYLE
from . import __version__


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Nova")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    instance_dir = instance_namespace()
    instance_dir.mkdir(parents=True, exist_ok=True)
    logs = DATA / "04_运行日志" / PACKAGE_SIGNATURE
    logs.mkdir(parents=True, exist_ok=True)
    # Source and frozen launches share this lock even though their data/log
    # directories remain separate; this prevents two desktop characters.
    lock = QLockFile(str(instance_dir / "coco.lock"))
    server_name = instance_server_name()
    if not lock.tryLock(100):
        socket = QLocalSocket()
        socket.connectToServer(server_name)
        if socket.waitForConnected(1000):
            socket.write(b"settings\n")
            socket.waitForBytesWritten(1000)
            socket.waitForReadyRead(1500)
            socket.disconnectFromServer()
            return 0
        QMessageBox.information(None, "Nova 已经在陪你啦", "请双击桌宠或托盘图标打开面板。")
        return 0
    handler = RotatingFileHandler(logs / "coco.log", maxBytes=300_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(handlers=[handler], level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    reporting = False

    def report_error(kind, value, traceback):
        nonlocal reporting
        logging.error("Unhandled application error", exc_info=(kind, value, traceback))
        if not reporting:
            reporting = True
            QMessageBox.warning(None, "Nova 遇到一点问题", "操作没有完成。请检查数据目录权限或磁盘空间；错误已写入运行日志。")
            reporting = False

    sys.excepthook = report_error
    service = None
    try:
        migrated = migrate_legacy()
        if migrated:
            logging.info("Migrated legacy database to %s", migrated)
        service = StateService()
        # Canonicalize before the controller, settings window, or wake worker
        # can cache a historical Chinese/custom phrase. StateService also
        # protects later reads, but this explicit startup boundary makes the
        # frozen/source migration ordering observable and deterministic.
        stored_wake = service.setting("wake_phrase", "hey nova")
        canonical_wake = canonical_wake_phrase(stored_wake)
        if stored_wake != canonical_wake:
            service.set_setting("wake_phrase", canonical_wake)
        state_module = importlib.import_module("coco.state")
        logging.info(
            "startup probe build=%s package_signature=%s state_module=%s data=%s service_path=%s wake_before=%r canonical=%r wake_after=%r",
            __version__, PACKAGE_SIGNATURE, getattr(state_module, "__file__", ""), DATA, service.path,
            stored_wake, canonical_wake, service.setting("wake_phrase", "hey nova"),
        )
        server = QLocalServer(app)
        QLocalServer.removeServer(server_name)
        server.listen(server_name)
        controller = Controller(service)

        def new_connection():
            client = server.nextPendingConnection()
            if client is None:
                return

            def request():
                command = bytes(client.readAll()).strip()
                if command == b"settings":
                    controller.show_settings()
                    client.write(b"ok\n")
                    client.flush()
                elif command == b"status":
                    body = {"version": __version__, "package_signature": PACKAGE_SIGNATURE, "startup_in_job": STARTUP_IN_JOB, "character_ready": controller.pet.character.ready,
                            "pid": os.getpid(), "parent_pid": os.getppid(),
                            "pet_visible": controller.pet.isVisible(), "input_visible": controller.pet.hit_surface.isVisible(),
                            "panel_visible": controller.panel.isVisible(), "panel_tab": controller.panel.tabs.currentIndex(),
                            "voice_phase": controller.voice.phase}
                    client.write(json.dumps(body).encode() + b"\n")
                    client.flush()
                elif command == b"quit":
                    client.write(b"ok\n")
                    client.flush()
                    QTimer.singleShot(0, controller.quit)
                client.disconnectFromServer()
            client.readyRead.connect(request)
            client.disconnected.connect(client.deleteLater)
            if client.bytesAvailable():
                request()

        server.newConnection.connect(new_connection)
        controller.start()
        if "--settings" in sys.argv:
            controller.show_settings()
        return app.exec()
    except Exception:
        report_error(*sys.exc_info())
        return 1
    finally:
        if service:
            service.close()
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
