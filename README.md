# Autonomous Startup Sim

**A simulated company operated entirely by autonomous AI agents**, competing in a
simulated Indian SMB-SaaS market. Starting capital: **₹1,00,000 virtual**.
No real financial transactions. No scripted outcomes — every rupee of revenue,
every churned customer, every bankruptcy comes out of the simulation mechanics.

```
python3 -m src.cli run --horizon year --seed 42      # simulate 1 year
python3 -m src.cli experiment --seeds 6              # strategy tournament
python3 -m src.cli dashboard --run runs/run_s42_d365 # offline dashboard
python3 -m pytest tests/ -q                          # test suite
```

## What is this?

Eight department agents — **CEO, Product, Engineering, Marketing, Sales,
Finance, Operations, Strategy** — make every decision for a virtual startup:
what to build, what to charge, where to advertise, whom to hire (and fire),
when to raise money, when to panic.

They act on *their own analytics only*. The market is a separate ground-truth
engine with thousands of heterogeneous customer agents (needs, budgets,
satisfaction, churn), four adaptive competitors, demand trends, seasonality and
random shocks (funding winters, festive booms, ad-price spikes, new entrants).
The agents never read the market's internals; they live with the consequences.

Major decisions are logged **with reasoning, data considered and quantified
expectations**. The simulator later fills in actual outcomes and scores each
decision `success / partial / fail`, generating lessons from failures that feed
back into policy. A cross-run knowledge base carries priors between runs, so
strategic intelligence measurably improves over successive experiments.

## Results are earned, not asserted

- Profitability emerges from unit economics (CAC vs LTV vs churn) — many seeds
  and strategies go bankrupt.
- The same seed produces identical trajectories (deterministic RNG); clones
  facing different strategies diverge only through their decisions.
- Competitors adapt: they cut prices, copy winning features, blitz ads, and
  can exit or be out-competed.
- Quality rot, tech debt, support backlogs, over-hiring ahead of payroll — all
  modeled failure modes that the agent layer must actually manage.

Example result - the same agents, different horizons (final mechanics,
accumulated knowledge):

| Horizon | Tournament winner | Median MRR |
|---|---|---|
| Year 1 | `product_led` | ₹43.5L |
| Year 2 | `product_led` | ₹138.3L |
| Year 5 | `blitz_growth` (lean records first death) | ₹203.0L |

Raw aggression wins in deep early markets; compounding quality and retention
economics take over as markets mature and saturate. Rankings shift as the
knowledge base accumulates - strategy evaluation is a moving target.

## Horizons & experiments

| Horizon | Command |
|---|---|
| 30 days | `run --horizon 30d` |
| 90 days | `run --horizon 90d` |
| 1 year  | `run --horizon year` |
| 5 years | `run --horizon 5y` |

Experiment mode clones companies onto **identical seeded market paths** and
varies only strategy (`balanced`, `lean_profitable`, `blitz_growth`,
`premium_first`, `product_led`), then ranks them by survival and value created:

```
python3 -m src.cli experiment --days 365 --seeds 8 --presets all
```

## Dashboard

Every run directory gets `dashboard.html` — fully self-contained (no network,
works from `file://`) with KPI cards, cash/MRR/customer charts, CAC/churn
dynamics, the full decision log with verdicts and lessons, event timeline,
competitor intel and channel-learning tables.

## Repository map

| Path | Purpose |
|---|---|
| `src/simulator.py` | causal day-loop world engine |
| `src/agents.py` | the eight decision-making agents |
| `src/market.py` | demand, shocks, channel health ground truth |
| `src/customers.py` | customer agents + discrete-choice purchase model |
| `src/competitors.py` | adaptive competitor AI |
| `src/product.py` | features, quality, tech debt, engineering capacity |
| `src/marketing.py` | channels, saturation curves, brand |
| `src/sales.py` | pipeline, rep capacity, ramp |
| `src/finance.py` | ledger, SaaS metrics, valuation proxy |
| `src/experiments.py` | clone-and-compare tournaments |
| `src/knowledge.py` | cross-run learning persistence |
| `docs/` | architecture deep-dive |
| `runs/` | generated artifacts (one dir per run) |

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design,
[DECISIONS.md](DECISIONS.md) for engineering decision records,
[FINAL_REPORT.md](FINAL_REPORT.md) for results from real overnight runs, and
[OVERNIGHT_LOG.md](OVERNIGHT_LOG.md) for the build journal.

## Requirements

Python 3.10+ standard library only for the engine; `pytest` to run tests.
