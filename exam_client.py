#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from typing import Any

import requests

# PyInstaller/WebEngine 黑屏缓解
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-gpu-compositing --disable-features=VizDisplayCompositor --disable-software-rasterizer --use-angle=swiftshader --use-gl=angle --no-sandbox")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

DEFAULT_API_BASE = "https://api.nooob.top/paper"
USER_AGENT = "PaperSystem-ExamClient/4.4"


@dataclass
class StudentProfile:
    student_id: str
    name: str
    class_name: str


@dataclass
class ExamConfig:
    exam_id: str
    exam_url: str
    force_fullscreen: bool = True
    top_most: bool = True
    require_single_monitor: bool = True
    allow_force_kill: bool = False
    blocked_processes: list[str] = field(default_factory=list)
    detect_vm: bool = True
    allowed_os: list[str] = field(default_factory=lambda: ["windows"])
    require_student_login: bool = True
    max_login_attempts_per_student: int = 1
    allow_exit_hotkey: bool = True
    exit_hotkey: str = "Esc"
    focus_guard: bool = True
    class_options: list[str] = field(default_factory=list)
    heartbeat_interval_sec: int = 12
    process_scan_interval_sec: int = 3
    focus_check_interval_sec: int = 1
    key_rules: list[str] = field(default_factory=lambda: ["F12", "Print", "Alt+F4", "Ctrl+Shift+Esc", "Ctrl+Esc", "Alt+Tab", "Alt+Esc", "Win"])


class InvigilatorClient:
    def __init__(self, exam_id: str, passkey: str, ip: str, api_base: str):
        self.exam_id = exam_id
        self.passkey = passkey
        self.ip = ip
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.token: str | None = None
        self.student: StudentProfile | None = None
        self._queue: Queue[dict[str, Any]] = Queue(maxsize=3000)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def set_token(self, token: str | None) -> None:
        self.token = token

    def set_student(self, student: StudentProfile | None) -> None:
        self.student = student

    def _payload(self, event_type: str, detail: dict[str, Any]) -> dict[str, Any]:
        p: dict[str, Any] = {
            "exam_id": self.exam_id,
            "passkey": self.passkey,
            "token": self.token or "",
            "ip": self.ip,
            "event_type": event_type,
            "detail": detail,
            "client_time": datetime.utcnow().isoformat() + "Z",
            "platform": platform.platform(),
        }
        if self.student:
            p["student"] = {
                "student_id": self.student.student_id,
                "name": self.student.name,
                "class_name": self.student.class_name,
            }
        return p

    def send_event(self, event_type: str, detail: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(self._payload(event_type, detail))
        except Exception:
            pass

    def send_event_sync(self, event_type: str, detail: dict[str, Any]) -> tuple[bool, str]:
        try:
            r = self.session.post(f"{self.api_base}/invigilate.php", json=self._payload(event_type, detail), timeout=10)
            d = r.json()
            return bool(d.get("ok")), str(d.get("error", ""))
        except Exception as exc:
            return False, str(exc)

    def student_login(self, profile: StudentProfile) -> tuple[bool, str]:
        self.set_student(profile)
        return self.send_event_sync("student_login", {"status": "attempt"})

    def pull_command(self) -> dict[str, Any]:
        if not self.student:
            return {}
        try:
            r = self.session.get(
                f"{self.api_base}/command.php",
                params={
                    "mode": "pull",
                    "exam_id": self.exam_id,
                    "student_id": self.student.student_id,
                    "token": self.token or "",
                    "ip": self.ip,
                },
                timeout=6,
            )
            d = r.json()
            if d.get("ok") and isinstance(d.get("commands"), dict):
                return d["commands"]
        except Exception:
            pass
        return {}

    def ack_command(self, action: str, value: Any) -> None:
        if not self.student:
            return
        try:
            self.session.get(
                f"{self.api_base}/command.php",
                params={
                    "mode": "set",
                    "exam_id": self.exam_id,
                    "student_id": self.student.student_id,
                    "token": self.token or "",
                    "ip": self.ip,
                    "action": action,
                    "value": str(value),
                },
                timeout=5,
            )
        except Exception:
            pass

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self._queue.get(timeout=0.8)
            except Empty:
                continue
            try:
                self.session.post(f"{self.api_base}/invigilate.php", json=payload, timeout=5)
            except Exception:
                pass
            finally:
                self._queue.task_done()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.2)


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def list_processes_windows(limit: int = 80) -> list[str]:
    if platform.system().lower() != "windows":
        return []
    try:
        out = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return []
    names: list[str] = []
    for line in out.splitlines():
        cols = [x.strip().strip('"') for x in line.strip().split('","')]
        if cols and cols[0]:
            names.append(cols[0].lower())
    return names[:limit]


