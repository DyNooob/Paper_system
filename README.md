# Paper System（重写版）

本版本实现了你要求的完整流程：

1. 输入考试 ID + 密码拉取配置。
2. **先检查环境冲突（非法设备/非法环境）**。
3. 通过后进入**考生登录**（考号、姓名、班级）。
4. 登录成功后进入考试链接。
5. 监考端 `dashboard.php` 实时查看每个考生是否登录、是否有异常行为。

---

## 目录

- `exam_client.py`：Python 客户端（PySide6 + WebEngine）
- `php_api/config.php`：下发考试配置 + session token
- `php_api/invigilate.php`：接收监考事件、更新状态
- `php_api/dashboard.php`：监考可视化页面
- `php_api/common.php`：公共函数
- `php_api/exams.json`：考试配置

---

## 客户端能力（按需求重写）

- 配置拉取：`config.php?id=...&passkey=...&ip=...`
- 环境冲突检查：
  - 多屏检测（`require_single_monitor`）
  - 禁用进程检测（可选强杀）
  - 虚拟机检测（WMIC 关键字）
  - OS 白名单检查
- 考生登录信息：
  - 考号（填写）
  - 姓名（填写）
  - 班级（选择，来自配置 `class_options`）
- 考试期间监考上报：
  - 登录事件、心跳
  - 禁用进程触发
  - 可疑按键与快捷键
  - 关闭尝试

---

## 监考面板

访问：

```text
http://<host>/dashboard.php?exam_id=demo-exam
```

字段包含：
- 是否登录
- 异常次数
- 最近异常
- 最后事件与时间
- IP

---

## 安装与运行

### Python 依赖

```bash
pip install -r requirements.txt
```

### 启动客户端

```bash
python exam_client.py
```

### 启动 PHP

```bash
php -S 0.0.0.0:8080 -t php_api
```

测试配置接口：

```text
http://127.0.0.1:8080/config.php?id=demo-exam&passkey=123456&ip=127.0.0.1
```

---

## 打包单 EXE

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed exam_client.py
```

---

## 生产建议

- 设置 `PAPER_API_SECRET`（或 `php_api/secret.key`）。
- 把 `exams.json` 放到受控目录，限制访问权限。
- 高风险考试建议结合系统级手段（Kiosk/GPO/终端管控）。
