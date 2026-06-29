"""The web app — the full product in the browser. No terminal needed.

Start it with:   .venv/bin/python -m ria_planner.webapp
Then open:       http://127.0.0.1:5050

Four tabs, all backed by the same engine:
  * Plan      — interactive retirement plan (assumptions update results live)
  * Meeting   — a pre-meeting cheat-sheet from the same client inputs
  * Portfolio — allocation drift + rebalancing from a list of holdings
  * Chat      — pressure-test the plan; the bot can re-run the simulation
"""

import datetime
import os
import re
from dataclasses import replace

import markdown
from flask import Flask, Response, jsonify, request
from markupsafe import escape

from .agent import MODEL, draft_plan
from .docqa import answer_question
from .engine import (
    claiming_comparison,
    monte_carlo,
    run_plan,
    scenarios,
    strategy_comparison,
)
from .meeting import prep_meeting
from .models import ClientProfile, Holding, MeetingContext
from .portfolio import ASSET_CLASS_LABELS, analyze_portfolio
from .portfolio_agent import portfolio_commentary
from .report import build_markdown, build_portfolio_markdown


def _dl_name(name, kind):
    """A tidy download filename like 'dana-whitfield-plan-2026-06-29.md'."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "client").lower()).strip("-") or "client"
    return f"{slug}-{kind}-{datetime.date.today().isoformat()}.md"

app = Flask(__name__)

# Optional password gate (set APP_PASSWORD in the host's env to turn it on).
APP_PASSWORD = os.environ.get("APP_PASSWORD")


@app.before_request
def _password_gate():
    if not APP_PASSWORD:
        return None
    auth = request.authorization
    if auth and auth.password == APP_PASSWORD:
        return None
    return Response(
        "Password required.", 401,
        {"WWW-Authenticate": 'Basic realm="Retirement Planner"'},
    )


def _money(x):
    return f"${x:,.0f}"


CSS = """
<style>
  :root {
    --bg: #eef1f6; --card: #ffffff; --ink: #0f1f3a; --muted: #5b6b86;
    --line: #e2e8f2; --accent: #0e7c5a; --accent-d: #0a6147;
    --green: #0e9d6e; --amber: #d9920b; --red: #d6453f;
    --shadow: 0 1px 2px rgba(16,32,58,.06), 0 8px 24px rgba(16,32,58,.07);
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
         background: radial-gradient(1200px 600px at 50% -200px, #fff, var(--bg));
         color: var(--ink); margin: 0; padding: 32px 18px 80px; line-height: 1.5;
         -webkit-font-smoothing: antialiased; }
  .wrap { max-width: 820px; margin: 0 auto; }
  header.top { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
  .mark { width: 44px; height: 44px; border-radius: 12px; flex: 0 0 auto;
          background: linear-gradient(135deg, var(--accent), #14b486);
          color: #fff; font-weight: 800; display: flex; align-items: center;
          justify-content: center; box-shadow: var(--shadow); }
  header.top h1 { font-size: 1.4rem; margin: 0; letter-spacing: -.01em; }
  header.top p { margin: 2px 0 0; color: var(--muted); font-size: .9rem; }

  .tabs { display: flex; gap: 6px; margin-bottom: 18px; flex-wrap: wrap; }
  .tab { padding: 9px 16px; border-radius: 999px; border: 1px solid var(--line);
         background: #fff; color: var(--muted); font-weight: 600; font-size: .9rem; cursor: pointer; }
  .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .panel { display: none; } .panel.active { display: block; }

  .card { background: var(--card); border: 1px solid var(--line); border-radius: 18px;
          box-shadow: var(--shadow); padding: 22px 24px; margin-bottom: 18px; }
  .section-title { font-size: .76rem; text-transform: uppercase; letter-spacing: .08em;
                   color: var(--muted); font-weight: 700; margin: 0 0 14px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; }
  .field { margin-bottom: 4px; }
  label { display: block; margin: 0 0 5px; font-weight: 600; font-size: .82rem; color: #34435f; }
  label .val { color: var(--accent-d); font-weight: 800; }
  input, select, textarea { width: 100%; padding: 10px 12px; font-size: .96rem; color: var(--ink);
                  background: #fff; border: 1px solid #d6deea; border-radius: 10px; font-family: inherit; }
  input:focus, select:focus, textarea:focus { outline: none; border-color: var(--accent);
                  box-shadow: 0 0 0 3px rgba(14,124,90,.15); }
  input[type=range] { padding: 0; height: 26px; accent-color: var(--accent); cursor: pointer; }
  .help { color: var(--muted); font-size: .77rem; margin-top: 4px; }

  .hero { text-align: center; padding: 4px 0 2px; }
  .hero .pct { font-size: 3.2rem; font-weight: 800; line-height: 1; }
  .hero .cap { color: var(--muted); font-size: .88rem; margin-top: 6px; }
  .track { height: 12px; border-radius: 99px; background: #eef2f7; margin: 16px 0 6px; overflow: hidden; }
  .fill { height: 100%; border-radius: 99px; transition: width .35s, background .35s; }
  .badge { display: inline-block; margin-top: 12px; padding: 7px 14px; border-radius: 99px; font-weight: 600; font-size: .9rem; }
  .badge.ok { background: #e6f6ef; color: var(--accent-d); }
  .badge.no { background: #fdeceb; color: #b3322d; }
  .explain { background: #f6f9fc; border: 1px solid var(--line); border-radius: 12px;
             padding: 12px 14px; margin: 16px 0 0; font-size: .9rem; color: #2c3a55; }

  .stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
  .stat { background: #f8fafc; border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; }
  .stat .v { font-size: 1.1rem; font-weight: 700; } .stat .l { color: var(--muted); font-size: .76rem; margin-top: 3px; }

  table.data { border-collapse: collapse; width: 100%; }
  table.data th, table.data td { padding: 9px 12px; text-align: left; font-size: .9rem; border-bottom: 1px solid var(--line); }
  table.data th { color: var(--muted); font-weight: 600; font-size: .74rem; text-transform: uppercase; letter-spacing: .05em; }
  table.data tr:last-child td { border-bottom: 0; }
  table.data td:last-child, table.data th:last-child { text-align: right; font-variant-numeric: tabular-nums; }

  button { padding: 13px 20px; font-size: 1rem; font-weight: 700; background: var(--accent);
           color: #fff; border: 0; border-radius: 12px; cursor: pointer; box-shadow: var(--shadow); }
  button:hover { background: var(--accent-d); } button:disabled { opacity: .6; cursor: default; }
  button.wide { width: 100%; }
  button.small { padding: 7px 12px; font-size: .85rem; border-radius: 9px; }
  button.ghost { background: #eef4f1; color: var(--accent-d); box-shadow: none; }

  .doc { margin-top: 16px; } .doc h1 { font-size: 1.3rem; } .doc h2 { font-size: 1.05rem; margin-top: 1.3em; }
  .doc table { border-collapse: collapse; width: 100%; margin: 10px 0; }
  .doc th, .doc td { border: 1px solid var(--line); padding: 7px 10px; font-size: .9rem; }
  .doc blockquote { border-left: 3px solid var(--accent); margin: 12px 0; padding: 4px 14px; background: #f5faf7; border-radius: 0 8px 8px 0; }

  .hold-row { display: grid; grid-template-columns: 2fr 1fr 1.3fr auto; gap: 8px; margin-bottom: 8px; align-items: center; }
  .hold-row button { background: #fdeceb; color: #b3322d; box-shadow: none; padding: 8px 12px; }

  .chatlog { display: flex; flex-direction: column; gap: 10px; max-height: 460px; overflow-y: auto; padding: 4px; margin-bottom: 12px; }
  .bubble { max-width: 88%; padding: 10px 14px; border-radius: 14px; font-size: .92rem; }
  .bubble.user { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
  .bubble.bot { align-self: flex-start; background: #f1f5f9; color: var(--ink); border-bottom-left-radius: 4px; }
  .bubble.bot p:first-child { margin-top: 0; } .bubble.bot p:last-child { margin-bottom: 0; }
  .chatbar { display: flex; gap: 8px; } .chatbar input { flex: 1; }
  .foot { color: var(--muted); font-size: .82rem; text-align: center; margin-top: 22px; }
  .spin { display:inline-block; width:14px; height:14px; margin-right:7px; vertical-align:-2px;
          border:2px solid #cfe6db; border-top-color:var(--accent); border-radius:50%; animation:sp .7s linear infinite; }
  @keyframes sp { to { transform: rotate(360deg); } }
  @media (max-width: 580px) { .grid, .stats { grid-template-columns: 1fr; } .hold-row { grid-template-columns: 1fr; } }
</style>
"""


def _page(body: str) -> str:
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Retirement Planner</title>{CSS}</head>
<body><div class="wrap">
<header class="top"><div class="mark">RP</div>
<div><h1>Retirement Planner</h1><p>Plan, prep, analyze — and pressure-test it.</p></div></header>
<div class="tabs">
  <div class="tab active" data-tab="plan" onclick="showTab('plan')">Retirement plan</div>
  <div class="tab" data-tab="meeting" onclick="showTab('meeting')">Meeting prep</div>
  <div class="tab" data-tab="portfolio" onclick="showTab('portfolio')">Portfolio</div>
  <div class="tab" data-tab="chat" onclick="showTab('chat')">Pressure-test</div>
  <div class="tab" data-tab="docs" onclick="showTab('docs')">Documents</div>
</div>
{body}
</div></body></html>"""


def _field(label, name, value, help_text=""):
    h = f'<div class="help">{help_text}</div>' if help_text else ""
    return (f'<div class="field"><label>{label}</label>'
            f'<input name="{name}" type="number" value="{value}" oninput="schedule()">{h}</div>')


def _slider(label, name, lo, hi, step, value, span_id, help_text, decimals=0):
    return (
        f'<div class="field"><label>{label}: <span class="val" id="{span_id}">{value}</span></label>'
        f'<input name="{name}" type="range" min="{lo}" max="{hi}" step="{step}" value="{value}" '
        f"oninput=\"document.getElementById('{span_id}').textContent=(+this.value).toFixed({decimals}); schedule()\">"
        f'<div class="help">{help_text}</div></div>'
    )


CLIENT_FORM = (
    '<div class="card"><div class="section-title">About you</div><div class="grid">'
    '<div class="field"><label>Name</label><input name="name" value="Me" oninput="schedule()"></div>'
    '<div class="field"><label>Risk tolerance</label><select name="risk_tolerance" oninput="schedule()">'
    '<option value="conservative">Conservative</option><option value="moderate">Moderate</option>'
    '<option value="aggressive" selected>Aggressive</option></select>'
    '<div class="help">How aggressive your investments are.</div></div>'
    + _field("Current age", "current_age", 32)
    + _field("Retirement age", "retirement_age", 65)
    + _slider("Plan through age", "life_expectancy", 80, 100, 1, 92, "le_v", "The age your money needs to last to.")
    + '</div></div>'
    '<div class="card"><div class="section-title">Money</div><div class="grid">'
    + _field("Annual household income ($)", "annual_income", 110000, "Household income before tax.")
    + _field("Current retirement savings ($)", "current_savings", 65000, "Invested for retirement so far.")
    + _field("Monthly contribution ($)", "monthly_contribution", 1500, "What you add each month.")
    + '</div></div>'
    '<div class="card"><div class="section-title">Guaranteed income (today\'s $/yr)</div><div class="grid">'
    + _field("Social Security, combined", "social_security_annual", 30000, "Age-67 estimate from ssa.gov.")
    + _field("Pension", "pension_annual", 0)
    + _field("Other (rental, part-time)", "other_retirement_income_annual", 0)
    + '</div></div>'
    '<div class="card"><div class="section-title">The assumptions (change any)</div><div class="grid">'
    + _slider("Income needed in retirement", "income_replacement_pct", 40, 100, 5, 75, "repl_v", "% of today's income. Most need 70–80%.")
    + _slider("Expected return", "expected_return_pct", 3, 10, 0.5, 6, "ret_v", "Average yearly growth before fees.", 1)
    + _slider("Investment fees", "annual_fee_pct", 0, 2, 0.1, 1, "fee_v", "Advisory + fund fees, taken from returns.", 1)
    + _slider("Inflation", "inflation_pct", 0, 5, 0.25, 2.5, "inf_v", "How fast prices rise each year.", 2)
    + _slider("Withdrawal rate", "withdrawal_pct", 3, 6, 0.25, 4, "wd_v", "Share of the nest egg spent per year.", 2)
    + '</div></div>'
    '<div class="card"><div class="section-title">Big late-life costs</div><div class="grid">'
    + _field("Long-term care ($/yr)", "ltc_annual_cost", 60000, "Care cost in the final years. 0 to ignore.")
    + _field("…for how many years", "ltc_years", 3)
    + _field("Pre-Medicare healthcare ($/yr)", "pre_medicare_annual_cost", 0, "Only if retiring before 65.")
    + '</div></div>'
)

PLAN_RESULTS = """
<div class="card">
  <div class="section-title">Result · updates as you type</div>
  <div class="hero">
    <div class="pct" id="pct">–</div>
    <div class="cap">probability the money lasts to age <span id="le">92</span></div>
    <div class="track"><div class="fill" id="fill"></div></div>
    <div id="badge"></div>
  </div>
  <p class="explain" id="explain"></p>
</div>
<div class="card"><div class="section-title">Key figures</div><div class="stats" id="stats"></div></div>
<div class="card"><div class="section-title">What-if scenarios</div><table class="data" id="scen"></table></div>
<div class="card"><div class="section-title">Strategy comparison</div><table class="data" id="strat"></table></div>
<div class="card"><div class="section-title">Social Security timing</div><table class="data" id="claim"></table></div>
<div class="card">
  <button type="button" class="wide" id="planbtn" onclick="writePlan()">Write the full advisor plan (AI · ~1 min)</button>
  <div id="plan" class="doc"></div>
</div>
"""

MEETING_PANEL = """
<div class="card">
  <div class="section-title">Meeting context</div>
  <p class="help" style="margin-top:-6px">Uses the client details from the Retirement plan tab, plus the context below.</p>
  <div class="field"><label>Meeting purpose</label><input name="purpose" value="Annual review"></div>
  <div class="field"><label>Last review</label><input name="last_review" value="June 2025"></div>
  <div class="field"><label>Open action items</label><textarea name="open_items" rows="2">Confirm updated Social Security estimate</textarea></div>
  <div class="field"><label>Notes for this meeting</label><textarea name="notes_meeting" rows="2"></textarea></div>
  <button type="button" class="wide" id="meetbtn" onclick="writeMeeting()" style="margin-top:14px">Generate pre-meeting briefing (AI · ~1 min)</button>
  <div id="meeting" class="doc"></div>
</div>
"""

PORTFOLIO_PANEL = """
<div class="card">
  <div class="section-title">Holdings</div>
  <div id="holdings"></div>
  <button type="button" class="ghost small" onclick="addHolding()">+ Add holding</button>
  <div class="field" style="margin-top:14px;max-width:260px"><label>Target risk model</label>
    <select id="pf_risk" onchange="computePortfolio()">
      <option value="conservative">Conservative</option>
      <option value="moderate" selected>Moderate</option>
      <option value="aggressive">Aggressive</option>
    </select></div>
</div>
<div class="card"><div class="section-title">Allocation vs. target · live</div>
  <table class="data" id="pf_table"></table>
  <div id="pf_flags" style="margin-top:10px"></div>
</div>
<div class="card">
  <button type="button" class="wide" id="pfbtn" onclick="analyzePortfolio()">Write the portfolio analysis (AI · ~1 min)</button>
  <div id="pf_out" class="doc"></div>
</div>
"""

CHAT_PANEL = """
<div class="card">
  <div class="section-title">Pressure-test the plan</div>
  <p class="help" style="margin-top:-6px">Ask anything about the plan from the Retirement plan tab. The assistant can
  re-run the simulation — e.g. "what if I retire 3 years later?" or "why is my probability low?"</p>
  <div class="chatlog" id="chatlog"></div>
  <div class="chatbar">
    <input id="chatin" placeholder="Ask a what-if…" onkeydown="if(event.key==='Enter')sendChat()">
    <button type="button" id="chatbtn" onclick="sendChat()">Send</button>
  </div>
</div>
"""

DOCS_PANEL = """
<div class="card">
  <div class="section-title">Ask questions about a client document</div>
  <p class="help" style="margin-top:-6px">Paste a statement's text or upload a PDF, then ask. Claude answers
  using only the document and tells you if something isn't in it.</p>
  <div class="field"><label>Paste document text (optional)</label>
    <textarea id="doc_text" rows="6" placeholder="Paste the relevant text from a statement, plan, or notes…"></textarea></div>
  <div class="field"><label>…or upload a PDF (optional, up to ~30 MB)</label>
    <input type="file" id="doc_pdf" accept="application/pdf"></div>
  <div class="field"><label>Your question</label>
    <input id="doc_q" placeholder="e.g. What is the total account value? When does the term life policy expire?"></div>
  <button type="button" class="wide" id="docbtn" onclick="askDoc()">Ask (AI)</button>
  <div id="doc_out" class="doc"></div>
</div>
"""

PAGE_BODY = (
    '<form id="f" onsubmit="return false;">'
    '<div class="panel active" id="panel-plan">' + CLIENT_FORM + PLAN_RESULTS + '</div>'
    '<div class="panel" id="panel-meeting">' + MEETING_PANEL + '</div>'
    '</form>'
    '<div class="panel" id="panel-portfolio">' + PORTFOLIO_PANEL + '</div>'
    '<div class="panel" id="panel-chat">' + CHAT_PANEL + '</div>'
    '<div class="panel" id="panel-docs">' + DOCS_PANEL + '</div>'
    '<p class="foot">Illustrative only — a draft for advisor review, not investment advice.</p>'
    + """
<script>
function showTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t.dataset.tab===name));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active', p.id==='panel-'+name));
}
function m(x){ return '$' + Math.round(x).toLocaleString('en-US'); }
function pctv(p){ return Math.round(p*100) + '%'; }
function color(p){ return p>=0.75 ? 'var(--green)' : p>=0.45 ? 'var(--amber)' : 'var(--red)'; }
function stat(v,l){ return '<div class="stat"><div class="v">'+v+'</div><div class="l">'+l+'</div></div>'; }
function thead(hs){ return '<tr>'+hs.map(h=>'<th>'+h+'</th>').join('')+'</tr>'; }
function row(cs){ return '<tr>'+cs.map(c=>'<td>'+c+'</td>').join('')+'</tr>'; }
function formObject(f){ var o={}; new FormData(f).forEach(function(v,k){o[k]=v;}); return o; }

function render(d){
  document.getElementById('le').textContent = d.life_expectancy;
  var p=d.probability, pc=color(p);
  var pe=document.getElementById('pct'); pe.textContent=Math.round(p*100)+'%'; pe.style.color=pc;
  var fl=document.getElementById('fill'); fl.style.width=(p*100)+'%'; fl.style.background=pc;
  document.getElementById('badge').innerHTML = d.on_track
    ? '<div class="badge ok">On track — surplus of '+m(d.surplus_or_gap)+'</div>'
    : '<div class="badge no">Shortfall of '+m(-d.surplus_or_gap)+' · save '+m(d.additional_monthly_needed)+'/mo more</div>';
  document.getElementById('explain').textContent = d.explain;
  document.getElementById('stats').innerHTML =
      stat(m(d.projected_nest_egg),'Projected nest egg') + stat(m(d.target_nest_egg),'Target nest egg')
    + stat(d.years_to_retirement+' yrs','Years to retirement') + stat(m(d.gross_income_need)+'/yr','Income needed (yr 1)')
    + stat(m(d.guaranteed_income)+'/yr','Guaranteed income') + stat(m(d.portfolio_income_need)+'/yr','Portfolio must provide');
  document.getElementById('scen').innerHTML = thead(['What-if lever','Success']) + d.scenarios.map(function(s){return row([s.label,pctv(s.prob)]);}).join('');
  document.getElementById('strat').innerHTML = thead(['Strategy','Success']) + d.strategy.map(function(s){return row([s.label,pctv(s.prob)]);}).join('');
  document.getElementById('claim').innerHTML = thead(['Claim age','Benefit','Success']) + d.claiming.map(function(c){return row(['Claim at '+c.claim_age, m(c.benefit)+'/yr', pctv(c.prob)]);}).join('');
}
async function compute(){
  var res=await fetch('/api/compute',{method:'POST',body:new FormData(document.getElementById('f'))});
  render(await res.json());
}
var timer; function schedule(){ clearTimeout(timer); timer=setTimeout(compute,300); }

var DOC_STYLE = 'body{font-family:Georgia,serif;color:#111;max-width:720px;margin:24px auto;line-height:1.5}'
  +'h1{font-size:20pt}h2{font-size:14pt;margin-top:16pt}'
  +'table{border-collapse:collapse;width:100%;margin:8pt 0}'
  +'th,td{border:1px solid #999;padding:5pt 8pt;font-size:10pt;text-align:left}'
  +'blockquote{border-left:3px solid #888;margin:8pt 0;padding:2pt 10pt;color:#444}';
function baseName(filename){ return (filename||'report').replace(/\\.md$/,''); }
function downloadBlob(filename, content, type){
  var blob = new Blob(content, {type:type});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a'); a.href=url; a.download=filename; document.body.appendChild(a);
  a.click(); a.remove(); URL.revokeObjectURL(url);
}
function downloadFile(filename, md){ downloadBlob(filename, [md], 'text/markdown'); }
function downloadWord(filename, reportHtml){
  var html = '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" '
    +'xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="utf-8"><style>'+DOC_STYLE+'</style></head><body>'
    +reportHtml+'</body></html>';
  downloadBlob(baseName(filename)+'.doc', ['\\ufeff', html], 'application/msword');
}
function printPdf(filename, reportHtml){
  var w = window.open('', '_blank');
  if(!w){ alert('Please allow pop-ups for this site to save as PDF.'); return; }
  w.document.write('<html><head><title>'+baseName(filename)+'</title><style>'+DOC_STYLE
    +'@media print{body{margin:0}}</style></head><body>'+reportHtml+'</body></html>');
  w.document.close(); w.focus(); setTimeout(function(){ w.print(); }, 400);
}
function addDownload(out, filename, md, reportHtml){
  var bar=document.createElement('div');
  bar.style.marginTop='14px'; bar.style.display='flex'; bar.style.gap='8px'; bar.style.flexWrap='wrap';
  function mk(label, fn){ var b=document.createElement('button'); b.type='button'; b.className='ghost small'; b.textContent=label; b.onclick=fn; return b; }
  bar.appendChild(mk('⬇ Word (.doc)', function(){ downloadWord(filename, reportHtml); }));
  bar.appendChild(mk('🖨 Save as PDF', function(){ printPdf(filename, reportHtml); }));
  bar.appendChild(mk('⬇ Markdown (.md)', function(){ downloadFile(filename || 'report.md', md); }));
  out.appendChild(bar);
}
async function aiButton(btnId, outId, url, getBody, label){
  var b=document.getElementById(btnId); b.disabled=true; b.textContent='Working… (~1 min)';
  var out=document.getElementById(outId); out.innerHTML='';
  try {
    var r=await fetch(url, getBody()); var d=await r.json();
    if (d.error){ out.innerHTML='<p class="help">'+d.error+'</p>'; }
    else { out.innerHTML = d.html; if (d.md) addDownload(out, d.filename, d.md, d.report_html); }
  } catch(e){ out.innerHTML='<p class="help">Something went wrong.</p>'; }
  b.disabled=false; b.textContent=label;
}
function writePlan(){ aiButton('planbtn','plan','/api/plan',
  function(){return {method:'POST',body:new FormData(document.getElementById('f'))};}, 'Re-write the full advisor plan (AI · ~1 min)'); }
function writeMeeting(){ aiButton('meetbtn','meeting','/api/meeting',
  function(){return {method:'POST',body:new FormData(document.getElementById('f'))};}, 'Re-generate pre-meeting briefing (AI · ~1 min)'); }

// ---- Portfolio ----
var DEFAULT_HOLDINGS = [
  ['S&P 500 Index Fund',180000,'equity'],['Tech Growth ETF',90000,'equity'],
  ['Total Bond Fund',60000,'fixed_income'],['Money Market',40000,'cash'],['REIT Fund',30000,'real_estate']];
var CLASSES = [['equity','Equities'],['fixed_income','Fixed income'],['cash','Cash'],['real_estate','Real estate'],['other','Other']];
function holdingRow(name,value,cls){
  var opts=CLASSES.map(function(c){return '<option value="'+c[0]+'"'+(c[0]===cls?' selected':'')+'>'+c[1]+'</option>';}).join('');
  var d=document.createElement('div'); d.className='hold-row';
  d.innerHTML='<input class="h-name" placeholder="Holding name" value="'+(name||'')+'" oninput="computePortfolio()">'
    +'<input class="h-val" type="number" placeholder="Value" value="'+(value||'')+'" oninput="computePortfolio()">'
    +'<select class="h-cls" onchange="computePortfolio()">'+opts+'</select>'
    +'<button type="button" onclick="this.parentNode.remove();computePortfolio()">✕</button>';
  return d;
}
function addHolding(){ document.getElementById('holdings').appendChild(holdingRow('','','equity')); computePortfolio(); }
function readHoldings(){
  return Array.from(document.querySelectorAll('#holdings .hold-row')).map(function(r){
    return {name:r.querySelector('.h-name').value, value:r.querySelector('.h-val').value, asset_class:r.querySelector('.h-cls').value};
  });
}
async function computePortfolio(){
  var body=JSON.stringify({holdings:readHoldings(), risk:document.getElementById('pf_risk').value});
  var r=await fetch('/api/portfolio/compute',{method:'POST',headers:{'Content-Type':'application/json'},body:body});
  var d=await r.json();
  if(d.error){ document.getElementById('pf_table').innerHTML=''; document.getElementById('pf_flags').innerHTML='<p class="help">'+d.error+'</p>'; return; }
  document.getElementById('pf_table').innerHTML = thead(['Asset class','Now','Target','Drift','Rebalance'])
    + d.rows.map(function(x){return row([x.label, x.current+'%', x.target+'%', (x.drift>=0?'+':'')+x.drift+' pts', x.action]);}).join('');
  document.getElementById('pf_flags').innerHTML = d.flags.length
    ? '<div class="section-title">Flags</div>'+d.flags.map(function(f){return '<div class="help">• '+f+'</div>';}).join('')
    : '<div class="help">No flags — allocation is close to target.</div>';
}
function analyzePortfolio(){ aiButton('pfbtn','pf_out','/api/portfolio/analyze',
  function(){return {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({holdings:readHoldings(), risk:document.getElementById('pf_risk').value})};},
  'Re-write the portfolio analysis (AI · ~1 min)'); }

// ---- Chat ----
var chatHistory=[];
function addBubble(role,html){
  var log=document.getElementById('chatlog'); var d=document.createElement('div');
  d.className='bubble '+role; d.innerHTML=html; log.appendChild(d); log.scrollTop=log.scrollHeight; return d;
}
async function sendChat(){
  var inp=document.getElementById('chatin'); var text=inp.value.trim(); if(!text) return;
  addBubble('user', text.replace(/</g,'&lt;')); chatHistory.push({role:'user',content:text}); inp.value='';
  var b=document.getElementById('chatbtn'); b.disabled=true;
  var thinking=addBubble('bot','<span class="spin"></span>thinking…');
  try {
    var body=JSON.stringify({inputs:formObject(document.getElementById('f')), history:chatHistory});
    var r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:body});
    var d=await r.json();
    thinking.innerHTML = d.error ? d.error : d.html;
    if(d.text) chatHistory.push({role:'assistant',content:d.text});
  } catch(e){ thinking.innerHTML='Something went wrong.'; }
  b.disabled=false;
}

// ---- Documents (Q&A) ----
function readFileB64(file){
  return new Promise(function(resolve){
    if(!file){ resolve(null); return; }
    var fr=new FileReader();
    fr.onload=function(){ resolve(fr.result.split(',')[1]); };  // strip data: prefix
    fr.readAsDataURL(file);
  });
}
async function askDoc(){
  var b=document.getElementById('docbtn'); b.disabled=true; b.textContent='Reading… (~30s)';
  var out=document.getElementById('doc_out'); out.innerHTML='';
  try {
    var pdf=await readFileB64(document.getElementById('doc_pdf').files[0]);
    var body=JSON.stringify({ question: document.getElementById('doc_q').value,
                              text: document.getElementById('doc_text').value, pdf_b64: pdf });
    var r=await fetch('/api/docqa',{method:'POST',headers:{'Content-Type':'application/json'},body:body});
    var d=await r.json();
    out.innerHTML = d.error ? '<p class="help">'+d.error+'</p>' : d.html;
  } catch(e){ out.innerHTML='<p class="help">Something went wrong.</p>'; }
  b.disabled=false; b.textContent='Ask (AI)';
}

window.addEventListener('DOMContentLoaded', function(){
  DEFAULT_HOLDINGS.forEach(function(h){ document.getElementById('holdings').appendChild(holdingRow(h[0],h[1],h[2])); });
  computePortfolio(); compute();
});
</script>
"""
)


def _num(form, key, default):
    try:
        return float(form.get(key, ""))
    except (TypeError, ValueError):
        return default


def _profile_from_form(f) -> ClientProfile:
    return ClientProfile(
        name=f.get("name") or "Me",
        current_age=int(_num(f, "current_age", 32)),
        retirement_age=int(_num(f, "retirement_age", 65)),
        life_expectancy=int(_num(f, "life_expectancy", 92)),
        annual_income=_num(f, "annual_income", 0),
        current_savings=_num(f, "current_savings", 0),
        monthly_contribution=_num(f, "monthly_contribution", 0),
        social_security_annual=_num(f, "social_security_annual", 0),
        pension_annual=_num(f, "pension_annual", 0),
        other_retirement_income_annual=_num(f, "other_retirement_income_annual", 0),
        ltc_annual_cost=_num(f, "ltc_annual_cost", 0),
        ltc_years=int(_num(f, "ltc_years", 3)),
        pre_medicare_annual_cost=_num(f, "pre_medicare_annual_cost", 0),
        expected_return=_num(f, "expected_return_pct", 6) / 100,
        annual_fee=_num(f, "annual_fee_pct", 1) / 100,
        inflation=_num(f, "inflation_pct", 2.5) / 100,
        income_replacement_ratio=_num(f, "income_replacement_pct", 75) / 100,
        withdrawal_rate=_num(f, "withdrawal_pct", 4) / 100,
        risk_tolerance=f.get("risk_tolerance", "aggressive"),
    )


def _all(profile):
    return (run_plan(profile), monte_carlo(profile), scenarios(profile),
            strategy_comparison(profile), claiming_comparison(profile))


@app.route("/")
def index():
    return _page(PAGE_BODY)


@app.route("/api/compute", methods=["POST"])
def api_compute():
    profile = _profile_from_form(request.form)
    r = run_plan(profile)
    mc = monte_carlo(profile)
    income_today = profile.annual_income * profile.income_replacement_ratio
    explain = (
        f"We assume you'll want {profile.income_replacement_ratio:.0%} of your "
        f"${profile.annual_income:,.0f} income = ${income_today:,.0f}/yr in today's dollars. "
        f"Inflation grows that to ${r.gross_income_need:,.0f}/yr by retirement. Guaranteed "
        f"income covers ${r.guaranteed_income:,.0f}, so your portfolio must supply "
        f"${r.portfolio_income_need:,.0f}/yr — which at a {profile.withdrawal_rate:.1%} "
        f"withdrawal rate needs a ${r.target_nest_egg:,.0f} nest egg."
    )
    return jsonify(
        life_expectancy=profile.life_expectancy, years_to_retirement=r.years_to_retirement,
        projected_nest_egg=r.projected_nest_egg, target_nest_egg=r.target_nest_egg,
        gross_income_need=r.gross_income_need, guaranteed_income=r.guaranteed_income,
        portfolio_income_need=r.portfolio_income_need, on_track=r.on_track,
        surplus_or_gap=r.surplus_or_gap, additional_monthly_needed=r.additional_monthly_needed,
        probability=mc.probability_of_success, explain=explain,
        scenarios=[{"label": s.label, "prob": s.probability_of_success} for s in scenarios(profile)],
        strategy=[{"label": s.label, "prob": s.probability_of_success} for s in strategy_comparison(profile)],
        claiming=[{"claim_age": c.claim_age, "benefit": c.annual_benefit, "prob": c.probability_of_success}
                  for c in claiming_comparison(profile)],
    )


@app.route("/api/plan", methods=["POST"])
def api_plan():
    profile = _profile_from_form(request.form)
    pieces = _all(profile)
    try:
        text = draft_plan(profile, *pieces)
        md = build_markdown(profile, *pieces, plan_text=text)
        return jsonify(html=markdown.markdown(text, extensions=["tables"]),
                       md=md, report_html=markdown.markdown(md, extensions=["tables"]),
                       filename=_dl_name(profile.name, "plan"))
    except RuntimeError as exc:
        return jsonify(error=str(escape(str(exc))))
    except Exception:
        return jsonify(error="The AI request failed (a temporary hiccup or rate limit). Please try again.")


@app.route("/api/meeting", methods=["POST"])
def api_meeting():
    f = request.form
    profile = _profile_from_form(f)
    context = MeetingContext(
        purpose=f.get("purpose") or "Portfolio review",
        last_review=f.get("last_review") or "",
        open_items=f.get("open_items") or "",
        notes=f.get("notes_meeting") or "",
    )
    pieces = _all(profile)
    try:
        text = prep_meeting(profile, *pieces, context=context)
        md = build_markdown(profile, *pieces, plan_text=text,
                            heading="Pre-Meeting Briefing", draft_section="Briefing")
        return jsonify(html=markdown.markdown(text, extensions=["tables"]),
                       md=md, report_html=markdown.markdown(md, extensions=["tables"]),
                       filename=_dl_name(profile.name, "meeting"))
    except RuntimeError as exc:
        return jsonify(error=str(escape(str(exc))))
    except Exception:
        return jsonify(error="The AI request failed (a temporary hiccup or rate limit). Please try again.")


def _holdings_from_json(data):
    holdings = []
    for h in (data.get("holdings") or []):
        name = (h.get("name") or "").strip()
        try:
            value = float(h.get("value") or 0)
        except (TypeError, ValueError):
            value = 0
        if name and value > 0:
            holdings.append(Holding(name=name, value=value,
                                    asset_class=(h.get("asset_class") or "other").strip().lower()))
    return holdings


@app.route("/api/portfolio/compute", methods=["POST"])
def api_portfolio_compute():
    data = request.get_json(silent=True) or {}
    holdings = _holdings_from_json(data)
    if not holdings:
        return jsonify(error="Add at least one holding with a name and a value.")
    a = analyze_portfolio(holdings, data.get("risk", "moderate"))
    rows = []
    for c in a.classes:
        trade = a.rebalancing[c]
        action = f"buy {_money(trade)}" if trade >= 0 else f"sell {_money(-trade)}"
        rows.append({"label": ASSET_CLASS_LABELS.get(c, c), "current": round(a.current_pct[c]),
                     "target": round(a.target_pct[c]), "drift": round(a.drift[c]), "action": action})
    return jsonify(total=a.total_value, rows=rows, flags=a.flags)


@app.route("/api/portfolio/analyze", methods=["POST"])
def api_portfolio_analyze():
    data = request.get_json(silent=True) or {}
    holdings = _holdings_from_json(data)
    if not holdings:
        return jsonify(error="Add at least one holding first.")
    risk = data.get("risk", "moderate")
    analysis = analyze_portfolio(holdings, risk)
    try:
        text = portfolio_commentary(holdings, analysis, risk)
        md = build_portfolio_markdown(holdings, analysis, risk, text)
        return jsonify(html=markdown.markdown(text, extensions=["tables"]),
                       md=md, report_html=markdown.markdown(md, extensions=["tables"]),
                       filename=f"portfolio-{risk}-{datetime.date.today().isoformat()}.md")
    except RuntimeError as exc:
        return jsonify(error=str(escape(str(exc))))
    except Exception:
        return jsonify(error="The AI request failed (a temporary hiccup or rate limit). Please try again.")


# --------------------------------------------------------------------------- #
# Pressure-test chat — Claude can re-run the simulation via a tool.
# --------------------------------------------------------------------------- #

CHAT_SYSTEM = """\
You are a financial planning assistant helping an advisor pressure-test a \
client's retirement plan. The client's current plan context is below. Answer \
clearly and concisely, always tying claims to the numbers.

When the user asks a what-if that changes an assumption (retirement age, \
savings, return, income, Social Security, risk tolerance, etc.), call the \
recompute_plan tool to get the REAL new numbers instead of guessing, then \
explain what changed and why. Keep answers short — a few sentences. These are \
illustrative figures for advisor use, not personalized investment advice."""

RECOMPUTE_TOOL = {
    "name": "recompute_plan",
    "description": "Re-run the retirement simulation with one or more changed assumptions and return the new probability the money lasts plus key figures. Only include fields you want to change.",
    "input_schema": {
        "type": "object",
        "properties": {
            "retirement_age": {"type": "integer"},
            "current_savings": {"type": "number"},
            "monthly_contribution": {"type": "number"},
            "annual_income": {"type": "number"},
            "social_security_annual": {"type": "number"},
            "income_replacement_pct": {"type": "number", "description": "e.g. 70 for 70%"},
            "expected_return_pct": {"type": "number", "description": "e.g. 6 for 6%"},
            "risk_tolerance": {"type": "string", "enum": ["conservative", "moderate", "aggressive"]},
        },
    },
}


def _apply_overrides(profile, ov):
    kw = {}
    if "retirement_age" in ov:
        kw["retirement_age"] = int(ov["retirement_age"])
    for k in ("current_savings", "monthly_contribution", "annual_income", "social_security_annual"):
        if k in ov:
            kw[k] = float(ov[k])
    if "income_replacement_pct" in ov:
        kw["income_replacement_ratio"] = float(ov["income_replacement_pct"]) / 100
    if "expected_return_pct" in ov:
        kw["expected_return"] = float(ov["expected_return_pct"]) / 100
    if "risk_tolerance" in ov:
        kw["risk_tolerance"] = ov["risk_tolerance"]
    return replace(profile, **kw)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    import anthropic
    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify(error="The chat needs an API key set on the server.")

    data = request.get_json(silent=True) or {}
    profile = _profile_from_form(data.get("inputs") or {})
    history = data.get("history") or []

    r = run_plan(profile)
    mc = monte_carlo(profile)
    context = (
        f"\n\nCURRENT PLAN:\n"
        f"- {profile.name}, age {profile.current_age}, retiring at {profile.retirement_age}, "
        f"plan to age {profile.life_expectancy}\n"
        f"- Income ${profile.annual_income:,.0f}; savings ${profile.current_savings:,.0f}; "
        f"contributing ${profile.monthly_contribution:,.0f}/mo; risk {profile.risk_tolerance}\n"
        f"- Probability the money lasts to {profile.life_expectancy}: {mc.probability_of_success:.0%}\n"
        f"- Projected nest egg ${r.projected_nest_egg:,.0f} vs target ${r.target_nest_egg:,.0f} "
        f"({'on track' if r.on_track else 'shortfall of $' + format(-r.surplus_or_gap, ',.0f')})"
    )

    client = anthropic.Anthropic()
    messages = [{"role": h["role"], "content": h["content"]} for h in history if h.get("content")]

    try:
        for _ in range(4):
            resp = client.messages.create(
                model=MODEL, max_tokens=1200, system=CHAT_SYSTEM + context,
                tools=[RECOMPUTE_TOOL], messages=messages,
            )
            if resp.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": resp.content})
                results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        np_ = _apply_overrides(profile, block.input)
                        nr = run_plan(np_)
                        nmc = monte_carlo(np_)
                        out = (
                            f"probability money lasts: {nmc.probability_of_success:.0%}; "
                            f"projected nest egg ${nr.projected_nest_egg:,.0f}; target ${nr.target_nest_egg:,.0f}; "
                            f"{'on track' if nr.on_track else 'shortfall of $' + format(-nr.surplus_or_gap, ',.0f')}"
                        )
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
                messages.append({"role": "user", "content": results})
                continue
            text = "".join(b.text for b in resp.content if b.type == "text")
            return jsonify(html=markdown.markdown(text, extensions=["tables"]), text=text)
        return jsonify(html="<p>I couldn't settle after several steps — try rephrasing.</p>", text="")
    except Exception:
        return jsonify(
            error="The chat hit a temporary error (a rate limit, overload, or timeout). Please try again.",
            text="",
        )


@app.route("/api/docqa", methods=["POST"])
def api_docqa():
    data = request.get_json(silent=True) or {}
    try:
        text = answer_question(
            data.get("question", ""),
            doc_text=(data.get("text") or "").strip() or None,
            pdf_b64=data.get("pdf_b64") or None,
        )
        return jsonify(html=markdown.markdown(text, extensions=["tables"]))
    except (ValueError, RuntimeError) as exc:
        return jsonify(error=str(escape(str(exc))))
    except Exception:
        return jsonify(error="The request failed (a temporary hiccup or rate limit). Please try again.")


# Allow larger request bodies for PDF uploads (~32 MB).
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024


def main():
    port = int(os.environ.get("PORT", 5050))
    print(f"Open this in your browser:  http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
