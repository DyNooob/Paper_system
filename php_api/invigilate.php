<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$payload = read_json();
if ($payload === []) {
    send_json(['ok' => false, 'error' => 'invalid json'], 200);
}

$examId = trim((string)($payload['exam_id'] ?? ''));
$passkey = trim((string)($payload['passkey'] ?? ''));
$token = trim((string)($payload['token'] ?? ''));
$eventType = trim((string)($payload['event_type'] ?? ''));
$ip = trim((string)($payload['ip'] ?? ''));
if ($ip === '') {
    $ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
}

if ($examId === '' || $eventType === '') {
    send_json(['ok' => false, 'error' => 'missing exam_id/event_type'], 200);
}

$exams = load_exams(__DIR__);
if (!isset($exams[$examId])) {
    send_json(['ok' => false, 'error' => 'auth failed: exam_id not exists'], 200);
}
$exam = $exams[$examId];
$examPass = (string)($exam['passkey'] ?? '');
$passOk = ($passkey !== '' && $passkey === $examPass);
$tokenOk = ($token !== '' && verify_token($token, $examId, $examPass, $ip, get_secret(__DIR__)));
if (!$passOk && !$tokenOk) {
    send_json(['ok' => false, 'error' => 'auth failed: token/passkey invalid'], 200);
}

$student = $payload['student'] ?? [];
if (!is_array($student)) {
    $student = [];
}
$studentId = trim((string)($student['student_id'] ?? ''));
$name = trim((string)($student['name'] ?? ''));
$className = trim((string)($student['class_name'] ?? ''));

$detail = $payload['detail'] ?? [];
if (!is_array($detail)) {
    $detail = ['raw' => (string)$detail];
}

$requireLogin = (bool)($exam['require_student_login'] ?? true);
$roster = get_exam_students(__DIR__, $examId);
if ($eventType === 'student_login' && $requireLogin) {
    if ($studentId === '' || $name === '' || $className === '') {
        send_json(['ok' => false, 'error' => 'student_login missing fields'], 200);
    }
    if ($roster !== []) {
        $matched = find_student_in_roster($roster, $studentId);
        if ($matched === null) {
            send_json(['ok' => false, 'error' => 'student not in roster'], 200);
        }
        if (trim((string)($matched['name'] ?? '')) !== $name || trim((string)($matched['class_name'] ?? '')) !== $className) {
            send_json(['ok' => false, 'error' => 'student name/class mismatch'], 200);
        }
    }
}

$record = [
    'server_time' => gmdate('c'),
    'exam_id' => $examId,
    'event_type' => substr($eventType, 0, 80),
    'ip' => $ip,
    'student_id' => $studentId,
    'name' => $name,
    'class_name' => $className,
    'detail' => $detail,
    'client_time' => (string)($payload['client_time'] ?? ''),
    'platform' => (string)($payload['platform'] ?? ''),
];

try {
    append_log(__DIR__, $examId, $record);
    $state = load_state(__DIR__, $examId);
    if (!isset($state['students']) || !is_array($state['students'])) {
        $state['students'] = [];
    }

    if ($studentId !== '') {
        $row = $state['students'][$studentId] ?? [
            'student_id' => $studentId,
            'name' => $name,
            'class_name' => $className,
            'login' => false,
            'last_event' => '',
            'last_event_time' => '',
            'abnormal_count' => 0,
            'abnormal_last' => '',
            'ip' => $ip,
        ];
        if ($name !== '') {
            $row['name'] = $name;
        }
        if ($className !== '') {
            $row['class_name'] = $className;
        }
        $row['ip'] = $ip;
        $row['last_event'] = $record['event_type'];
        $row['last_event_time'] = $record['server_time'];
        if ($record['event_type'] === 'student_login') {
            $row['login'] = true;
        }

        $abnormal = ['entry_denied_environment', 'blocked_process_detected', 'blocked_process_killed', 'suspicious_key', 'shortcut_blocked', 'client_close_attempt', 'close_blocked'];
        if (in_array($record['event_type'], $abnormal, true)) {
            $row['abnormal_count'] = (int)($row['abnormal_count'] ?? 0) + 1;
            $row['abnormal_last'] = $record['event_type'];
        }
        $state['students'][$studentId] = $row;
    }

    save_state(__DIR__, $examId, $state);
} catch (Throwable $e) {
    send_json(['ok' => false, 'error' => 'server write error: ' . $e->getMessage()], 200);
}

send_json(['ok' => true], 200);
