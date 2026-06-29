"""A tiny local web app — fill in a form, get a plan. No terminal needed.

Start it with:   .venv/bin/python -m ria_planner.webapp
Then open:       http://127.0.0.1:5050

Every planning assumption is an editable control with a plain-English note, and
the numbers recompute live as you change them. The slow AI plan is behind its
own button so it only runs (and only costs money) when you ask.
"""

import os

import markdown
from flask import Flask, Response, jsonify, request
from markupsafe import escape

from .agent import draft_plan
from .engine import (
    claiming_comparison,
    monte_carlo,
    run_plan,
    scenarios,
    strategy_comparison,
)
from .models import ClientProfile

app = Flask(__name__)

# Optional password gate. If APP_PASSWORD is set (e.g. in the host's env vars),
# the whole site asks for it. If unset, the site is open.
APP_PASSWORD = os.environ.get("APP_PASSWORD")


@app.before_request
def _password_gate():
    if not APP_PASSWORD:
        return None
    auth = request.authorization
    if auth and auth.password == APP_PASSWORD:
        return None
    return Response(
        "Password required.",
        401,
        {"WWW-Authenticate": 'Basic realm="Retirement Planner"'},
    )


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
         color: var(--ink); margin: 0; padding: 36px 18px 80px; line-height: 1.5;
         -webkit-font-smoothing: antialiased; }
  .wrap { max-width: 820px; margin: 0 auto; }
  header.top { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; }
  .mark { width: 44px; height: 44px; border-radius: 12px; flex: 0 0 auto;
          background: linear-gradient(135deg, var(--accent), #14b486);
          color: #fff; font-weight: 800; display: flex; align-items: center;
          justify-content: center; box-shadow: var(--shadow); }
  header.top h1 { font-size: 1.4rem; margin: 0; letter-spacing: -.01em; }
  header.top p { margin: 2px 0 0; color: var(--muted); font-size: .9rem; }

  .card { background: var(--card); border: 1px solid var(--line); border-radius: 18px;
          box-shadow: var(--shadow); padding: 22px 24px; margin-bottom: 18px; }
  .section-title { font-size: .76rem; text-transform: uppercase; letter-spacing: .08em;
                   color: var(--muted); font-weight: 700; margin: 0 0 14px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; }
  .field { margin-bottom: 4px; }
  label { display: block; margin: 0 0 5px; font-weight: 600; font-size: .85rem; color: #34435f; }
  label .val { color: var(--accent-d); font-weight: 800; }
  input, select { width: 100%; padding: 10px 12px; font-size: .96rem; color: var(--ink);
                  background: #fff; border: 1px solid #d6deea; border-radius: 10px;
                  transition: border-color .15s, box-shadow .15s; }
  input:focus, select:focus { outline: none; border-color: var(--accent);
                  box-shadow: 0 0 0 3px rgba(14,124,90,.15); }
  input[type=range] { padding: 0; height: 26px; accent-color: var(--accent); cursor: pointer; }
  .help { color: var(--muted); font-size: .77rem; margin-top: 4px; }

  .hero { text-align: center; padding: 4px 0 2px; }
  .hero .pct { font-size: 3.2rem; font-weight: 800; line-height: 1; letter-spacing: -.02em; }
  .hero .cap { color: var(--muted); font-size: .88rem; margin-top: 6px; }
  .track { height: 12px; border-radius: 99px; background: #eef2f7; margin: 16px 0 6px; overflow: hidden; }
  .fill { height: 100%; border-radius: 99px; transition: width .35s, background .35s; }
  .badge { display: inline-block; margin-top: 12px; padding: 7px 14px; border-radius: 99px;
           font-weight: 600; font-size: .9rem; }
  .badge.ok { background: #e6f6ef; color: var(--accent-d); }
  .badge.no { background: #fdeceb; color: #b3322d; }
  .explain { background: #f6f9fc; border: 1px solid var(--line); border-radius: 12px;
             padding: 12px 14px; margin: 16px 0 0; font-size: .9rem; color: #2c3a55; }

  .stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
  .stat { background: #f8fafc; border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; }
  .stat .v { font-size: 1.1rem; font-weight: 700; } .stat .l { color: var(--muted); font-size: .76rem; margin-top: 3px; }

  table.data { border-collapse: collapse; width: 100%; }
  table.data th, table.data td { padding: 9px 12px; text-align: left; font-size: .9rem;
                                 border-bottom: 1px solid var(--line); }
  table.data th { color: var(--muted); font-weight: 600; font-size: .74rem;
                  text-transform: uppercase; letter-spacing: .05em; }
  table.data tr:last-child td { border-bottom: 0; }
  table.data td:last-child, table.data th:last-child { text-align: right; font-variant-numeric: tabular-nums; }

  button { width: 100%; padding: 13px 20px; font-size: 1rem; font-weight: 700;
           background: var(--accent); color: #fff; border: 0; border-radius: 12px; cursor: pointer;
           box-shadow: var(--shadow); transition: background .15s; }
  button:hover { background: var(--accent-d); } button:disabled { opacity: .7; cursor: default; }

  .doc { margin-top: 16px; } .doc h1 { font-size: 1.3rem; } .doc h2 { font-size: 1.05rem; margin-top: 1.3em; }
  .doc table { border-collapse: collapse; width: 100%; margin: 10px 0; }
  .doc th, .doc td { border: 1px solid var(--line); padding: 7px 10px; font-size: .9rem; }
  .doc blockquote { border-left: 3px solid var(--accent); margin: 12px 0; padding: 4px 14px;
                    background: #f5faf7; color: #2a3b54; border-radius: 0 8px 8px 0; }
  .foot { color: var(--muted); font-size: .82rem; text-align: center; margin-top: 22px; }
  @media (max-width: 580px) { .grid, .stats { grid-template-columns: 1fr; } }
</style>
"""


def _page(body: str) -> str:
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Retirement Planner</title>{CSS}</head>
<body><div class="wrap">
<header class="top"><div class="mark">RP</div>
<div><h1>Retirement Planner</h1><p>Every assumption is yours to change — numbers update live.</p></div></header>
{body}
</div></body></html>"""


# The single interactive page. Plain string (NOT an f-string) so the JS braces
# are left alone.
PAGE_BODY = """
<form id="f" onsubmit="return false;">

<div class="card">
  <div class="section-title">About you</div>
  <div class="grid">
    <div class="field"><label>Name</label><input name="name" value="Me" oninput="schedule()"></div>
    <div class="field"><label>Risk tolerance</label>
      <select name="risk_tolerance" oninput="schedule()">
        <option value="conservative">Conservative</option>
        <option value="moderate">Moderate</option>
        <option value="aggressive" selected>Aggressive</option>
      </select>
      <div class="help">How aggressive your investments are — drives the size of the ups and downs.</div>
    </div>
    <div class="field"><label>Current age</label><input name="current_age" type="number" value="32" oninput="schedule()"></div>
    <div class="field"><label>Retirement age</label><input name="retirement_age" type="number" value="65" oninput="schedule()"></div>
    <div class="field"><label>Plan through age: <span class="val" id="le_v">92</span></label>
      <input name="life_expectancy" type="range" min="80" max="100" step="1" value="92"
             oninput="le_v.textContent=this.value; schedule()">
      <div class="help">The age your money needs to last to. Planning to ~92 guards against living longer than average.</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="section-title">Money</div>
  <div class="grid">
    <div class="field"><label>Annual household income ($)</label><input name="annual_income" type="number" value="110000" oninput="schedule()">
      <div class="help">Total household income before tax, today.</div></div>
    <div class="field"><label>Current retirement savings ($)</label><input name="current_savings" type="number" value="65000" oninput="schedule()">
      <div class="help">Everything invested for retirement so far.</div></div>
    <div class="field"><label>Monthly contribution ($)</label><input name="monthly_contribution" type="number" value="1500" oninput="schedule()">
      <div class="help">What you add to retirement savings each month.</div></div>
  </div>
</div>

<div class="card">
  <div class="section-title">Guaranteed income in retirement (today's $/yr)</div>
  <div class="grid">
    <div class="field"><label>Social Security, combined</label><input name="social_security_annual" type="number" value="30000" oninput="schedule()">
      <div class="help">Estimate from your ssa.gov statement (age-67 figure). Lowers how big a nest egg you need.</div></div>
    <div class="field"><label>Pension</label><input name="pension_annual" type="number" value="0" oninput="schedule()">
      <div class="help">Any employer/government pension income.</div></div>
    <div class="field"><label>Other (rental, part-time…)</label><input name="other_retirement_income_annual" type="number" value="0" oninput="schedule()">
      <div class="help">Any other reliable income in retirement.</div></div>
  </div>
</div>

<div class="card">
  <div class="section-title">The assumptions (change any of these)</div>
  <div class="grid">
    <div class="field"><label>Income you'll need in retirement: <span class="val" id="repl_v">75</span>% of today's income</label>
      <input name="income_replacement_pct" type="range" min="40" max="100" step="5" value="75"
             oninput="repl_v.textContent=this.value; schedule()">
      <div class="help">Most people need 70–80% — some costs drop (no commute, mortgage paid off, no more saving).</div></div>
    <div class="field"><label>Expected investment return: <span class="val" id="ret_v">6.0</span>%/yr</label>
      <input name="expected_return_pct" type="range" min="3" max="10" step="0.5" value="6"
             oninput="ret_v.textContent=(+this.value).toFixed(1); schedule()">
      <div class="help">Average yearly growth before fees. ~6% is a common long-run stock/bond blend.</div></div>
    <div class="field"><label>Investment fees: <span class="val" id="fee_v">1.0</span>%/yr</label>
      <input name="annual_fee_pct" type="range" min="0" max="2" step="0.1" value="1"
             oninput="fee_v.textContent=(+this.value).toFixed(1); schedule()">
      <div class="help">Advisory + fund fees, taken out of returns. ~1% is common; lower is better.</div></div>
    <div class="field"><label>Inflation: <span class="val" id="inf_v">2.5</span>%/yr</label>
      <input name="inflation_pct" type="range" min="0" max="5" step="0.25" value="2.5"
             oninput="inf_v.textContent=(+this.value).toFixed(2); schedule()">
      <div class="help">How fast prices rise. ~2.5% is the long-run average; it makes future dollars worth less.</div></div>
    <div class="field"><label>Withdrawal rate: <span class="val" id="wd_v">4.0</span>%/yr</label>
      <input name="withdrawal_pct" type="range" min="3" max="6" step="0.25" value="4"
             oninput="wd_v.textContent=(+this.value).toFixed(2); schedule()">
      <div class="help">Share of the nest egg you spend per year. 4% is the classic "safe" rule of thumb.</div></div>
  </div>
</div>

<div class="card">
  <div class="section-title">Big late-life costs</div>
  <div class="grid">
    <div class="field"><label>Long-term care ($/yr)</label><input name="ltc_annual_cost" type="number" value="60000" oninput="schedule()">
      <div class="help">Care cost in your final years — large and commonly overlooked. Set 0 to ignore.</div></div>
    <div class="field"><label>…for how many years</label><input name="ltc_years" type="number" value="3" oninput="schedule()">
      <div class="help">How long that care lasts (applied at the end of the plan).</div></div>
    <div class="field"><label>Pre-Medicare healthcare ($/yr)</label><input name="pre_medicare_annual_cost" type="number" value="0" oninput="schedule()">
      <div class="help">Extra healthcare cost only if you retire before 65 (the gap before Medicare).</div></div>
  </div>
</div>

</form>

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
  <button type="button" id="planbtn" onclick="writePlan()">Write the full advisor plan (AI · ~1 min)</button>
  <div id="plan" class="doc"></div>
</div>
<p class="foot">Illustrative only — a draft for advisor review, not investment advice.</p>

<script>
function m(x){ return '$' + Math.round(x).toLocaleString('en-US'); }
function pctv(p){ return Math.round(p*100) + '%'; }
function color(p){ return p>=0.75 ? 'var(--green)' : p>=0.45 ? 'var(--amber)' : 'var(--red)'; }
function stat(v,l){ return '<div class="stat"><div class="v">'+v+'</div><div class="l">'+l+'</div></div>'; }
function thead(hs){ return '<tr>'+hs.map(h=>'<th>'+h+'</th>').join('')+'</tr>'; }
function row(cs){ return '<tr>'+cs.map(c=>'<td>'+c+'</td>').join('')+'</tr>'; }

function render(d){
  document.getElementById('le').textContent = d.life_expectancy;
  var p = d.probability, pc = color(p);
  var pe = document.getElementById('pct'); pe.textContent = Math.round(p*100)+'%'; pe.style.color = pc;
  var fl = document.getElementById('fill'); fl.style.width = (p*100)+'%'; fl.style.background = pc;
  document.getElementById('badge').innerHTML = d.on_track
    ? '<div class="badge ok">On track — surplus of '+m(d.surplus_or_gap)+'</div>'
    : '<div class="badge no">Shortfall of '+m(-d.surplus_or_gap)+' · save '+m(d.additional_monthly_needed)+'/mo more</div>';
  document.getElementById('explain').textContent = d.explain;
  document.getElementById('stats').innerHTML =
      stat(m(d.projected_nest_egg),'Projected nest egg')
    + stat(m(d.target_nest_egg),'Target nest egg')
    + stat(d.years_to_retirement+' yrs','Years to retirement')
    + stat(m(d.gross_income_need)+'/yr','Income needed (yr 1)')
    + stat(m(d.guaranteed_income)+'/yr','Guaranteed income')
    + stat(m(d.portfolio_income_need)+'/yr','Portfolio must provide');
  document.getElementById('scen').innerHTML = thead(['What-if lever','Success'])
    + d.scenarios.map(function(s){ return row([s.label, pctv(s.prob)]); }).join('');
  document.getElementById('strat').innerHTML = thead(['Strategy','Success'])
    + d.strategy.map(function(s){ return row([s.label, pctv(s.prob)]); }).join('');
  document.getElementById('claim').innerHTML = thead(['Claim age','Benefit','Success'])
    + d.claiming.map(function(c){ return row(['Claim at '+c.claim_age, m(c.benefit)+'/yr', pctv(c.prob)]); }).join('');
}

async function compute(){
  var res = await fetch('/api/compute', {method:'POST', body: new FormData(document.getElementById('f'))});
  render(await res.json());
}
var timer;
function schedule(){ clearTimeout(timer); timer = setTimeout(compute, 300); }

async function writePlan(){
  var b = document.getElementById('planbtn'); b.disabled = true; b.textContent = 'Writing the plan… (~1 min)';
  var plan = document.getElementById('plan'); plan.innerHTML = '';
  try {
    var res = await fetch('/api/plan', {method:'POST', body: new FormData(document.getElementById('f'))});
    var d = await res.json();
    plan.innerHTML = d.error ? '<p class="help">'+d.error+'</p>' : d.html;
  } catch(e) { plan.innerHTML = '<p class="help">Something went wrong generating the plan.</p>'; }
  b.disabled = false; b.textContent = 'Re-write the full advisor plan (AI · ~1 min)';
}

window.addEventListener('DOMContentLoaded', compute);
</script>
"""


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
        life_expectancy=profile.life_expectancy,
        years_to_retirement=r.years_to_retirement,
        projected_nest_egg=r.projected_nest_egg,
        target_nest_egg=r.target_nest_egg,
        gross_income_need=r.gross_income_need,
        guaranteed_income=r.guaranteed_income,
        portfolio_income_need=r.portfolio_income_need,
        on_track=r.on_track,
        surplus_or_gap=r.surplus_or_gap,
        additional_monthly_needed=r.additional_monthly_needed,
        probability=mc.probability_of_success,
        explain=explain,
        scenarios=[{"label": s.label, "prob": s.probability_of_success}
                   for s in scenarios(profile)],
        strategy=[{"label": s.label, "prob": s.probability_of_success}
                  for s in strategy_comparison(profile)],
        claiming=[{"claim_age": c.claim_age, "benefit": c.annual_benefit,
                   "prob": c.probability_of_success}
                  for c in claiming_comparison(profile)],
    )


@app.route("/api/plan", methods=["POST"])
def api_plan():
    profile = _profile_from_form(request.form)
    r = run_plan(profile)
    mc = monte_carlo(profile)
    scen = scenarios(profile)
    strat = strategy_comparison(profile)
    claim = claiming_comparison(profile)
    try:
        text = draft_plan(profile, r, mc, scen, strat, claim)
        return jsonify(html=markdown.markdown(text, extensions=["tables"]))
    except RuntimeError as exc:
        return jsonify(error=str(escape(str(exc))))


def main():
    # Local run. In production a host like Render runs gunicorn and sets PORT.
    # Port 5050 — macOS AirPlay Receiver occupies 5000.
    port = int(os.environ.get("PORT", 5050))
    print(f"Open this in your browser:  http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
