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

## 2. Flagship runs (seed 42, balanced policy, final mechanics)

| Horizon | End state |
|---|---|
| **30 days** | Alive. Cash ₹85,900. MRR ₹0 (0 customers). Cold start is genuinely hard. |
| **90 days** | Alive. Cash ₹82,744. MRR ₹15,992 (8 customers). PMF search phase. |
| **1 year** | Alive. Cash ₹9.9L. **MRR ₹21.4L**, 1,224 customers, 10.2% share, churn 5.1%/mo, GM 97.6%, team 19. Decision scorecard: 20 success / 3 partial / 13 fail. |
| **5 years** | Alive. **MRR ₹2.84Cr**, 7,795 customers, 58% share (backlash-capped), churn 3.2%/mo, GM ~98%, org of 175, quality 0.63, LTV/CAC 16.0, cumulative cash ₹51.7Cr, valuation proxy ₹283Cr. |

The 5-year arc: a modest honest first year, then the sales-led segments
(manufacturers, enterprise) unlock as AE capacity builds - the classic SaaS
J-curve. Support scaled predictively ahead of churn; TAM-saturation-aware
marketing tilts spend toward referral/content as the pool thins; one incumbent-
backlash event capped dominance mid-run.

## 3. Strategy tournaments (cloned companies, identical market paths)

Final-mechanics tournaments, run with the accumulated knowledge base:

### Year-1 tournament (365 days × 8 seeds × 5 presets = 40 runs)

| Rank | Strategy | Survival | Median MRR |
|---|---|---|---|
| 1 | blitz_growth | 100% | ₹30.2L |
| 2 | balanced | 100% | ₹18.3L |
| 3 | product_led | 100% | ₹15.2L |
| 4 | lean_profitable | 100% | ₹13.8L |
| 5 | premium_first | 100% | ₹0.7L |

### Year-2 tournament (730 days × 5 seeds × 4 presets = 20 runs)

| Rank | Strategy | Survival | Median MRR |
|---|---|---|---|
| 1 | blitz_growth | 100% | ₹132.1L |
| 2 | balanced | **80%** | ₹123.9L |
| 3 | product_led | 100% | ₹120.1L |
| 4 | lean_profitable | 100% | ₹111.4L |

### The long game: 5-year tournament (1825 days × 3 seeds × 3 presets)

| Rank | Strategy | Survival | Median MRR |
|---|---|---|---|
| 1 | blitz_growth | 100% | ₹255.9L |
| 2 | lean_profitable | 100% | ₹255.9L |
| 3 | balanced | 100% | ₹242.5L |

Key findings:
- **Aggression leads on survivors at every horizon** in this seed set, but its
  edge narrows from 65% over balanced (year 1) to a rounding error by year 5 -
  and earlier tournament generations showed blitz dying outright under other
  mechanics/knowledge states. Risk-adjusted, the gap is smaller than raw
  medians suggest.
- **Mortality appears by year 2**: balanced lost a clone to over-extension.
- **Premium pricing without quality parity is non-viable**: premium_first's
  +35% price stance nearly zeroes win rates - emergent from the discrete-choice
  model, not scripted.
- **lean_profitable's patience pays long-term**: it matches blitz's median by
  year 5 after surviving everything - slow capital efficiency compounding.

### Capital stress test (balanced policy, 365 days, 8 seeds per level)

| Starting capital | Survival | Median year-1 MRR |
|---|---|---|
| ₹50,000 | 8/8 | ₹9.4L |
| ₹1,00,000 (default) | 7/8 | ₹16.2L |
| ₹2,00,000 | 8/8 | ₹13.3L |

Non-monotonic and honest: with ₹2L the agents spend more aggressively before
product-market fit and end slightly *worse* than the disciplined ₹1L runs on
this seed set - money without discipline buys noise.

## 4. Cross-run learning verification

Knowledge base state at report time: **446 runs observed**, price elasticity
mean moved from prior −1.3 to measured **−2.83**, per-channel efficiency
priors and strategy outcome statistics populated, 1,000+ counted failure
lessons by category.

A/B check on 12 fresh seeds (identical seeds; blank priors vs accumulated
priors), year-1 horizon:

| Priors | Median MRR | Per-seed wins |
|---|---|---|
| Blank | ₹26.9L | 4/12 |
| Learned (446 runs) | **₹40.3L** | **8/12** |

Median uplift from institutional memory: **+50%**. The mechanism is concrete:
seeded bandit scores start new runs on empirically efficient channels, and the
measured elasticity prior points the first pricing experiment in the right
direction. (An earlier n=6 check showed only +11% - small samples are noisy,
which is exactly why this was re-measured.)

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
