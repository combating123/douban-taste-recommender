from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Mapping
from urllib.parse import quote

from .privacy import scrub_sensitive


AUTH_COOKIE_NAME = "dbcl2"
DOUBAN_SUFFIX = "douban.com"
AUTH_TIMEOUT_SECONDS = 10 * 60
CDP_POLL_SECONDS = 1.0
CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _is_douban_domain(domain: object) -> bool:
    clean = str(domain or "").strip().lower().lstrip(".")
    return clean == DOUBAN_SUFFIX or clean.endswith(f".{DOUBAN_SUFFIX}")


def douban_cookie_header(cookies: Iterable[Mapping[str, object]]) -> str:
    selected: dict[str, str] = {}
    order: list[str] = []
    now = time.time()
    for cookie in cookies or ():
        if not isinstance(cookie, Mapping) or not _is_douban_domain(cookie.get("domain")):
            continue
        try:
            expires = float(cookie.get("expires") or 0)
        except (TypeError, ValueError):
            expires = 0.0
        if expires > 0 and expires <= now:
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "").strip()
        if not name or not value or any(marker in name + value for marker in ("\r", "\n", ";")):
            continue
        if name not in selected:
            order.append(name)
        selected[name] = value
    return "; ".join(f"{name}={selected[name]}" for name in order)


