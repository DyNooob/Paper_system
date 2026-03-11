<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$payload = read_json();
if ($payload === []) {
    send_json(['ok' => false, 'error' => 'invalid json'], 200);
}

$examIdRaw = trim((string)($payload['exam_id'] ?? ''));
$examId = $examIdRaw;
$passkey = trim((string)($payload['passkey'] ?? ''));
$token = trim((string)($payload['token'] ?? ''));
$eventType = trim((string)($payload['event_type'] ?? ''));
$ip = trim((string)($payload['ip'] ?? ($_SERVER['REMOTE_ADDR'] ?? '')));

if ($examIdRaw === '' || $eventType === '') {
    send_json(['ok' => false, 'error' => 'missing exam_id/event_type'], 200);
}

$exams = load_exams(__DIR__);
$resolved = resolve_exam($exams, $examIdRaw);
if (!$resolved['ok']) {
    send_json(['ok' => false, 'error' => 'auth failed: exam_id not exists', 'exam_id' => $examIdRaw], 200);
}
$examId = (string)$resolved['key'];
$exam = is_array($resolved['exam']) ? $resolved['exam'] : [];
$examPass = (string)($exam['passkey'] ?? '');

$auth = ($passkey !== '' && $passkey === $examPass) || ($token !== '' && verify_token($token, $examId, $examPass, $ip, get_secret(__DIR__)));
if (!$auth) {
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

$state = load_state(__DIR__, $examId);
if (!isset($state['students']) || !is_array($state['students'])) {
    $state['students'] = [];
}
if (!isset($state['events']) || !is_array($state['events'])) {
    $state['events'] = [];
}

$maxLogin = max(1, (int)($exam['max_login_attempts_per_student'] ?? 1));
$requireLogin = (bool)($exam['require_student_login'] ?? true);
$roster = get_exam_students(__DIR__, $examId);

if ($studentId !== '' && !isset($state['students'][$studentId])) {
    $state['students'][$studentId] = [
        'student_id' => $studentId,
        'name' => $name,
        'class_name' => $className,
        'login' => false,
        'login_count' => 0,
        'locked_out' => false,
        'last_event' => '',
        'last_event_time' => '',
        'abnormal_count' => 0,
        'abnormal_last' => '',
        'ip' => $ip,
        'latest_shot' => '',
    ];
}

if ($eventType === 'student_login' && $requireLogin) {
    if ($studentId === '' || $name === '' || $className === '') {
        send_json(['ok' => false, 'error' => 'student_login missing fields'], 200);
    }

    $row = $state['students'][$studentId] ?? null;
    if (is_array($row) && !empty($row['locked_out'])) {
        send_json(['ok' => false, 'error' => 'student locked out due to previous exit/termination'], 200);
    }
    if (is_array($row) && (int)($row['login_count'] ?? 0) >= $maxLogin) {
        send_json(['ok' => false, 'error' => 'max login attempts reached'], 200);
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

if ($eventType === 'screenshot_frame' && isset($detail['image_b64']) && $studentId !== '') {
    try {
        ensure_dir(__DIR__ . '/shots/' . safe_id($examId));
        $bin = base64_decode((string)$detail['image_b64'], true);
        if (is_string($bin) && strlen($bin) > 0) {
            $path = __DIR__ . '/shots/' . safe_id($examId) . '/' . safe_id($studentId) . '.jpg';
            file_put_contents($path, $bin, LOCK_EX);
            $detail = ['saved' => true];
            $state['students'][$studentId]['latest_shot'] = 'shots/' . safe_id($examId) . '/' . safe_id($studentId) . '.jpg';
        }
    } catch (Throwable $e) {
        $detail = ['saved' => false, 'error' => $e->getMessage()];
    }
}

$record = [
    'server_time' => gmdate('c'),
    'exam_id' => $examId,
    'student_id' => $studentId,
    'name' => $name,
    'class_name' => $className,
    'event_type' => substr($eventType, 0, 80),
    'event_label' => event_label($eventType),
    'is_cheat' => is_cheat_event($eventType),
    'ip' => $ip,
    'detail' => $detail,
    'client_time' => (string)($payload['client_time'] ?? ''),
];

try {
    append_log(__DIR__, $examId, $record);

    if ($studentId !== '') {
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

        if ($eventType === 'student_login') {
            $row['login'] = true;
            $row['login_count'] = (int)($row['login_count'] ?? 0) + 1;
        }
        if ($eventType === 'exam_exit' || $eventType === 'terminated_by_admin') {
            $row['locked_out'] = true;
            $row['login'] = false;
        }

        if ($eventType === 'session_state') {
            if (array_key_exists('login', $detail)) {
                $row['login'] = (bool)$detail['login'];
            }
            if (array_key_exists('locked_out', $detail)) {
                $row['locked_out'] = (bool)$detail['locked_out'];
            }
        }

        if (is_cheat_event($eventType)) {
            $row['abnormal_count'] = (int)($row['abnormal_count'] ?? 0) + 1;
            $row['abnormal_last'] = $eventType;
        }

        $state['students'][$studentId] = $row;
    }

    $state['events'][] = $record;
    if (count($state['events']) > 5000) {
        $state['events'] = array_slice($state['events'], -5000);
    }

    save_state(__DIR__, $examId, $state);
} catch (Throwable $e) {
    send_json(['ok' => false, 'error' => 'server write error: ' . $e->getMessage()], 200);
}

send_json(['ok' => true], 200);