def kill_process_windows(name: str) -> bool:
    if platform.system().lower() != "windows":
        return False
    try:
        subprocess.check_call(["taskkill", "/F", "/IM", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def detect_virtual_machine() -> bool:
    if platform.system().lower() != "windows":
        return False
    try:
        out = subprocess.check_output(["wmic", "computersystem", "get", "model,manufacturer"], text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).lower()
    except Exception:
        return False
    return any(x in out for x in ["virtualbox", "vmware", "kvm", "qemu", "xen", "hyper-v"])


def load_config(exam_id: str, passkey: str, ip: str, api_base: str) -> tuple[ExamConfig, str | None, str]:
    r = requests.get(f"{api_base.rstrip('/')}/config.php", params={"id": exam_id, "passkey": passkey, "ip": ip}, headers={"User-Agent": USER_AGENT}, timeout=10)
    try:
        d = r.json()
    except Exception:
        raise RuntimeError(f"config not json: {r.status_code}, {r.text[:200]}")
    if not d.get("ok"):
        raise RuntimeError(str(d.get("error", "config rejected")))
    c = d.get("config", {})
    url = str(c.get("exam_url", "")).strip()
    if not url:
        raise RuntimeError("config missing exam_url")
    resolved_exam_id = str(d.get("resolved_exam_id", exam_id) or exam_id)
    return ExamConfig(
        exam_id=resolved_exam_id,
        exam_url=url,
        force_fullscreen=bool(c.get("force_fullscreen", True)),
        top_most=bool(c.get("top_most", True)),
        require_single_monitor=bool(c.get("require_single_monitor", True)),
        allow_force_kill=bool(c.get("allow_force_kill", False)),
        blocked_processes=[str(x).lower() for x in c.get("blocked_processes", [])],
        detect_vm=bool(c.get("detect_vm", True)),
        allowed_os=[str(x).lower() for x in c.get("allowed_os", ["windows"] )],
        require_student_login=bool(c.get("require_student_login", True)),
        max_login_attempts_per_student=max(1, int(c.get("max_login_attempts_per_student", 1))),
        allow_exit_hotkey=bool(c.get("allow_exit_hotkey", True)),
        exit_hotkey=str(c.get("exit_hotkey", "Esc")),
        focus_guard=bool(c.get("focus_guard", True)),
        class_options=[str(x) for x in c.get("class_options", [])],
        heartbeat_interval_sec=max(5, int(c.get("heartbeat_interval_sec", 12))),
        process_scan_interval_sec=max(1, int(c.get("process_scan_interval_sec", 3))),
        focus_check_interval_sec=max(1, int(c.get("focus_check_interval_sec", 1))),
        key_rules=[str(x) for x in c.get("key_rules", ["F12", "Print", "Alt+F4", "Ctrl+Shift+Esc", "Ctrl+Esc", "Alt+Tab", "Alt+Esc", "Win"])],
    ), d.get("session_token"), resolved_exam_id


def check_environment_conflicts(cfg: ExamConfig) -> list[str]:
    bad: list[str] = []
    os_name = platform.system().lower()
    if cfg.allowed_os and os_name not in cfg.allowed_os:
        bad.append(f"系统不允许: {os_name}")
    if cfg.require_single_monitor and len(QtGui.QGuiApplication.screens()) > 1:
        bad.append("检测到多屏幕")
    if cfg.detect_vm and detect_virtual_machine():
        bad.append("检测到虚拟机")
    hits = sorted(set(cfg.blocked_processes).intersection(set(list_processes_windows(300))))
    if hits:
        if cfg.allow_force_kill:
            failed = [p for p in hits if not kill_process_windows(p)]
            if failed:
                bad.append("禁用进程无法关闭: " + ", ".join(failed))
        else:
            bad.append("存在禁用进程: " + ", ".join(hits))
    return bad


class StartupDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("启动中")
        self.setModal(True)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        lay = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel("正在启动考试客户端，请稍候…", self)
        self.bar = QtWidgets.QProgressBar(self)
        self.bar.setRange(0, 0)
        lay.addWidget(self.label)
        lay.addWidget(self.bar)
        self.resize(360, 110)

    def set_text(self, text: str) -> None:
        self.label.setText(text)
        QtWidgets.QApplication.processEvents()


class LoginDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("考试入口")
        form = QtWidgets.QFormLayout(self)
        self.exam_id = QtWidgets.QLineEdit(self)
        self.passkey = QtWidgets.QLineEdit(self)
        self.passkey.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_base = QtWidgets.QLineEdit(self)
        self.api_base.setText(DEFAULT_API_BASE)
        form.addRow("考试 ID", self.exam_id)
        form.addRow("学生登录密码", self.passkey)
        form.addRow("API Base", self.api_base)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, parent=self)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        form.addWidget(btn)


class StudentLoginDialog(QtWidgets.QDialog):
    def __init__(self, classes: list[str]):
        super().__init__()
        self.setWindowTitle("考生登录")
        f = QtWidgets.QFormLayout(self)
        self.student_id = QtWidgets.QLineEdit(self)
        self.name = QtWidgets.QLineEdit(self)
        self.class_box = QtWidgets.QComboBox(self)
        self.class_box.addItems(classes if classes else ["默认班级"])
        f.addRow("学号", self.student_id)
        f.addRow("姓名", self.name)
        f.addRow("班级", self.class_box)
        b = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, parent=self)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        f.addWidget(b)

    def profile(self) -> StudentProfile:
        return StudentProfile(self.student_id.text().strip(), self.name.text().strip(), self.class_box.currentText().strip())


