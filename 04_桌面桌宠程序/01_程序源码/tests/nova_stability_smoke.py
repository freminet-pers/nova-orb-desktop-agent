"""Run the Nova renderer through a long idle/interaction cycle.

The test deliberately uses a fresh StateService directory and never reads the
user's real database, credentials, microphone, or model files.  It samples
the rendered SVG and the complete process tree so a 30-minute run can expose
DOM growth, stale animation timers, or an accumulating WebEngine process.
"""

import json
import os
import tempfile
import time
from pathlib import Path

if not os.environ.get("COCO_STABILITY_NATIVE"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

import psutil
from PySide6.QtCore import QPoint, Qt, QThread, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from coco.state import ROOT, StateService
from coco.ui import Controller, STYLE


def process_tree_rss(process):
    total = 0
    processes = [process]
    try:
        processes.extend(process.children(recursive=True))
    except (psutil.Error, OSError):
        pass
    for item in processes:
        try:
            total += item.memory_info().rss
        except (psutil.Error, OSError):
            continue
    return total


def process_tree_details(process):
    processes = [process]
    try:
        processes.extend(process.children(recursive=True))
    except (psutil.Error, OSError):
        pass
    details = []
    for item in processes:
        try:
            details.append({
                "pid": item.pid,
                "name": item.name(),
                "rss_mib": round(item.memory_info().rss / 1024 / 1024, 2),
                "cmdline": " ".join(item.cmdline())[:240],
            })
        except (psutil.Error, OSError):
            continue
    return details


def read_snapshot(controller):
    result = []
    controller.pet.character.page().runJavaScript(
        "JSON.stringify({dom: document.querySelectorAll('*').length, "
        "snapshot: window.coco.snapshot(), render: window.coco.renderSnapshot()})",
        lambda value: result.append(value),
    )
    for _ in range(100):
        QTest.qWait(20)
        if result:
            value = json.loads(result[0])
            render = value["render"]
            snapshot = value["snapshot"]
            return {
                "dom": value["dom"],
                "state": snapshot["state"],
                "body": render["body"],
                "eyes": render["eyes"],
                "diagnostics": snapshot.get("diagnostics", {}),
            }
    raise AssertionError("Nova renderer snapshot timed out")


def qt_runtime_counts(controller):
    timers = controller.findChildren(QTimer)
    threads = controller.findChildren(QThread)
    return {
        "timers": len(timers),
        "active_timers": sum(timer.isActive() for timer in timers),
        "threads": len(threads),
        "running_threads": sum(thread.isRunning() for thread in threads),
    }


def main():
    duration = int(os.environ.get("NOVA_STABILITY_SECONDS", "1800"))
    idle_only = bool(os.environ.get("NOVA_STABILITY_IDLE_ONLY"))
    snapshot_interval = int(os.environ.get("NOVA_STABILITY_SNAPSHOT_INTERVAL", "10"))
    event_names = {
        item.strip().lower()
        for item in os.environ.get("NOVA_STABILITY_EVENTS", "states,gaze,reactions").split(",")
        if item.strip()
    }
    if duration < 1:
        raise ValueError("NOVA_STABILITY_SECONDS must be positive")

    app = QApplication([])
    app.setStyleSheet(STYLE)
    scratch = ROOT / "10_临时文件_确认后可删除" / "coco_test"
    run = Path(tempfile.mkdtemp(prefix="nova_stability_", dir=scratch))
    service = StateService(run / "ui.sqlite3")
    controller = Controller(service)
    process = psutil.Process()
    samples = []
    try:
        controller.start()
        if os.environ.get("NOVA_STABILITY_DISABLE_GAZE_TIMER"):
            controller.pet.gaze_timer.stop()
        if os.environ.get("NOVA_STABILITY_DISABLE_IDLE_TIMER"):
            controller.idle_timer.stop()
        if idle_only:
            controller.idle_timer.stop()
        for _ in range(200):
            QTest.qWait(100)
            if controller.pet.character.ready:
                break
        if not controller.pet.character.ready:
            raise AssertionError("Nova renderer did not initialize")

        first = read_snapshot(controller)
        samples.append({
            "seconds": 0,
            "rss_bytes": process_tree_rss(process),
            "qt_runtime": qt_runtime_counts(controller),
            **first,
        })
        rss_history = [{"seconds": 0, "rss_mib": round(process_tree_rss(process) / 1024 / 1024, 2)}]

        states = ("idle", "thinking", "working", "listening", "curious", "idle")
        for second in range(1, duration + 1):
            if not idle_only and "states" in event_names and second % 15 == 0:
                controller.pet.character.set_state(states[(second // 15) % len(states)], transient=False)
            if not idle_only and "gaze" in event_names and second % 20 == 5:
                controller.pet.character.gaze(QPoint(205, 40))
            elif not idle_only and "gaze" in event_names and second % 20 == 10:
                controller.pet.character.gaze(QPoint(20, 180))
            elif not idle_only and "gaze" in event_names and second % 20 == 15:
                controller.pet.character.clear_gaze()
            if not idle_only and "reactions" in event_names and second % 45 == 30:
                controller.pet.character.react("happy", "spark", 900)
            if not idle_only and "reactions" in event_names and second % 60 == 45:
                controller.pet.character.drag_release("sway", 0.55)

            QTest.qWait(1000)
            if second % 30 == 0:
                rss_history.append({"seconds": second, "rss_mib": round(process_tree_rss(process) / 1024 / 1024, 2)})
            if (snapshot_interval > 0 and second % snapshot_interval == 0) or second == duration:
                snapshot = read_snapshot(controller)
                samples.append({
                    "seconds": second,
                    "rss_bytes": process_tree_rss(process),
                    "qt_runtime": qt_runtime_counts(controller),
                    **snapshot,
                })

        dom_values = [item["dom"] for item in samples]
        rss_values = [item["rss_bytes"] for item in samples]
        if max(dom_values) != min(dom_values):
            raise AssertionError(f"DOM node count changed: {min(dom_values)}..{max(dom_values)}")
        report = {
            "result": "PASS",
            "duration_seconds": duration,
            "samples": len(samples),
            "dom_nodes": dom_values[0],
            "rss_start_mib": round(rss_values[0] / 1024 / 1024, 2),
            "rss_end_mib": round(rss_values[-1] / 1024 / 1024, 2),
            "rss_peak_mib": round(max(rss_values) / 1024 / 1024, 2),
            "rss_growth_mib": round((max(rss_values) - rss_values[0]) / 1024 / 1024, 2),
            "rss_history": rss_history,
            "qt_runtime_start": samples[0]["qt_runtime"],
            "qt_runtime_end": samples[-1]["qt_runtime"],
            "renderer_diagnostics_start": samples[0]["diagnostics"],
            "renderer_diagnostics_end": samples[-1]["diagnostics"],
            "process_tree": process_tree_details(process),
            "final_state": samples[-1]["state"],
            "run_dir": str(run),
        }
        print(json.dumps(report, ensure_ascii=False))
    finally:
        controller.quit()
        for _ in range(100):
            app.processEvents()
            QTest.qWait(20)
        service.close()


if __name__ == "__main__":
    main()
