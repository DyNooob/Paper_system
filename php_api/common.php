<?php
declare(strict_types=1);

function send_json(array $payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function read_json(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') {
        return [];
    }
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : [];
}

function load_json_file(string $file, array $fallback = []): array
{
    if (!is_file($file)) {
        return $fallback;
    }
    $decoded = json_decode((string)file_get_contents($file), true);
    return is_array($decoded) ? $decoded : $fallback;
}

function safe_id(string $id): string
{
    return preg_replace('/[^a-zA-Z0-9_-]/', '_', $id) ?: 'unknown';
}

function ensure_dir(string $dir): void
{
    if (!is_dir($dir) && !mkdir($dir, 0775, true) && !is_dir($dir)) {
        throw new RuntimeException('cannot create dir: ' . $dir);
    }
}

function load_exams(string $base): array
{
    $data = load_json_file($base . '/exams.json', []);
    if ($data === []) {
        send_json(['ok' => false, 'error' => 'exams.json missing or invalid'], 200);
    }
    return $data;
}

function load_students_map(string $base): array
{
    return load_json_file($base . '/students.json', []);
}

function get_exam_students(string $base, string $examId): array
{
    $map = load_students_map($base);
    $rows = $map[$examId] ?? [];
    return is_array($rows) ? $rows : [];
}

function find_student_in_roster(array $roster, string $studentId): ?array
{
    foreach ($roster as $row) {
        if (!is_array($row)) {
            continue;
        }
        if (trim((string)($row['student_id'] ?? '')) === $studentId) {
            return $row;
        }
    }
    return null;
}

function get_secret(string $base): string
{
    $env = getenv('PAPER_API_SECRET');
    if (is_string($env) && $env !== '') {
        return $env;
    }
    $f = $base . '/secret.key';
    if (is_file($f)) {
        $k = trim((string)file_get_contents($f));
        if ($k !== '') {
            return $k;
        }
    }
    return 'change-me';
}

function b64u_enc(string $v): string
{
    return rtrim(strtr(base64_encode($v), '+/', '-_'), '=');
}

function b64u_dec(string $v): string|false
{
    $pad = strlen($v) % 4;
    if ($pad > 0) {
        $v .= str_repeat('=', 4 - $pad);
    }
    return base64_decode(strtr($v, '-_', '+/'), true);
}

function create_token(string $examId, string $passkey, string $ip, int $exp, string $secret): string
{
    $payload = [
        'exam_id' => $examId,
        'passkey_sha' => hash('sha256', $passkey),
        'ip' => $ip,
        'exp' => $exp,
    ];
    $json = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    $sig = hash_hmac('sha256', $json, $secret, true);
    return b64u_enc($json) . '.' . b64u_enc($sig);
}

function verify_token(string $token, string $examId, string $passkey, string $ip, string $secret): bool
{
    if (strpos($token, '.') === false) {
        return false;
    }
    [$pj, $ps] = explode('.', $token, 2);
    $json = b64u_dec($pj);
    $sig = b64u_dec($ps);
    if (!is_string($json) || !is_string($sig)) {
        return false;
    }
    if (!hash_equals(hash_hmac('sha256', $json, $secret, true), $sig)) {
        return false;
    }
    $x = json_decode($json, true);
    if (!is_array($x)) {
        return false;
    }
    return ($x['exam_id'] ?? '') === $examId
        && ($x['passkey_sha'] ?? '') === hash('sha256', $passkey)
        && ($x['ip'] ?? '') === $ip
        && (int)($x['exp'] ?? 0) >= time();
}

function load_state(string $base, string $examId): array
{
    ensure_dir($base . '/data');
    return load_json_file($base . '/data/' . safe_id($examId) . '_state.json', ['students' => [], 'last_update' => gmdate('c')]);
}

function save_state(string $base, string $examId, array $state): void
{
    ensure_dir($base . '/data');
    $state['last_update'] = gmdate('c');
    $json = json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if (file_put_contents($base . '/data/' . safe_id($examId) . '_state.json', $json, LOCK_EX) === false) {
        throw new RuntimeException('write state failed');
    }
}

function append_log(string $base, string $examId, array $record): void
{
    ensure_dir($base . '/logs');
    $f = $base . '/logs/' . safe_id($examId) . '-' . date('Ymd') . '.log';
    $line = json_encode($record, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . PHP_EOL;
    if (file_put_contents($f, $line, FILE_APPEND | LOCK_EX) === false) {
        throw new RuntimeException('write log failed');
    }
}

function load_commands(string $base, string $examId): array
{
    ensure_dir($base . '/data');
    return load_json_file($base . '/data/' . safe_id($examId) . '_commands.json', ['students' => []]);
}

function save_commands(string $base, string $examId, array $commands): void
{
    ensure_dir($base . '/data');
    $json = json_encode($commands, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if (file_put_contents($base . '/data/' . safe_id($examId) . '_commands.json', $json, LOCK_EX) === false) {
        throw new RuntimeException('write commands failed');
    }
}

function event_label(string $eventType): string
{
    $map = [
        'suspicious_key' => '可疑按键',
        'shortcut_blocked' => '拦截快捷键',
        'focus_lost' => '窗口失焦',
        'blocked_process_detected' => '发现禁用进程',
        'blocked_process_killed' => '结束禁用进程',
        'entry_denied_environment' => '环境冲突阻止进入',
        'close_blocked' => '拦截关闭',
        'student_login' => '考生登录',
        'heartbeat' => '心跳',
        'exam_exit' => '主动退出考试',
        'terminated_by_admin' => '监考员终止答题',
        'screenshot_frame' => '实时截图',
        'process_report' => '进程快照上报',
    ];
    return $map[$eventType] ?? $eventType;
}

function is_cheat_event(string $eventType): bool
{
    $cheat = ['suspicious_key', 'shortcut_blocked', 'focus_lost', 'blocked_process_detected', 'entry_denied_environment', 'exam_exit'];
    return in_array($eventType, $cheat, true);
}
