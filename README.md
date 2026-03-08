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
- `command.php`：监考下发命令（`terminate` / `screenshot_once` / `process_report_once`）
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
http://127.0.0.1:8080/dashboard.php?exam_id=demo-exam&passkey=123456
```
