"""Separate packaged assets from writable per-user data."""
import hashlib
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, 'frozen', False))
SOURCE_ROOT = Path(__file__).resolve().parents[3] if not FROZEN else None
BUNDLE = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parents[1]
APP_DIR = Path(sys.executable).parent if FROZEN else BUNDLE
ROOT = SOURCE_ROOT if not FROZEN else APP_DIR
PACKAGE_SIGNATURE = 'nova-original-visual-20260915'
INSTANCE_DIR_NAME = 'NovaOrbDesktop'
if FROZEN:
    default_data = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'CocoDesktop'
    DATA = Path(os.environ.get('COCO_DATA_DIR', str(default_data))).expanduser()
else:
    DATA = SOURCE_ROOT / '05_记忆与状态数据'
PROFILE_FILE = BUNDLE / 'config/coco_profile.json' if FROZEN else SOURCE_ROOT / '04_桌面桌宠程序/04_配置文件/coco_profile.json'
MODEL_DIR = BUNDLE / 'models/faster-whisper-small' if FROZEN else SOURCE_ROOT / '04_桌面桌宠程序/06_语音模型/faster-whisper-small'
SPEAKER_MODEL_NAME = '3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx'
SPEAKER_MODEL_DIR = BUNDLE / 'models/speaker' if FROZEN else SOURCE_ROOT / '04_桌面桌宠程序/06_语音模型/speaker'
SPEAKER_MODEL_FILE = SPEAKER_MODEL_DIR / SPEAKER_MODEL_NAME
SPEAKER_MODEL_SHA256 = 'F682B514C05D947EE3FA91CD6EC6C5C7543479A128373FA29B1FAEDCCD21FD11'
SPEAKER_PROFILE_FILE = DATA / '04_本地凭据/nova_speaker.dpapi'
ICON_FILE = BUNDLE / 'brand/Nova_Orb.ico' if FROZEN else SOURCE_ROOT / '04_桌面桌宠程序/02_角色图片与动画/品牌图标/Nova_Orb.ico'
# Optional DPAPI ciphertext lives outside SQLite and is never copied into a
# model package or included in export()/backup() results.
def credential_file(scope='https://api.deepseek.com/chat/completions'):
    """Return a per-endpoint DPAPI ciphertext path without storing the URL."""
    digest = hashlib.sha256(str(scope).encode('utf-8')).hexdigest()[:20]
    return DATA / f'04_本地凭据/api_key_{digest}.dpapi'


CREDENTIAL_FILE = credential_file()


def instance_namespace():
    """Return one user-level namespace for source and frozen launches alike.

    The Nova package deliberately has a different lock/IPC signature from the
    earlier Coco/Saturday package. Its data directory remains compatible with
    the historical ``CocoDesktop`` location, while the lock and local server
    live under a Nova-specific directory so both installed versions can exist
    and run without activating each other's window.
    """
    configured = os.environ.get("COCO_INSTANCE_DIR")
    base = configured or (Path(os.environ.get("LOCALAPPDATA", Path.home())) / INSTANCE_DIR_NAME)
    return Path(base).expanduser().resolve()


def instance_server_name():
    identity = f'{PACKAGE_SIGNATURE}\0{instance_namespace()}'
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]
    return 'nova-orb-' + digest


def migrate_legacy():
    """Copy legacy data once via SQLite's backup API, never bundle it in the app."""
    if not FROZEN:
        return None
    target = DATA / '01_本地数据库/coco.sqlite3'
    if target.exists():
        return None
    legacy = None
    for parent in (APP_DIR, *APP_DIR.parents):
        if (parent / '项目资料存放说明.md').is_file():
            candidate = parent / '05_记忆与状态数据/01_本地数据库/coco.sqlite3'
            if candidate.is_file():
                legacy = candidate
            break
    if legacy is None or legacy.resolve() == target.resolve():
        return None
    import sqlite3
    target.parent.mkdir(parents=True, exist_ok=True)
    # The source remains untouched; SQLite backup also works while the old app
    # has an open connection and avoids copying a partially written file.
    with sqlite3.connect(legacy.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return target
