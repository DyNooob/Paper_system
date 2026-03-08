# Paper System（增强监考版）

本版新增：
- 监考端可点击学生查看详细操作，并按“作弊相关”筛选。
- 监考端可对学生下发“终止答题”命令。
- 监考端可开启/关闭某学生实时截屏。
- 客户端加强焦点守护：失焦自动拉回并上报。
- 增加“每个学生最大登录次数”配置。
- 支持 ESC 退出并锁定（退出后不能再进入）。

## 主要配置

`php_api/exams.json`:
- `require_student_login`: 是否启用学生二次登录
- `max_login_attempts_per_student`: 每个学生最多登录次数
- `allow_exit_hotkey` + `exit_hotkey`
- `focus_guard`: 焦点守护
- `allow_realtime_screenshot_control`: 允许监考控制实时截屏

`php_api/students.json`:
- 按考试 ID 维护考生名单（学号/姓名/班级）

## 关键接口

- `config.php`: 拉取考试配置
- `invigilate.php`: 上传事件（含作弊标签）
- `command.php`: 客户端拉取监考命令 / 监考设置命令
- `dashboard.php`: 监考面板

## 运行

```bash
pip install -r requirements.txt
python exam_client.py
php -S 0.0.0.0:8080 -t php_api
```

监考面板：

```text
http://127.0.0.1:8080/dashboard.php?exam_id=demo-exam
```

## 打包

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed exam_client.py
```
