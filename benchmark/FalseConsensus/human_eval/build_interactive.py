#!/usr/bin/env python3
"""Shared builder for a single self-contained interactive annotation page.

One HTML per task = the ONLY file you send an annotator. It embeds:
  - the instructions/codebook (INTRO),
  - every case (DATA, inline JSON),
  - per-case form controls (FIELDS),
and generates the filled CSV client-side (Download button). Progress auto-saves
to the browser's localStorage, so a refresh never loses work. No server, no
internet, no extra files: double-click to open.

`?selftest=1` runs the real export path in-browser and dumps the resulting CSV
(base64) into <pre id=selftest> so a headless Chrome check can verify it.
"""
import json

# %%TOKENS%% are replaced with str.replace (NOT an f-string), so all the CSS/JS
# braces below stay literal. DATA is injected last (it may contain arbitrary text).
_TEMPLATE = r"""<meta charset="utf-8">
<title>%%TITLE%%</title>
<style>
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  max-width:920px;margin:0 auto;padding:0 1rem 6rem;color:#111;background:#fff}
#bar{position:sticky;top:0;z-index:10;background:#111;color:#fff;margin:0 -1rem 1rem;padding:.6rem 1rem;
  display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;box-shadow:0 2px 8px rgba(0,0,0,.2)}
#bar input[type=text]{padding:.35rem .5rem;border-radius:6px;border:1px solid #555;background:#222;color:#fff;font-size:14px}
#bar label.chk{font-size:13px;opacity:.85;display:flex;align-items:center;gap:.3rem}
#prog{font-weight:600;font-variant-numeric:tabular-nums}
button{cursor:pointer;border:0;border-radius:8px;padding:.5rem .95rem;font-size:14px;font-weight:600;background:#0a7;color:#fff}
button:hover{background:#096}
#intro{background:#f5f5f7;border-radius:10px;padding:.4rem 1.1rem;margin:0 0 1.4rem}
#intro summary{cursor:pointer;font-weight:700;font-size:16px;padding:.6rem 0}
#intro ul{margin:.3rem 0 .8rem}#intro code{background:#e6e6ea;padding:0 .3em;border-radius:3px}
.card{border:1px solid #e3e3e8;border-left:5px solid #d33;border-radius:10px;padding:.2rem 1.1rem 1rem;margin:1.1rem 0;background:#fff}
.card.done{border-left-color:#0a7;background:#fbfffd}
.card h2{font-size:15px;color:#333;margin:1rem 0 .4rem}
.meta{background:#f5f5f7;border-radius:8px;padding:.5rem .8rem;margin:.4rem 0;font-size:14px;word-break:break-word}
.wrong{color:#c00}.right{color:#080}
.ai{background:#fff7e6;border-left:3px solid #e0a800;padding:.4rem .8rem;margin:.4rem 0;font-size:14px}
details>summary{cursor:pointer;color:#06c;margin:.4rem 0}
pre{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;border-radius:6px;padding:.7rem;font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:340px;overflow:auto}
.fields{display:flex;flex-wrap:wrap;gap:.7rem 1.2rem;align-items:center;margin-top:.8rem;padding-top:.7rem;border-top:1px dashed #ddd}
.fields label{font-size:14px;font-weight:600}
.fields select{font-size:14px;padding:.3rem .4rem;border-radius:6px;border:1px solid #bbb}
.fields label.notes{flex:1 1 100%;font-weight:400}
.fields label.notes input{width:100%;padding:.4rem .5rem;border-radius:6px;border:1px solid #bbb;font-size:14px}
body.hideDone .card.done{display:none}
@media (prefers-color-scheme:dark){
  body{background:#161618;color:#e6e6e6}#intro{background:#222}#intro code{background:#333}
  .card{background:#1c1c1f;border-color:#333}.card.done{background:#16201b}.card h2{color:#bbb}
  .meta{background:#252528}.ai{background:#2a2410}pre{background:#111;border-color:#333;color:#ddd}
  .fields select,.fields label.notes input{background:#222;color:#eee;border-color:#555}
  .wrong{color:#ff7b7b}.right{color:#5cd68a}
}
</style>

<div id="bar">
  <span>标注员姓名:</span><input type="text" id="annot" placeholder="pinyin / name" size="12">
  <span id="prog">0 / 0</span>
  <button id="dl">⬇ 下载 CSV</button>
  <label class="chk"><input type="checkbox" id="onlyTodo"> 只看未标注</label>
</div>

<details id="intro" open>
<summary>说明书(点此展开/收起)</summary>
%%INTRO%%
</details>

<div id="list"></div>

<script type="application/json" id="data">%%DATA%%</script>
<script>
const COLUMNS = %%COLUMNS%%;
const FIELDS  = %%FIELDS%%;
const TASK_ID = "%%TASK_ID%%";
const FILE_PREFIX = "%%FILE_PREFIX%%";
const DATA = JSON.parse(document.getElementById('data').textContent);
const REQ = FIELDS[0].key;               // first human field = the required label
const KEY = 'fc_annot_' + TASK_ID;

function escHtml(v){ return String(v==null?'':v)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function esc(v){ v=(v==null?'':String(v)); return /[",\n\r]/.test(v) ? '"'+v.replace(/"/g,'""')+'"' : v; }

%%RENDER_INFO%%

let state = {};
try{ state = JSON.parse(localStorage.getItem(KEY)) || {}; }catch(e){ state = {}; }
function save(){ try{ localStorage.setItem(KEY, JSON.stringify(state)); }catch(e){} }

const listEl = document.getElementById('list');
const progEl = document.getElementById('prog');
const nameEl = document.getElementById('annot');

DATA.forEach(function(rec, i){
  const card = document.createElement('div');
  card.className = 'card'; card.id = 'card'+i;
  let h = renderInfo(rec, i) + '<div class="fields">';
  FIELDS.forEach(function(f){
    if (f.type === 'text'){
      h += '<label class="notes">'+escHtml(f.label)+'<br><input type="text" data-i="'+i+'" data-k="'+f.key+'"></label>';
    } else {
      h += '<label>'+escHtml(f.label)+' <select data-i="'+i+'" data-k="'+f.key+'">';
      f.options.forEach(function(o){ h += '<option value="'+escHtml(o.value)+'">'+escHtml(o.label)+'</option>'; });
      h += '</select></label>';
    }
  });
  card.innerHTML = h + '</div>';
  listEl.appendChild(card);
});

// restore saved values into the controls (no HTML-attr escaping headaches)
function applyState(){
  DATA.forEach(function(_, i){
    const st = state[i]; if(!st) return;
    FIELDS.forEach(function(f){
      const el = listEl.querySelector('[data-i="'+i+'"][data-k="'+f.key+'"]');
      if (el && st[f.key] != null) el.value = st[f.key];
    });
    markCard(i);
  });
}
function markCard(i){
  const done = !!(state[i] && state[i][REQ]);
  document.getElementById('card'+i).classList.toggle('done', done);
}
function updateProgress(){
  let n=0; for(let i=0;i<DATA.length;i++){ if(state[i] && state[i][REQ]) n++; }
  progEl.textContent = n + ' / ' + DATA.length;
  progEl.style.color = (n===DATA.length) ? '#5cd68a' : '#ffd27a';
}
function setField(i, k, v){ state[i] = state[i] || {}; state[i][k] = v; save(); markCard(i); updateProgress(); }

listEl.addEventListener('change', function(e){
  const t = e.target; if(t.dataset && t.dataset.i!==undefined) setField(+t.dataset.i, t.dataset.k, t.value);
});
listEl.addEventListener('input', function(e){
  const t = e.target; if(t.tagName==='INPUT' && t.dataset && t.dataset.i!==undefined) setField(+t.dataset.i, t.dataset.k, t.value);
});

nameEl.value = state.__name__ || '';
nameEl.addEventListener('input', function(){ state.__name__ = nameEl.value; save(); });

document.getElementById('onlyTodo').addEventListener('change', function(e){
  document.body.classList.toggle('hideDone', e.target.checked);
});

function buildCSV(){
  const rows = [ COLUMNS.map(esc).join(',') ];
  DATA.forEach(function(rec, i){
    const hum = FIELDS.map(function(f){ return (state[i] && state[i][f.key]) || ''; });
    rows.push(rec.csv.concat(hum).map(esc).join(','));
  });
  return '﻿' + rows.join('\r\n');
}
document.getElementById('dl').addEventListener('click', function(){
  let n=0; for(let i=0;i<DATA.length;i++){ if(state[i] && state[i][REQ]) n++; }
  if (n < DATA.length && !confirm('还有 '+(DATA.length-n)+' 条未标注,仍要导出吗?')) return;
  const name = (nameEl.value.trim() || 'anon').replace(/[^0-9A-Za-z_-]/g,'_');
  const blob = new Blob([buildCSV()], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = FILE_PREFIX + '_' + name + '.csv';
  document.body.appendChild(a); a.click(); a.remove();
});

applyState(); updateProgress();

// ---- headless self-test: exercise the REAL export path and dump the CSV ----
if (location.search.indexOf('selftest') >= 0){
  state = {};
  state[0] = {};
  FIELDS.forEach(function(f){
    state[0][f.key] = (f.type==='text') ? 'has, comma "quote"\nand newline 中文' : f.options[1].value;
  });
  const pre = document.createElement('pre'); pre.id = 'selftest';
  pre.textContent = btoa(unescape(encodeURIComponent(buildCSV())));
  document.body.appendChild(pre);
}
</script>
"""


