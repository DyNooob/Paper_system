<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$mode = trim((string)($_GET['mode'] ?? $_POST['mode'] ?? 'pull'));
$examId = trim((string)($_GET['exam_id'] ?? $_POST['exam_id'] ?? ''));
$passkey = trim((string)($_GET['passkey'] ?? $_POST['passkey'] ?? ''));
$token = trim((string)($_GET['token'] ?? $_POST['token'] ?? ''));
$studentId = trim((string)($_GET['student_id'] ?? $_POST['student_id'] ?? ''));
$ip = trim((string)($_GET['ip'] ?? $_POST['ip'] ?? ($_SERVER['REMOTE_ADDR'] ?? '')));

if ($examId === '' || $studentId === '') {
    send_json(['ok' => false, 'error' => 'missing exam_id/student_id'], 200);
}

$exams = load_exams(__DIR__);
if (!isset($exams[$examId])) {
    send_json(['ok' => false, 'error' => 'exam not found'], 200);
}
$exam = $exams[$examId];
$examPass = (string)($exam['passkey'] ?? '');

$auth = ($passkey !== '' && $passkey === $examPass) || ($token !== '' && verify_token($token, $examId, $examPass, $ip, get_secret(__DIR__)));
if (!$auth) {
    send_json(['ok' => false, 'error' => 'auth failed'], 200);
}

$commands = load_commands(__DIR__, $examId);
if (!isset($commands['students']) || !is_array($commands['students'])) {
    $commands['students'] = [];
}
if (!isset($commands['students'][$studentId]) || !is_array($commands['students'][$studentId])) {
    $commands['students'][$studentId] = ['terminate' => false, 'realtime_screenshot' => false];
}

if ($mode === 'set') {
    $action = trim((string)($_POST['action'] ?? $_GET['action'] ?? ''));
    $value = (string)($_POST['value'] ?? $_GET['value'] ?? '1');
    $flag = in_array(strtolower($value), ['1', 'true', 'on', 'yes'], true);
    if (!in_array($action, ['terminate', 'realtime_screenshot'], true)) {
        send_json(['ok' => false, 'error' => 'unknown action'], 200);
    }
    $commands['students'][$studentId][$action] = $flag;
    save_commands(__DIR__, $examId, $commands);
    send_json(['ok' => true, 'student_id' => $studentId, 'commands' => $commands['students'][$studentId]], 200);
}

send_json(['ok' => true, 'student_id' => $studentId, 'commands' => $commands['students'][$studentId]], 200);
