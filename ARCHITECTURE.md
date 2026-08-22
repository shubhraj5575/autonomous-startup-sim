# Architecture

## Design goals

1. **Genuine causality.** Outcomes must be produced by market mechanics, never
   scripted. The agent layer can only choose actions; a separate ground-truth
   engine resolves them.
2. **Information asymmetry.** Agents observe their own analytics and public
   signals (competitor list prices, rough brand estimates, market news). They
   never read competitor P&Ls or demand internals.
3. **Determinism & counterfactual fairness.** A seed fully determines the
   world path; experiment clones face identical randomness so outcome
   differences measure strategy quality.
4. **Real failure modes.** Bankruptcy is reachable. Over-hiring ahead of
   payroll kills companies (this was observed during calibration - see
   DECISIONS.md).

## System diagram

```
+---------------------------------------------------------------+
|                        WORLD (day loop)                       |
|                                                               |
|  +-----------+      +---------+   actions   +-------------+   |
|  | Market    |      | Agent   +-----------> | Execution    |  |
|  | ground    |<-----+ Suite   |           | marketing /  |  |
|  | truth     |      +----^----+           | eng / sales  |  |
|  +-----^-----+           |                +------+------ |  |
|        |                 | analytics             v          |
|        |          +------+----------------+ +-------------+   |
|  +-----+-----+    | CompanyAnalytics |     | Customer     |  |
|  |Competitors|<---+ (own data only)  |     | pool ~9k:    |  |
|  | adaptive  |    +------------------+     | dormant ->   |  |
|  +-----------+                             | shopping ->  |  |
|                                            | trial/deal ->|  |
|                                            | active/churn |  |
|                                            +--------------+   |
+---------------------------------------------------------------+
```

## The day loop (`src/simulator.py`)

Strict causal ordering each tick:

1. `Market.advance_day` - AR(1) demand per segment + growth drift +
   seasonality; channel health random walk; shock trigger/expire.
2. Competitor monthly update (day % 30 == 15) - archetype-driven adaptation;
   customer flows respond to relative value vs us; entries/exits.
3. Agents plan (weekly cadence + daily reactive) and emit action dicts.
4. Actions execute with real frictions: hiring has notice periods, recruiting
   fees, severance; price changes apply to new subscriptions only.
5. Engineering converts capacity into features / quality / debt paydown.
6. Marketing spend -> saturating lead curves per channel -> pool members flip
   to `shopping` with source attribution.
7. Customer state machine:
   - `dormant -> shopping`: organic hazard (segment-level binomial draw) or
     paid/referral flips.
   - `shopping`: after 2-3 days evaluates us plus up to 2 competitors sampled
     by brand via a logit discrete-choice model:
     `U = ln(fit x qf x bf x sf) - lambda_seg * ln(price/budget)`.
     A challenger trust penalty applies to the new entrant.
   - win -> trial (self-serve) or AE deal (sales-led); loss -> cooldown.
   - trial end: conversion from fit x quality minus price-ratio penalty.
   - active: monthly renewal - billing, churn hazard from satisfaction,
     poach pressure from best competitor utility gap, expansion upgrades.
8. Incidents roll against product surface x debt x inverse quality ->
   satisfaction damage plus tickets; support capacity resolves tickets -> CSAT.
9. Finance settles every rupee through the ledger (day-indexed windows).
10. KPI snapshot -> history; decision evaluations close; bankruptcy check.

## Economic model highlights

**Discrete choice.** Customers pick the max-utility vendor among a
consideration set that includes an outside option ("do nothing"). Price
elasticity therefore *emerges*; the CPO agent estimates it empirically from
price experiments rather than being told.

**Unit economics are tight by design.** Channel CPLs calibrated to Indian B2B
SaaS reality (INR 270-1450 per lead), salaries INR 32k-115k/mo, payment fees
1.9%, infra INR 11/account/mo. With INR 1L starting capital, hiring ahead of
revenue is genuinely dangerous.

**Valuation proxy** = ARR x multiple, where
`multiple = (3 + 18*growth - 6*churn_frac) x margin_factor`, clamped [2,16].
Term sheets are priced off the same curve with a negotiation spread.

## Learning systems

| Loop | Mechanism | Horizon |
|---|---|---|
| Marketing allocation | Discounted Thompson-style sampling on observed channel CAC vs LTV/3 target | weekly |
| Pricing | Periodic +/-6-10% experiments; elasticity estimate updated from win-rate response; keep if revenue-per-evaluation improves | ~45d cycles |
| Hiring | Workload signals (unassigned deals, ticket backlog, feature gap) gated by post-hire runway math | weekly |
| Risk appetite | Strategy agent adjusts growth bias from measured spend ROI, anchored to preset identity (+/-0.15) | 14d |
| Decision post-mortems | Expected-vs-actual scoring when evaluation windows close; failures generate lessons | 30-120d |
| Cross-run | KnowledgeBase persists channel priors, elasticity mean and strategy outcomes between runs | forever |

## Performance engineering

Naive per-customer daily loops made a 5-year run take minutes. Three fixes:

1. **Day-indexed ledger windows** (`FinanceEngine.cat_day`): category sums are
   O(window) instead of O(full history), removing quadratic behavior.
2. **Statistical organic demand**: the dormant pool is not iterated daily;
   instead one binomial draw per segment-day (hash-derived uniforms keep runs
   deterministic) plus uniform sampling of who flips.
3. **Bucket-based lead realization**: candidates bucketed by (state, segment)
   once per day; channels sample buckets proportionally to affinity - O(leads)
   rather than O(pool x channels).

Renewals are event-driven via a day->customer index; satisfaction is
recomputed at renewal from its equilibrium equation minus incident damage.
A 365-day run takes ~2-4s; 1825 days ~60s on an M-series MacBook.

## Determinism & experiment fairness

- Every subsystem draws from named RNG streams (`RngManager`) seeded from one
  master seed; adding systems does not shift other streams.
- Organic-demand randomness is derived per (seed, segment, day) so it does not
  depend on consumption order.
- Experiment clones share the seed: `test_clone_faces_identical_market_path`
  asserts two strategy variants see byte-identical public market events.
- Known trade-off: sequential stream draws inside decision-dependent code
  paths (e.g., which competitor joins a consideration set) diverge across
  variants after decisions diverge. This is distributionally fair and keeps
  the engine simple; documented here deliberately.

## Extension guide

- New channel: add spec to `CHANNELS` (CPL, saturation exponent, reference
  spend, segment affinities); bandit picks it up automatically.
- New shock: append a template to `EVENT_TEMPLATES`.
- New agent policy: presets live in `STRATEGY_PRESETS`; the strategy agent
  adapts within +/-0.15 of the preset anchor so identities persist.
- New customer segment: add to `SEGMENTS`; pools, needs and budgets flow
  through everything automatically.
