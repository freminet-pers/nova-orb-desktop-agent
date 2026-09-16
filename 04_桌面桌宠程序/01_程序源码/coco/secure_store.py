"""Small Windows-user-bound store for an optional Saturday API key.

The default application path keeps the key in memory only.  When the user
opts in, this module protects the value with Windows DPAPI tied to the current
user account.  The resulting file is ciphertext and is deliberately outside
SQLite exports/backups and application resources.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import tempfile
from ctypes import wintypes
from pathlib import Path


MAGIC = b"SATURDAY-DPAPI-1\n"


class SecureStoreError(Exception):
    """A safe, user-facing credential-store error without secret content."""


def available():
    return os.name == "nt"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _data_blob(value=b""):
    data = bytes(value)
    if data:
        array = (ctypes.c_byte * len(data)).from_buffer_copy(data)
        pointer = ctypes.cast(array, ctypes.POINTER(ctypes.c_byte))
    else:
        array = None
        pointer = ctypes.POINTER(ctypes.c_byte)()

    blob = _DataBlob(len(data), pointer)
    # Keep the source allocation alive for the duration of CryptProtectData.
    blob._source = array
    return blob


def _entropy(scope):
    return hashlib.sha256(("Saturday API Key\0" + str(scope or "default")).encode("utf-8")).digest()


def _blob_entropy(scope):
    """Separate entropy namespace for non-credential local protected data.

    The API-key entropy above is kept stable so existing saved keys remain
    readable.  Speaker profiles use this namespace and a model hash in their
    scope, so a profile cannot be reused with a different model format.
    """
    return hashlib.sha256(("Saturday Local Data\0" + str(scope or "default")).encode("utf-8")).digest()


def _protect_bytes(value, scope="default", description=b"Saturday local data"):
    if not available():
        raise SecureStoreError("Windows 用户加密不可用。")
    data = bytes(value or b"")
    if not data:
        raise SecureStoreError("没有可保存的本机数据。")
    source = _data_blob(data)
    entropy = _data_blob(_blob_entropy(scope))
    desc = _data_blob(description)
    target = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.POINTER(_DataBlob),
                                         ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                         wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(ctypes.byref(source), ctypes.byref(desc), ctypes.byref(entropy), None, None, 0,
                                    ctypes.byref(target)):
        raise SecureStoreError("Windows 用户加密保存失败。")
    try:
        return bytes(ctypes.string_at(target.pbData, target.cbData))
    finally:
        if target.pbData:
            kernel32.LocalFree(target.pbData)


def _unprotect_bytes(blob, scope="default"):
    if not available():
        raise SecureStoreError("Windows 用户加密不可用。")
    source = _data_blob(blob)
    entropy = _data_blob(_blob_entropy(scope))
    target = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.POINTER(_DataBlob),
                                           ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0,
                                      ctypes.byref(target)):
        raise SecureStoreError("Windows 用户加密读取失败。")
    try:
        return bytes(ctypes.string_at(target.pbData, target.cbData))
    finally:
        if target.pbData:
            kernel32.LocalFree(target.pbData)


def protect_blob(value, scope="default"):
    """Protect opaque local bytes with the current Windows user account."""
    return _protect_bytes(value, scope=scope)


def unprotect_blob(value, scope="default"):
    """Unprotect opaque local bytes; callers must handle SecureStoreError."""
    return _unprotect_bytes(value, scope=scope)


def _protect(value, scope="default"):
    if not available():
        raise SecureStoreError("Windows 用户加密不可用；密钥仅保存在本次运行中。")
    if not value:
        raise SecureStoreError("没有可保存的 API Key。")
    source = _data_blob(value.encode("utf-8"))
    description = _data_blob(b"Saturday API Key")
    entropy = _data_blob(_entropy(scope))
    target = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.POINTER(_DataBlob),
                                         ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                         wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(ctypes.byref(source), ctypes.byref(description), ctypes.byref(entropy), None, None, 0,
                                    ctypes.byref(target)):
        raise SecureStoreError("Windows 用户加密保存失败；密钥仍只保留在本次运行中。")
    try:
        return bytes(ctypes.string_at(target.pbData, target.cbData))
    finally:
        if target.pbData:
            kernel32.LocalFree(target.pbData)


def _unprotect(blob, scope="default"):
    if not available():
        raise SecureStoreError("Windows 用户加密不可用。")
    source = _data_blob(blob)
    entropy = _data_blob(_entropy(scope))
    target = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.POINTER(_DataBlob),
                                           ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0, ctypes.byref(target)):
        raise SecureStoreError("Windows 用户加密读取失败；请重新输入 API Key。")
    try:
        return ctypes.string_at(target.pbData, target.cbData).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise SecureStoreError("Windows 用户加密数据无效；请重新输入 API Key。") from None
    finally:
        if target.pbData:
            kernel32.LocalFree(target.pbData)


def save(path: Path, value: str, scope="default"):
    """Protect and atomically write a key; never writes plaintext."""
    protected = base64.b64encode(_protect(str(value), scope)).decode("ascii")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".saturday-key-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="") as stream:
            stream.write(MAGIC.decode("ascii"))
            stream.write(protected)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return target


def load(path: Path, scope="default"):
    target = Path(path)
    if not target.is_file():
        return None
    try:
        raw = target.read_bytes()
        if not raw.startswith(MAGIC):
            raise SecureStoreError("本机加密数据格式无效；请重新输入 API Key。")
        blob = base64.b64decode(raw[len(MAGIC):], validate=True)
        value = _unprotect(blob, scope)
        return value if value else None
    except SecureStoreError:
        raise
    except (OSError, ValueError):
        raise SecureStoreError("本机加密数据无法读取；请重新输入 API Key。") from None


def clear(path: Path):
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        raise SecureStoreError("无法清除本机保存的 API Key，请检查数据目录权限。") from None