class KeyMonitor(QtCore.QObject):
    def __init__(self, inv: InvigilatorClient, rules: list[str]):
        super().__init__()
        self.inv = inv
        self._last_sent: dict[str, float] = {}
        self.rules = {self.normalize_shortcut(x) for x in rules if str(x).strip()}

    @staticmethod
    def normalize_shortcut(shortcut: str) -> str:
        s = shortcut.strip().replace(" ", "")
        s = s.replace("Control", "Ctrl")
        s = s.replace("Meta", "Win")
        return s

    def _emit(self, shortcut: str, desc: str) -> None:
        now = QtCore.QDateTime.currentDateTimeUtc().toMSecsSinceEpoch() / 1000.0
        key = f"{shortcut}:{desc}"
        if now - self._last_sent.get(key, 0.0) < 0.5:
            return
        self._last_sent[key] = now
        self.inv.send_event("suspicious_key", {"shortcut": shortcut, "description": desc, "is_cheat": True})

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if event.type() not in (QtCore.QEvent.KeyPress, QtCore.QEvent.ShortcutOverride):
            return False
        if not isinstance(event, QtGui.QKeyEvent):
            return False
        key = int(event.key())
        mods = event.modifiers()
        shortcut = self.normalize_shortcut(QtGui.QKeySequence(int(mods) | key).toString() or f"key_{key}")
        if key in (int(QtCore.Qt.Key_Meta),):
            shortcut = "Win"
        if shortcut in self.rules:
            self._emit(shortcut, f"触发受控按键: {shortcut}")
        return False


