"""A tiny local web app — fill in a form, get a plan. No terminal needed.

Start it with:   .venv/bin/python -m ria_planner.webapp
Then open:       http://127.0.0.1:5000

It wraps the same engine and Claude agent the command line uses; the form just
builds a ClientProfile for you and shows the results as a web page.
"""

import os

import markdown
from flask import Flask, Response, request
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
# the whole site asks for it. If it's unset, the site is open. This lets you
# deploy first and lock it down later by just setting one environment variable.
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
         color: var(--ink); margin: 0; padding: 40px 18px 80px; line-height: 1.55;
         -webkit-font-smoothing: antialiased; }
  .wrap { max-width: 780px; margin: 0 auto; }

  header.top { display: flex; align-items: center; gap: 14px; margin-bottom: 26px; }
  .mark { width: 44px; height: 44px; border-radius: 12px; flex: 0 0 auto;
          background: linear-gradient(135deg, var(--accent), #14b486);
          color: #fff; font-weight: 800; font-size: 1.05rem; letter-spacing: .5px;
          display: flex; align-items: center; justify-content: center;
          box-shadow: var(--shadow); }
  header.top h1 { font-size: 1.4rem; margin: 0; letter-spacing: -.01em; }
  header.top p { margin: 2px 0 0; color: var(--muted); font-size: .9rem; }

  .card { background: var(--card); border: 1px solid var(--line); border-radius: 18px;
          box-shadow: var(--shadow); padding: 26px 26px; margin-bottom: 22px; }
  .card > h2:first-child { margin-top: 0; }
  h2 { font-size: 1.05rem; letter-spacing: -.01em; margin: 0 0 14px; }
  .section-title { font-size: .78rem; text-transform: uppercase; letter-spacing: .08em;
                   color: var(--muted); font-weight: 700; margin: 26px 0 10px; }

  label { display: block; margin: 0 0 6px; font-weight: 600; font-size: .82rem; color: #3b4a66; }
  input, select { width: 100%; padding: 11px 12px; font-size: .98rem; color: var(--ink);
                  background: #fff; border: 1px solid #d6deea; border-radius: 11px;
                  transition: border-color .15s, box-shadow .15s; }
  input:focus, select:focus { outline: none; border-color: var(--accent);
                  box-shadow: 0 0 0 3px rgba(14,124,90,.15); }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .field { margin-bottom: 16px; }
  .check { display: flex; align-items: center; gap: 9px; margin: 20px 0 4px;
           padding: 12px 14px; background: #f3f7f4; border: 1px solid #dcebe3; border-radius: 12px; }
  .check input { width: auto; } .check label { margin: 0; font-weight: 500; color: var(--ink); }

  button { width: 100%; margin-top: 18px; padding: 14px 20px; font-size: 1rem; font-weight: 700;
           letter-spacing: .01em; background: var(--accent); color: #fff; border: 0;
           border-radius: 12px; cursor: pointer; box-shadow: var(--shadow);
           transition: background .15s, transform .05s; }
  button:hover { background: var(--accent-d); } button:active { transform: translateY(1px); }
  .hint { color: var(--muted); font-size: .85rem; margin: 0 0 18px; }
  #loading { display: none; margin-top: 14px; text-align: center; color: var(--accent); font-weight: 600; }
  .spin { display: inline-block; width: 16px; height: 16px; margin-right: 8px; vertical-align: -3px;
          border: 2px solid #cfe6db; border-top-color: var(--accent); border-radius: 50%;
          animation: sp .7s linear infinite; }
  @keyframes sp { to { transform: rotate(360deg); } }

  /* results hero */
  .hero { text-align: center; padding: 8px 0 4px; }
  .hero .pct { font-size: 3.4rem; font-weight: 800; line-height: 1; letter-spacing: -.02em; }
  .hero .cap { color: var(--muted); font-size: .9rem; margin-top: 6px; }
  .track { height: 12px; border-radius: 99px; background: #eef2f7; margin: 18px 0 6px; overflow: hidden; }
  .fill { height: 100%; border-radius: 99px; transition: width .4s; }
  .badge { display: inline-block; margin-top: 14px; padding: 7px 14px; border-radius: 99px;
           font-weight: 600; font-size: .9rem; }
  .badge.ok { background: #e6f6ef; color: var(--accent-d); }
  .badge.no { background: #fdeceb; color: #b3322d; }

  .stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
  .stat { background: #f8fafc; border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; }
  .stat .v { font-size: 1.15rem; font-weight: 700; letter-spacing: -.01em; }
  .stat .l { color: var(--muted); font-size: .78rem; margin-top: 3px; }

  table.data { border-collapse: collapse; width: 100%; }
  table.data th, table.data td { padding: 10px 12px; text-align: left; font-size: .92rem;
                                 border-bottom: 1px solid var(--line); }
  table.data th { color: var(--muted); font-weight: 600; font-size: .78rem;
                  text-transform: uppercase; letter-spacing: .05em; }
  table.data tr:last-child td { border-bottom: 0; }
  table.data td:last-child, table.data th:last-child { text-align: right; font-variant-numeric: tabular-nums; }

  .doc h1 { font-size: 1.35rem; } .doc h2 { font-size: 1.05rem; margin-top: 1.4em; }
  .doc table { border-collapse: collapse; width: 100%; margin: 10px 0; }
  .doc th, .doc td { border: 1px solid var(--line); padding: 7px 10px; font-size: .9rem; }
  .doc blockquote { border-left: 3px solid var(--accent); margin: 12px 0; padding: 4px 14px;
                    background: #f5faf7; color: #2a3b54; border-radius: 0 8px 8px 0; }

  .back { display: inline-flex; align-items: center; gap: 6px; color: var(--accent-d);
          text-decoration: none; font-weight: 600; font-size: .9rem; margin-bottom: 18px; }
  .back:hover { text-decoration: underline; }
  .foot { color: var(--muted); font-size: .82rem; text-align: center; margin-top: 26px; }
  @media (max-width: 560px) { .grid, .stats { grid-template-columns: 1fr; } }
</style>
"""


def _page(body: str) -> str:
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Retirement Planner</title>{CSS}</head>
<body><div class="wrap">
<header class="top"><div class="mark">RP</div>
<div><h1>Retirement Planner</h1><p>Plan-drafting agent for advisors</p></div></header>
{body}
</div></body></html>"""


FORM = _page(
    """
<div class="card">
  <p class="hint">Enter the client's numbers and build a plan. With the AI plan on, it can take up to a minute.</p>
  <form method="post" action="/plan" onsubmit="document.getElementById('go').disabled=true;document.getElementById('loading').style.display='block';">
    <div class="field"><label>Name</label><input name="name" value="Me"></div>
    <div class="grid">
      <div class="field"><label>Current age</label><input name="current_age" type="number" value="32"></div>
      <div class="field"><label>Retirement age</label><input name="retirement_age" type="number" value="65"></div>
    </div>
    <div class="grid">
      <div class="field"><label>Annual household income ($)</label><input name="annual_income" type="number" value="110000"></div>
      <div class="field"><label>Current retirement savings ($)</label><input name="current_savings" type="number" value="65000"></div>
    </div>
    <div class="grid">
      <div class="field"><label>Monthly contribution ($)</label><input name="monthly_contribution" type="number" value="1500"></div>
      <div class="field"><label>Social Security, combined ($/yr)</label><input name="social_security_annual" type="number" value="30000"></div>
    </div>
    <div class="grid">
      <div class="field"><label>Long-term care ($/yr, last 3 yrs)</label><input name="ltc_annual_cost" type="number" value="60000"></div>
      <div class="field"><label>Risk tolerance</label>
        <select name="risk_tolerance">
          <option value="conservative">Conservative</option>
          <option value="moderate">Moderate</option>
          <option value="aggressive" selected>Aggressive</option>
        </select>
      </div>
    </div>
    <div class="check"><input type="checkbox" id="ai" name="include_ai" checked>
      <label for="ai">Include the AI-written plan (slower, ~1 min)</label></div>
    <button id="go" type="submit">Build plan</button>
    <div id="loading"><span class="spin"></span>Building your plan…</div>
  </form>
</div>
"""
)


def _money(x):
    return f"${x:,.0f}"


def _color(prob):
    return "var(--green)" if prob >= 0.75 else "var(--amber)" if prob >= 0.45 else "var(--red)"


def _stat(value, label):
    return f'<div class="stat"><div class="v">{value}</div><div class="l">{label}</div></div>'


def _table(headers, rows):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="data"><tr>{head}</tr>{body}</table>'


@app.route("/")
def index():
    return FORM


@app.route("/plan", methods=["POST"])
def plan():
    f = request.form
    try:
        profile = ClientProfile(
            name=f.get("name") or "Me",
            current_age=int(f["current_age"]),
            retirement_age=int(f["retirement_age"]),
            annual_income=float(f["annual_income"]),
            current_savings=float(f["current_savings"]),
            monthly_contribution=float(f["monthly_contribution"]),
            social_security_annual=float(f["social_security_annual"]),
            ltc_annual_cost=float(f["ltc_annual_cost"]),
            risk_tolerance=f.get("risk_tolerance", "aggressive"),
        )
    except (ValueError, KeyError):
        return _page(
            "<div class='card'><p>Those numbers didn't read cleanly — please use plain "
            "numbers (no $ or commas). <a class='back' href='/'>← Back</a></p></div>"
        )

    r = run_plan(profile)
    mc = monte_carlo(profile)
    scen = scenarios(profile)
    strat = strategy_comparison(profile)
    claim = claiming_comparison(profile)

    pct = round(mc.probability_of_success * 100)
    color = _color(mc.probability_of_success)
    if r.on_track:
        badge = f'<div class="badge ok">On track — surplus of {_money(r.surplus_or_gap)}</div>'
    else:
        badge = (
            f'<div class="badge no">Shortfall of {_money(-r.surplus_or_gap)} · '
            f'save {_money(r.additional_monthly_needed)}/mo more</div>'
        )

    hero = f"""
<div class="card"><div class="hero">
  <div class="pct" style="color:{color}">{pct}%</div>
  <div class="cap">probability the money lasts to age {profile.life_expectancy}</div>
  <div class="track"><div class="fill" style="width:{pct}%;background:{color}"></div></div>
  {badge}
</div></div>"""

    stats = (
        '<div class="stats">'
        + _stat(_money(r.projected_nest_egg), "Projected nest egg")
        + _stat(_money(r.target_nest_egg), "Target nest egg")
        + _stat(f"{r.years_to_retirement} yrs", "To retirement")
        + _stat(_money(r.gross_income_need) + "/yr", "Income needed (yr 1)")
        + _stat(_money(r.guaranteed_income) + "/yr", "Guaranteed income")
        + _stat(_money(r.portfolio_income_need) + "/yr", "Portfolio must provide")
        + "</div>"
    )

    scen_t = _table(
        ["What-if lever", "Success"],
        [(s.label, f"{s.probability_of_success:.0%}") for s in scen],
    )
    strat_t = _table(
        ["Strategy", "Success"],
        [(s.label, f"{s.probability_of_success:.0%}") for s in strat],
    )
    claim_t = _table(
        ["Social Security claim age", "Benefit", "Success"],
        [(f"Claim at {c.claim_age}", _money(c.annual_benefit) + "/yr",
          f"{c.probability_of_success:.0%}") for c in claim],
    )

    plan_html = ""
    if f.get("include_ai"):
        try:
            text = draft_plan(profile, r, mc, scen, strat, claim)
            plan_html = (
                '<div class="card doc"><div class="section-title">Advisor plan · AI-written</div>'
                + markdown.markdown(text, extensions=["tables"])
                + "</div>"
            )
        except RuntimeError as exc:
            plan_html = f'<div class="card"><p class="hint">Couldn\'t generate the AI plan: {escape(str(exc))}</p></div>'

    body = f"""
<a class="back" href="/">← Build another</a>
<h2 style="margin:0 0 14px">Plan for {escape(profile.name)}</h2>
{hero}
<div class="card"><div class="section-title">Key figures</div>{stats}</div>
<div class="card"><div class="section-title">What-if scenarios</div>{scen_t}</div>
<div class="card"><div class="section-title">Strategy comparison</div>{strat_t}</div>
<div class="card"><div class="section-title">Social Security timing</div>{claim_t}</div>
{plan_html}
<p class="foot">Illustrative only — a draft for advisor review, not investment advice.</p>
"""
    return _page(body)


def main():
    # Local run. (In production, a host like Render runs gunicorn instead, and
    # sets the PORT env var.) Port 5050 — macOS AirPlay Receiver occupies 5000.
    port = int(os.environ.get("PORT", 5050))
    print(f"Open this in your browser:  http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
