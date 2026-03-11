<?php
declare(strict_types=1);
$examIdRaw = (string)($_GET['exam_id'] ?? 'demo-exam');
$examId = htmlspecialchars($examIdRaw, ENT_QUOTES, 'UTF-8');
$passkeyRaw = (string)($_GET['passkey'] ?? '');
?>
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>监考面板 - <?php echo $examId; ?></title>
<style>
body{font-family:Inter,Arial;background:#f3f5fb;margin:0;padding:16px;color:#1f2937}
.top{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}
.grid{display:grid;grid-template-columns:minmax(760px,1.7fr) minmax(440px,1fr);gap:12px;align-items:start}
.card{background:#fff;border-radius:12px;padding:12px;box-shadow:0 3px 12px rgba(0,0,0,.06);overflow:hidden}
table{width:100%;border-collapse:collapse;table-layout:fixed}
th,td{padding:8px;border-bottom:1px solid #eee;font-size:13px;vertical-align:top;word-break:break-word}
th{text-align:left;background:#fafafa}
.badge{padding:2px 8px;border-radius:999px;font-weight:700;font-size:12px;color:#222;display:inline-block}
.badge.gray{background:#e5e7eb;color:#374151}.badge.red{background:#fecaca;color:#7f1d1d}.badge.green{background:#bbf7d0;color:#166534}.badge.orange{background:#fed7aa;color:#9a3412}.badge.yellow{background:#fef08a;color:#854d0e}
.btn{border:1px solid #cfd4dc;background:#fff;border-radius:6px;padding:4px 8px;cursor:pointer;margin-right:4px}
.btn:hover{background:#f7f8fa}
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
pre{white-space:pre-wrap;max-height:180px;overflow:auto;margin:0}
#toast{position:fixed;right:16px;bottom:16px;background:#111;color:#fff;padding:10px 12px;border-radius:8px;display:none}
.col-op{width:240px}
input,textarea{border:1px solid #ccd2db;border-radius:6px;padding:5px 8px}
textarea{width:100%;min-height:58px}
</style>
</head>
<body>
<div class="top">
  <h2 style="margin:0">监考面板（<?php echo $examId; ?>）</h2>
  <div class="toolbar">
    <label>管理员口令：</label><input id="passkey" type="password" value="<?php echo htmlspecialchars($passkeyRaw, ENT_QUOTES, 'UTF-8'); ?>">
    <button class="btn" onclick="savePasskey()">保存</button>
    <span id="last" style="color:#6b7280"></span>
  </div>
</div>

<div class="grid">
  <div class="card">
    <div class="toolbar">
      <button class="btn" onclick="refreshNow()">刷新</button><span style="color:#6b7280">自动刷新 2s</span>
      <label>自动警告阈值</label><input id="warnCount" type="number" min="0" value="0" style="width:70px">
      <label>自动终止阈值</label><input id="termCount" type="number" min="0" value="0" style="width:70px">
      <button class="btn" onclick="savePolicy()">保存阈值</button>
    </div>
    <table id="students"><thead><tr><th>学号</th><th>姓名</th><th>班级</th><th>状态</th><th>异常</th><th>最后事件</th><th>截图</th><th class="col-op">操作</th></tr></thead><tbody></tbody></table>
  </div>
  <div class="card">
    <div class="toolbar">
      <b id="detailTitle">学生详情</b>
      <label><input type="checkbox" id="cheatOnly"> 仅作弊相关</label>
    </div>
    <div style="margin-bottom:8px">
      <textarea id="noticeText" placeholder="给当前选中学生发送通知/警告"></textarea>
      <button class="btn" onclick="sendNotice()">发送通知</button>
    </div>
    <table id="detail"><thead><tr><th style="width:130px">时间</th><th style="width:90px">事件</th><th style="width:110px">说明</th><th>详情</th></tr></thead><tbody></tbody></table>
  </div>
</div>
<div id="toast"></div>
<script>
const examId = <?php echo json_encode($examIdRaw, JSON_UNESCAPED_UNICODE); ?>;
let selected = '';
let passkey = localStorage.getItem('paper_admin_passkey') || <?php echo json_encode($passkeyRaw, JSON_UNESCAPED_UNICODE); ?>;
const esc = (s)=>String(s??'').replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));
document.getElementById('passkey').value = passkey;

function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.style.display='block';setTimeout(()=>t.style.display='none',1800)}
function savePasskey(){passkey=document.getElementById('passkey').value.trim();localStorage.setItem('paper_admin_passkey',passkey);toast('管理员口令已保存')}

async function sendCmd(studentId, action, value='1') {
  if(!passkey){toast('请先填写管理员口令');return}
  if(action==='terminate' && !confirm('确认终止该考生考试？')) return;
  const url = `command.php?mode=set&exam_id=${encodeURIComponent(examId)}&student_id=${encodeURIComponent(studentId)}&passkey=${encodeURIComponent(passkey)}&action=${encodeURIComponent(action)}&value=${encodeURIComponent(value)}`;
  const res = await fetch(url); const data = await res.json();
  if(!data.ok){toast('命令失败: '+(data.error||'unknown'));return}
  toast('命令已下发');
  await refreshNow();
}

async function savePolicy(){
  if(!passkey){toast('请先填写管理员口令');return}
  const w=document.getElementById('warnCount').value||'0';
  const t=document.getElementById('termCount').value||'0';
  const url=`command.php?mode=set_policy&exam_id=${encodeURIComponent(examId)}&student_id=${encodeURIComponent(selected||'__policy__')}&passkey=${encodeURIComponent(passkey)}&auto_warn_cheat_count=${encodeURIComponent(w)}&auto_terminate_cheat_count=${encodeURIComponent(t)}`;
  const res=await fetch(url);const data=await res.json();
  if(!data.ok){toast('保存失败');return}
  toast('阈值已保存');
}

function statusBadge(r){
  const color = esc(r.status_color || 'gray');
  const label = esc(r.status_label || '未登录');
  return `<span class="badge ${color}">${label}</span>`;
}

function renderStudents(rows){
  const tbody=document.querySelector('#students tbody'); tbody.innerHTML='';
  for(const r of rows){
    const tr=document.createElement('tr');
    const shot = r.latest_shot ? `<a target="_blank" href="${esc(r.latest_shot)}">查看</a>` : '<span style="color:#6b7280">无</span>';
    tr.innerHTML=`<td><a href="#" data-sid="${esc(r.student_id)}">${esc(r.student_id)}</a></td><td>${esc(r.name)}</td><td>${esc(r.class_name)}</td><td>${statusBadge(r)}<br><span style="color:#6b7280">次数:${r.login_count}</span></td><td>${r.abnormal_count}<br><span style="color:#6b7280">${esc(r.abnormal_last)}</span></td><td>${esc(r.last_event)}<br><span style="color:#6b7280">${esc(r.last_event_time)}</span></td><td>${shot}</td><td><button class="btn" data-act="terminate" data-sid="${esc(r.student_id)}">终止</button><button class="btn" data-act="screenshot_once" data-sid="${esc(r.student_id)}">截屏</button><button class="btn" data-act="process_report_once" data-sid="${esc(r.student_id)}">获取进程</button></td>`;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll('a[data-sid]').forEach(a=>a.onclick=(e)=>{e.preventDefault();selected=a.dataset.sid;refreshNow();});
  tbody.querySelectorAll('button[data-act]').forEach(b=>b.onclick=()=>sendCmd(b.dataset.sid,b.dataset.act,'1'));
}

function renderDetail(events){
  document.getElementById('detailTitle').textContent = selected ? `学生详情：${selected}` : '学生详情';
  const tbody=document.querySelector('#detail tbody'); tbody.innerHTML='';
  for(const e of events){
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${esc(e.server_time)}</td><td>${esc(e.event_type)}</td><td>${esc(e.event_label)} ${e.is_cheat?'⚠️':''}</td><td><pre>${esc(JSON.stringify(e.detail||{},null,0))}</pre></td>`;
    tbody.appendChild(tr);
  }
}

async function sendNotice(){
  if(!selected){toast('请先选择学生');return}
  const msg=document.getElementById('noticeText').value.trim();
  if(!msg){toast('通知内容不能为空');return}
  await sendCmd(selected,'notice_message',msg);
  document.getElementById('noticeText').value='';
}

async function refreshNow(){
  const cheat = document.getElementById('cheatOnly').checked ? '1' : '0';
  const url = `dashboard_data.php?exam_id=${encodeURIComponent(examId)}&student_id=${encodeURIComponent(selected)}&cheat_only=${cheat}`;
  const res = await fetch(url); const data = await res.json();
  if(!data.ok){toast('加载失败');return}
  document.getElementById('last').textContent = `最后更新：${data.last_update}`;
  if(data.policy){document.getElementById('warnCount').value=data.policy.auto_warn_cheat_count??0;document.getElementById('termCount').value=data.policy.auto_terminate_cheat_count??0;}
  renderStudents(data.students||[]); renderDetail(data.detail||[]);
}

document.getElementById('cheatOnly').addEventListener('change', refreshNow);
refreshNow(); setInterval(refreshNow, 2000);
</script>
</body></html>
