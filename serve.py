"""Coding tool. Read source documents, select a passage, code it.

    python serve.py --data ../myproject
    python serve.py --data ../myproject --coder jb --read-only

Runs on your own machine, binds to 127.0.0.1, standard library only.

Nothing is segmented in advance. Selecting a passage creates an excerpt; coding
it puts that excerpt in the corpus. The codebook can start completely empty and
grow as you go, which is the point — the frame and the corpus are built by the
same act.

File handling lives in project.py.
"""
import argparse, json, os, subprocess, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from project import Project


class Server(ThreadingHTTPServer):
    allow_reuse_address = False   # bind must fail if something is already there
    daemon_threads = True


def who_has(port):
    """Best effort: name the process holding a port, so the message is useful."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             timeout=5).stdout
        for line in out.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = line.split()[-1]
                name = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                                      capture_output=True, text=True, timeout=5).stdout
                proc = name.strip().splitlines()[-1].split(",")[0].strip('"')
                return pid, proc
    except Exception:
        pass
    return None, None


def bind(handler, port, fixed):
    """Bind `port`. If the port was not asked for explicitly, walk forward."""
    last = None
    for p in ([port] if fixed else range(port, port + 12)):
        try:
            return Server(("127.0.0.1", p), handler), p
        except OSError as e:
            last = e
    pid, proc = who_has(port)
    held = (f"\nPort {port} is held by {proc} (pid {pid}). Stop it with:"
            f"  taskkill /PID {pid} /F") if pid else ""
    raise SystemExit(
        f"could not bind port {port}: {last}{held}\n"
        "Most likely an older copy of this tool is still running. Stop it, or "
        "pass --port to pick another.")

HERE = os.path.dirname(os.path.abspath(__file__))

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Coding tool</title>
<style>
:root{
  color-scheme:light;
  --ground:#F2F2EF; --surface:#FFF; --surface-2:#F8F8F5;
  --ink:#22212A; --ink-2:#56545F; --ink-3:#86848F;
  --rule:#E0DFDA; --rule-soft:#EBEAE6;
  --accent:#6B7233; --accent-ink:#4E541F; --accent-wash:#EDEFE0;
  --mark:#EDE8B8; --mark-ink:#3F3A12;
  --pos:#1F6FB8; --neg:#C0731F; --warn:#8A4B42;
  --mono:Consolas,"Cascadia Mono","SF Mono",Menlo,monospace;
  --body:"Segoe UI",-apple-system,BlinkMacSystemFont,Arial,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  color-scheme:dark;
  --ground:#17171B; --surface:#1F1F25; --surface-2:#25252C;
  --ink:#EDECEE; --ink-2:#A9A7B2; --ink-3:#75737E;
  --rule:#31313A; --rule-soft:#292930;
  --accent:#A8B45C; --accent-ink:#C3CE84; --accent-wash:#2A2D1E;
  --mark:#4A431C; --mark-ink:#F0E9BE;
  --pos:#4E93CE; --neg:#BC8437; --warn:#CC9186;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font:16px/1.6 var(--body)}
.wrap{display:grid;grid-template-columns:290px 1fr;gap:28px;max-width:1560px;margin:0 auto;padding:18px 22px 90px}
.rail{position:sticky;top:18px;align-self:start;display:grid;gap:13px;max-height:calc(100vh - 36px);overflow:auto;padding-right:4px}
h1{font-size:17px;margin:0}
.sub{margin:2px 0 0;font-family:var(--mono);font-size:10.5px;color:var(--ink-3);line-height:1.5;word-break:break-all}
label.f{display:block;font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);margin:0 0 5px}
input,select,textarea{width:100%;padding:7px 9px;font:14px var(--body);color:var(--ink);background:var(--surface);border:1px solid var(--rule);border-radius:3px}
textarea{resize:vertical;min-height:56px}
button{font:14px var(--body);padding:7px 13px;border-radius:3px;border:1px solid var(--rule);background:var(--surface);color:var(--ink);cursor:pointer}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
button.small{font-size:12.5px;padding:4px 9px}
button.danger{color:var(--warn)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.tally{font-family:var(--mono);font-size:12px;color:var(--ink-3);border-top:1px solid var(--rule);padding-top:11px;margin:0}
.msg{font-family:var(--mono);font-size:11.5px;color:var(--accent-ink);margin:0;min-height:1em}
.msg.err{color:var(--warn)}
/* codebook in the rail */
.cb{display:grid;gap:2px;max-height:300px;overflow:auto}
.cbrow{display:grid;grid-template-columns:1fr auto;gap:6px;align-items:baseline;padding:3px 5px;border-radius:2px;cursor:pointer}
.cbrow:hover{background:var(--surface-2)}
.cbrow b{font-family:var(--mono);font-size:11px;color:var(--accent-ink);font-weight:600}
.cbrow em{font-style:normal;color:var(--ink-2);font-size:12.5px}
.cbrow span{font-family:var(--mono);font-size:10.5px;color:var(--ink-3)}
.cbempty{color:var(--ink-3);font-size:13px;font-style:italic}
/* source list */
.src{background:var(--surface);border:1px solid var(--rule);border-left:3px solid transparent;
  border-radius:3px;padding:12px 15px;margin-bottom:7px;cursor:pointer}
.src:hover{border-color:var(--accent)}
.src.has{border-left-color:var(--accent)}
.src .hdr{display:flex;flex-wrap:wrap;gap:4px 11px;font-family:var(--mono);font-size:10.5px;color:var(--ink-3)}
.src .hdr .pid{color:var(--ink-2);font-weight:600}
.src p{margin:6px 0 0;color:var(--ink-2);font-size:14px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
/* document view */
.doc{background:var(--surface);border:1px solid var(--rule);border-radius:3px;padding:22px 26px}
.doc .hdr{display:flex;flex-wrap:wrap;gap:5px 13px;font-family:var(--mono);font-size:11px;color:var(--ink-3);margin-bottom:14px}
.body{white-space:pre-wrap;font-size:16.5px;line-height:1.75;-webkit-user-select:text;user-select:text}
.body mark{background:var(--mark);color:var(--mark-ink);padding:1px 0;cursor:pointer;border-radius:2px}
.body mark:hover{outline:1px solid var(--accent)}
.hint{color:var(--ink-3);font-size:13px;margin:0 0 14px;font-family:var(--mono)}
/* coding panel */
.panel{position:fixed;right:22px;bottom:22px;width:390px;max-height:78vh;overflow:auto;
  background:var(--surface);border:1px solid var(--accent);border-radius:4px;
  box-shadow:0 12px 40px -12px rgba(0,0,0,.4);padding:16px 18px;display:none;z-index:20}
.panel.on{display:block}
.panel h3{margin:0 0 4px;font-size:15px}
.quote{background:var(--surface-2);border-left:3px solid var(--mark);border-radius:2px;
  padding:9px 11px;font-size:13.5px;margin:0 0 12px;max-height:130px;overflow:auto}
.picker{max-height:230px;overflow:auto;border:1px solid var(--rule);border-radius:3px;padding:7px;margin-top:6px}
.crow{display:grid;grid-template-columns:auto 1fr auto;gap:7px;align-items:center;padding:3px 4px;border-radius:2px}
.crow:hover{background:var(--surface-2)}
.crow.on{background:var(--accent-wash)}
.crow .nm{font-size:13px;line-height:1.3}
.crow .nm b{font-family:var(--mono);font-size:10.5px;color:var(--accent-ink)}
.crow .nm span{color:var(--ink-3);font-size:12px}
.crow select{width:auto;padding:1px 4px;font-size:11.5px;visibility:hidden}
.crow.on select{visibility:visible}
.lensgrp{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);margin:7px 0 3px}
.lensgrp:first-child{margin-top:0}
.empty{color:var(--ink-3);font-family:var(--mono);font-size:13px;padding:26px 0}
dialog{border:1px solid var(--rule);border-radius:4px;background:var(--surface);color:var(--ink);max-width:620px;width:92%;padding:22px}
dialog::backdrop{background:rgba(0,0,0,.45)}
dialog h2{margin:0 0 14px;font-size:17px}
.fld{margin-bottom:11px}
@media(max-width:960px){.wrap{grid-template-columns:1fr}.rail{position:static;max-height:none}
  .panel{position:static;width:auto;max-height:none;margin-top:14px}}
</style></head><body>
<div class="wrap">
<aside class="rail">
  <div><h1>Coding tool</h1><p class="sub" id="meta"></p></div>
  <div><label class="f" for="q">Search sources</label><input id="q" type="search" placeholder="word or phrase"></div>
  <div><label class="f" for="pid">Participant</label><select id="pid"></select></div>
  <div><label class="f" for="game" id="unitlab">Unit</label><select id="game"></select></div>
  <div><label class="f" for="kind">Kind</label><select id="kind"></select></div>
  <div><label class="f" for="status">Status</label><select id="status">
    <option value="">all</option><option value="has">coded</option><option value="none">not coded yet</option></select></div>
  <div><label class="f" for="valence">Valence</label><select id="valence">
    <option value="">all</option><option value="pos">pos</option><option value="neg">neg</option>
    <option value="mixed">mixed</option><option value="neutral">neutral</option>
    <option value="unjudged">not judged yet</option></select></div>
  <div><label class="f" for="lens">Lens</label><select id="lens"></select></div>
  <div id="facets"></div>
  <div><label class="f">Codebook <span id="ccount" style="text-transform:none;letter-spacing:0"></span></label>
    <div class="cb" id="cb"></div>
    <div class="row" style="margin-top:7px"><button class="small" id="newcode">+ New code</button></div>
  </div>
  <p class="tally" id="tally"></p>
  <p class="msg" id="msg"></p>
</aside>
<main id="main"></main>
</div>

<div class="panel" id="panel">
  <h3 id="p_title">Code this passage</h3>
  <p class="sub" id="p_where"></p>
  <blockquote class="quote" id="p_quote"></blockquote>
  <label class="f">Codes</label>
  <input type="search" id="p_search" placeholder="filter codes">
  <div class="picker" id="p_picker"></div>
  <div style="margin-top:10px"><label class="f">Note</label><textarea id="p_note"></textarea></div>
  <p class="msg" id="p_msg"></p>
  <div class="row" style="margin-top:8px">
    <button class="primary" id="p_save">Save</button>
    <button id="p_cancel">Cancel</button>
    <button class="danger small" id="p_del" style="margin-left:auto">Delete</button>
  </div>
</div>

<dialog id="dlgCode"><h2>Define a code</h2>
  <div class="fld"><label class="f">Code id</label><input type="text" id="n_id" placeholder="ENJ-SOMETHING"></div>
  <div class="fld"><label class="f">Lens</label><input type="text" id="n_lens" list="lenslist" placeholder="e.g. 1. Enjoyment">
    <datalist id="lenslist"></datalist></div>
  <div class="fld"><label class="f">Name</label><input type="text" id="n_name" placeholder="Short readable name"></div>
  <div class="fld"><label class="f">Definition</label><textarea id="n_def"></textarea></div>
  <div class="fld"><label class="f">Include — what counts</label><textarea id="n_inc"></textarea></div>
  <div class="fld"><label class="f">Exclude — where it stops, and what to use instead</label><textarea id="n_exc"></textarea></div>
  <p class="msg err" id="n_err"></p>
  <div class="row"><button class="primary" id="n_save">Create</button><button id="n_cancel">Cancel</button></div>
</dialog>

<script>
let D=null, CODES={}, openDoc=null, sel=null;   // sel = {source_id,start,end,text,existing}
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

fetch('api/data').then(r=>r.json()).then(boot);
function boot(d){
  D=d; CODES={}; d.codes.forEach(c=>CODES[c.id]=c);
  $('meta').innerHTML=`${d.meta.sources} sources · ${d.meta.participants} participants · `
    +`${d.meta.plays} ${esc(d.meta.units||'units')}<br>${d.meta.excerpts} excerpts · coder “${esc(d.meta.coder)}”<br>${esc(d.meta.root)}`;
  // Interviews cover a whole session and carry no unit, so filter the blanks out
  // rather than offering an empty option that reads as a missing game.
  const unit=d.meta.unit||'unit', units=d.meta.units||(unit+'s');
  $('unitlab').textContent=unit;
  const games=[...new Set(d.sources.map(s=>s.game))].filter(Boolean).sort();
  $('game').innerHTML=`<option value="">all ${esc(units)}</option>`+games.map(g=>`<option>${esc(g)}</option>`).join('');
  // Source kinds come from the corpus. Hardcoding "survey" and "interview" made
  // this filter match nothing in a study that collected anything else.
  const kinds=[...new Set(d.sources.map(s=>s.kind))].filter(Boolean).sort();
  $('kind').innerHTML='<option value="">all</option>'+kinds.map(k=>`<option>${esc(k)}</option>`).join('');
  const pids=[...new Set(d.sources.map(s=>s.pid))].filter(Boolean)
    .sort((a,b)=>(+a||0)-(+b||0)||String(a).localeCompare(b));
  $('pid').innerHTML='<option value="">all participants</option>'
    +pids.map(p=>`<option value="${esc(p)}">PID${esc(p)}</option>`).join('');
  // One dropdown per facet. Which columns those are is the project's business,
  // not this file's - see frame.json.
  $('facets').innerHTML=(d.facets||[]).map(f=>{
    const vals=[...new Set(d.sources.map(s=>s[f]).filter(v=>v!==''&&v!=null))].sort();
    if(vals.length<2) return '';
    return `<div><label class="f" for="f_${esc(f)}">${esc(f.replace(/_/g,' '))}</label>`
      +`<select id="f_${esc(f)}" data-facet="${esc(f)}"><option value="">all</option>`
      +vals.map(v=>`<option>${esc(v)}</option>`).join('')+`</select></div>`;
  }).join('');
  $('facets').querySelectorAll('select').forEach(el=>
    el.addEventListener('change',()=>{ if(!openDoc) showList(); }));
  $('lenslist').innerHTML=d.lenses.map(l=>`<option>${esc(l)}</option>`).join('');
  // The lens is how the discussion page groups everything, so it needs to be
  // steerable while coding, not only visible afterwards.
  $('lens').innerHTML='<option value="">all lenses</option>'
    +d.lenses.map(l=>`<option>${esc(l)}</option>`).join('')
    +(d.codes.some(c=>!c.lens)?'<option value="__none__">(no lens set)</option>':'');
  drawCodebook();
  openDoc?showDoc(openDoc):showList();
}

function drawCodebook(){
  const cs=D.codes;
  $('ccount').textContent=cs.length?`(${cs.length})`:'';
  if(!cs.length){
    $('cb').innerHTML='<p class="cbempty">Empty. Codes appear here as you define them.</p>';
    return;
  }
  // Grouped by lens, because that is the structure the discussion page reports
  // in - seeing it while coding is what stops a lens quietly filling up.
  const by={};
  cs.forEach(c=>{const L=c.lens||'(no lens set)';(by[L]=by[L]||[]).push(c);});
  $('cb').innerHTML=Object.keys(by).sort().map(L=>
    `<div class="lensgrp">${esc(L)}</div>`+by[L].map(c=>
      `<div class="cbrow" title="${esc(c.definition||'')}" data-code="${esc(c.id)}">
         <span><b>${esc(c.id)}</b><br><em>${esc(c.name)}</em></span>
         <span>${c.plays?c.pct+'%':'—'}</span></div>`).join('')).join('');
}

function filtered(){
  const q=$('q').value.trim().toLowerCase(),game=$('game').value,pid=$('pid').value,
        kind=$('kind').value,status=$('status').value,val=$('valence').value,
        lens=$('lens').value,
        fs=[...document.querySelectorAll('#facets select')]
             .map(e=>[e.dataset.facet,e.value]).filter(([,v])=>v);
  // Valence sits on a coding, not on a document, so this asks whether the
  // document holds any coding judged that way. "unjudged" is the one that has to
  // match a blank rather than a value.
  const hasVal=s=>(D.excerpts[s.source_id]||[]).some(x=>x.codes.some(
    c=>val==='unjudged'?!c[1]:c[1]===val));
  // " " is the sentinel for codes with no lens at all - the ones that would
  // land in "Uncategorised" on the discussion page.
  const hasLens=s=>(D.excerpts[s.source_id]||[]).some(x=>x.codes.some(
    c=>{const L=(CODES[c[0]]||{}).lens||''; return lens==='__none__'?!L:L===lens;}));
  return D.sources.filter(s=>{
    const n=(D.excerpts[s.source_id]||[]).length;
    return (!q||s.text.toLowerCase().includes(q))&&(!game||s.game===game)
      &&(!pid||s.pid===pid)
      &&(!kind||s.kind===kind)&&(!status||(status==='has')===(n>0))
      &&(!val||hasVal(s))&&(!lens||hasLens(s))
      &&fs.every(([f,v])=>s[f]===v);
  });
}

function showList(){
  openDoc=null; hidePanel();
  const rows=filtered();
  const done=D.sources.filter(s=>(D.excerpts[s.source_id]||[]).length).length;
  $('tally').textContent=`showing ${rows.length} of ${D.sources.length} · ${done} touched · ${D.meta.excerpts} excerpts`;
  $('main').innerHTML=rows.length?rows.map(s=>{
    const n=(D.excerpts[s.source_id]||[]).length;
    return `<article class="src${n?' has':''}" data-src="${esc(s.source_id)}">
      <div class="hdr"><span class="pid">PID${esc(s.pid)}</span><span>${esc(s.game)}</span>
        <span>${esc((D.facets||[]).map(f=>s[f]).filter(Boolean).slice(0,3).join(' · '))}</span><span>${esc(s.kind)} · ${esc(s.label)}</span>
        ${n?`<span style="color:var(--accent-ink)">${n} excerpt${n>1?'s':''}</span>`:''}</div>
      <p>${esc(s.text.slice(0,240))}</p></article>`;
  }).join('') : '<p class="empty">Nothing matches those filters.</p>';
}

function showDoc(sid){
  openDoc=sid; hidePanel();
  const s=D.sources.find(x=>x.source_id===sid);
  const exs=(D.excerpts[sid]||[]).slice().sort((a,b)=>a.start-b.start);
  let html='',pos=0;
  for(const e of exs){
    if(e.start<pos) continue;                       // overlaps are not rendered
    html+=`<span data-s="${pos}">${esc(s.text.slice(pos,e.start))}</span>`;
    html+=`<mark data-s="${e.start}" data-x="${esc(e.id)}" title="${esc(e.codes.map(c=>c[0]+' '+c[1]).join(', ')||'no codes')}">`
        + `${esc(s.text.slice(e.start,e.end))}</mark>`;
    pos=e.end;
  }
  html+=`<span data-s="${pos}">${esc(s.text.slice(pos))}</span>`;
  $('tally').textContent=`${exs.length} excerpt${exs.length===1?'':'s'} in this document`;
  $('main').innerHTML=`<div class="doc">
    <div class="hdr"><span style="color:var(--ink-2);font-weight:600">PID${esc(s.pid)}</span>
      <span>${esc(s.game)}</span><span>${esc((D.facets||[]).map(f=>s[f]).filter(Boolean).slice(0,3).join(' · '))}</span>
      <span>${esc(s.kind)} · ${esc(s.label)}</span></div>
    <p class="hint">Select any passage to code it. Click a highlight to edit it.</p>
    <div class="body" id="body">${html}</div>
    <div class="row" style="margin-top:18px"><button id="back">← All sources</button></div></div>`;
  $('back').addEventListener('click',showList);
  $('body').addEventListener('mouseup',onSelect);
  $('body').querySelectorAll('mark').forEach(m=>m.addEventListener('click',ev=>{
    ev.stopPropagation(); window.getSelection().removeAllRanges();
    const e=(D.excerpts[sid]||[]).find(x=>x.id===m.dataset.x);
    if(e) openPanel({source_id:sid,start:e.start,end:e.end,
                     text:s.text.slice(e.start,e.end),existing:e});
  }));
}

/* map a browser selection back to character offsets in the source text */
function onSelect(){
  const g=window.getSelection();
  if(!g||g.isCollapsed) return;
  const abs=(node,off)=>{
    let el=node.nodeType===3?node.parentElement:node;
    el=el.closest('[data-s]'); if(!el) return null;
    return parseInt(el.dataset.s,10)+off;
  };
  let a=abs(g.anchorNode,g.anchorOffset), b=abs(g.focusNode,g.focusOffset);
  if(a===null||b===null) return;
  if(a>b) [a,b]=[b,a];
  const s=D.sources.find(x=>x.source_id===openDoc);
  // trim whitespace the drag picked up at either end
  while(a<b && /\s/.test(s.text[a])) a++;
  while(b>a && /\s/.test(s.text[b-1])) b--;
  if(b-a<2) return;
  const clash=(D.excerpts[openDoc]||[]).find(e=>a<e.end&&b>e.start);
  if(clash){ flash('that overlaps an existing excerpt — click the highlight to edit it',1); return; }
  openPanel({source_id:openDoc,start:a,end:b,text:s.text.slice(a,b),existing:null});
}

function openPanel(x){
  sel=x;
  const s=D.sources.find(y=>y.source_id===x.source_id);
  $('p_title').textContent=x.existing?'Edit this excerpt':'Code this passage';
  $('p_where').textContent=`PID${s.pid} · ${s.game} · ${s.kind} · chars ${x.start}–${x.end}`;
  $('p_quote').textContent=x.text;
  $('p_note').value=x.existing?x.existing.note||'':'';
  $('p_del').style.display=x.existing?'':'none';
  $('p_msg').textContent=''; $('p_msg').className='msg';
  $('p_search').value='';
  drawPicker(x.existing?Object.fromEntries(x.existing.codes):{});
  $('panel').classList.add('on');
}
function drawPicker(cur){
  if(!D.codes.length){
    $('p_picker').innerHTML='<p class="cbempty">No codes yet — define one first.</p>';
    return;
  }
  const byLens={};
  D.codes.forEach(c=>{(byLens[c.lens||'—']=byLens[c.lens||'—']||[]).push(c);});
  $('p_picker').innerHTML=Object.entries(byLens).map(([lens,cs])=>
    `<div class="lensgrp">${esc(lens)}</div>`+cs.map(c=>{
      const on=cur[c.id]!==undefined;
      return `<div class="crow${on?' on':''}" data-code="${esc(c.id)}" title="${esc(c.definition||'')}">
        <input type="checkbox" ${on?'checked':''}>
        <span class="nm"><b>${esc(c.id)}</b> <span>${esc(c.name)}</span></span>
        <select>${[['','not judged'],['pos','pos'],['neg','neg'],['mixed','mixed'],
                   ['neutral','neutral']].map(([v,lbl])=>
          `<option value="${v}"${on&&cur[c.id]===v?' selected':''}>${lbl}</option>`).join('')}</select></div>`;
    }).join('')).join('');
  $('p_picker').querySelectorAll('.crow input').forEach(cb=>cb.addEventListener('change',e=>
    e.target.closest('.crow').classList.toggle('on',e.target.checked)));
}
function hidePanel(){ $('panel').classList.remove('on'); sel=null; }

$('p_search').addEventListener('input',e=>{
  const t=e.target.value.toLowerCase();
  $('p_picker').querySelectorAll('.crow').forEach(r=>{
    r.style.display=!t||r.textContent.toLowerCase().includes(t)?'':'none';});
});
$('p_cancel').addEventListener('click',()=>{window.getSelection().removeAllRanges();hidePanel();});
$('p_save').addEventListener('click',()=>{
  const codes=[...$('p_picker').querySelectorAll('.crow')]
    .filter(r=>r.querySelector('input').checked)
    .map(r=>[r.dataset.code,r.querySelector('select').value]);
  if(!codes.length){ $('p_msg').textContent='tick at least one code'; $('p_msg').className='msg err'; return; }
  $('p_msg').textContent='saving…';
  post('api/excerpt',{source_id:sel.source_id,start:sel.start,end:sel.end,
                      codes,note:$('p_note').value})
    .then(()=>refresh(()=>{window.getSelection().removeAllRanges();flash('saved');}))
    .catch(e=>{$('p_msg').textContent=e;$('p_msg').className='msg err';});
});
$('p_del').addEventListener('click',()=>{
  if(!sel||!sel.existing) return;
  post('api/excerpt/delete',{excerpt_id:sel.existing.id})
    .then(()=>refresh(()=>flash('excerpt deleted')))
    .catch(e=>{$('p_msg').textContent=e;$('p_msg').className='msg err';});
});

function refresh(after){
  return fetch('api/data').then(r=>r.json()).then(d=>{ boot(d); hidePanel(); after&&after(); });
}
function post(url,body){
  return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)}).then(async r=>{
      const t=await r.text();
      if(!r.ok) throw (t||('HTTP '+r.status));
      return t?JSON.parse(t):{};});
}
function flash(t,err){const m=$('msg');m.textContent=t;m.className='msg'+(err?' err':'');
  clearTimeout(flash.t);flash.t=setTimeout(()=>m.textContent='',5000);}

document.addEventListener('click',e=>{
  const card=e.target.closest('.src');
  if(card) return showDoc(card.dataset.src);
  const cb=e.target.closest('.cbrow');
  if(cb&&!openDoc){ $('q').value=''; flash(CODES[cb.dataset.code].definition||cb.dataset.code); }
});
['q','pid','game','kind','status','valence','lens'].forEach(id=>
  $(id).addEventListener(id==='q'?'input':'change',()=>{ if(!openDoc) showList(); }));

$('newcode').addEventListener('click',()=>{$('n_err').textContent='';$('dlgCode').showModal();});
$('n_cancel').addEventListener('click',()=>$('dlgCode').close());
$('n_save').addEventListener('click',()=>{
  post('api/code',{code_id:$('n_id').value,lens:$('n_lens').value,name:$('n_name').value,
    definition:$('n_def').value,include:$('n_inc').value,exclude:$('n_exc').value})
  .then(()=>{
    const keep=sel;
    return fetch('api/data').then(r=>r.json()).then(d=>{
      $('dlgCode').close();
      ['n_id','n_name','n_def','n_inc','n_exc'].forEach(i=>$(i).value='');
      boot(d); if(keep) openPanel(keep); flash('code created');
    });
  }).catch(e=>$('n_err').textContent=e);
});
document.addEventListener('keydown',e=>{
  const t=document.activeElement.tagName;
  if(e.key==='Escape'){ if($('dlgCode').open) return; hidePanel(); }
  if(e.key==='/'&&t!=='INPUT'&&t!=='TEXTAREA'){e.preventDefault();$('q').focus();}
});
</script></body></html>
"""


