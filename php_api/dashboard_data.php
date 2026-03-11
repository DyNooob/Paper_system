<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$examIdRaw = trim((string)($_GET['exam_id'] ?? 'demo-exam'));
$examId = $examIdRaw;
$studentId = trim((string)($_GET['student_id'] ?? ''));
$cheatOnly = ((string)($_GET['cheat_only'] ?? '0')) === '1';

$exams = load_exams(__DIR__);
$resolved = resolve_exam($exams, $examIdRaw);
if ($resolved['ok']) {
    $examId = (string)$resolved['key'];
}

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
    $commands = $cmdStudents[$sid] ?? ['terminate' => false, 'terminate_reason' => '', 'screenshot_once' => false, 'process_report_once' => false, 'notice_message' => ''];
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

        'status' => (string)($saved['status'] ?? ((bool)($saved['locked_out'] ?? false) ? 'terminated' : (((bool)($saved['login'] ?? false)) ? 'answering' : 'not_logged_in'))),
        'status_label' => (string)($saved['status_label'] ?? ((bool)($saved['locked_out'] ?? false) ? '强制结束' : (((bool)($saved['login'] ?? false)) ? '作答中' : '未登录'))),
        'status_color' => (string)($saved['status_color'] ?? ((bool)($saved['locked_out'] ?? false) ? 'red' : (((bool)($saved['login'] ?? false)) ? 'orange' : 'gray'))),
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

        'status' => (string)($saved['status'] ?? ((bool)($saved['locked_out'] ?? false) ? 'terminated' : (((bool)($saved['login'] ?? false)) ? 'answering' : 'not_logged_in'))),
        'status_label' => (string)($saved['status_label'] ?? ((bool)($saved['locked_out'] ?? false) ? '强制结束' : (((bool)($saved['login'] ?? false)) ? '作答中' : '未登录'))),
        'status_color' => (string)($saved['status_color'] ?? ((bool)($saved['locked_out'] ?? false) ? 'red' : (((bool)($saved['login'] ?? false)) ? 'orange' : 'gray'))),
        'cmd' => $cmdStudents[$sid] ?? ['terminate' => false, 'terminate_reason' => '', 'screenshot_once' => false, 'process_report_once' => false, 'notice_message' => ''],
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

$policy = is_array($state['policy'] ?? null) ? $state['policy'] : [];
send_json([
    'ok' => true,
    'exam_id' => $examId,
    'last_update' => (string)($state['last_update'] ?? ''),
    'students' => $rows,
    'detail' => $detail,
    'policy' => [
        'auto_warn_cheat_count' => (int)($policy['auto_warn_cheat_count'] ?? ($resolved['exam']['auto_warn_cheat_count'] ?? 0)),
        'auto_terminate_cheat_count' => (int)($policy['auto_terminate_cheat_count'] ?? ($resolved['exam']['auto_terminate_cheat_count'] ?? 0)),
    ],
]);
