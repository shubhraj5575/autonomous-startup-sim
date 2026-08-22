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
| **30 days** | Alive. Cash ₹87,861. MRR ₹1,999 (1 customer). Cold start is hard. |
| **90 days** | Alive. Cash ₹86,209. MRR ₹15,992 (8 customers). PMF search phase. |
| **1 year** | Alive. Cash ₹38.4L. **MRR ₹46.1L**, ARR ₹5.5Cr, 2,640 customers, 20.4% share, churn 5.2%/mo, GM 97.6%, team 17, valuation proxy ₹88.9Cr. |
| **5 years** | Alive. **MRR ₹2.24Cr**, ARR ₹26.9Cr, 7,170 customers, 55.1% share (backlash-capped), churn 3.6%/mo, GM 97.8%, org of 139 (45 eng / 59 support / 33 AE), quality 0.57, LTV/CAC 14.9, cumulative cash ₹50.9Cr, valuation proxy ₹168Cr, founder equity still 100% (never needed dilution). |

The 5-year arc: disciplined capacity hiring (engineering no longer deadlocked),
support scaled ahead of churn (predictive 1:120 rule), TAM-saturation-aware
marketing tilting spend to referral/content as the dormant pool thins, one
incumbent-backlash event capping dominance. Decision scorecard over 5 years:
232 major decisions, 114 success / 59 partial / 59 fail - a genuinely mixed
record, recorded as it happened.

## 3. Strategy tournaments (cloned companies, identical market paths)

Final-mechanics tournaments, run with the accumulated knowledge base:

### Year-1 tournament (365 days × 8 seeds × 5 presets = 40 runs)

| Rank | Strategy | Survival | Median MRR |
|---|---|---|---|
| 1 | product_led | 100% | ₹43.5L |
| 2 | balanced | 100% | ₹35.0L |
| 3 | blitz_growth | 100% | ₹32.7L |
| 4 | lean_profitable | 100% | ₹15.5L |
| 5 | premium_first | 100% | ₹4.5L |

### Year-2 tournament (730 days × 5 seeds × 4 presets = 20 runs)

| Rank | Strategy | Survival | Median MRR |
|---|---|---|---|
| 1 | product_led | 100% | ₹138.3L |
| 2 | balanced | 100% | ₹135.5L |
| 3 | blitz_growth | 100% | ₹122.9L |
| 4 | lean_profitable | 100% | ₹98.0L |

### The long game: 5-year tournament (1825 days × 3 seeds × 3 presets)

| Rank | Strategy | Survival | Median MRR |
|---|---|---|---|
| 1 | blitz_growth | 100% | ₹203.0L |
| 2 | balanced | 100% | ₹198.8L |
| 3 | lean_profitable | **67%** | ₹129.0L |

Key findings:
- **The lifecycle arc**: blitz leads in deep early markets; product-led and
  balanced overtake by years 1–2 as compounding retention and quality economics
  dominate raw spend; by year 5 blitz edges back ahead on survivors while lean
  records its first death.
- **Premium pricing without quality parity is near-fatal for growth**:
  premium_first's +35% price stance crushed win rates - an emergent result of
  the discrete-choice model, not a scripted penalty.
- **Knowledge priors shift tournament rankings between sessions** - learned
  channel scores favor content/referral, which benefits product-led policies.
  Strategy evaluation is a moving target as the firm learns; rankings are
  reported per session rather than claimed as universal.

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