class WindowsLowLevelKeyHook:
    def __init__(self, inv: InvigilatorClient, rules: list[str]):
        self.inv = inv
        self._thread: threading.Thread | None = None
        self.rules = {self._norm(x) for x in rules if str(x).strip()}
        self._stop = threading.Event()

    @staticmethod
    def _norm(s: str) -> str:
        return s.strip().replace(" ", "").replace("Control", "Ctrl").replace("Meta", "Win")

    def start(self) -> None:
        if platform.system().lower() != "windows" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        WH_KEYBOARD_LL = 13
        WM_KEYDOWN = 0x0100
        WM_SYSKEYDOWN = 0x0104
        HC_ACTION = 0

        VK_TAB = 0x09
        VK_ESCAPE = 0x1B
        VK_F4 = 0x73
        VK_F12 = 0x7B
        VK_SNAPSHOT = 0x2C
        VK_LWIN = 0x5B
        VK_RWIN = 0x5C
        VK_MENU = 0x12
        VK_CONTROL = 0x11
        VK_SHIFT = 0x10

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", ctypes.c_uint32), ("scanCode", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_void_p)]

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSG(ctypes.Structure):
            _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint), ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t), ("time", ctypes.c_uint32), ("pt", POINT), ("lPrivate", ctypes.c_uint32)]

        recent = {}
        def report(k: str, payload: dict[str, Any]) -> None:
            import time
            t = time.time()
            if t - recent.get(k, 0) > 0.7:
                recent[k] = t
                self.inv.send_event("suspicious_key", payload)

        @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
        def proc(n_code, w_param, l_param):
            if n_code == HC_ACTION and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kb.vkCode
                alt = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                shift = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)

                hit = None
                if vk in (VK_LWIN, VK_RWIN):
                    hit = 'Win'
                elif alt and vk == VK_TAB:
                    hit = 'Alt+Tab'
                elif alt and vk == VK_F4:
                    hit = 'Alt+F4'
                elif alt and vk == VK_ESCAPE:
                    hit = 'Alt+Esc'
                elif ctrl and shift and vk == VK_ESCAPE:
                    hit = 'Ctrl+Shift+Esc'
                elif ctrl and vk == VK_ESCAPE:
                    hit = 'Ctrl+Esc'
                elif vk == VK_SNAPSHOT:
                    hit = 'Print'
                elif vk == VK_F12:
                    hit = 'F12'
                if hit and self._norm(hit) in self.rules:
                    report(hit.lower(), {"shortcut":hit,"description":f"触发受控按键: {hit}","is_cheat":True})
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            return

        msg = MSG()
        while not self._stop.is_set() and user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        while not self._stop.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                kernel32.Sleep(30)

        user32.UnhookWindowsHookEx(hook)

