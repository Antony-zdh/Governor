#!/usr/bin/env python3
"""Shared builder for a single self-contained interactive annotation page.

One HTML per task = the ONLY file you send an annotator. It embeds:
  - the instructions/codebook (INTRO),
  - every case (DATA, inline JSON),
  - KaTeX (vendored, fonts inlined) so all $...$ / \\[...\\] math RENDERS,
  - each [asy] figure compiled to an inline <svg> (via asy_render.py) so
    annotators see the actual diagram instead of Asymptote source,
  - per-case form controls (FIELDS),
and generates the filled CSV client-side (Download button). Progress auto-saves
to the browser's localStorage. No server, no internet, no extra files.

`?selftest=1` runs the real export path in-browser and dumps the resulting CSV
(base64) into <pre id=selftest> so a headless check can verify it.
"""
import json, re, hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASY_RE = re.compile(r"\[asy\](.*?)\[/asy\]", re.S | re.I)


def load_figmap():
    """{block_hash: inline_svg} produced by asy_render.py; {} if not yet rendered."""
    fp = HERE / "fig_svgs.json"
    return json.load(open(fp)) if fp.exists() else {}


def problem_to_parts(problem, figmap):
    """Split a problem into text/figure segments; figures carry rendered SVG (or None)."""
    parts, last = [], 0
    for m in ASY_RE.finditer(problem):
        if m.start() > last:
            parts.append({"t": "text", "v": problem[last:m.start()]})
        h = hashlib.sha1(m.group(1).encode("utf-8")).hexdigest()[:16]
        parts.append({"t": "fig", "v": figmap.get(h)})
        last = m.end()
    if last < len(problem):
        parts.append({"t": "text", "v": problem[last:]})
    return parts or [{"t": "text", "v": problem}]


# %%TOKENS%% are replaced with str.replace (NOT an f-string), so all CSS/JS braces
# below stay literal. DATA is injected last (may contain arbitrary text).
_TEMPLATE = r"""<meta charset="utf-8">
<title>%%TITLE%%</title>
<style>%%KATEX_CSS%%</style>
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
.prob{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;border-radius:6px;padding:.8rem;margin:.3rem 0;font-size:14.5px}
.prob .tx{white-space:pre-wrap}
.fig{display:block;background:#fff;border:1px solid #e6e6e6;border-radius:8px;padding:10px;margin:.6rem 0;text-align:center}
.fig svg{max-width:100%;height:auto}
.fig.nofig{color:#999;font-style:italic;background:#f7f7f7}
pre.rzpre{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;border-radius:6px;padding:.7rem;font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:360px;overflow:auto}
.fields{display:flex;flex-wrap:wrap;gap:.7rem 1.2rem;align-items:center;margin-top:.8rem;padding-top:.7rem;border-top:1px dashed #ddd}
.fields label{font-size:14px;font-weight:600}
.fields select{font-size:14px;padding:.3rem .4rem;border-radius:6px;border:1px solid #bbb}
.fields label.notes{flex:1 1 100%;font-weight:400}
.fields label.notes input{width:100%;padding:.4rem .5rem;border-radius:6px;border:1px solid #bbb;font-size:14px}
body.hideDone .card.done{display:none}
@media (prefers-color-scheme:dark){
  body{background:#161618;color:#e6e6e6}#intro{background:#222}#intro code{background:#333}
  .card{background:#1c1c1f;border-color:#333}.card.done{background:#16201b}.card h2{color:#bbb}
  .meta{background:#252528}.ai{background:#2a2410}.prob{background:#111;border-color:#333}
  pre.rzpre{background:#111;border-color:#333;color:#ddd}
  .fields select,.fields label.notes input{background:#222;color:#eee;border-color:#555}
  .wrong{color:#ff7b7b}.right{color:#5cd68a}
  .katex{color:#e6e6e6}
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

<script>%%KATEX_JS%%</script>
<script type="application/json" id="data">%%DATA%%</script>
<script id="app">
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
// wrap a short answer in \( \) so KaTeX renders it, iff it looks like TeX
function M(v){ v=String(v==null?'':v).replace(/^\$+|\$+$/g,'');
  return /[\\^_{}]/.test(v) ? '\\('+escHtml(v)+'\\)' : escHtml(v); }
// build the problem block from text/figure parts (figure = trusted inline SVG)
function renderProblem(parts){
  let h='<div class="prob">';
  for(const p of parts){
    if(p.t==='fig') h += p.v ? '<span class="fig">'+p.v+'</span>' : '<span class="fig nofig">［配图无法渲染，请看原题］</span>';
    else h += '<span class="tx">'+escHtml(p.v)+'</span>';
  }
  return h+'</div>';
}
// Self-rolled math renderer using katex core (the contrib auto-render's
// renderMathInElement no-ops in this build, but katex.renderToString works).
// Walks text nodes under `el`, splits on $$..$$ / \[..\] / \(..\) / $..$, and
// replaces each math run with a rendered span. Skips .rle/.rzpre and already
// rendered .katex subtrees; safe to call more than once.
function typeset(el){
  if(!el || typeof katex==='undefined' || typeof document.createTreeWalker!=='function') return;
  var SKIP={SCRIPT:1,STYLE:1,TEXTAREA:1};
  var walker=document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {acceptNode:function(n){
    if(!/\$|\\\(|\\\[/.test(n.nodeValue)) return NodeFilter.FILTER_REJECT;
    for(var p=n.parentNode; p && p!==el.parentNode; p=p.parentNode){
      if(SKIP[p.nodeName]) return NodeFilter.FILTER_REJECT;
      var cl=''+(p.className||'');
      if(cl.indexOf('katex')>=0 || cl.indexOf('rle')>=0 || cl.indexOf('rzpre')>=0) return NodeFilter.FILTER_REJECT;
    }
    return NodeFilter.FILTER_ACCEPT;
  }});
  var todo=[], n; while(n=walker.nextNode()) todo.push(n);
  var RE=/\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$([^$\n]+?)\$/g;
  todo.forEach(function(tn){
    var s=tn.nodeValue, frag=document.createDocumentFragment(), last=0, m, any=false;
    RE.lastIndex=0;
    while(m=RE.exec(s)){
      any=true;
      if(m.index>last) frag.appendChild(document.createTextNode(s.slice(last,m.index)));
      var disp=(m[1]!=null||m[2]!=null), tex=m[1]||m[2]||m[3]||m[4]||'';
      var span=document.createElement('span');
      try{ span.innerHTML=katex.renderToString(tex,{displayMode:disp,throwOnError:false}); }
      catch(e){ span.textContent=m[0]; }
      frag.appendChild(span); last=RE.lastIndex;
    }
    if(!any) return;
    if(last<s.length) frag.appendChild(document.createTextNode(s.slice(last)));
    tn.parentNode.replaceChild(frag, tn);
  });
}

%%RENDER_INFO%%

let state = {};
try{ state = JSON.parse(localStorage.getItem(KEY)) || {}; }catch(e){ state = {}; }
function save(){ try{ localStorage.setItem(KEY, JSON.stringify(state)); }catch(e){} }

const listEl = document.getElementById('list');
const progEl = document.getElementById('prog');
const nameEl = document.getElementById('annot');
const cards = [];

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
  listEl.appendChild(card); cards.push(card);
});

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
  cards[i].classList.toggle('done', done);
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

// render math: problem+meta eagerly; heavy reasoning lazily on first open
cards.forEach(function(card){
  typeset(card);
  const rz = card.querySelector && card.querySelector('details.rz');
  if(rz) rz.addEventListener('toggle', function(){
    if(rz.open && !rz._done){ rz._done = 1; typeset(rz.querySelector('pre')); }
  });
});

// ---- headless self-test: exercise the REAL export path and dump the CSV ----
if (location.search.indexOf('selftest') >= 0){
  state = {}; state[0] = {};
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
    """Assemble the interactive HTML string. Each rec in `data` MUST carry
    rec['csv'] (fixed cell values in header order) and rec['parts'] (problem
    segments from problem_to_parts). Task-specific renderInfo is in RENDER_INFO."""
    vendor = HERE / "vendor"
    katex_css = (vendor / "katex.min.css").read_text(encoding="utf-8")
    katex_js = (vendor / "katex.min.js").read_text(encoding="utf-8")
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (_TEMPLATE
            .replace("%%TITLE%%", title)
            .replace("%%KATEX_CSS%%", katex_css)
            .replace("%%INTRO%%", intro_html)
            .replace("%%COLUMNS%%", json.dumps(columns, ensure_ascii=False))
            .replace("%%FIELDS%%", json.dumps(fields, ensure_ascii=False))
            .replace("%%TASK_ID%%", task_id)
            .replace("%%FILE_PREFIX%%", file_prefix)
            .replace("%%RENDER_INFO%%", RENDER_INFO[task_id])
            .replace("%%KATEX_JS%%", katex_js)
            .replace("%%DATA%%", data_json))     # DATA last: may contain arbitrary text
    return html


# Task-specific JS: turn a record into the card's info block. Must define
# `function renderInfo(rec, i){...}` and use renderProblem(rec.parts) + M().
RENDER_INFO = {
    "taxonomy": r"""
