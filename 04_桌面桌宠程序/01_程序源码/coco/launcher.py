"""Ask the existing Windows desktop shell to launch Nova outside the editor job."""
import subprocess
import sys
from pathlib import Path


def launch(settings=False):
    import win32com.client
    source = Path(__file__).resolve().parents[1]
    executable = Path(sys.executable).with_name('pythonw.exe')
    params = subprocess.list2cmdline(['-m', 'coco'] + (['--settings'] if settings else []))
    # The desktop folder's Application is the existing Explorer process. A fresh
    # Shell.Application alone or CREATE_BREAKAWAY_FROM_JOB can retain an outer job.
    windows = win32com.client.Dispatch('Shell.Application').Windows()
    desktop = windows.FindWindowSW(0, 0, 8, 0, 1)
    desktop.Document.Application.ShellExecute(str(executable), params, str(source), 'open', 1)


if __name__ == '__main__':
    try:
        launch('--settings' in sys.argv)
        print('Nova 已由 Windows 桌面独立启动。')
    except Exception as exc:
        raise SystemExit('Nova 独立启动失败，请从资源管理器双击启动入口。错误：' + str(exc))
