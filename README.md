# Paper System（监考增强修正版）

本次修复重点：

- **ESC 退出修复**：学生按 ESC 会弹确认，确认后立即结束考试，并被锁定不可再次进入。
- **远程终止修复**：监考员点“终止”后客户端立即结束，弹窗“考试结束”，无法继续作答提交。
- **按键监控增强**：记录详细快捷键（如 Alt+Tab / Alt+F4 / Ctrl+Shift+Esc / Print / F12 等），并作为作弊事件上报。
- **进程上报优化**：
  - 首次登录后自动上报一次完整进程快照；
  - 监考员点“获取进程”才会再上报进程。
- **截屏修复**：改为“一键截屏”，并尝试桌面级抓图（`grabWindow(0)`），不是软件窗口自身截图。
- **服务端面板重做**：更现代的监考页，自动刷新（2s），学生详情与作弊筛选无需手动全页刷新。

## 主要接口

- `config.php`：下发配置
- `invigilate.php`：接收行为/作弊/截图/进程快照
- `command.php`：监考下发命令（`terminate` / `screenshot_once` / `process_report_once` / `notice_message`）
- `dashboard.php`：监考端主页面（自动刷新）
- `dashboard_data.php`：监考端数据接口

## 运行

```bash
pip install -r requirements.txt
python exam_client.py
php -S 0.0.0.0:8080 -t php_api
```

监考端：

```text
http://127.0.0.1:8080/dashboard.php?exam_id=demo-exam&passkey=admin123
```


## 打包体积与启动速度优化（Windows）

你反馈 onefile 体积大（200MB+）且启动慢，这个是 PyInstaller onefile 解包机制导致的常见现象。建议：

1. 使用 **onefile** 单文件（方便分发）。
2. 使用 `build_windows.bat` 进行裁剪构建。
3. 若安装了 UPX，设置 `UPX_DIR` 后可进一步压缩。

```bat
set UPX_DIR=C:\upx
build_windows.bat
```

> 注意：`QtWebEngine` 本身资源体积较大，单文件启动会有解压阶段；可用 UPX 与模块裁剪减小体积。


## 说明

- `php_api/exams.json` 支持在每个考试项中配置 `id` 字段，客户端可以使用该 `id` 登录（后端会自动解析到实际考试键名）。
- 客户端在考试登录失败/考生登录失败时会保留登录窗口并提示错误，无需重启软件。
- 客户端启动和网络校验阶段会显示“正在初始化”提示窗口，避免打包后无界面等待。

- `php_api/exams.json` 现支持分离 `student_passkey`（学生端）与 `admin_passkey`（监考端）。
- 支持配置 `key_rules` 自定义按键监控列表。
- 监考端支持给单个学生发送通知，且支持设置自动警告/自动终止作弊阈值。
