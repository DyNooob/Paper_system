# Paper System（终版增强）

本版针对你最新需求修复：

- 学生可按 **ESC** 后二次确认主动退出；退出后被锁定，不可再次进入考试。
- 监考员可远程终止学生答题，客户端立即结束并弹窗“考试结束”。
- 截屏改为 **一键截屏**（点击即抓取一次并可查看），不再需要开始/停止两次操作。
- 截屏改为桌面级抓图：客户端使用系统桌面抓图（`grabWindow(0)`），不是只截软件窗口。
- 增加更详细日志：心跳/失焦/退出等上报含主要进程列表。

## 配置（`php_api/exams.json`）

- `require_student_login`
- `max_login_attempts_per_student`
- `allow_exit_hotkey` + `exit_hotkey`
- `focus_guard`
- `heartbeat_interval_sec`
- `focus_check_interval_sec`

## 接口

- `config.php`：拉取考试配置
- `invigilate.php`：上报行为、存日志、保存截图、维护状态
- `command.php`：监考下发命令（`terminate` / `screenshot_once`）
- `dashboard.php`：监考端页面（学生列表、详情、作弊筛选、操作按钮）

## 运行

```bash
pip install -r requirements.txt
python exam_client.py
php -S 0.0.0.0:8080 -t php_api
```

监考页：

```text
http://127.0.0.1:8080/dashboard.php?exam_id=demo-exam
```
