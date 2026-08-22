# Development Guide

## Quickstart

```bash
python3 -m src.cli run --horizon year --seed 42 --name demo
python3 -m src.cli run --horizon 5y --seed 7 --name longrun
python3 -m src.cli experiment --days 365 --seeds 6 --presets all
python3 -m src.cli dashboard --run runs/demo
python3 -m pytest tests/ -q
```

Outputs land in `runs/<name>/`: `result.json`, `summary.md`, `config.json`,
`dashboard.html`. Experiments write `runs/experiments/tournament_*.md|json`.

## Layout

```
src/
  config.py       all tunables: segments, features, channels, salaries, presets
  rng.py          seeded stream management + INR formatting
  market.py       demand ground truth, shocks, channel health
  customers.py    Customer agents, offers, discrete choice, pool indexes
  competitors.py  competitor AI archetypes + adaptation
  product.py      ProductState + EngineeringSystem (capacity/quality/debt)
  marketing.py    channel curves, brand accumulation
  sales.py        deals, reps, capacity
  ops.py          support tickets / CSAT state
  finance.py      ledger (day-indexed), metrics helpers, valuation proxy
  company.py      aggregate container; cloneable; decision log
  agents.py       the eight department heads + MarketView
  investors.py    term sheet generation from traction
  simulator.py    World: causal day loop + metrics + evaluation
  experiments.py  tournament runner + reports
  knowledge.py    cross-run knowledge persistence
  reporting.py    JSON serialization + markdown summaries
  dashboard_gen.py self-contained HTML dashboard generator
  cli.py          entrypoints
tests/            pytest suite (determinism, invariants, funnel, units)
```

## Conventions

- **Actions are dicts** (`{"type": "hire", "role": ..., "n": ...}`) executed by
  `World.execute_actions` - agents never mutate world state directly.
- **Agents read `kpis()` and `MarketView` only.** If you find an agent reaching
  into ground-truth internals, that's a bug.
- **Money is float INR**; format with `fmt_inr` for display.
- **Days are integers**; months are 30-day blocks for billing anniversaries.
- Every major decision should call `company.log_decision(...)` with a real
  quantified expectation and `company.queue_evaluation(...)` with a metric,
  direction and magnitude the evaluator can measure.

## Running experiments

Fair comparison rules:
1. Same seed list for every variant (the tournament does this).
2. Only strategy params differ between clones.
3. Report survival *and* value - a strategy that wins on median MRR but dies
   40% of the time is not obviously better.

The tournament seeds are independent of CLI-run seeds (`1000 + i*137`) so
flagship runs and tournaments don't interfere.

## Knowledge base

`data/knowledge.json` accumulates channel priors, elasticity estimates,
strategy outcomes and failure lessons across every tournament run. Delete it to
reset learning; commit snapshots when you want to freeze "what the firm knows".

## Testing

```bash
python3 -m pytest tests/ -q          # full suite (~20s)
python3 -m pytest tests/test_determinism.py -q   # fastest invariant checks
```

Key invariants enforced:
- Same seed -> byte-identical final KPI snapshot.
- Cash == starting capital + sum(ledger) + equity raises, exactly.
- Pool conservation: per-state counts sum to universe size; active_ids match.
- MRR book equals sum of active subscription fees within a paisa.
- Clones with different strategies observe identical public market events.

## Performance notes

If you add per-customer daily work, prefer:
- event-driven scheduling (renewals use `_renewals_due`),
- segment-day statistical draws (`_hash_uniforms(seed, ns, seg, day)`),
- bucket sampling instead of full-pool scans.

Budget: 365 days should stay under ~4s; 1825 days under ~90s.
