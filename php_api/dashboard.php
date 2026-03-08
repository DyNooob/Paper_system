<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$examId = trim((string)($_GET['exam_id'] ?? 'demo-exam'));
$selectedStudent = trim((string)($_GET['student_id'] ?? ''));
$cheatOnly = ((string)($_GET['cheat_only'] ?? '0')) === '1';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $sid = trim((string)($_POST['student_id'] ?? ''));
    $action = trim((string)($_POST['action'] ?? ''));
    $value = trim((string)($_POST['value'] ?? '1'));
    if ($sid !== '' && in_array($action, ['terminate', 'screenshot_once'], true)) {
        $cmd = load_commands(__DIR__, $examId);
        if (!isset($cmd['students']) || !is_array($cmd['students'])) {
            $cmd['students'] = [];
        }
        if (!isset($cmd['students'][$sid]) || !is_array($cmd['students'][$sid])) {
            $cmd['students'][$sid] = ['terminate' => false, 'screenshot_once' => false];
        }
        $cmd['students'][$sid][$action] = in_array(strtolower($value), ['1', 'true', 'on', 'yes'], true);
        save_commands(__DIR__, $examId, $cmd);
    }
    header('Location: ?exam_id=' . urlencode($examId) . '&student_id=' . urlencode($selectedStudent) . '&cheat_only=' . ($cheatOnly ? '1' : '0'));
    exit;
}

$state = load_state(__DIR__, $examId);
$stateStudents = is_array($state['students'] ?? null) ? $state['students'] : [];
$events = is_array($state['events'] ?? null) ? $state['events'] : [];
$cmd = load_commands(__DIR__, $examId);
$cmdStudents = is_array($cmd['students'] ?? null) ? $cmd['students'] : [];
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
    $commands = $cmdStudents[$sid] ?? ['terminate' => false, 'screenshot_once' => false];
    $rows[$sid] = [
        'student_id' => $sid,
        'name' => (string)($saved['name'] ?? $entry['name'] ?? ''),
        'class_name' => (string)($saved['class_name'] ?? $entry['class_name'] ?? ''),
        'login' => (bool)($saved['login'] ?? false),
        'login_count' => (int)($saved['login_count'] ?? 0),
        'locked_out' => (bool)($saved['locked_out'] ?? false),
        'abnormal_count' => (int)($saved['abnormal_count'] ?? 0),
        'abnormal_last' => (string)($saved['abnormal_last'] ?? ''),
        'last_event' => (string)($saved['last_event'] ?? ''),
        'last_event_time' => (string)($saved['last_event_time'] ?? ''),
        'ip' => (string)($saved['ip'] ?? ''),
        'latest_shot' => (string)($saved['latest_shot'] ?? ''),
        'cmd_terminate' => (bool)($commands['terminate'] ?? false),
        'cmd_shot' => (bool)($commands['screenshot_once'] ?? false),
    ];
}

foreach ($stateStudents as $sid => $saved) {
    if (isset($rows[$sid]) || !is_array($saved)) {
        continue;
    }
    $commands = $cmdStudents[$sid] ?? ['terminate' => false, 'screenshot_once' => false];
    $rows[$sid] = [
        'student_id' => (string)$sid,
        'name' => (string)($saved['name'] ?? ''),
        'class_name' => (string)($saved['class_name'] ?? ''),
        'login' => (bool)($saved['login'] ?? false),
        'login_count' => (int)($saved['login_count'] ?? 0),
        'locked_out' => (bool)($saved['locked_out'] ?? false),
        'abnormal_count' => (int)($saved['abnormal_count'] ?? 0),
        'abnormal_last' => (string)($saved['abnormal_last'] ?? ''),
        'last_event' => (string)($saved['last_event'] ?? ''),
        'last_event_time' => (string)($saved['last_event_time'] ?? ''),
        'ip' => (string)($saved['ip'] ?? ''),
        'latest_shot' => (string)($saved['latest_shot'] ?? ''),
        'cmd_terminate' => (bool)($commands['terminate'] ?? false),
        'cmd_shot' => (bool)($commands['screenshot_once'] ?? false),
    ];
}

uasort($rows, static fn(array $a, array $b): int => strcmp($a['student_id'], $b['student_id']));