def render_page(*, title, intro_html, columns, fields, data, task_id, file_prefix):
    """Assemble the interactive HTML string.

    columns: list[str] full CSV header (fixed cols + the human cols, in order).
    fields:  list[{key,label,type('select'|'text'),options?:[{value,label}]}].
             fields[0] is the required label used for progress/done state.
    data:    list[dict]; each MUST carry rec['csv'] = the fixed cell values in
             header order (len == len(columns) - len(fields)). Other keys feed
             the task-specific renderInfo(rec, i) JS.
    """
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (_TEMPLATE
            .replace("%%TITLE%%", title)
            .replace("%%INTRO%%", intro_html)
            .replace("%%COLUMNS%%", json.dumps(columns, ensure_ascii=False))
            .replace("%%FIELDS%%", json.dumps(fields, ensure_ascii=False))
            .replace("%%TASK_ID%%", task_id)
            .replace("%%FILE_PREFIX%%", file_prefix)
            .replace("%%RENDER_INFO%%", RENDER_INFO[task_id])
            .replace("%%DATA%%", data_json))     # DATA last: may contain arbitrary text
    return html


# Task-specific JS that turns a record into the card's info block. Kept here so
# the make_* scripts stay tiny. Must define `function renderInfo(rec, i){...}`.
RENDER_INFO = {
    "taxonomy": r"""
function renderInfo(rec, i){
  var fc = rec.fc ? 'right' : 'wrong';
  var ai = rec.ai_type ? '<div class="ai">AI 初判: <b>'+escHtml(rec.ai_type)+'</b> — '+escHtml(rec.ai_reason||'')+'（可推翻）</div>' : '';
  return '<h2>#'+(i+1)+' · problem '+escHtml(rec.pid)+'</h2>'
    + '<div class="meta">gold 正解: <b>'+escHtml(rec.target)+'</b> &nbsp;|&nbsp; 错误停在: <b class="wrong">'+escHtml(rec.stop)+'</b>'
    + ' &nbsp;|&nbsp; 完整推理答案: <b class="'+fc+'">'+escHtml(rec.final)+'</b> ('+(rec.fc?'correct':'incorrect')+')</div>'
    + '<div class="meta">probe 流 ('+rec.nprobes+'): '+escHtml(rec.rle)+'</div>'
    + ai
    + '<details open><summary>题目</summary><pre>'+escHtml(rec.problem)+'</pre></details>'
    + '<details><summary>完整模型推理（'+(rec.full_text?rec.full_text.length:0)+' 字符）</summary><pre>'+escHtml(rec.full_text||'')+'</pre></details>';
}
""",
    "grader": r"""
function renderInfo(rec, i){
  var v = rec.correct ? 'right' : 'wrong';
  return '<h2>Row '+rec.row+' · '+escHtml(rec.model)+' / '+escHtml(rec.benchmark)+' / problem '+escHtml(rec.pid)+'</h2>'
    + '<div class="meta">gold 正解: <b>'+escHtml(rec.gold)+'</b> &nbsp;|&nbsp; 模型答案: <b>'+escHtml(rec.ans)+'</b>'
    + ' &nbsp;|&nbsp; grader 判定: <b class="'+v+'">'+(rec.correct?'correct':'incorrect')+'</b></div>'
    + '<details><summary>题目（等价性不明时再看）</summary><pre>'+escHtml(rec.problem)+'</pre></details>';
}
""",
}
