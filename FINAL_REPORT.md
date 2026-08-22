# Final Report - Autonomous Startup Simulation

**Session:** overnight autonomous build & experiment window
**Repository:** https://github.com/shubhraj5575/autonomous-startup-sim
**Capital:** INR 1,00,000 virtual. **All numbers below are measured from actual
simulation runs.** Nothing is scripted or asserted.

---

## 1. What was built

A complete simulated company operated by eight autonomous agents (CEO, Product,
Engineering, Marketing, Sales, Finance, Operations, Strategy) inside a
ground-truth market engine:

- **~8,900 customer agents** across 5 segments with heterogeneous needs,
  budgets, satisfaction and churn; purchases resolved by a logit discrete-choice
  model against **4 adaptive competitors** and an outside option.
- **Market dynamics**: demand trends + seasonality, channel-health drift,
  shock events (funding winters, festive booms, ad-CPM spikes, new entrants).
- **Full business mechanics**: saturating ad channels, sales pipeline with rep
  capacity and ramp, engineering capacity split across features/quality/tech
  debt, support backlogs, monthly payroll with notice periods and severance,
  VC term sheets priced off traction.
- **Decision accountability**: every major decision logs reasoning + data +
  quantified expectation; the simulator mechanically scores expected-vs-actual
  when the horizon closes and generates lessons from failures.
- **Learning**: in-run Thompson sampling over channels, empirical price
  elasticity estimation, ROI-anchored risk appetite, plus a cross-run
  knowledge base carrying priors between runs.
- **Experiment mode**: clone companies onto identical seeded market paths;
  tournaments compare strategies fairly. **25-test suite** enforces
  determinism, ledger invariants and funnel conservation.

## 2. Flagship runs (seed 42, balanced policy)

| Horizon | End state |
|---|---|
| **30 days** | Alive. Cash ₹87,857. MRR ₹1,999 (1 customer). Cold start is hard. |
| **90 days** | Alive. Cash ₹83,815. MRR ₹10,494 (6 customers). PMF search phase. |
| **1 year** | Alive. Cash ₹30.6L. **MRR ₹41L**, ARR ₹4.9Cr, 2,311 customers, 17.4% share, churn 4.3%/mo, GM 98%, team scaling begins, valuation proxy ₹78.9Cr. |
| **5 years** | Alive. **MRR ₹2.27Cr**, ARR ₹27Cr, 7,060 customers, 55.8% share, churn 3.6%/mo, GM 98%, org scales to 138 people (44 eng / 58 support / 33 AE), quality 0.61 with all 14 features shipped, cumulative cash ₹51.5Cr, valuation proxy ₹193Cr. |

The 5-year arc after the intelligence upgrade: disciplined capacity hiring
(engineering no longer deadlocked), support scaled ahead of churn (1:120
ratio rule), TAM-saturation-aware marketing tilting spend to referral/content
as the dormant pool thins. Decision scorecard over 5 years: 225 major
decisions, 107 success / 62 partial / 56 fail - a genuinely mixed record,
recorded as it happened.

## 3. Strategy tournaments (cloned companies, identical market paths)

### Year-1 tournament (365 days × 8 seeds × 5 presets = 40 runs)

| Rank | Strategy | Survival | Median MRR |
|---|---|---|---|
| 1 | blitz_growth | 100% | ₹43.4L |
| 2 | product_led | 100% | ₹26.5L |
| 3 | lean_profitable | 100% | ₹23.6L |
| 4 | balanced | 100% | ₹18.2L |
| 5 | premium_first | 100% | ₹4.5L |

### Year-2 tournament (730 days × 5 seeds × 4 presets = 20 runs)

| Rank | Strategy | Survival | Median MRR |
|---|---|---|---|
| 1 | blitz_growth | 100% | ₹143.2L |
| 2 | product_led | **80%** | ₹133.4L |
| 3 | balanced | 100% | ₹131.6L |
| 4 | lean_profitable | 100% | ₹91.6L |

Key findings:
- **Aggression pays while markets are deep**: blitz leads both horizons on
  median MRR among survivors, with large per-seed variance - its risk is real
  even when this seed set doesn't kill it.
- **The first deaths appear at year 2**: product_led's heavy engineering spend
  killed one of five clones - over-investment ahead of collections remains a
  lethal failure mode even for smart agents.
- **Premium pricing without quality parity is near-fatal for growth**:
  premium_first's +35% price stance crushed win rates - an emergent result of
  the discrete-choice model, not a scripted penalty.
- **lean_profitable never dies but never wins**: capital efficiency preserves
  optionality at the cost of scale.

## 4. Cross-run learning verification

Knowledge base accumulated over ~100 observed runs (channel efficiency priors,
price elasticity mean moved from prior −1.3 to measured **−2.81**, strategy
outcome statistics, 400+ counted failure lessons).

A/B check on 6 fresh seeds (blank KB vs experienced KB): median year-1 MRR
₹32.0L vs **₹35.4L** (+11%). Honest caveat: per-seed results were mixed
(3 better / 3 worse) - the learning effect is modest relative to market noise
at this sample size, but directionally positive.

## 5. Failure analysis highlights (real post-mortems from runs)

- **Day-92 payroll deaths** (early calibration): hires approved on trailing
  burn landed right as cash ran out. Fixed with forward-looking runway gates
  (DECISIONS.md D-004); disciplined presets stopped dying this way while
  aggressive ones retain the risk by design.
- **Founder paid himself ₹40k with zero revenue** (guardrail bug): now gated
  on genuine profitability (D-005).
- **Win rate 81.6% → market domination**: static incumbents made the game too
  easy. Adaptive competitors (feature copying, brand trust, zero-sum flows)
  brought win rates to 59–86% and created the mid-run erosion seen at 5y (D-007).
- **Strategy convergence**: unanchored adaptation erased preset differences
  within weeks; identity anchoring restored treatment separation (D-009).

## 6. Verification & reproducibility

- `python3 -m pytest tests/` → **25 passed** (determinism, cash==ledger exact,
  pool conservation, MRR-book equality, clone fairness, funnel units).
- Same seed ⇒ byte-identical trajectories across processes.
- Experiment clones observe byte-identical public market events
  (`test_clone_faces_identical_market_path`).
- Dashboards: `runs/*/dashboard.html` - fully offline, embeds full KPI series,
  decision log with verdicts/lessons, timelines and competitor intel.

## 7. Honest limitations

1. Sequential-RNG draws in decision-dependent paths diverge across clones after
   decisions diverge (distributionally fair, not event-identical; documented).
2. Individual awareness decay approximated by aggregate brand factor (D-008).
3. Competitor financials are proxies (health score), not full ledgers.
4. Learning effect sizes are small vs noise at n=6 A/B samples.
5. Year-1 survival for disciplined presets is currently high (~100%); deaths
   concentrate in aggressive presets, longer horizons, or thin-capital configs.
   The world could be made harsher, but not without making the default policy
   artificially incompetent - the current balance keeps agent skill as the
   differentiator.

## 8. Where intelligence improves next

The action API (`set_marketing`, `hire`, `set_price_mult`, ...) is
LLM-agent-ready: a language-model CEO could replace the heuristic layer without
touching the market engine, using the same decision log format for reasoning.
The knowledge base gives any successor agent institutional memory.

---

*Every figure in this report regenerable via:*
```bash
python3 -m src.cli run --horizon year --seed 42 --name flagship_year1
python3 -m src.cli run --horizon 5y   --seed 42 --name flagship_5y
python3 -m src.cli experiment --days 365 --seeds 8 --presets all
```
