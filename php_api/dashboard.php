<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$examId = trim((string)($_GET['exam_id'] ?? 'demo-exam'));
$state = load_state(__DIR__, $examId);
$stateStudents = $state['students'] ?? [];
if (!is_array($stateStudents)) {
    $stateStudents = [];
}

$roster = get_exam_students(__DIR__, $examId);
$rows = [];
foreach ($roster as $entry) {
    if (!is_array($entry)) {
        continue;
    }
    $sid = trim((string)($entry['student_id'] ?? ''));
    if ($sid === '') {
        continue;
    }
    $saved = $stateStudents[$sid] ?? [];
    $rows[$sid] = [
        'student_id' => $sid,
        'name' => (string)($saved['name'] ?? $entry['name'] ?? ''),
        'class_name' => (string)($saved['class_name'] ?? $entry['class_name'] ?? ''),
        'login' => (bool)($saved['login'] ?? false),
        'abnormal_count' => (int)($saved['abnormal_count'] ?? 0),
        'abnormal_last' => (string)($saved['abnormal_last'] ?? ''),
        'last_event' => (string)($saved['last_event'] ?? ''),
        'last_event_time' => (string)($saved['last_event_time'] ?? ''),
        'ip' => (string)($saved['ip'] ?? ''),
    ];
}

foreach ($stateStudents as $sid => $saved) {
    if (isset($rows[$sid])) {
        continue;
    }
    if (!is_array($saved)) {
        continue;
    }
    $rows[$sid] = [
        'student_id' => (string)$sid,
        'name' => (string)($saved['name'] ?? ''),
        'class_name' => (string)($saved['class_name'] ?? ''),
        'login' => (bool)($saved['login'] ?? false),
        'abnormal_count' => (int)($saved['abnormal_count'] ?? 0),
        'abnormal_last' => (string)($saved['abnormal_last'] ?? ''),
        'last_event' => (string)($saved['last_event'] ?? ''),
        'last_event_time' => (string)($saved['last_event_time'] ?? ''),
        'ip' => (string)($saved['ip'] ?? ''),
    ];
}

uasort($rows, static fn(array $a, array $b): int => strcmp($a['student_id'], $b['student_id']));
?>
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>监考面板 - <?php echo htmlspecialchars($examId, ENT_QUOTES, 'UTF-8'); ?></title>
<style>body{font-family:Arial;background:#f5f7fb;padding:20px}.card{background:#fff;padding:16px;border-radius:10px}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #eee;padding:8px}.ok{color:#11823b}.bad{color:#cf222e}</style>
</head>
<body><div class="card"><h2>监考面板（<?php echo htmlspecialchars($examId, ENT_QUOTES, 'UTF-8'); ?>）</h2>
<div>最后更新时间：<?php echo htmlspecialchars((string)($state['last_update'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></div>
<table><thead><tr><th>学号</th><th>姓名</th><th>班级</th><th>登录</th><th>异常次数</th><th>最近异常</th><th>最后事件</th><th>时间</th><th>IP</th></tr></thead><tbody>
<?php if ($rows === []): ?><tr><td colspan="9">暂无数据</td></tr><?php else: foreach ($rows as $r): ?>
<tr><td><?php echo htmlspecialchars($r['student_id'], ENT_QUOTES, 'UTF-8'); ?></td><td><?php echo htmlspecialchars($r['name'], ENT_QUOTES, 'UTF-8'); ?></td><td><?php echo htmlspecialchars($r['class_name'], ENT_QUOTES, 'UTF-8'); ?></td><td><?php echo $r['login'] ? '<span class="ok">已登录</span>' : '<span class="bad">未登录</span>'; ?></td><td><?php echo (int)$r['abnormal_count']; ?></td><td><?php echo htmlspecialchars($r['abnormal_last'], ENT_QUOTES, 'UTF-8'); ?></td><td><?php echo htmlspecialchars($r['last_event'], ENT_QUOTES, 'UTF-8'); ?></td><td><?php echo htmlspecialchars($r['last_event_time'], ENT_QUOTES, 'UTF-8'); ?></td><td><?php echo htmlspecialchars($r['ip'], ENT_QUOTES, 'UTF-8'); ?></td></tr>
<?php endforeach; endif; ?></tbody></table></div></body></html>
