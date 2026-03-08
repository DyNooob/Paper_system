<?php
declare(strict_types=1);
require_once __DIR__ . '/common.php';

$id = trim((string)($_GET['id'] ?? $_GET['exam_id'] ?? ''));
$passkey = trim((string)($_GET['passkey'] ?? $_GET['key'] ?? ''));
$ip = trim((string)($_GET['ip'] ?? ''));
if ($ip === '') {
    $ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
}

if ($id === '' || $passkey === '') {
    send_json(['ok' => false, 'error' => 'missing id/passkey'], 200);
}

$exams = load_exams(__DIR__);
if (!isset($exams[$id])) {
    send_json([
        'ok' => false,
        'error' => 'exam not found',
        'exam_id' => $id,
        'available_ids' => array_keys($exams),
    ], 200);
}

$exam = $exams[$id];
if (($exam['passkey'] ?? '') !== $passkey) {
    send_json(['ok' => false, 'error' => 'invalid passkey', 'exam_id' => $id], 200);
}

$ttl = max(60, (int)($exam['session_ttl_sec'] ?? 21600));
$exp = time() + $ttl;
$token = create_token($id, $passkey, $ip, $exp, get_secret(__DIR__));

send_json([
    'ok' => true,
    'config' => [
        'exam_url' => (string)($exam['exam_url'] ?? ''),
        'force_fullscreen' => (bool)($exam['force_fullscreen'] ?? true),
        'top_most' => (bool)($exam['top_most'] ?? true),
        'require_single_monitor' => (bool)($exam['require_single_monitor'] ?? true),
        'allow_force_kill' => (bool)($exam['allow_force_kill'] ?? false),
        'blocked_processes' => array_values($exam['blocked_processes'] ?? []),
        'detect_vm' => (bool)($exam['detect_vm'] ?? true),
        'allowed_os' => array_values($exam['allowed_os'] ?? ['windows']),
        'require_student_login' => (bool)($exam['require_student_login'] ?? true),
        'max_login_attempts_per_student' => max(1, (int)($exam['max_login_attempts_per_student'] ?? 1)),
        'allow_exit_hotkey' => (bool)($exam['allow_exit_hotkey'] ?? true),
        'exit_hotkey' => (string)($exam['exit_hotkey'] ?? 'Esc'),
        'focus_guard' => (bool)($exam['focus_guard'] ?? true),
        'allow_realtime_screenshot_control' => (bool)($exam['allow_realtime_screenshot_control'] ?? true),
        'class_options' => array_values($exam['class_options'] ?? []),
        'heartbeat_interval_sec' => max(5, (int)($exam['heartbeat_interval_sec'] ?? 20)),
        'process_scan_interval_sec' => max(1, (int)($exam['process_scan_interval_sec'] ?? 3)),
        'focus_check_interval_sec' => max(1, (int)($exam['focus_check_interval_sec'] ?? 1)),
    ],
    'session_token' => $token,
    'token_expire_at' => gmdate('c', $exp),
]);
