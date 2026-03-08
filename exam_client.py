#!/usr/bin/env python3
"""Paper System Exam Client (Python, Windows-focused).

流程：
1) 输入考试 ID / 密码，获取配置
2) 先做环境冲突检查（非法设备/环境）
3) 学生登录（考号、姓名、班级）
4) 进入考试页面并持续监考上报
"""
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
USER_AGENT = "PaperSystem-ExamClient/3.0"


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
    class_options: list[str] = field(default_factory=list)
    heartbeat_interval_sec: int = 20
    process_scan_interval_sec: int = 3


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

        self._queue: Queue[dict[str, Any]] = Queue(maxsize=1000)
        self._stop = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def set_token(self, token: str | None) -> None:
        self.token = token

    def set_student(self, student: StudentProfile) -> None:
        self.student = student

    def send_event(self, event_type: str, detail: dict[str, Any]) -> None:
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
        try:
            self._queue.put_nowait(payload)
        except Exception:
            pass

    def login_student(self, student: StudentProfile) -> None:
        self.set_student(student)
        self.send_event("student_login", {"status": "success"})

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
        self._worker_thread.join(timeout=1.2)


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def list_processes_windows() -> set[str]:
    if platform.system().lower() != "windows":
        return set()
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return set()

    procs: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        cols = [x.strip().strip('"') for x in line.split('","')]
        if cols and cols[0]:
            procs.add(cols[0].lower())
    return procs


