<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$payload = read_json();
if ($payload === []) {
    send_json(['ok' => false, 'error' => 'invalid json'], 400);
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
    send_json(['ok' => false, 'error' => 'missing exam_id/event_type'], 400);
}

$exams = load_exams(__DIR__);
if (!isset($exams[$examId])) {
    send_json(['ok' => false, 'error' => 'auth failed'], 403);
}
$exam = $exams[$examId];
$examPass = (string)($exam['passkey'] ?? '');

$passOk = ($passkey !== '' && $passkey === $examPass);
$tokenOk = ($token !== '' && verify_token($token, $examId, $examPass, $ip, get_secret(__DIR__)));
if (!$passOk && !$tokenOk) {
    send_json(['ok' => false, 'error' => 'auth failed'], 403);
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
    'user_agent' => (string)($_SERVER['HTTP_USER_AGENT'] ?? ''),
];

try {
    append_log(__DIR__, $examId, $record);

    if ($studentId !== '') {
        $state = load_state(__DIR__, $examId);
        if (!isset($state['students']) || !is_array($state['students'])) {
            $state['students'] = [];
        }

        if (!isset($state['students'][$studentId]) || !is_array($state['students'][$studentId])) {
            $state['students'][$studentId] = [
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
        }

        $row = $state['students'][$studentId];
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

        $abnormalEvents = [
            'entry_denied_environment',
            'blocked_process_detected',
            'blocked_process_killed',
            'suspicious_key',
            'shortcut_blocked',
            'client_close_attempt',
            'close_blocked',
        ];
        if (in_array($record['event_type'], $abnormalEvents, true)) {
            $row['abnormal_count'] = (int)($row['abnormal_count'] ?? 0) + 1;
            $row['abnormal_last'] = $record['event_type'];
        }

        $state['students'][$studentId] = $row;
        save_state(__DIR__, $examId, $state);
    }
} catch (Throwable $e) {
    send_json(['ok' => false, 'error' => 'server write error: ' . $e->getMessage()], 500);
}

send_json(['ok' => true]);