class ExamWindow(QtWidgets.QMainWindow):
    def __init__(self, cfg: ExamConfig, inv: InvigilatorClient):
        super().__init__()
        self.cfg = cfg
        self.inv = inv
        self.ended = False

        self.setWindowTitle(f"Exam Client - {cfg.exam_id}")
        if cfg.top_most:
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        self.web = QWebEngineView(self)
        self.setCentralWidget(self.web)
        st = self.web.settings()
        st.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        st.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        self.web.load(QtCore.QUrl(cfg.exam_url))

        self.escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.escape_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.escape_shortcut.activated.connect(self.on_escape_exit)

        self.hotkeys: list[QShortcut] = []
        for seq in self.cfg.key_rules:
            if seq.lower() in ('win','alt+tab','alt+esc'):
                continue
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(QtCore.Qt.ApplicationShortcut)
            sc.activated.connect(lambda s=seq: self.inv.send_event("suspicious_key", {"shortcut": s, "description": f"触发受控按键: {s}", "is_cheat": True}))
            self.hotkeys.append(sc)

        self.hb = QtCore.QTimer(self)
        self.hb.timeout.connect(self.on_heartbeat)
        self.hb.start(cfg.heartbeat_interval_sec * 1000)

        self.focus_timer = QtCore.QTimer(self)
        self.focus_timer.timeout.connect(self.focus_guard)
        self.focus_timer.start(cfg.focus_check_interval_sec * 1000)

        self.proc_stop = threading.Event()
        self.proc_thread = threading.Thread(target=self.proc_watch_loop, daemon=True)
        self.proc_thread.start()
        self.notice_dialog_open = False
        self.suspend_focus_guard_until = 0.0

        if cfg.force_fullscreen:
            self.showFullScreen()
        else:
            self.resize(1280, 860)
            self.show()

    def force_end_exam(self, reason: str, event_type: str) -> None:
        if self.ended:
            return
        self.ended = True
        self.inv.send_event_sync(event_type, {"reason": reason})
        self.inv.send_event("session_state", {"login": False, "locked_out": True, "reason": reason})
        self.proc_stop.set()
        self.setEnabled(False)
        if event_type == "terminated_by_admin":
            msg = "考试已被监考员强制结束。"
        elif event_type == "terminated_by_system":
            msg = "因多次违规操作被考试系统检测到，已强制终止考试。"
        elif event_type == "exam_exit":
            msg = "你已确认退出考试，考试已结束。"
        else:
            msg = "考试已结束，客户端将退出。"
        self.show_safe_message("information", "考试结束", msg)
        QtWidgets.QApplication.instance().quit()

    def on_escape_exit(self) -> None:
        if self.ended or not self.cfg.allow_exit_hotkey:
            return
        c = self.ask_safe_question("确认退出", "确认退出考试？退出后将无法再次进入本场考试。")
        if c == QtWidgets.QMessageBox.Yes:
            self.force_end_exam("student_confirm_exit", "exam_exit")

    def on_heartbeat(self) -> None:
        self.inv.send_event("heartbeat", {"active": self.isActiveWindow()})
        cmd = self.inv.pull_command()
        if cmd.get("notice_message"):
            msg = str(cmd.get("notice_message", "")).strip()
            self.inv.ack_command("notice_message", "")
            if msg and not self.notice_dialog_open:
                self.notice_dialog_open = True
                self.show_safe_message("warning", "监考通知", msg)
                self.notice_dialog_open = False
                self.inv.send_event("admin_notice_ack", {"notice": msg})
        if cmd.get("terminate"):
            self.inv.ack_command("terminate", False)
            reason = str(cmd.get("terminate_reason") or "admin_terminate")
            event = "terminated_by_system" if reason == "auto_cheat_terminate" else "terminated_by_admin"
            self.force_end_exam(reason, event)
            return
        if cmd.get("screenshot_once"):
            self.capture_full_system_once()
            self.inv.ack_command("screenshot_once", False)
        if cmd.get("process_report_once"):
            self.inv.send_event("process_report", {"reason": "admin_request", "processes": list_processes_windows(300)})
            self.inv.ack_command("process_report_once", False)

    def focus_guard(self) -> None:
        if not self.cfg.focus_guard or self.ended:
            return
        if time.time() < self.suspend_focus_guard_until:
            return
        active = self.isActiveWindow()
        full = self.windowState() == QtCore.Qt.WindowFullScreen
        if not active or (self.cfg.force_fullscreen and not full):
            self.inv.send_event("focus_lost", {"active": active, "fullscreen": full})
            if self.cfg.force_fullscreen:
                self.showFullScreen()
            self.raise_()
            self.activateWindow()

    def show_safe_message(self, level: str, title: str, text: str) -> None:
        self.suspend_focus_guard_until = max(self.suspend_focus_guard_until, time.time() + 2.0)
        if level == "warning":
            QtWidgets.QMessageBox.warning(self, title, text)
        else:
            QtWidgets.QMessageBox.information(self, title, text)
        self.suspend_focus_guard_until = max(self.suspend_focus_guard_until, time.time() + 1.0)

    def ask_safe_question(self, title: str, text: str) -> int:
        self.suspend_focus_guard_until = max(self.suspend_focus_guard_until, time.time() + 3.0)
        ans = QtWidgets.QMessageBox.question(self, title, text)
        self.suspend_focus_guard_until = max(self.suspend_focus_guard_until, time.time() + 1.0)
        return ans

    def capture_full_system_once(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if not screen:
            self.inv.send_event("screenshot_frame", {"saved": False, "error": "no screen"})
            return
        pix = screen.grabWindow(0)
        ba = QtCore.QByteArray()
        buf = QtCore.QBuffer(ba)
        buf.open(QtCore.QIODevice.WriteOnly)
        pix.toImage().save(buf, "JPG", quality=60)
        b64 = bytes(ba.toBase64()).decode("ascii", errors="ignore")
        self.inv.send_event("screenshot_frame", {"image_b64": b64[:1200000], "source": "desktop"})

    def proc_watch_loop(self) -> None:
        blocked = set(self.cfg.blocked_processes)
        while not self.proc_stop.is_set():
            hits = sorted(blocked.intersection(set(list_processes_windows(300))))
            if hits:
                self.inv.send_event("blocked_process_detected", {"hits": hits})
                if self.cfg.allow_force_kill:
                    result = {p: kill_process_windows(p) for p in hits}
                    self.inv.send_event("blocked_process_killed", result)
            self.proc_stop.wait(self.cfg.process_scan_interval_sec)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        if self.ended:
            event.accept()
            return
        self.inv.send_event("client_close_attempt", {})
        if self.cfg.force_fullscreen:
            self.inv.send_event("close_blocked", {"reason": "force_fullscreen"})
            event.ignore()
            return
        self.proc_stop.set()
        event.accept()


def main() -> int:
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseSoftwareOpenGL)
    app = QtWidgets.QApplication(sys.argv)

    single_lock = QtCore.QSharedMemory("PaperSystemExamClientSingleton")
    if not single_lock.create(1):
        QtWidgets.QMessageBox.warning(None, "提示", "考试客户端已经在运行，请勿重复启动。")
        return 0

    startup = StartupDialog()
    startup.show()
    startup.set_text("正在加载登录窗口…")

    ip = get_local_ip()
    inv: InvigilatorClient | None = None
    cfg: ExamConfig | None = None

    while True:
        login = LoginDialog()
        startup.hide()
        if login.exec() != QtWidgets.QDialog.Accepted:
            if inv:
                inv.close()
            return 0

        exam_id = login.exam_id.text().strip()
        passkey = login.passkey.text().strip()
        api_base = login.api_base.text().strip() or DEFAULT_API_BASE
        if not exam_id or not passkey:
            QtWidgets.QMessageBox.critical(login, "错误", "考试ID和密码不能为空")
            continue

        startup.show()
        startup.set_text("正在验证考试配置，请稍候…")

        if inv:
            inv.close()
        inv = InvigilatorClient(exam_id, passkey, ip, api_base)

        try:
            cfg, token, resolved_exam_id = load_config(exam_id, passkey, ip, api_base)
        except Exception as exc:
            startup.hide()
            QtWidgets.QMessageBox.critical(login, "配置错误", str(exc))
            inv.close()
            inv = None
            continue

        inv.exam_id = resolved_exam_id
        inv.set_token(token)

        conflicts = check_environment_conflicts(cfg)
        inv.send_event("environment_checked", {"conflicts": conflicts})
        if conflicts:
            startup.hide()
            inv.send_event("entry_denied_environment", {"conflicts": conflicts})
            QtWidgets.QMessageBox.critical(login, "环境冲突", "\n".join(conflicts))
            inv.close()
            inv = None
            continue
        break

    assert inv is not None and cfg is not None

    if cfg.require_student_login:
        while True:
            sdlg = StudentLoginDialog(cfg.class_options)
            startup.hide()
            if sdlg.exec() != QtWidgets.QDialog.Accepted:
                inv.close()
                return 0
            stu = sdlg.profile()
            if not stu.student_id or not stu.name or not stu.class_name:
                QtWidgets.QMessageBox.critical(sdlg, "错误", "学号/姓名/班级必须填写")
                continue
            startup.show()
            startup.set_text("正在验证考生身份，请稍候…")
            ok, err = inv.student_login(stu)
            if ok:
                break
            startup.hide()
            QtWidgets.QMessageBox.critical(sdlg, "登录失败", err or "未知错误")

    startup.hide()

    inv.send_event("process_report", {"reason": "first_login", "processes": list_processes_windows(250)})

    key_monitor = KeyMonitor(inv, cfg.key_rules)
    app.installEventFilter(key_monitor)
    low_hook = WindowsLowLevelKeyHook(inv, cfg.key_rules)
    low_hook.start()

    w = ExamWindow(cfg, inv)
    rc = app.exec()
    low_hook.stop()
    inv.send_event_sync("client_exit", {"code": rc})
    inv.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
