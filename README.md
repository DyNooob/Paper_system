# Paper System（修正版）

本版重点修复：
- `config.php` 业务错误不再直接返回 HTTP 404（避免客户端被误判成 Nginx 404）。
- 考试 ID 继续是**自定义**（由 `exams.json` 自行维护）。
- 支持配置是否需要二次登录（`require_student_login`）。
- 新增可编辑人员名单：`students.json`（考试ID、姓名、学号、班级）。

## 配置文件

### 1) `php_api/exams.json`
每个考试可配置：
- `passkey`
- `exam_url`
- `require_student_login`（true/false）
- 环境检测策略（单屏、VM、进程黑名单等）

### 2) `php_api/students.json`（新增）
格式如下：

```json
{
  "demo-exam": [
    {"student_id": "2026001", "name": "张三", "class_name": "高三(1)班"}
  ]
}
```

> 说明：当 `require_student_login=true` 且该考试在 `students.json` 中有名单时，客户端登录会进行人员校验（学号+姓名+班级）。

## 接口说明

- `config.php?id=xxx&passkey=xxx&ip=xxx`
  - 成功：`ok=true`
  - 失败：`ok=false` + `error`（HTTP 状态码仍返回 200，便于客户端展示明确错误）
- `invigilate.php`
  - 接收监考事件
  - `student_login` 时可校验人员名单

## 监考页面

`dashboard.php?exam_id=demo-exam`

可查看：
- 名单人员是否已登录
- 异常次数/最近异常
- 最后事件、时间、IP

## 运行

```bash
pip install -r requirements.txt
python exam_client.py
php -S 0.0.0.0:8080 -t php_api
```

## 打包

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed exam_client.py
```
