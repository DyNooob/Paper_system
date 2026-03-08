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
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-gpu-compositing --disable-features=VizDisplayCompositor --no-sandbox")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

DEFAULT_API_BASE = "https://api.nooob.top/paper"
USER_AGENT = "PaperSystem-ExamClient/4.3"


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

    def ack_command(self, action: str, value: bool) -> None:
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
                    "value": "1" if value else "0",
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


def load_config(exam_id: str, passkey: str, ip: str, api_base: str) -> tuple[ExamConfig, str | None]:
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
    return ExamConfig(
        exam_id=exam_id,
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
    ), d.get("session_token")


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
        form.addRow("考试密码", self.passkey)
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
    def __init__(self, inv: InvigilatorClient):
        super().__init__()
        self.inv = inv

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if event.type() not in (QtCore.QEvent.KeyPress, QtCore.QEvent.ShortcutOverride):
            return False
        if not isinstance(event, QtGui.QKeyEvent):
            return False
        key = int(event.key())
        mods = event.modifiers()
        shortcut = QtGui.QKeySequence(int(mods) | key).toString() or f"key_{key}"

        desc = None
        if key == int(QtCore.Qt.Key_F12):
            desc = "尝试开发者工具"
        elif key == int(QtCore.Qt.Key_Print):
            desc = "尝试截图"
        elif (mods & QtCore.Qt.AltModifier) and key == int(QtCore.Qt.Key_F4):
            desc = "尝试关闭考试窗口"
        elif (mods & QtCore.Qt.ControlModifier) and (mods & QtCore.Qt.ShiftModifier) and key == int(QtCore.Qt.Key_Escape):
            desc = "尝试打开任务管理器"
        elif (mods & QtCore.Qt.ControlModifier) and key == int(QtCore.Qt.Key_Escape):
            desc = "尝试打开开始菜单"
        elif key in (int(QtCore.Qt.Key_Meta), int(QtCore.Qt.Key_Super_L), int(QtCore.Qt.Key_Super_R)):
            desc = "尝试Win键操作"
        if desc:
            self.inv.send_event("suspicious_key", {"shortcut": shortcut, "description": desc, "is_cheat": True})
        return False


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
        for seq, desc in [
            ("F12", "尝试开发者工具"),
            ("Print", "尝试截图"),
            ("Ctrl+Shift+Esc", "尝试打开任务管理器"),
            ("Ctrl+Esc", "尝试打开开始菜单"),
            ("Alt+F4", "尝试关闭考试窗口"),
        ]:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(QtCore.Qt.ApplicationShortcut)
            sc.activated.connect(lambda d=desc, s=seq: self.inv.send_event("suspicious_key", {"shortcut": s, "description": d, "is_cheat": True}))
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

        if cfg.force_fullscreen:
            self.showFullScreen()
        else:
            self.resize(1280, 860)
            self.show()

    def force_end_exam(self, reason: str, event_type: str) -> None:
        if self.ended:
            return
        self.ended = True
        self.inv.send_event(event_type, {"reason": reason})
        self.proc_stop.set()
        self.setEnabled(False)
        QtWidgets.QMessageBox.critical(self, "考试结束", "考试结束")
        QtWidgets.QApplication.instance().quit()

    def on_escape_exit(self) -> None:
        if self.ended or not self.cfg.allow_exit_hotkey:
            return
        c = QtWidgets.QMessageBox.question(self, "确认退出", "确认退出考试？退出后不可再次进入。")
        if c == QtWidgets.QMessageBox.Yes:
            self.force_end_exam("student_confirm_exit", "exam_exit")

    def on_heartbeat(self) -> None:
        self.inv.send_event("heartbeat", {"active": self.isActiveWindow()})
        cmd = self.inv.pull_command()
        if cmd.get("terminate"):
            self.inv.ack_command("terminate", False)
            self.force_end_exam("admin_terminate", "terminated_by_admin")
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
        active = self.isActiveWindow()
        full = self.windowState() == QtCore.Qt.WindowFullScreen
        if not active or (self.cfg.force_fullscreen and not full):
            self.inv.send_event("focus_lost", {"active": active, "fullscreen": full})
            if self.cfg.force_fullscreen:
                self.showFullScreen()
            self.raise_()
            self.activateWindow()

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

    login = LoginDialog()
    if login.exec() != QtWidgets.QDialog.Accepted:
        return 0

    exam_id = login.exam_id.text().strip()
    passkey = login.passkey.text().strip()
    api_base = login.api_base.text().strip() or DEFAULT_API_BASE
    if not exam_id or not passkey:
        QtWidgets.QMessageBox.critical(None, "错误", "考试ID和密码不能为空")
        return 1

    ip = get_local_ip()
    inv = InvigilatorClient(exam_id, passkey, ip, api_base)

    try:
        cfg, token = load_config(exam_id, passkey, ip, api_base)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(None, "配置错误", str(exc))
        inv.close()
        return 2

    inv.set_token(token)

    conflicts = check_environment_conflicts(cfg)
    inv.send_event("environment_checked", {"conflicts": conflicts})
    if conflicts:
        inv.send_event("entry_denied_environment", {"conflicts": conflicts})
        QtWidgets.QMessageBox.critical(None, "环境冲突", "\n".join(conflicts))
        inv.close()
        return 3

    if cfg.require_student_login:
        sdlg = StudentLoginDialog(cfg.class_options)
        if sdlg.exec() != QtWidgets.QDialog.Accepted:
            inv.close()
            return 0
        stu = sdlg.profile()
        if not stu.student_id or not stu.name or not stu.class_name:
            QtWidgets.QMessageBox.critical(None, "错误", "学号/姓名/班级必须填写")
            inv.close()
            return 4
        ok, err = inv.student_login(stu)
        if not ok:
            QtWidgets.QMessageBox.critical(None, "登录失败", err or "未知错误")
            inv.close()
            return 5

    # 首次登录只上报一次完整进程快照
    inv.send_event("process_report", {"reason": "first_login", "processes": list_processes_windows(250)})

    app.installEventFilter(KeyMonitor(inv))

    w = ExamWindow(cfg, inv)
    rc = app.exec()
    inv.send_event("client_exit", {"code": rc})
    inv.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
