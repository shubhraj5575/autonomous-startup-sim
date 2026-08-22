# Overnight Build Log

Chronological journal of the autonomous build session. Every number quoted is
measured from actual runs, not estimated.

---

## Phase 0 - Reconnaissance

- Environment verified: Python 3.12.6, git, `gh` authenticated as
  **shubhraj5575**.
- Repository created: https://github.com/shubhraj5575/autonomous-startup-sim

## Phase 1 - Core engine (market, customers, finance)

- Built the causal day-loop world: market demand AR(1)+drift+seasonality,
  shock catalog (funding winter, festive boom, GST deadline, ad-CPM spike,
  new entrant...), channel health drift, competitor archetypes.
- Customer agents with needs vectors, budgets, logit discrete choice over a
  consideration set including competitors and an outside option.
- Finance ledger as single source of truth for cash; SaaS metrics derived.
- First smoke run crashed twice (`__slots__` vs dataclass) then ran.

## Phase 2 - Agents & first calibration lessons

First full-system runs exposed real governance failures that were *fixed in
the agent layer*, not papered over in the market:

| Observed failure | Root cause | Fix |
|---|---|---|
| Company paid founder ₹40k while revenue was zero | draw condition compared MRR to a zero bill | D-005 profit gate |
| Day-92 payroll bankruptcies | trailing burn lagged committed salaries; double hires same day | D-004 forward runway + post-hire affordability |
| Win rate 81.6%, share >60% by month 12 | static competitors, challenger too trusted | D-007 adaptive incumbents + trust penalty |
| All strategies converged to identical outcomes by month 8 | static TAM saturation erased preset differences | D-006 market births + D-009 identity anchoring |
| 365-day run took ~25s at realistic market size | O(pool x channels) daily loops | D-008 statistical sampling |

Calibration target reached: across 12 seeds, year-1 MRR spread **₹7L–₹48L**,
share **4–20%**, win rates **59–86%**, near-insolvent survivors present.

## Phase 3 - System completion

- CLI with horizon presets (30d/90d/half/year/2y/5y).
- JSON persistence + markdown reports per run.
- Experiment mode: clone companies onto identical seeded market paths;
  tournament aggregation + markdown/json artifacts.
- Knowledge base: cross-run priors for channels, elasticity, strategy outcomes.
- Self-contained dashboard (offline HTML, canvas charts, decision browser).
- Test suite: **25 tests** covering determinism, finance invariants, pool
  conservation, funnel mechanics, agent sanity.

## Phase 4 - Flagship runs & tournaments

- **Flagship runs** (seed 42, balanced): 30d / 90d / year / 5y all completed
  and persisted with dashboards. Year-1: MRR ₹44.4L, share 19.3%. Five-year:
  MRR ₹1.24Cr, cash ₹39.2Cr cumulative, share peak 38% then erosion to 28%,
  team scaling to 42. See FINAL_REPORT.md for tables.
- **Year-1 tournament** (40 cloned-company runs): blitz_growth #1 (₹46.4L
  median MRR) but with huge per-seed variance; premium_first near-fails
  (+35% price stance crushes win rate - emergent, not scripted).
- **Year-2 tournament** (24 runs): balanced overtakes blitz as markets mature -
  aggression stops paying under saturation.
- **Learning A/B**: knowledge-base priors worth +11% median year-1 MRR on a
  6-seed check; honestly reported as within noise at that sample size.
- **Late bug found by metric audit**: revenue window mixed event counts with
  day counts → gross margin floored at 5%, LTV garbage. Replaced with ledger
  sums (single source of truth); all metrics now economically coherent.
- Valuation proxy corrected to equity value (operating multiple + cash).

## Phase 5 - Strategic intelligence upgrade (measure → learn → adjust)

The 5-year flagship exposed a genuine flaw in the agent layer: **33 sales
hires vs 1 engineer in five years**. The CTO's hiring policy required quality
> 0.5 before scaling the team, but only engineers raise quality capacity - a
self-imposed deadlock that capped quality at 0.44 while churn crept to 8%.

Fixes (all in agent policy, none in market mechanics):
1. Engineering scaled with installed base (`2 + customers/60`), quality
   treated as the *reason* to hire, not a precondition.
2. Support staffed predictively at 1:120 customers plus backlog/churn-reactive.
3. TAM-saturation guardrail: when dormant pool < 25%, marketing throttles and
   tilts toward referral/content.

**Measured effect on the same seed (5-year run):**

| Metric | v1 agents | v2 agents |
|---|---|---|
| MRR | ₹1.24Cr | **₹2.27Cr** |
| Customers | 3,492 | 7,060 |
| Cash (cumulative) | ₹39.2Cr | ₹51.5Cr |
| Valuation proxy | ₹69Cr | **₹193Cr** |
| Quality | 0.44 | 0.61 |
| Org balance | 33 AE / 7 support / 1 eng | 44 eng / 58 support / 33 AE |