def make_handler(proj, read_only):
    page = PAGE.encode("utf-8")

    class H(BaseHTTPRequestHandler):
        def _send(self, data, ctype="application/json; charset=utf-8", code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            # The page and the data change every time the tool is edited or a
            # coding is saved. A cached copy is always wrong.
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/") or "/"
            if path == "/":
                self._send(page, "text/html; charset=utf-8")
            elif path == "/api/data":
                self._send(json.dumps(proj.payload()).encode())
            else:
                self.send_error(404)

        def do_POST(self):
            if read_only:
                return self._send(b"server is running read-only", "text/plain", 403)
            path = self.path.split("?")[0].rstrip("/")
            n = int(self.headers.get("Content-Length") or 0)
            try:
                b = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(b"bad json", "text/plain", 400)
            try:
                if path == "/api/excerpt":
                    xid = proj.save_excerpt(b["source_id"], b["start"], b["end"],
                                            [(c, v) for c, v in b.get("codes", [])],
                                            b.get("note", ""))
                    return self._send(json.dumps({"excerpt_id": xid}).encode())
                if path == "/api/excerpt/delete":
                    proj.delete_excerpt(b["excerpt_id"])
                    return self._send(b"{}")
                if path == "/api/code":
                    proj.add_code(b)
                    return self._send(b"{}")
            except (ValueError, KeyError) as e:
                return self._send(str(e).encode(), "text/plain", 400)
            self.send_error(404)

        def log_message(self, *a):
            pass

    return H


def main():
    ap = argparse.ArgumentParser(description="Code a corpus by selecting passages.")
    ap.add_argument("--data", required=True,
                    help="project directory holding sources.csv")
    ap.add_argument("--coder", default="researcher", help="recorded on every coding")
    ap.add_argument("--port", type=int, default=None,
                    help="default 8765, walking forward if that is busy")
    ap.add_argument("--read-only", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    proj = Project(a.data, coder=a.coder)
    m = proj.payload()["meta"]
    say = lambda t: print(t, flush=True)   # visible even when redirected
    say(f"project : {m['root']}")
    say(f"sources : {m['sources']} documents, {m['participants']} participants, "
          f"{m['plays']} {m['units']}")
    say(f"codebook: {len(proj.codes)} codes · excerpts: {m['excerpts']}")
    say(f"coder   : {a.coder}{'  (READ-ONLY)' if a.read_only else ''}")
    # Bind BEFORE opening a browser. Opening first means a failed bind still
    # sends you to whatever else is answering on that port, which looks exactly
    # like the page refusing to update.
    srv, port = bind(make_handler(proj, a.read_only), a.port or 8765, a.port is not None)
    url = f"http://127.0.0.1:{port}/"
    if a.port is None and port != 8765:
        say(f"note    : 8765 was busy, using {port} instead")
    print(f"\nserving {url}   ctrl-c to stop")
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
