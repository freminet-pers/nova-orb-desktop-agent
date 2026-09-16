"""Small, allow-listed Windows tools for Nova's structured agent loop.

The model can select a tool, but it cannot supply shell text, arbitrary
process arguments, coordinates, or an unbounded filesystem path.  Every tool
returns a typed result so the caller can distinguish execution from a model
claim.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .paths import DATA, ROOT

try:  # pywin32 is optional in source tests on non-Windows hosts.
    import win32api
    import win32con
    import win32gui
    import win32process
except ImportError:  # pragma: no cover - Windows package path
    win32api = None
    win32con = None
    win32gui = None
    win32process = None


MAX_TOOL_TEXT = 4000
MAX_FILE_CHARS = 50000
MAX_STEPS = 6


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open one uniquely named application from Nova's registered application catalog.",
            "strict": True,
            "parameters": {"type": "object", "properties": {"name": {"type": "string", "maxLength": 100}}, "required": ["name"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "List visible top-level Windows windows by title and process id; do not read their document contents.",
            "strict": True,
            "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Focus one visible window by an exact or unique title fragment supplied by the user.",
            "strict": True,
            "parameters": {"type": "object", "properties": {"title": {"type": "string", "maxLength": 200}}, "required": ["title"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type user-provided text only into a uniquely identified visible Notepad/WordPad-style text editor after re-focusing it. No hotkeys or generated commands are accepted.",
            "strict": True,
            "parameters": {"type": "object", "properties": {"title": {"type": "string", "maxLength": 200}, "text": {"type": "string", "maxLength": 2000}}, "required": ["title", "text"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_new_text_file",
            "description": "Create a new text file in the allowed project/Documents/Desktop directories; never overwrite an existing file.",
            "strict": True,
            "parameters": {"type": "object", "properties": {"path": {"type": "string", "maxLength": 500}, "content": {"type": "string", "maxLength": 4000}}, "required": ["path", "content"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "Read a small user-selected text file from an allowed directory; do not read databases, credentials, or environment files.",
            "strict": True,
            "parameters": {"type": "object", "properties": {"path": {"type": "string", "maxLength": 500}, "max_chars": {"type": "integer", "minimum": 1, "maximum": 50000}}, "required": ["path"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_path",
            "description": "Open a user-selected existing text file or folder through the normal Windows association; applications and scripts require the application catalog.",
            "strict": True,
            "parameters": {"type": "object", "properties": {"path": {"type": "string", "maxLength": 500}}, "required": ["path"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a user-requested public http(s) URL in the normal browser; never use file, javascript, data, credentials, or generated URLs with secrets.",
            "strict": True,
            "parameters": {"type": "object", "properties": {"url": {"type": "string", "maxLength": 2000}}, "required": ["url"], "additionalProperties": False},
        },
    },
]


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    kind: str
    message: str
    data: dict = field(default_factory=dict)

    def as_payload(self):
        return {"ok": self.ok, "kind": self.kind, "message": self.message, "data": self.data}


class ToolCancelled(Exception):
    pass


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise ToolCancelled()


def _allowed_roots():
    home = Path.home()
    roots = [ROOT.resolve(), DATA.resolve()]
    for name in ("Documents", "Desktop"):
        candidate = home / name
        if candidate.is_dir():
            roots.append(candidate.resolve())
    # Keep deterministic order and remove duplicates.
    output = []
    for root in roots:
        if root not in output:
            output.append(root)
    return tuple(output)


def _safe_path(raw, *, must_exist=False, text_only=False):
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise ValueError("路径不能为空")
    candidate = Path(os.path.expanduser(raw.strip()))
    if not candidate.is_absolute():
        raise ValueError("Agent 只接受完整绝对路径")
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise ValueError("路径无法解析") from exc
    if not any(resolved == root or root in resolved.parents for root in _allowed_roots()):
        raise ValueError("路径不在 Nova 允许的项目、Documents 或 Desktop 目录内")
    name = resolved.name.casefold()
    if any(token in name for token in (".env", "secret", "credential", "password", "token", "api_key", "apikey")):
        raise ValueError("凭据或环境文件不交给 Agent 读取")
    if resolved.suffix.casefold() in {".sqlite", ".sqlite3", ".db", ".dpapi", ".pem", ".key", ".pfx"}:
        raise ValueError("数据库和凭据文件不交给 Agent 处理")
    if text_only and resolved.suffix.casefold() not in {".txt", ".md", ".csv", ".json", ".log", ".ini", ".yaml", ".yml"}:
        raise ValueError("只允许常见文本文件扩展名")
    if must_exist and not resolved.is_file():
        raise ValueError("文件不存在")
    return resolved


def _visible_windows():
    if win32gui is None:
        return []
    rows = []

    def callback(hwnd, _extra):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = str(win32gui.GetWindowText(hwnd) or "").strip()
        if not title:
            return True
        pid = 0
        if win32process is not None:
            try:
                _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                pid = 0
        rows.append({"title": title[:240], "pid": int(pid), "hwnd": int(hwnd)})
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception as exc:
        raise RuntimeError("无法读取 Windows 窗口列表") from exc
    return rows


def _find_window(title):
    query = str(title or "").strip().casefold()
    if not query:
        raise ValueError("请提供窗口标题")
    rows = _visible_windows()
    exact = [row for row in rows if row["title"].casefold() == query]
    matches = exact or [row for row in rows if query in row["title"].casefold()]
    if not matches:
        raise ValueError("没有找到这个可见窗口")
    if len(matches) > 1:
        raise ValueError("窗口标题不唯一，请提供更完整的标题")
    return matches[0]


def _focus_window(row):
    if win32gui is None:
        raise RuntimeError("当前系统没有 Windows UI 支持")
    hwnd = int(row["hwnd"])
    try:
        win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
        win32gui.SetForegroundWindow(hwnd)
        if int(win32gui.GetForegroundWindow()) != hwnd:
            raise RuntimeError("目标窗口没有取得前台焦点")
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError("Windows 拒绝了窗口聚焦请求") from exc
    return row


def _safe_text_target(row):
    """Only allow a verified editor process and child edit control."""
    title = str(row.get("title", "")).casefold()
    denied = ("powershell", "cmd", "terminal", "命令提示", "运行", "run ",
              "chrome", "edge", "firefox", "浏览器", "devtools", "开发者",
              "地址栏", "password", "密码", "登录", "login", "安全", "设置")
    if any(token in title for token in denied):
        return False
    if not any(token in title for token in ("记事本", "notepad", "写字板", "wordpad", "text editor", "文本编辑器")):
        return False
    process_path = _window_process_path(row)
    if not process_path or Path(process_path).name.casefold() not in {"notepad.exe", "wordpad.exe"}:
        return False
    return _has_edit_control(row)


def _window_process_path(row):
    if win32api is None or win32process is None or not row.get("pid"):
        return None
    handle = None
    try:
        rights = getattr(win32con, "PROCESS_QUERY_LIMITED_INFORMATION", 0x1000) | getattr(win32con, "PROCESS_VM_READ", 0x0010)
        handle = win32api.OpenProcess(rights, False, int(row["pid"]))
        return str(win32process.GetModuleFileNameEx(handle, 0) or "")
    except Exception:
        return None
    finally:
        if handle is not None:
            try:
                win32api.CloseHandle(handle)
            except Exception:
                pass


def _has_edit_control(row):
    """Classic Notepad exposes an Edit/RichEdit child; unknown XAML windows fail closed."""
    if win32gui is None or not row.get("hwnd"):
        return False
    classes = []

    def callback(hwnd, _extra):
        try:
            classes.append(str(win32gui.GetClassName(hwnd) or "").casefold())
        except Exception:
            pass
        return True

    try:
        win32gui.EnumChildWindows(int(row["hwnd"]), callback, None)
    except Exception:
        return False
    allowed = {"edit", "richedit20w", "richedit50w", "richeditd2dpt", "textbox"}
    return any(name in allowed or "edit" in name or "textbox" in name for name in classes)


def _send_unicode(text):
    """Send UTF-16 code units without using the clipboard or shell."""
    if os.name != "nt":
        raise RuntimeError("文字输入工具只支持 Windows")

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                    ("dwExtraInfo", ctypes.c_void_p)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_uint32), ("ki", KEYBDINPUT)]

    SendInput = ctypes.windll.user32.SendInput
    SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
    SendInput.restype = ctypes.c_uint
    KEYEVENTF_UNICODE, KEYEVENTF_KEYUP = 0x0004, 0x0002
    units = text.encode("utf-16-le", errors="strict")
    sent = 0
    for index in range(0, len(units), 2):
        scan = int.from_bytes(units[index:index + 2], "little")
        down = INPUT(1, KEYBDINPUT(0, scan, KEYEVENTF_UNICODE, 0, None))
        up = INPUT(1, KEYBDINPUT(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None))
        if SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT)) != 1:
            raise RuntimeError("文字输入被 Windows 拒绝")
        if SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT)) != 1:
            raise RuntimeError("文字输入结束失败")
        sent += 1
    return sent


class AgentExecutor:
    """Execute only the named tools against the current desktop context."""

    def __init__(self, catalog=None):
        self.catalog = catalog
        self.used_call_ids = set()
        self.history = []

    def execute(self, name, arguments, cancel_event=None, call_id=None):
        _check_cancel(cancel_event)
        if call_id and call_id in self.used_call_ids:
            return ToolResult(False, "duplicate_call", "同一个工具调用已执行，不会重复操作")
        if call_id:
            self.used_call_ids.add(call_id)
        if not isinstance(arguments, dict):
            return ToolResult(False, "invalid_arguments", "工具参数必须是 JSON 对象")
        try:
            if name == "open_application":
                result = self._open_application(arguments)
            elif name == "list_windows":
                result = self._list_windows(arguments)
            elif name == "focus_window":
                result = self._focus_window(arguments)
            elif name == "type_text":
                result = self._type_text(arguments)
            elif name == "write_new_text_file":
                result = self._write_file(arguments)
            elif name == "read_text_file":
                result = self._read_file(arguments)
            elif name == "open_path":
                result = self._open_path(arguments)
            elif name == "open_url":
                result = self._open_url(arguments)
            else:
                result = ToolResult(False, "unknown_tool", "没有这个安全工具")
        except ToolCancelled:
            raise
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            result = ToolResult(False, "tool_error", str(exc))
        self.history.append({"tool": name, "ok": bool(result.ok), "kind": result.kind})
        return result

    def _open_application(self, args):
        name = str(args.get("name", "")).strip()
        if not name or self.catalog is None:
            return ToolResult(False, "not_found", "没有可用的应用目录")
        entries = self.catalog.find(name)
        if len(entries) != 1:
            if len(entries) > 1:
                return ToolResult(False, "ambiguous", "应用名称不唯一，请提供完整名称")
            return ToolResult(False, "not_found", "应用不在 Nova 的已登记目录中")
        entry = entries[0]
        message = self.catalog.launch(entry)
        return ToolResult(True, "application_started", message, {"name": entry.name})

    def _list_windows(self, _args):
        rows = _visible_windows()
        safe = [{"title": row["title"], "pid": row["pid"]} for row in rows[:80]]
        return ToolResult(True, "windows", f"找到 {len(safe)} 个可见窗口。", {"windows": safe})

    def _focus_window(self, args):
        row = _focus_window(_find_window(args.get("title", "")))
        return ToolResult(True, "window_focused", f"已聚焦窗口“{row['title']}”。", {"title": row["title"], "pid": row["pid"]})

    def _type_text(self, args):
        title = str(args.get("title", "")).strip()
        text = str(args.get("text", ""))
        if not title or not text:
            raise ValueError("窗口标题和文字都不能为空")
        if len(text) > 2000:
            raise ValueError("一次输入最多 2000 个字符")
        row = _find_window(title)
        if not _safe_text_target(row):
            raise ValueError("为了防止把文字发送到终端、浏览器或安全窗口，只允许记事本类文本编辑器")
        row = _focus_window(row)
        time.sleep(0.08)
        count = _send_unicode(text)
        return ToolResult(True, "text_typed", f"已向“{row['title']}”输入 {count} 个字符。", {"title": row["title"], "characters": count})

    def _write_file(self, args):
        path = _safe_path(args.get("path", ""), text_only=True)
        content = str(args.get("content", ""))
        if len(content) > MAX_TOOL_TEXT:
            raise ValueError("单个新文件最多 4000 个字符")
        if path.exists():
            raise ValueError("目标文件已存在，为避免覆盖没有写入")
        if not path.parent.is_dir():
            raise ValueError("目标目录不存在；请先选择已有目录")
        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)
        return ToolResult(True, "file_created", f"已创建新文件“{path}”。", {"path": str(path), "characters": len(content)})

    def _read_file(self, args):
        path = _safe_path(args.get("path", ""), must_exist=True, text_only=True)
        limit = int(args.get("max_chars", MAX_FILE_CHARS) or MAX_FILE_CHARS)
        limit = max(1, min(MAX_FILE_CHARS, limit))
        if path.stat().st_size > MAX_FILE_CHARS * 4:
            raise ValueError("文件过大，不交给 Agent 读取")
        content = path.read_text(encoding="utf-8", errors="replace")[:limit]
        return ToolResult(True, "file_read", f"已读取“{path.name}”，内容可能被截断。", {"path": str(path), "content": content, "truncated": len(content) >= limit})

    def _open_path(self, args):
        path = _safe_path(args.get("path", ""), must_exist=True)
        if path.is_file() and path.suffix.casefold() not in {".txt", ".md", ".csv", ".json", ".log", ".ini", ".yaml", ".yml"}:
            raise ValueError("open_path 只允许打开文本文件或目录；应用请使用应用目录工具")
        if os.name != "nt":
            raise RuntimeError("打开路径工具只支持 Windows")
        os.startfile(str(path))
        return ToolResult(True, "path_opened", f"已请求 Windows 打开“{path.name}”。", {"path": str(path)})

    def _open_url(self, args):
        from urllib.parse import urlsplit
        url = str(args.get("url", "")).strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.netloc:
            raise ValueError("只允许不带账号信息的 http(s) 地址")
        if "\x00" in url or any(token in url.casefold() for token in ("javascript:", "data:", "file:")):
            raise ValueError("地址协议不受支持")
        if os.name != "nt":
            raise RuntimeError("打开 URL 工具只支持 Windows")
        os.startfile(url)
        return ToolResult(True, "url_opened", "已请求浏览器打开指定网页。", {"url": url})


_OPEN_TYPE_RE = re.compile(r"^(?:请|帮我|请帮我)?\s*(?:打开|启动)\s*(?P<app>.+?)\s*(?:并|然后|，|,)?\s*(?P<verb>写入|输入|打字|键入)\s*[:：]?\s*(?P<content>.+)$", re.I)
_OPEN_RE = re.compile(r"^(?:请|帮我|请帮我)?\s*(?:打开|启动)\s*(?P<app>[^，,。；;]+?)\s*[。！!]?\s*$", re.I)
_WINDOWS_RE = re.compile(r"(?:列出|查看|看看|显示).*(?:窗口|打开的程序)", re.I)
_FOCUS_RE = re.compile(r"^(?:请|帮我|请帮我)?\s*(?:切换到|聚焦|激活)\s*(?P<title>.+?)\s*[。！!]?\s*$", re.I)
_FILE_RE = re.compile(r"^(?:请|帮我|请帮我)?\s*(?:新建|创建)\s*(?:一个)?\s*(?:文本)?文件\s*[:：]?\s*(?P<path>[^，,]+?)\s*(?:内容|写入|文本)\s*[:：]?\s*(?P<content>.+)$", re.I)
_READ_FILE_RE = re.compile(r"^(?:请|帮我|请帮我)?\s*(?:读取|查看)文件\s*[:：]?\s*(?P<path>.+?)\s*$", re.I)
_OPEN_PATH_RE = re.compile(r"^(?:请|帮我|请帮我)?\s*打开文件\s*[:：]?\s*(?P<path>.+?)\s*$", re.I)
_OPEN_URL_RE = re.compile(r"^(?:请|帮我|请帮我)?\s*(?:打开网址|打开网页)\s*[:：]?\s*(?P<url>https?://\S+)\s*$", re.I)


def local_agent_request(text, executor: AgentExecutor, cancel_event=None):
    """Handle explicit, deterministic commands without consuming an API call.

    Return ``None`` when the phrase needs model planning; otherwise return a
    ToolResult-backed user-facing string.  This keeps the core demonstration
    useful in offline mode while the structured model loop handles composition.
    """
    text = str(text or "").strip()
    if not text:
        return None
    if _WINDOWS_RE.search(text):
        return executor.execute("list_windows", {}, cancel_event=cancel_event)
    match = _READ_FILE_RE.fullmatch(text)
    if match:
        return executor.execute("read_text_file", {"path": match.group("path").strip()}, cancel_event=cancel_event)
    match = _OPEN_PATH_RE.fullmatch(text)
    if match:
        return executor.execute("open_path", {"path": match.group("path").strip()}, cancel_event=cancel_event)
    match = _OPEN_URL_RE.fullmatch(text)
    if match:
        return executor.execute("open_url", {"url": match.group("url").strip()}, cancel_event=cancel_event)
    match = _FILE_RE.fullmatch(text)
    if match:
        return executor.execute("write_new_text_file", match.groupdict(), cancel_event=cancel_event)
    match = _OPEN_TYPE_RE.fullmatch(text)
    if match:
        app = re.sub(r"[\s，,]+$", "", match.group("app")).strip()
        result = executor.execute("open_application", {"name": app}, cancel_event=cancel_event)
        if not result.ok:
            return result
        content = match.group("content").strip().strip('"“”\'')
        # Give a newly launched app a short bounded opportunity to expose its
        # window.  If it is not ready, report the real partial result instead
        # of claiming that text was entered.
        for _ in range(20):
            _check_cancel(cancel_event)
            try:
                queries = [app]
                if app.casefold() in {"记事本", "notepad"}:
                    queries.extend(["记事本", "notepad"])
                row = None
                for query in queries:
                    try:
                        row = _find_window(query)
                        break
                    except ValueError:
                        continue
                if row is None:
                    raise ValueError("窗口尚未出现")
            except ValueError:
                time.sleep(0.15)
                continue
            typed = executor.execute("type_text", {"title": row["title"], "text": content}, cancel_event=cancel_event)
            if typed.ok:
                return ToolResult(True, "application_started_and_typed", result.message + " 已输入指定文字。", {"name": app, "title": row["title"], "characters": typed.data.get("characters", len(content))})
            return typed
        return ToolResult(True, "application_started", result.message + " 窗口尚未出现，暂未输入文字。", {"name": app, "pending_text": content})
    match = _FOCUS_RE.fullmatch(text)
    if match:
        return executor.execute("focus_window", {"title": match.group("title").strip()}, cancel_event=cancel_event)
    match = _OPEN_RE.fullmatch(text)
    if match:
        return executor.execute("open_application", {"name": match.group("app").strip()}, cancel_event=cancel_event)
    return None


def is_agent_request(text):
    value = str(text or "").strip()
    if not value:
        return False
    return bool(local_agent_request.__name__ and (
        _WINDOWS_RE.search(value) or _OPEN_RE.fullmatch(value) or
        _OPEN_TYPE_RE.fullmatch(value) or _FILE_RE.fullmatch(value) or
        _READ_FILE_RE.fullmatch(value) or _OPEN_PATH_RE.fullmatch(value) or
        _OPEN_URL_RE.fullmatch(value) or _FOCUS_RE.fullmatch(value) or
        any(word in value for word in ("窗口", "写入记事本", "创建文本文件", "读取文件", "打开文件", "打开网页"))
    ))
