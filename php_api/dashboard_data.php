<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$examId = trim((string)($_GET['exam_id'] ?? 'demo-exam'));
$studentId = trim((string)($_GET['student_id'] ?? ''));
$cheatOnly = ((string)($_GET['cheat_only'] ?? '0')) === '1';

$state = load_state(__DIR__, $examId);
$stateStudents = is_array($state['students'] ?? null) ? $state['students'] : [];
$events = is_array($state['events'] ?? null) ? $state['events'] : [];
$cmd = load_commands(__DIR__, $examId);
$cmdStudents = is_array($cmd['students'] ?? null) ? $cmd['students'] : [];
$roster = get_exam_students(__DIR__, $examId);

$rows = [];
foreach ($roster as $entry) {
    if (!is_array($entry)) continue;
    $sid = trim((string)($entry['student_id'] ?? ''));
    if ($sid === '') continue;
    $saved = $stateStudents[$sid] ?? [];
    $commands = $cmdStudents[$sid] ?? ['terminate' => false, 'screenshot_once' => false, 'process_report_once' => false];
    $rows[] = [
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
        'latest_shot' => (string)($saved['latest_shot'] ?? ''),
        'cmd' => $commands,
    ];
}

$ids = array_map(static fn($r) => (string)($r['student_id'] ?? ''), $rows);
foreach ($stateStudents as $sid => $saved) {
    if (in_array((string)$sid, $ids, true) || !is_array($saved)) continue;
    $rows[] = [
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
        'latest_shot' => (string)($saved['latest_shot'] ?? ''),
        'cmd' => $cmdStudents[$sid] ?? ['terminate' => false, 'screenshot_once' => false, 'process_report_once' => false],
    ];
}

usort($rows, static fn($a, $b) => strcmp((string)$a['student_id'], (string)$b['student_id']));

$detail = [];
if ($studentId !== '') {
    foreach (array_reverse($events) as $e) {
        if (!is_array($e)) continue;
        if ((string)($e['student_id'] ?? '') !== $studentId) continue;
        if ($cheatOnly && empty($e['is_cheat'])) continue;
        $detail[] = $e;
        if (count($detail) >= 250) break;
    }
}

send_json([
    'ok' => true,
    'exam_id' => $examId,
    'last_update' => (string)($state['last_update'] ?? ''),
    'students' => $rows,
    'detail' => $detail,
]);
