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

function load_exams(string $base): array
{
    $file = $base . '/exams.json';
    $data = load_json_file($file, []);
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

function ensure_dir(string $dir): void
{
    if (!is_dir($dir) && !mkdir($dir, 0775, true) && !is_dir($dir)) {
        throw new RuntimeException('cannot create dir: ' . $dir);
    }
}

function safe_id(string $id): string
{
    return preg_replace('/[^a-zA-Z0-9_-]/', '_', $id) ?: 'unknown';
}

function load_state(string $base, string $examId): array
{
    $dir = $base . '/data';
    ensure_dir($dir);
    $f = $dir . '/' . safe_id($examId) . '_state.json';
    return load_json_file($f, ['students' => [], 'last_update' => gmdate('c')]);
}

function save_state(string $base, string $examId, array $state): void
{
    $dir = $base . '/data';
    ensure_dir($dir);
    $f = $dir . '/' . safe_id($examId) . '_state.json';
    $state['last_update'] = gmdate('c');
    $json = json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if (file_put_contents($f, $json, LOCK_EX) === false) {
        throw new RuntimeException('write state failed');
    }
}

function append_log(string $base, string $examId, array $record): void
{
    $dir = $base . '/logs';
    ensure_dir($dir);
    $f = $dir . '/' . safe_id($examId) . '-' . date('Ymd') . '.log';
    $line = json_encode($record, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . PHP_EOL;
    if (file_put_contents($f, $line, FILE_APPEND | LOCK_EX) === false) {
        throw new RuntimeException('write log failed');
    }
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