def is_authenticated_cookie(header: object) -> bool:
    for part in str(header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name.strip() == AUTH_COOKIE_NAME and bool(value.strip()):
            return True
    return False


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _input_blob(value: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(value, len(value))
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return _DataBlob(len(value), pointer), buffer


def _dpapi_transform(value: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is unavailable")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    source, source_buffer = _input_blob(value)
    _ = source_buffer
    output = _DataBlob()
    if protect:
        operation = crypt32.CryptProtectData
        operation.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_wchar_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        operation.restype = ctypes.c_int
        succeeded = operation(
            ctypes.byref(source),
            "CineScope Douban authorization",
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output),
        )
    else:
        operation = crypt32.CryptUnprotectData
        operation.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        operation.restype = ctypes.c_int
        succeeded = operation(
            ctypes.byref(source),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output),
        )
    if not succeeded:
        raise OSError(ctypes.get_last_error(), "Windows DPAPI operation failed")
    try:
        return ctypes.string_at(output.pbData, int(output.cbData))
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(output.pbData)


def protect_with_dpapi(value: bytes) -> bytes:
    return _dpapi_transform(value, protect=True)


def unprotect_with_dpapi(value: bytes) -> bytes:
    return _dpapi_transform(value, protect=False)


class ProtectedCookieStore:
    def __init__(
        self,
        path: Path | str,
        *,
        protect: Callable[[bytes], bytes] = protect_with_dpapi,
        unprotect: Callable[[bytes], bytes] = unprotect_with_dpapi,
    ):
        self.path = Path(path).expanduser().resolve()
        self.protect = protect
        self.unprotect = unprotect
        self._lock = threading.RLock()

    def save(self, header: str) -> None:
        clean = str(header or "").strip()
        if not is_authenticated_cookie(clean):
            raise ValueError("authenticated Douban session was not found")
        protected = self.protect(clean.encode("utf-8"))
        payload = {
            "version": 1,
            "protected": base64.b64encode(protected).decode("ascii"),
            "updated_at": time.time(),
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(encoded, encoding="utf-8")
            temporary.replace(self.path)

    def load(self) -> str:
        with self._lock:
            if not self.path.exists():
                return ""
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                protected = base64.b64decode(str(payload.get("protected") or ""), validate=True)
                header = self.unprotect(protected).decode("utf-8")
            except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
                return ""
        return header if is_authenticated_cookie(header) else ""

    def has_session(self) -> bool:
        return bool(self.load())

    def clear(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)
            self.path.with_suffix(self.path.suffix + ".tmp").unlink(missing_ok=True)


def find_browser_executable() -> tuple[str, Path]:
    environment = os.environ
    candidates = [
        (
            "Microsoft Edge",
            Path(environment.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
        ),
        (
            "Microsoft Edge",
            Path(environment.get("ProgramFiles", r"C:\Program Files"))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
        ),
        (
            "Google Chrome",
            Path(environment.get("ProgramFiles", r"C:\Program Files"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
        ),
        (
            "Google Chrome",
            Path(environment.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
        ),
        (
            "Google Chrome",
            Path(environment.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ),
    ]
    for name, candidate in candidates:
        if candidate.is_file():
            return name, candidate.resolve()
    for command, name in (("msedge", "Microsoft Edge"), ("chrome", "Google Chrome")):
        found = shutil.which(command)
        if found:
            return name, Path(found).resolve()
    raise FileNotFoundError("Microsoft Edge or Google Chrome was not found")


def reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def launch_auth_browser(executable: Path, profile_dir: Path, port: int, url: str):
    profile_dir.mkdir(parents=True, exist_ok=True)
    arguments = [
        str(executable),
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={int(port)}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        str(url),
    ]
    return subprocess.Popen(
        arguments,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def _browser_websocket_url(port: int) -> str:
    request = urllib.request.Request(
        f"http://127.0.0.1:{int(port)}/json/version",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=2.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload.get("webSocketDebuggerUrl") or "").strip()


def _cdp_cookies(websocket_url: str) -> list[dict[str, object]]:
    import websocket

    connection = websocket.create_connection(
        websocket_url,
        timeout=3.0,
        origin="http://127.0.0.1",
        http_proxy_host=None,
    )
    try:
        request_id = int(time.time() * 1000) % 2_000_000_000
        connection.send(json.dumps({"id": request_id, "method": "Storage.getCookies"}))
        deadline = time.time() + 4.0
        while time.time() < deadline:
            message = json.loads(connection.recv())
            if int(message.get("id") or 0) != request_id:
                continue
            if message.get("error"):
                raise RuntimeError("browser authorization channel rejected the cookie request")
            result = message.get("result") if isinstance(message.get("result"), dict) else {}
            cookies = result.get("cookies") if isinstance(result, dict) else []
            return [dict(cookie) for cookie in cookies if isinstance(cookie, dict)]
        raise TimeoutError("browser authorization channel did not respond")
    finally:
        connection.close()


def capture_douban_cookie(port: int, stop_event: threading.Event, process) -> str:
    deadline = time.time() + AUTH_TIMEOUT_SECONDS
    while not stop_event.is_set() and time.time() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("authorization browser was closed before login completed")
        try:
            websocket_url = _browser_websocket_url(port)
            if websocket_url:
                header = douban_cookie_header(_cdp_cookies(websocket_url))
                if is_authenticated_cookie(header):
                    return header
        except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError):
            pass
        stop_event.wait(CDP_POLL_SECONDS)
    if stop_event.is_set():
        return ""
    raise TimeoutError("Douban browser authorization timed out")


class BrowserAuthManager:
    ACTIVE_STATES = {"opening_browser", "waiting_for_login", "authorized", "resuming"}

    def __init__(
        self,
        store: ProtectedCookieStore,
        profile_dir: Path | str,
        *,
        browser_locator: Callable[[], tuple[str, Path]] = find_browser_executable,
        process_launcher: Callable[[Path, Path, int, str], object] = launch_auth_browser,
        cookie_capture: Callable[[int, threading.Event, object], str] = capture_douban_cookie,
        on_authorized: Callable[[], Mapping[str, object] | None] | None = None,
        now: Callable[[], float] = time.time,
    ):
        self.store = store
        self.profile_dir = Path(profile_dir).expanduser().resolve()
        self.browser_locator = browser_locator
        self.process_launcher = process_launcher
        self.cookie_capture = cookie_capture
        self.on_authorized = on_authorized
        self.now = now
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._attempt_stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process = None
        timestamp = self.now()
        self._status: dict[str, object] = {
            "state": "idle",
            "has_session": self.store.has_session(),
            "user_id": "",
            "job_id": "",
            "browser": "",
            "error": "",
            "started_at": 0.0,
            "updated_at": timestamp,
        }

    def _public_locked(self, **extra: object) -> dict[str, object]:
        payload = dict(self._status)
        payload["has_session"] = self.store.has_session()
        payload.update(extra)
        return payload

    def status(self) -> dict[str, object]:
        with self._lock:
            return self._public_locked()

    def _set_status(self, state: str, **changes: object) -> dict[str, object]:
        with self._lock:
            self._status.update(changes)
            self._status["state"] = str(state or "error")
            self._status["updated_at"] = self.now()
            return self._public_locked()

    def start(self, user_id: str = "", job_id: str = "") -> dict[str, object]:
        with self._lock:
            if self._closed.is_set():
                return self._public_locked(state="error", error="browser authorization manager is closed")
            if self._thread is not None and self._thread.is_alive():
                return self._public_locked(reused=True)
            self._attempt_stop = threading.Event()
            started_at = self.now()
            self._status.update(
                {
                    "state": "opening_browser",
                    "user_id": str(user_id or "").strip(),
                    "job_id": str(job_id or "").strip(),
                    "browser": "",
                    "error": "",
                    "started_at": started_at,
                    "updated_at": started_at,
                }
            )
            snapshot = self._public_locked(reused=False)
            self._thread = threading.Thread(
                target=self._run,
                name="cinescope-browser-authorization",
                daemon=True,
            )
            self._thread.start()
            return snapshot

    def _run(self) -> None:
        process = None
        try:
            header = self.store.load()
            if not header:
                browser_name, executable = self.browser_locator()
                port = reserve_local_port()
                with self._lock:
                    user_id = str(self._status.get("user_id") or "")
                target = f"https://movie.douban.com/people/{quote(user_id, safe='')}/collect" if user_id else "https://www.douban.com/accounts/login"
                process = self.process_launcher(executable, self.profile_dir, port, target)
                with self._lock:
                    self._process = process
                self._set_status("waiting_for_login", browser=browser_name)
                header = self.cookie_capture(port, self._attempt_stop, process)
                if not header:
                    if not self._closed.is_set():
                        self._set_status("idle")
                    return
                if not is_authenticated_cookie(header):
                    raise ValueError("Douban login session was not detected")
                self.store.save(header)
            self._set_status("authorized", error="")
            callback = self.on_authorized
            if callback is None:
                return
            self._set_status("resuming")
            raw_result = callback() or {}
            result = dict(raw_result) if isinstance(raw_result, Mapping) else {}
            safe_result = scrub_sensitive(result)
            next_state = str(safe_result.get("state") or "queued")
            changes = {
                key: safe_result[key]
                for key in ("job_id", "resume_of", "user_id", "reused", "resumed", "authorization_required")
                if key in safe_result
            }
            if next_state == "needs_cookie":
                self.store.clear()
                self._set_status("error", error="saved browser session was rejected", **changes)
            else:
                self._set_status(next_state, error="", **changes)
        except Exception as exc:
            safe_error = str(scrub_sensitive(str(exc))) or exc.__class__.__name__
            self._set_status("error", error=safe_error)
        finally:
            if process is not None:
                try:
                    if process.poll() is None:
                        process.terminate()
                except (OSError, AttributeError):
                    pass
            with self._lock:
                if self._process is process:
                    self._process = None

    def invalidate(self) -> None:
        self.store.clear()
        self._set_status("idle", error="")

    def close(self) -> None:
        self._closed.set()
        self._attempt_stop.set()
        with self._lock:
            process = self._process
            thread = self._thread
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
            except (OSError, AttributeError):
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)