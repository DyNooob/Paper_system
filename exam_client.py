#!/usr/bin/env python3
from __future__ import annotations

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
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

DEFAULT_API_BASE = "https://api.nooob.top/paper"
USER_AGENT = "PaperSystem-ExamClient/4.1"


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
        p = {
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
            data = r.json()
            return bool(data.get("ok")), str(data.get("error", ""))
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
            data = r.json()
            if data.get("ok"):
                c = data.get("commands", {})
                return c if isinstance(c, dict) else {}
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
                timeout=6,
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
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def list_processes_windows(limit: int = 30) -> list[str]:
    if platform.system().lower() != "windows":
        return []
    try:
        out = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return []
    rows: list[str] = []
    for line in out.splitlines():
        cols = [x.strip().strip('"') for x in line.strip().split('","')]
        if cols and cols[0]:
            rows.append(cols[0].lower())
    return rows[:limit]


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
    txt = r.text
    try:
        d = r.json()
    except Exception:
        raise RuntimeError(f"config not json: {r.status_code}, {txt[:200]}")
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
        allowed_os=[str(x).lower() for x in c.get("allowed_os", ["windows"])],
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
    hits = sorted(set(cfg.blocked_processes).intersection(set(list_processes_windows(200))))
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
        f = QtWidgets.QFormLayout(self)
        self.exam_id = QtWidgets.QLineEdit(self)
        self.passkey = QtWidgets.QLineEdit(self)
        self.passkey.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_base = QtWidgets.QLineEdit(self)
        self.api_base.setText(DEFAULT_API_BASE)
        f.addRow("考试 ID", self.exam_id)
        f.addRow("考试密码", self.passkey)
        f.addRow("API Base", self.api_base)
        b = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, parent=self)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        f.addWidget(b)


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


class ExamWindow(QtWidgets.QMainWindow):
    terminate_requested = QtCore.Signal(str)

    def __init__(self, cfg: ExamConfig, inv: InvigilatorClient):
        super().__init__()
        self.cfg = cfg
        self.inv = inv
        self.setWindowTitle(f"Exam Client - {cfg.exam_id}")
        if cfg.top_most:
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        self.web = QWebEngineView(self)
        self.setCentralWidget(self.web)
        st = self.web.settings()
        st.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        st.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        self.web.load(QtCore.QUrl(cfg.exam_url))

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

    def on_heartbeat(self) -> None:
        self.inv.send_event("heartbeat", {"active": self.isActiveWindow(), "processes": list_processes_windows(30)})
        cmd = self.inv.pull_command()
        if cmd.get("terminate"):
            self.inv.send_event("terminated_by_admin", {"reason": "admin_command"})
            self.terminate_requested.emit("考试结束：监考员已终止你的作答权限")
            return
        if cmd.get("screenshot_once"):
            self.capture_full_system_once()
            self.inv.ack_command("screenshot_once", False)

    def focus_guard(self) -> None:
        if not self.cfg.focus_guard:
            return
        if not self.isActiveWindow() or (self.cfg.force_fullscreen and self.windowState() != QtCore.Qt.WindowFullScreen):
            self.inv.send_event("focus_lost", {"active": self.isActiveWindow(), "fullscreen": self.windowState() == QtCore.Qt.WindowFullScreen, "processes": list_processes_windows(25)})
            if self.cfg.force_fullscreen:
                self.showFullScreen()
            self.raise_()
            self.activateWindow()

    def capture_full_system_once(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if not screen:
            self.inv.send_event("screenshot_frame", {"saved": False, "error": "no screen"})
            return
        pix = screen.grabWindow(0)  # 全系统窗口截图（桌面级）
        ba = QtCore.QByteArray()
        buf = QtCore.QBuffer(ba)
        buf.open(QtCore.QIODevice.WriteOnly)
        pix.toImage().save(buf, "JPG", quality=60)
        b64 = bytes(ba.toBase64()).decode("ascii", errors="ignore")
        self.inv.send_event("screenshot_frame", {"image_b64": b64[:1200000], "source": "desktop"})

    def proc_watch_loop(self) -> None:
        blocked = set(self.cfg.blocked_processes)
        while not self.proc_stop.is_set():
            hits = sorted(blocked.intersection(set(list_processes_windows(200))))
            if hits:
                self.inv.send_event("blocked_process_detected", {"hits": hits, "processes": list_processes_windows(40)})
                if self.cfg.allow_force_kill:
                    result = {p: kill_process_windows(p) for p in hits}
                    self.inv.send_event("blocked_process_killed", result)
            self.proc_stop.wait(self.cfg.process_scan_interval_sec)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        key = int(event.key())
        if key in (int(QtCore.Qt.Key_F12), int(QtCore.Qt.Key_Print)):
            self.inv.send_event("suspicious_key", {"key": key})
        if self.cfg.allow_exit_hotkey and key == int(QtCore.Qt.Key_Escape):
            c = QtWidgets.QMessageBox.question(self, "确认退出", "确认退出考试？退出后将不能再次进入。")
            if c == QtWidgets.QMessageBox.Yes:
                self.inv.send_event("exam_exit", {"hotkey": self.cfg.exit_hotkey, "processes": list_processes_windows(50)})
                QtWidgets.QMessageBox.information(self, "考试结束", "你已退出考试，考试结束。")
                self.proc_stop.set()
                QtWidgets.QApplication.instance().quit()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        self.inv.send_event("client_close_attempt", {})
        if self.cfg.force_fullscreen:
            self.inv.send_event("close_blocked", {"reason": "force_fullscreen"})
            event.ignore()
            return
        self.proc_stop.set()
        event.accept()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    l = LoginDialog()
    if l.exec() != QtWidgets.QDialog.Accepted:
        return 0

    exam_id = l.exam_id.text().strip()
    passkey = l.passkey.text().strip()
    api_base = l.api_base.text().strip() or DEFAULT_API_BASE
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
    inv.send_event("environment_checked", {"conflicts": conflicts, "processes": list_processes_windows(50)})
    if conflicts:
        inv.send_event("entry_denied_environment", {"conflicts": conflicts})
        QtWidgets.QMessageBox.critical(None, "环境冲突", "\n".join(conflicts))
        inv.close()
        return 3

    if cfg.require_student_login:
        sd = StudentLoginDialog(cfg.class_options)
        if sd.exec() != QtWidgets.QDialog.Accepted:
            inv.close()
            return 0
        p = sd.profile()
        if not p.student_id or not p.name or not p.class_name:
            QtWidgets.QMessageBox.critical(None, "错误", "学号/姓名/班级必须填写")
            inv.close()
            return 4
        ok, err = inv.student_login(p)
        if not ok:
            QtWidgets.QMessageBox.critical(None, "登录失败", err or "未知错误")
            inv.close()
            return 5

    w = ExamWindow(cfg, inv)

    def on_term(msg: str) -> None:
        QtWidgets.QMessageBox.critical(w, "考试结束", msg)
        w.proc_stop.set()
        QtWidgets.QApplication.instance().quit()

    w.terminate_requested.connect(on_term)
    rc = app.exec()
    inv.send_event("client_exit", {"code": rc})
    inv.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
