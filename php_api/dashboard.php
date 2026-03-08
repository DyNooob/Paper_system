<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$examId = trim((string)($_GET['exam_id'] ?? 'demo-exam'));
$state = load_state(__DIR__, $examId);
$students = $state['students'] ?? [];
if (!is_array($students)) {
    $students = [];
}

uasort($students, static function (array $a, array $b): int {
    return strcmp((string)($a['student_id'] ?? ''), (string)($b['student_id'] ?? ''));
});
?>
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>监考面板 - <?php echo htmlspecialchars($examId, ENT_QUOTES, 'UTF-8'); ?></title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;background:#f5f7fb;margin:0;padding:20px}
    .wrap{max-width:1200px;margin:0 auto}
    .card{background:#fff;border-radius:10px;padding:16px;box-shadow:0 2px 10px rgba(0,0,0,.06)}
    table{width:100%;border-collapse:collapse}
    th,td{padding:10px;border-bottom:1px solid #eee;font-size:14px;text-align:left}
    th{background:#fafafa}
    .ok{color:#0a8f3c;font-weight:700}
    .bad{color:#d93025;font-weight:700}
    .meta{color:#666;font-size:13px;margin-top:8px}
  </style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h2>监考面板（考试：<?php echo htmlspecialchars($examId, ENT_QUOTES, 'UTF-8'); ?>）</h2>
    <div class="meta">最后更新时间：<?php echo htmlspecialchars((string)($state['last_update'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></div>
    <table>
      <thead>
      <tr>
        <th>考号</th>
        <th>姓名</th>
        <th>班级</th>
        <th>是否登录</th>
        <th>异常次数</th>
        <th>最近异常</th>
        <th>最后事件</th>
        <th>最后时间</th>
        <th>IP</th>
      </tr>
      </thead>
      <tbody>
      <?php if ($students === []): ?>
        <tr><td colspan="9">暂无考生上报数据</td></tr>
      <?php else: foreach ($students as $row): ?>
        <tr>
          <td><?php echo htmlspecialchars((string)($row['student_id'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td>
          <td><?php echo htmlspecialchars((string)($row['name'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td>
          <td><?php echo htmlspecialchars((string)($row['class_name'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td>
          <td>
            <?php if (!empty($row['login'])): ?>
              <span class="ok">已登录</span>
            <?php else: ?>
              <span class="bad">未登录</span>
            <?php endif; ?>
          </td>
          <td><?php echo (int)($row['abnormal_count'] ?? 0); ?></td>
          <td><?php echo htmlspecialchars((string)($row['abnormal_last'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td>
          <td><?php echo htmlspecialchars((string)($row['last_event'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td>
          <td><?php echo htmlspecialchars((string)($row['last_event_time'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td>
          <td><?php echo htmlspecialchars((string)($row['ip'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td>
        </tr>
      <?php endforeach; endif; ?>
      </tbody>
    </table>
  </div>
</div>
</body>
</html>