def kill_process_windows(name: str) -> bool:
    if platform.system().lower() != "windows":
        return False
    try:
        subprocess.check_call(
            ["taskkill", "/F", "/IM", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def detect_virtual_machine() -> bool:
    if platform.system().lower() != "windows":
        return False
    signatures = ["virtualbox", "vmware", "kvm", "qemu", "hyper-v", "xen"]
    try:
        out = subprocess.check_output(
            ["wmic", "computersystem", "get", "model,manufacturer"],
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).lower()
    except Exception:
        return False
    return any(sig in out for sig in signatures)


def load_config(exam_id: str, passkey: str, ip: str, api_base: str) -> tuple[ExamConfig, str | None]:
    resp = requests.get(
        f"{api_base.rstrip('/')}/config.php",
        params={"id": exam_id, "passkey": passkey, "ip": ip},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "config rejected"))

    cfg = data.get("config", {})
    if not cfg.get("exam_url"):
        raise RuntimeError("config missing exam_url")

    exam_cfg = ExamConfig(
        exam_id=exam_id,
        exam_url=str(cfg["exam_url"]),
        force_fullscreen=bool(cfg.get("force_fullscreen", True)),
        top_most=bool(cfg.get("top_most", True)),
        require_single_monitor=bool(cfg.get("require_single_monitor", True)),
        allow_force_kill=bool(cfg.get("allow_force_kill", False)),
        blocked_processes=[str(x).lower() for x in cfg.get("blocked_processes", [])],
        detect_vm=bool(cfg.get("detect_vm", True)),
        allowed_os=[str(x).lower() for x in cfg.get("allowed_os", ["windows"])],
        class_options=[str(x) for x in cfg.get("class_options", [])],
        heartbeat_interval_sec=max(5, int(cfg.get("heartbeat_interval_sec", 20))),
        process_scan_interval_sec=max(1, int(cfg.get("process_scan_interval_sec", 3))),
    )
    return exam_cfg, data.get("session_token")


def check_environment_conflicts(cfg: ExamConfig) -> list[str]:
    conflicts: list[str] = []
    os_name = platform.system().lower()

    if cfg.allowed_os and os_name not in cfg.allowed_os:
        conflicts.append(f"当前系统 {os_name} 不在允许列表 {cfg.allowed_os}")

    if cfg.require_single_monitor and len(QtGui.QGuiApplication.screens()) > 1:
        conflicts.append("检测到多屏幕，考试要求单屏")

    if cfg.detect_vm and detect_virtual_machine():
        conflicts.append("检测到虚拟机环境，已禁止进入考试")

    running = list_processes_windows()
    blocked_hits = sorted(set(cfg.blocked_processes).intersection(running))
    if blocked_hits:
        if cfg.allow_force_kill:
            failed = [p for p in blocked_hits if not kill_process_windows(p)]
            if failed:
                conflicts.append("以下禁用进程无法自动结束：" + ", ".join(failed))
        else:
            conflicts.append("检测到禁用进程：" + ", ".join(blocked_hits))

    return conflicts


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

        btn = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addWidget(btn)


class StudentLoginDialog(QtWidgets.QDialog):
    def __init__(self, class_options: list[str]):
        super().__init__()
        self.setWindowTitle("考生登录")
        layout = QtWidgets.QFormLayout(self)

        self.student_id = QtWidgets.QLineEdit(self)
        self.name = QtWidgets.QLineEdit(self)
        self.class_box = QtWidgets.QComboBox(self)
        if class_options:
            self.class_box.addItems(class_options)
        else:
            self.class_box.addItems(["默认班级"])

        layout.addRow("考号", self.student_id)
        layout.addRow("姓名", self.name)
        layout.addRow("班级", self.class_box)

        btn = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addWidget(btn)

    def get_profile(self) -> StudentProfile:
        return StudentProfile(
            student_id=self.student_id.text().strip(),
            name=self.name.text().strip(),
            class_name=self.class_box.currentText().strip(),
        )


class ExamWindow(QtWidgets.QMainWindow):
    def __init__(self, cfg: ExamConfig, invigilator: InvigilatorClient):
        super().__init__()
        self.cfg = cfg
        self.invigilator = invigilator

        self.setWindowTitle(f"Exam Client - {cfg.exam_id}")
        if cfg.top_most:
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        self.web = QWebEngineView(self)
        self.setCentralWidget(self.web)
        ws = self.web.settings()
        ws.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        ws.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)

        self.web.load(QtCore.QUrl(cfg.exam_url))
        self.web.loadFinished.connect(self._on_loaded)

        self.heartbeat_timer = QtCore.QTimer(self)
        self.heartbeat_timer.timeout.connect(self._heartbeat)
        self.heartbeat_timer.start(cfg.heartbeat_interval_sec * 1000)

        self.proc_stop = threading.Event()
        self.proc_thread = threading.Thread(target=self._process_watch_loop, daemon=True)
        self.proc_thread.start()

        if cfg.force_fullscreen:
            self.showFullScreen()
        else:
            self.resize(1280, 860)
            self.show()

    def _on_loaded(self, ok: bool) -> None:
        self.invigilator.send_event("exam_page_loaded", {"ok": ok, "url": self.web.url().toString()})

    def _heartbeat(self) -> None:
        self.invigilator.send_event("heartbeat", {"active": self.isActiveWindow()})

    def _process_watch_loop(self) -> None:
        blocked = set(self.cfg.blocked_processes)
        while not self.proc_stop.is_set():
            running = list_processes_windows()
            hits = sorted(blocked.intersection(running))
            if hits:
                self.invigilator.send_event("blocked_process_detected", {"hits": hits})
                if self.cfg.allow_force_kill:
                    result = {p: kill_process_windows(p) for p in hits}
                    self.invigilator.send_event("blocked_process_killed", result)
            self.proc_stop.wait(self.cfg.process_scan_interval_sec)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        key = int(event.key())
        if key in (int(QtCore.Qt.Key_F12), int(QtCore.Qt.Key_Escape), int(QtCore.Qt.Key_Print)):
            self.invigilator.send_event("suspicious_key", {"key": key})
        if event.modifiers() & QtCore.Qt.AltModifier and event.key() in (QtCore.Qt.Key_Tab, QtCore.Qt.Key_F4):
            self.invigilator.send_event("shortcut_blocked", {"shortcut": "alt_tab_or_alt_f4"})
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        self.invigilator.send_event("client_close_attempt", {})
        if self.cfg.force_fullscreen:
            event.ignore()
            self.invigilator.send_event("close_blocked", {"reason": "force_fullscreen"})
            return
        self.proc_stop.set()
        event.accept()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)

    # step1 exam auth
    login = LoginDialog()
    if login.exec() != QtWidgets.QDialog.Accepted:
        return 0

    exam_id = login.exam_id.text().strip()
    passkey = login.passkey.text().strip()
    api_base = login.api_base.text().strip() or DEFAULT_API_BASE
    if not exam_id or not passkey:
        QtWidgets.QMessageBox.critical(None, "错误", "考试 ID / 密码不能为空")
        return 1

    ip = get_local_ip()
    invigilator = InvigilatorClient(exam_id, passkey, ip, api_base)

    try:
        cfg, token = load_config(exam_id, passkey, ip, api_base)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(None, "配置获取失败", str(exc))
        invigilator.close()
        return 2

    invigilator.set_token(token)

    # step2 env precheck
    conflicts = check_environment_conflicts(cfg)
    invigilator.send_event("environment_checked", {"conflicts": conflicts})
    if conflicts:
        QtWidgets.QMessageBox.critical(None, "环境冲突（非法设备）", "\n".join(conflicts))
        invigilator.send_event("entry_denied_environment", {"conflicts": conflicts})
        invigilator.close()
        return 3

    # step3 student login
    stu_dialog = StudentLoginDialog(cfg.class_options)
    if stu_dialog.exec() != QtWidgets.QDialog.Accepted:
        invigilator.close()
        return 0
    profile = stu_dialog.get_profile()
    if not profile.student_id or not profile.name or not profile.class_name:
        QtWidgets.QMessageBox.critical(None, "错误", "考号/姓名/班级均为必填")
        invigilator.close()
        return 4

    invigilator.login_student(profile)

    # step4 exam
    window = ExamWindow(cfg, invigilator)
    rc = app.exec()
    invigilator.send_event("client_exit", {"code": rc})
    invigilator.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
