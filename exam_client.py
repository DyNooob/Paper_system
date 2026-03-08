#!/usr/bin/env python3
from __future__ import annotations

import base64
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
USER_AGENT = "PaperSystem-ExamClient/4.0"


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
    allow_realtime_screenshot_control: bool = True
    class_options: list[str] = field(default_factory=list)
    heartbeat_interval_sec: int = 20
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

        self._queue: Queue[dict[str, Any]] = Queue(maxsize=2000)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def set_token(self, token: str | None) -> None:
        self.token = token

    def set_student(self, student: StudentProfile | None) -> None:
        self.student = student

    def _build_payload(self, event_type: str, detail: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
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
            payload["student"] = {
                "student_id": self.student.student_id,
                "name": self.student.name,
                "class_name": self.student.class_name,
            }
        return payload

    def send_event(self, event_type: str, detail: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(self._build_payload(event_type, detail))
        except Exception:
            pass

    def send_event_sync(self, event_type: str, detail: dict[str, Any]) -> tuple[bool, str]:
        try:
            resp = self.session.post(f"{self.api_base}/invigilate.php", json=self._build_payload(event_type, detail), timeout=10)
            data = resp.json()
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
            resp = self.session.get(
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
            data = resp.json()
            if data.get("ok"):
                commands = data.get("commands", {})
                return commands if isinstance(commands, dict) else {}
        except Exception:
            pass
        return {}

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


def list_processes_windows() -> set[str]:
    if platform.system().lower() != "windows":
        return set()
    try:
        out = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return set()
    rows: set[str] = set()
    for line in out.splitlines():
        cols = [x.strip().strip('"') for x in line.strip().split('","')]
        if cols and cols[0]:
            rows.add(cols[0].lower())
    return rows


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
    resp = requests.get(
        f"{api_base.rstrip('/')}/config.php",
        params={"id": exam_id, "passkey": passkey, "ip": ip},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    text = resp.text
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"config not json: http={resp.status_code}, body={text[:200]}")
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error", "config rejected")))
    cfg = data.get("config", {})
    exam_url = str(cfg.get("exam_url", "")).strip()
    if not exam_url:
        raise RuntimeError("config missing exam_url")
    return ExamConfig(
        exam_id=exam_id,
        exam_url=exam_url,
        force_fullscreen=bool(cfg.get("force_fullscreen", True)),
        top_most=bool(cfg.get("top_most", True)),
        require_single_monitor=bool(cfg.get("require_single_monitor", True)),
        allow_force_kill=bool(cfg.get("allow_force_kill", False)),
        blocked_processes=[str(x).lower() for x in cfg.get("blocked_processes", [])],
        detect_vm=bool(cfg.get("detect_vm", True)),
        allowed_os=[str(x).lower() for x in cfg.get("allowed_os", ["windows"])],
        require_student_login=bool(cfg.get("require_student_login", True)),
        max_login_attempts_per_student=max(1, int(cfg.get("max_login_attempts_per_student", 1))),
        allow_exit_hotkey=bool(cfg.get("allow_exit_hotkey", True)),
        exit_hotkey=str(cfg.get("exit_hotkey", "Esc")),
        focus_guard=bool(cfg.get("focus_guard", True)),
        allow_realtime_screenshot_control=bool(cfg.get("allow_realtime_screenshot_control", True)),
        class_options=[str(x) for x in cfg.get("class_options", [])],
        heartbeat_interval_sec=max(5, int(cfg.get("heartbeat_interval_sec", 20))),
        process_scan_interval_sec=max(1, int(cfg.get("process_scan_interval_sec", 3))),
        focus_check_interval_sec=max(1, int(cfg.get("focus_check_interval_sec", 1))),
    ), data.get("session_token")


def check_environment_conflicts(cfg: ExamConfig) -> list[str]:
    bad: list[str] = []
    os_name = platform.system().lower()
    if cfg.allowed_os and os_name not in cfg.allowed_os:
        bad.append(f"系统不允许: {os_name}")
    if cfg.require_single_monitor and len(QtGui.QGuiApplication.screens()) > 1:
        bad.append("检测到多屏幕")
    if cfg.detect_vm and detect_virtual_machine():
        bad.append("检测到虚拟机")
    hits = sorted(set(cfg.blocked_processes).intersection(list_processes_windows()))
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
        layout = QtWidgets.QFormLayout(self)
        self.exam_id = QtWidgets.QLineEdit(self)
        self.passkey = QtWidgets.QLineEdit(self)
        self.passkey.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_base = QtWidgets.QLineEdit(self)
        self.api_base.setText(DEFAULT_API_BASE)
        layout.addRow("考试 ID", self.exam_id)
        layout.addRow("考试密码", self.passkey)
        layout.addRow("API Base", self.api_base)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, parent=self)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addWidget(btn)


class StudentLoginDialog(QtWidgets.QDialog):
    def __init__(self, classes: list[str]):
        super().__init__()
        self.setWindowTitle("考生登录")
        layout = QtWidgets.QFormLayout(self)
        self.student_id = QtWidgets.QLineEdit(self)
        self.name = QtWidgets.QLineEdit(self)
        self.class_box = QtWidgets.QComboBox(self)
        self.class_box.addItems(classes if classes else ["默认班级"])
        layout.addRow("学号", self.student_id)
        layout.addRow("姓名", self.name)
        layout.addRow("班级", self.class_box)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, parent=self)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addWidget(btn)

    def profile(self) -> StudentProfile:
        return StudentProfile(self.student_id.text().strip(), self.name.text().strip(), self.class_box.currentText().strip())


class ExamWindow(QtWidgets.QMainWindow):
    terminate_requested = QtCore.Signal(str)

    def __init__(self, cfg: ExamConfig, inv: InvigilatorClient):
        super().__init__()
        self.cfg = cfg
        self.inv = inv
        self.screenshot_on = False
        self.setWindowTitle(f"Exam Client - {cfg.exam_id}")
        if cfg.top_most:
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        self.web = QWebEngineView(self)
        self.setCentralWidget(self.web)
        st = self.web.settings()
        st.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        st.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        self.web.load(QtCore.QUrl(cfg.exam_url))
        self.web.loadFinished.connect(lambda ok: self.inv.send_event("exam_page_loaded", {"ok": ok}))

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
        self.inv.send_event("heartbeat", {"active": self.isActiveWindow()})
        if self.cfg.require_student_login:
            cmd = self.inv.pull_command()
            if cmd.get("terminate"):
                self.inv.send_event("terminated_by_admin", {"reason": "admin_command"})
                self.terminate_requested.emit("监考员已终止你的答题权限")
                return
            shot = bool(cmd.get("realtime_screenshot", False))
            if shot != self.screenshot_on:
                self.screenshot_on = shot
                self.inv.send_event("screenshot_mode", {"enabled": shot})
            if self.screenshot_on and self.cfg.allow_realtime_screenshot_control:
                self.capture_and_upload()

    def focus_guard(self) -> None:
        if not self.cfg.focus_guard:
            return
        if not self.isActiveWindow():
            self.inv.send_event("focus_lost", {"window": self.windowTitle()})
            self.raise_()
            self.activateWindow()
        if self.cfg.force_fullscreen and self.windowState() != QtCore.Qt.WindowFullScreen:
            self.inv.send_event("focus_lost", {"reason": "left_fullscreen"})
            self.showFullScreen()

    def capture_and_upload(self) -> None:
        pix = self.grab()
        buf = QtCore.QBuffer()
        buf.open(QtCore.QIODevice.WriteOnly)
        pix.toImage().save(buf, "JPG", quality=50)
        b64 = bytes(buf.data().toBase64()).decode("ascii", errors="ignore")
        self.inv.send_event("screenshot_frame", {"image_b64": b64[:900000]})

    def proc_watch_loop(self) -> None:
        blocked = set(self.cfg.blocked_processes)
        while not self.proc_stop.is_set():
            hits = sorted(blocked.intersection(list_processes_windows()))
            if hits:
                self.inv.send_event("blocked_process_detected", {"hits": hits})
                if self.cfg.allow_force_kill:
                    result = {p: kill_process_windows(p) for p in hits}
                    self.inv.send_event("blocked_process_killed", result)
            self.proc_stop.wait(self.cfg.process_scan_interval_sec)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        key = int(event.key())
        if key in (int(QtCore.Qt.Key_F12), int(QtCore.Qt.Key_Print)):
            self.inv.send_event("suspicious_key", {"key": key})
        if self.cfg.allow_exit_hotkey and key == int(QtCore.Qt.Key_Escape):
            self.inv.send_event("exam_exit", {"hotkey": self.cfg.exit_hotkey})
            QtWidgets.QMessageBox.warning(self, "已退出", "你已退出考试，且不可再次进入。")
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
    dlg = LoginDialog()
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return 0

    exam_id = dlg.exam_id.text().strip()
    passkey = dlg.passkey.text().strip()
    api_base = dlg.api_base.text().strip() or DEFAULT_API_BASE
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
        profile = sdlg.profile()
        if not profile.student_id or not profile.name or not profile.class_name:
            QtWidgets.QMessageBox.critical(None, "错误", "学号/姓名/班级必须填写")
            inv.close()
            return 4
        ok, err = inv.student_login(profile)
        if not ok:
            QtWidgets.QMessageBox.critical(None, "登录失败", err or "未知错误")
            inv.close()
            return 5
    else:
        inv.set_student(None)
        inv.send_event("student_login_skipped", {"reason": "require_student_login=false"})

    window = ExamWindow(cfg, inv)

    def on_terminated(msg: str) -> None:
        QtWidgets.QMessageBox.critical(window, "已终止", msg)
        QtWidgets.QApplication.instance().quit()

    window.terminate_requested.connect(on_terminated)
    rc = app.exec()
    inv.send_event("client_exit", {"code": rc})
    inv.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
