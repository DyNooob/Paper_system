<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$mode = trim((string)($_GET['mode'] ?? $_POST['mode'] ?? 'pull'));
$examIdRaw = trim((string)($_GET['exam_id'] ?? $_POST['exam_id'] ?? ''));
$examId = $examIdRaw;
$adminPasskey = trim((string)($_GET['passkey'] ?? $_POST['passkey'] ?? ''));
$token = trim((string)($_GET['token'] ?? $_POST['token'] ?? ''));
$studentId = trim((string)($_GET['student_id'] ?? $_POST['student_id'] ?? ''));
$ip = trim((string)($_GET['ip'] ?? $_POST['ip'] ?? ($_SERVER['REMOTE_ADDR'] ?? '')));

if ($examIdRaw === '' || $studentId === '') {
    send_json(['ok' => false, 'error' => 'missing exam_id/student_id'], 200);
}

$exams = load_exams(__DIR__);
$resolved = resolve_exam($exams, $examIdRaw);
if (!$resolved['ok']) {
    send_json(['ok' => false, 'error' => 'exam not found', 'exam_id' => $examIdRaw], 200);
}
$examId = (string)$resolved['key'];
$exam = is_array($resolved['exam']) ? $resolved['exam'] : [];
$adminPass = get_admin_passkey($exam);
$studentPass = get_student_passkey($exam);
$auth = ($adminPasskey !== '' && $adminPasskey === $adminPass) || ($token !== '' && verify_token($token, $examId, $studentPass, $ip, get_secret(__DIR__)));
if (!$auth) {
    send_json(['ok' => false, 'error' => 'auth failed'], 200);
}


if ($mode === 'set_policy') {
    $warn = max(0, (int)($_POST['auto_warn_cheat_count'] ?? $_GET['auto_warn_cheat_count'] ?? 0));
    $terminate = max(0, (int)($_POST['auto_terminate_cheat_count'] ?? $_GET['auto_terminate_cheat_count'] ?? 0));
    $state = load_state(__DIR__, $examId);
    if (!isset($state['policy']) || !is_array($state['policy'])) {
        $state['policy'] = [];
    }
    $state['policy']['auto_warn_cheat_count'] = $warn;
    $state['policy']['auto_terminate_cheat_count'] = $terminate;
    save_state(__DIR__, $examId, $state);
    send_json(['ok' => true, 'policy' => $state['policy']], 200);
}

$commands = load_commands(__DIR__, $examId);
if (!isset($commands['students']) || !is_array($commands['students'])) {
    $commands['students'] = [];
}
if (!isset($commands['students'][$studentId]) || !is_array($commands['students'][$studentId])) {
    $commands['students'][$studentId] = ['terminate' => false, 'screenshot_once' => false, 'process_report_once' => false, 'notice_message' => ''];
}

if ($mode === 'set') {
    $action = trim((string)($_POST['action'] ?? $_GET['action'] ?? ''));
    $value = (string)($_POST['value'] ?? $_GET['value'] ?? '1');
    if (!in_array($action, ['terminate', 'screenshot_once', 'process_report_once', 'notice_message'], true)) {
        send_json(['ok' => false, 'error' => 'unknown action'], 200);
    }
    if ($action === 'notice_message') {
        $commands['students'][$studentId][$action] = substr(trim($value), 0, 200);
    } else {
        $commands['students'][$studentId][$action] = in_array(strtolower($value), ['1', 'true', 'on', 'yes'], true);
    }
    save_commands(__DIR__, $examId, $commands);
    send_json(['ok' => true, 'commands' => $commands['students'][$studentId]], 200);
}

send_json(['ok' => true, 'commands' => $commands['students'][$studentId]], 200);
