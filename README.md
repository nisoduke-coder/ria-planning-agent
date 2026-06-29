# RIA Planning Agent

An agentic retirement-plan drafter for the RIA (Registered Investment Advisor)
market. It turns a client's intake numbers into a draft retirement plan an
advisor can review and deliver.

## The idea in one picture

```
ClientProfile ──▶ engine.py ──▶ PlanResults ──▶ agent.py (Claude) ──▶ draft plan
  (intake data)    (the math)    (the numbers)    (the writing)
```

Two deliberate layers:

- **`engine.py` — the math.** Pure Python. Reproducible, auditable, no AI. The
  projections never come from a language model, which is what you want in a
  regulated industry.
- **`agent.py` — the writing.** Claude takes the computed numbers and drafts the
  advisor-facing plan (summary, on-track verdict, recommendations, risks, next
  steps). It explains; it does not calculate.

## Easiest way: the web form (no terminal)

```bash
.venv/bin/python -m ria_planner.webapp
```

Then open **http://127.0.0.1:5050**, fill in the boxes, and click Build plan.
Runs entirely on your machine.

## Run it (command line)

```bash
# one-time setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# see the math immediately — no API key needed
.venv/bin/python -m ria_planner.cli --no-ai

# full plan with the AI draft — needs a key in .env
.venv/bin/python -m ria_planner.cli
```

## Running real clients & saving deliverables

Don't edit Python — put client data in a file:

```bash
# one client from JSON
.venv/bin/python -m ria_planner.cli --client clients/dana.json

# a whole book of clients from CSV (one row each)
.venv/bin/python -m ria_planner.cli --clients-csv clients/book.csv

# save the finished plan as a Markdown deliverable (lands in output/)
.venv/bin/python -m ria_planner.cli --client clients/dana.json --save
```

See `clients/dana.json` and `clients/book.csv` for the format. Saved reports
go to `output/` (gitignored, since they hold client data) and contain the
auditable number tables plus the AI-written plan.

## Meeting prep (job #3)

Same numbers, different deliverable: a short pre-meeting cheat-sheet (talking
points, decisions to tee up, questions to ask) instead of a full plan.

```bash
python -m ria_planner.cli --client clients/dana.json --meeting
python -m ria_planner.cli --client clients/dana.json --meeting \
    --purpose "Annual review" --since "June 2025" --save
```

Meeting context comes from an optional `"meeting"` block in the client JSON
(see `clients/dana.json`) and can be overridden with `--purpose`, `--since`,
`--open-items`, and `--notes`.

## File map

| File | What it does |
|------|--------------|
| `ria_planner/models.py` | `ClientProfile` — the intake data |
| `ria_planner/engine.py` | Retirement projection math |
| `ria_planner/agent.py`  | Claude drafts the plan from the math |
| `ria_planner/webapp.py` | Browser form — fill in boxes, get a plan (no terminal) |
| `ria_planner/meeting.py`| Claude writes a pre-meeting cheat-sheet (job #3) |
| `ria_planner/intake.py` | Loads clients from JSON / CSV files |
| `ria_planner/report.py` | Exports the plan/brief to a Markdown deliverable |
| `ria_planner/cli.py`    | Runs it end to end (sample, file, or batch) |

## Monte Carlo

Alongside the straight-line projection, the engine runs 10,000 randomized
"possible futures" (`engine.monte_carlo`) and reports a **probability of
success** plus the range of outcomes. Random year-to-year returns reveal
*volatility drag* the single-number estimate hides — which is why this number
is usually lower (and more honest) than the straight-line projection suggests.

## What the engine accounts for

- Growth of current savings + monthly contributions to retirement
- Guaranteed income (Social Security, pensions, other) that lowers the nest-egg
  target
- Investment fees (projections use a net-of-fee return)
- Inflation, a pre-tax replacement target (so income taxes are implicitly covered)
- Household (both-spouse) totals
- **Full-lifecycle Monte Carlo** — saves up *and* spends down, so "success" means
  the money lasts through retirement (captures sequence-of-returns risk)
- **What-if levers** — work longer / save more
- **Strategy levers** — glide-path de-risking and dynamic/guardrail withdrawals
- **Social Security timing** — claim at 62 / 67 / 70
- **Major cost provisions** — long-term care and pre-Medicare healthcare

## What's left out (by design)

What the agent still raises now is *professional diligence* ("confirm these
numbers with the real client") and *strategy options* (e.g. evaluating LTC
insurance) — not missing model inputs. Going further (estate planning,
disability insurance, tax-location, detailed tax modeling) would turn this from
a retirement projector into full financial-planning software.

## Where this is headed

Per the project plan, this starts as a **financial-plan drafter** and will grow
toward the other three jobs: client-meeting prep, portfolio analysis, and Q&A
over client documents — eventually as a product for advisors.

---

*Illustrative only. Output is a draft for advisor review, not investment advice.*
