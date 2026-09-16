# -*- mode: python ; coding: utf-8 -*-
"""Local Nova Orb onedir build plus its isolated Whisper worker.

Run this spec with PyInstaller from the repository root.  It puts both
executables in one directory so the frozen controller can start
``CocoSpeech.exe`` beside itself, while the shared COLLECT payload is copied
only once.  The source checkout, model and profile remain outside the
generated package; credentials and private SQLite state are never collected.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


SPEC_ROOT = Path(SPECPATH)
SOURCE = SPEC_ROOT
PROJECT = SOURCE.parent
MODEL = PROJECT / "06_语音模型/faster-whisper-small"
SPEAKER_MODEL = PROJECT / "06_语音模型/speaker"
PROFILE = PROJECT / "04_配置文件/coco_profile.json"
BRAND = PROJECT / "02_角色图片与动画/品牌图标"
ENTRY = SPEC_ROOT / "coco_build_entry.py"
WORKER_ENTRY = SPEC_ROOT / "coco_build_speech_entry.py"
QT_RUNTIME_HOOK = SPEC_ROOT / "coco_qt_runtime.py"
SPEAKER_NOTICE = SOURCE / "coco/speaker_model_notice.txt"
THIRD_PARTY_NOTICE = SOURCE.parents[1] / "THIRD_PARTY_NOTICES.md"


datas = [
    (str(SOURCE / "coco/web"), "coco/web"),
    (str(SOURCE / "coco/wake.ps1"), "coco"),
    (str(PROFILE), "config"),
    (str(MODEL), "models/faster-whisper-small"),
    (str(SPEAKER_MODEL), "models/speaker"),
    (str(SPEAKER_NOTICE), "coco"),
    (str(THIRD_PARTY_NOTICE), "licenses"),
    (str(BRAND / "Nova_Orb.svg"), "brand"),
    (str(BRAND / "Nova_Orb_preview.png"), "brand"),
    (str(BRAND / "Nova_Orb.ico"), "brand"),
]

hiddenimports = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtMultimedia",
    "PySide6.QtNetwork",
    "win32com.client",
    "pythoncom",
    "win32gui",
    "win32process",
    "win32api",
    "win32con",
]
binaries = []
for package in ("faster_whisper", "ctranslate2", "onnxruntime", "sherpa_onnx"):
    datas.extend(collect_data_files(package))
    binaries.extend(collect_dynamic_libs(package))
hiddenimports.extend(collect_submodules("faster_whisper"))
hiddenimports.extend(["ctranslate2", "onnxruntime", "sherpa_onnx"])

a = Analysis(
    [str(ENTRY), str(WORKER_ENTRY)],
    pathex=[str(SOURCE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(QT_RUNTIME_HOOK)],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# The build environment also exposes Poppler's ICU 78 DLL.  Qt 6 imports the
# unsuffixed ICU ABI supplied by Windows; retaining Poppler's DLL under the
# same name makes QtCore fail before Python starts.  Replace that collected
# entry with the system ABI and let the runtime hook preload the matching CRT.
a.binaries = [item for item in a.binaries if item[0].lower() not in {"icuuc.dll", "icudt78.dll"}]
system_icu = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/icuuc.dll"
if system_icu.is_file():
    a.binaries.append(("icuuc.dll", str(system_icu), "BINARY"))
pyz = PYZ(a.pure)

# Recent PyInstaller versions prepend runtime hooks to ``Analysis.scripts``.
# Select each real entry explicitly and retain every runtime hook in both
# executables; slicing by index would silently build a worker that exits
# without running its entry module.
entry_paths = {ENTRY.resolve(), WORKER_ENTRY.resolve()}
entry_by_path = {Path(item[1]).resolve(): item for item in a.scripts
                 if Path(item[1]).resolve() in entry_paths}
runtime_scripts = [item for item in a.scripts if item not in entry_by_path.values()]
coco_scripts = runtime_scripts + [entry_by_path[ENTRY.resolve()]]
speech_scripts = runtime_scripts + [entry_by_path[WORKER_ENTRY.resolve()]]

coco = EXE(
    pyz,
    coco_scripts,
    [],
    exclude_binaries=True,
    name="Coco",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(BRAND / "Nova_Orb.ico"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
speech = EXE(
    pyz,
    speech_scripts,
    [],
    exclude_binaries=True,
    name="CocoSpeech",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(BRAND / "Nova_Orb.ico"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    coco,
    speech,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NovaOrb",
)