function renderInfo(rec, i){
  var fc = rec.fc ? 'right' : 'wrong';
  var ai = rec.ai_type ? '<div class="ai">AI 初判: <b>'+escHtml(rec.ai_type)+'</b> — '+escHtml(rec.ai_reason||'')+'（可推翻）</div>' : '';
  return '<h2>#'+(i+1)+' · problem '+escHtml(rec.pid)+'</h2>'
    + '<div class="meta">gold 正解: <b>'+M(rec.target)+'</b> &nbsp;|&nbsp; 错误停在: <b class="wrong">'+M(rec.stop)+'</b>'
    + ' &nbsp;|&nbsp; 完整推理答案: <b class="'+fc+'">'+M(rec.final)+'</b> ('+(rec.fc?'correct':'incorrect')+')</div>'
    + '<div class="meta rle">probe 流 ('+rec.nprobes+'): '+escHtml(rec.rle)+'</div>'
    + ai
    + '<div><b>题目:</b></div>' + renderProblem(rec.parts)
    + '<details class="rz"><summary>完整模型推理（'+(rec.rlen||0)+' 字符）</summary><pre class="rzpre">'+escHtml(rec.full_text||'')+'</pre></details>';
}
""",
    "grader": r"""
function renderInfo(rec, i){
  var v = rec.correct ? 'right' : 'wrong';
  return '<h2>Row '+rec.row+' · '+escHtml(rec.model)+' / '+escHtml(rec.benchmark)+' / problem '+escHtml(rec.pid)+'</h2>'
    + '<div class="meta">gold 正解: <b>'+M(rec.gold)+'</b> &nbsp;|&nbsp; 模型答案: <b>'+M(rec.ans)+'</b>'
    + ' &nbsp;|&nbsp; grader 判定: <b class="'+v+'">'+(rec.correct?'correct':'incorrect')+'</b></div>'
    + '<details class="rz"><summary>题目（等价性不明时再看）</summary>' + renderProblem(rec.parts) + '</details>';
}
""",
}