$studentEvents = [];
if ($selectedStudent !== '') {
    foreach (array_reverse($events) as $e) {
        if (!is_array($e)) {
            continue;
        }
        if ((string)($e['student_id'] ?? '') !== $selectedStudent) {
            continue;
        }
        if ($cheatOnly && empty($e['is_cheat'])) {
            continue;
        }
        $studentEvents[] = $e;
        if (count($studentEvents) >= 200) {
            break;
        }
    }
}
?>
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>监考面板 - <?php echo htmlspecialchars($examId, ENT_QUOTES, 'UTF-8'); ?></title>
<style>
body{font-family:Arial;background:#f5f7fb;padding:16px}.card{background:#fff;padding:14px;border-radius:8px;margin-bottom:12px}
table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #eee;padding:8px;font-size:13px}th{background:#fafafa}
.ok{color:#11823b}.bad{color:#cf222e}.muted{color:#666}.btn{padding:4px 8px;border:1px solid #bbb;background:#fff;border-radius:4px;cursor:pointer}
</style></head><body>
<div class="card"><h2>监考面板（<?php echo htmlspecialchars($examId, ENT_QUOTES, 'UTF-8'); ?>）</h2><div class="muted">最后更新时间：<?php echo htmlspecialchars((string)($state['last_update'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></div></div>

<div class="card">
<table><thead><tr><th>学号</th><th>姓名</th><th>班级</th><th>登录/次数</th><th>锁定</th><th>异常</th><th>最后事件</th><th>截图</th><th>控制</th></tr></thead><tbody>
<?php if ($rows === []): ?><tr><td colspan="9">暂无数据</td></tr><?php else: foreach ($rows as $r): ?>
<tr>
<td><a href="?exam_id=<?php echo urlencode($examId); ?>&student_id=<?php echo urlencode($r['student_id']); ?>&cheat_only=<?php echo $cheatOnly ? '1' : '0'; ?>"><?php echo htmlspecialchars($r['student_id'], ENT_QUOTES, 'UTF-8'); ?></a></td>
<td><?php echo htmlspecialchars($r['name'], ENT_QUOTES, 'UTF-8'); ?></td>
<td><?php echo htmlspecialchars($r['class_name'], ENT_QUOTES, 'UTF-8'); ?></td>
<td><?php echo $r['login'] ? '<span class="ok">已登录</span>' : '<span class="bad">未登录</span>'; ?> / <?php echo (int)$r['login_count']; ?></td>
<td><?php echo $r['locked_out'] ? '<span class="bad">已锁定</span>' : '<span class="ok">正常</span>'; ?></td>
<td><?php echo (int)$r['abnormal_count']; ?> <?php echo htmlspecialchars($r['abnormal_last'], ENT_QUOTES, 'UTF-8'); ?></td>
<td><?php echo htmlspecialchars($r['last_event'], ENT_QUOTES, 'UTF-8'); ?><br><span class="muted"><?php echo htmlspecialchars($r['last_event_time'], ENT_QUOTES, 'UTF-8'); ?></span></td>
<td><?php if ($r['latest_shot'] !== ''): ?><a target="_blank" href="<?php echo htmlspecialchars($r['latest_shot'], ENT_QUOTES, 'UTF-8'); ?>">查看</a><?php else: ?><span class="muted">无</span><?php endif; ?></td>
<td>
<form method="post" style="display:inline"><input type="hidden" name="student_id" value="<?php echo htmlspecialchars($r['student_id'], ENT_QUOTES, 'UTF-8'); ?>"><input type="hidden" name="action" value="terminate"><input type="hidden" name="value" value="1"><button class="btn" type="submit">终止答题</button></form>
<form method="post" style="display:inline"><input type="hidden" name="student_id" value="<?php echo htmlspecialchars($r['student_id'], ENT_QUOTES, 'UTF-8'); ?>"><input type="hidden" name="action" value="screenshot_once"><input type="hidden" name="value" value="1"><button class="btn" type="submit">截屏</button></form>
</td>
</tr>
<?php endforeach; endif; ?>
</tbody></table>
</div>

<div class="card">
<h3>学生详情：<?php echo htmlspecialchars($selectedStudent === '' ? '未选择' : $selectedStudent, ENT_QUOTES, 'UTF-8'); ?></h3>
<div><a href="?exam_id=<?php echo urlencode($examId); ?>&student_id=<?php echo urlencode($selectedStudent); ?>&cheat_only=0">全部操作</a> | <a href="?exam_id=<?php echo urlencode($examId); ?>&student_id=<?php echo urlencode($selectedStudent); ?>&cheat_only=1">仅作弊相关</a></div>
<table><thead><tr><th>时间</th><th>事件</th><th>说明</th><th>详情</th></tr></thead><tbody>
<?php if ($studentEvents === []): ?><tr><td colspan="4">暂无记录</td></tr><?php else: foreach ($studentEvents as $e): ?>
<tr><td><?php echo htmlspecialchars((string)($e['server_time'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td><td><?php echo htmlspecialchars((string)($e['event_type'] ?? ''), ENT_QUOTES, 'UTF-8'); ?></td><td><?php echo htmlspecialchars((string)($e['event_label'] ?? ''), ENT_QUOTES, 'UTF-8'); ?><?php if (!empty($e['is_cheat'])) echo ' ⚠️'; ?></td><td><pre style="margin:0;white-space:pre-wrap"><?php echo htmlspecialchars(json_encode($e['detail'] ?? [], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), ENT_QUOTES, 'UTF-8'); ?></pre></td></tr>
<?php endforeach; endif; ?>
</tbody></table>
</div>
</body></html>