This is the overnight loop working as intended: ANALYZE runs, find the
weakness, fix the *policy*, MEASURE the delta - the improvement came from
better decisions, not from changing the game.

## Phase 6 - World depth & final verification

- **Dominance counter-pressure** (D-012): share > 40% triggers rival
  coordination and backlash sentiment shocks. In the flagship run it fired at
  day 1305 and plateaued share near 53% - the market now pushes back.
- **Competitor exits conserve the universe**: scattered customers flow to
  remaining rivals instead of vanishing.
- **Tournament comparison dashboard**: `compare.html` renders median MRR/cash
  trajectories per strategy offline.
- **Capital stress sweep**: ₹50k / ₹1L / ₹2L × 8 seeds - survival 8/8, 7/8,
  8/8 with non-monotonic medians (₹9.4L / ₹16.2L / ₹13.3L). Extra capital made
  outcomes *worse* on this seed set: undisciplined spend pre-PMF.
- **Full test suite re-run**: 25 passed; both dashboard JS files parse under
  node.

## Phase 7 - The lifecycle finding & learning verification

Final-mechanics tournaments (with accumulated knowledge priors):

| Horizon | Winner |
|---|---|
| Year 1 | product_led (₹43.5L) |
| Year 2 | product_led (₹138.3L) |
| Year 5 | blitz_growth (₹203L), balanced close behind (₹198.8L); lean's first death |

Raw aggression wins in deep early markets; compounding quality/retention
economics take over as markets saturate; rankings shift as the knowledge base
learns - all emergent, none scripted.

**Learning A/B strengthened**: with the KB at 446 observed runs, a 12-seed
A/B showed learned priors deliver **+50% median year-1 MRR** vs blank priors
(8/12 seeds better) - up from +11% at the earlier n=6 check.

Also this phase: winback flow (churned re-enter at reduced organic rate),
investor cooldown after repeated declines, CPO guard for underpowered pricing
tests, dead-code cleanup pass.

## Phase 8 - The deal-state machine bug (deepest find of the night)

A segment census after 3 years showed **zero manufacturing customers** despite
full feature coverage. Census by funnel stage found 270 mfg prospects stuck in
`shopping`; the deal-loss ledger showed 485 deals lost to "lead vanished".

Root cause: customers with a pending AE deal stayed in `shopping` state, where
the evaluation loop re-evaluated them *every day* - until one re-evaluation
lost them to a competitor, which transitioned them out of shopping and voided
their own pending deal.

Fix: skip re-evaluation for deal-pending customers. Effects on seed 42:
mfg_sme actives 12 → 664; enterprise_pilot 1 → 179; year-3 MRR +66%. All five
segments became winnable. Year-1 medians across tournaments dropped (blitz
₹43L → ₹30L) because inflated duplicate evaluations were removed - honest
numbers over flattering ones.

Also this phase: sales hiring scaled to pipeline flow with an AE-bill ≤35% of
MRR discipline (an earlier naive version overspent into insolvency - caught by
the same measure→adjust loop), and a capacity gate at deal creation so doomed
deals are never promised to prospects.

## Session wrap-up

**Final state:** 4,262 lines of Python across 20 modules + 1,316 lines of
documentation, 25 passing tests, all flagship runs and tournament artifacts
committed, everything pushed to GitHub.

**The loop, honestly executed:**

| Cycle | What measurement exposed | What changed |
|---|---|---|
| 1 | Day-92 payroll bankruptcies | Forward-runway hiring gates |
| 2 | Win rate 81.6%, free domination | Adaptive competitors + trust penalty |
| 3 | All strategies converged by month 8 | Market births + preset anchoring |
| 4 | O(pool×channels) runtime | Statistical sampling rewrite |
| 5 | CTO hiring deadlock (1 eng hire in 5y) | Capacity-based eng scaling (+83% MRR) |
| 6 | Free dominance at 55% share | Backlash shocks + rival coordination |
| 7 | GM floored at 5%, LTV garbage | Ledger as single revenue source of truth |
| 8 | Zero mfg customers; 485 voided deals | Deal-state machine fix (mfg 12→664) |

**Clearest emergent finding:** strategy rankings invert across horizons -
aggression wins early, compounding quality/retention wins late - and shift
again as the knowledge base learns. Nothing in that sentence was programmed.

---

## Engineering post-mortems worth keeping

1. **Lagging indicators kill.** The single most lethal agent bug was trusting
   trailing burn. The fix (forward runway) is now also enforced for every hire.
2. **Adaptation erases identity.** Any learning loop strong enough to optimize
   will homogenize policies unless anchored. Presets needed bounded adaptation
   to remain distinct treatments in experiments.
3. **Saturation hides strategy differences.** A finite universe converts
   "spend more" into pure waste; markets must grow for growth strategies to be
   distinguishable from efficient ones.
