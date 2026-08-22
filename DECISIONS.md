# Decision Records

Engineering and design decisions made while building the simulation, in
chronological order. Each records context, choice, and observed consequence -
mirroring how the simulated CEO operates, but for the real codebase.

---

## D-001: Python stdlib-only core engine

**Context.** Overnight autonomous build; no guarantee of dependency stability;
simulation correctness matters more than raw speed.

**Decision.** Pure Python 3.10+ stdlib for the engine. pytest only for tests.
Dashboard is dependency-free vanilla JS with hand-rolled canvas charts.

**Consequence.** Runs anywhere; deterministic across platforms (hash-seeded
RNG). A 365-day run takes ~2-4s after optimization - acceptable.

## D-002: Heuristic + learning agents instead of LLM calls

**Context.** Agents could call an LLM API, but that would make runs
non-deterministic, slow, network-dependent, and impossible to verify honestly.

**Decision.** Agents are rule/heuristic systems with genuine learning
components (Thompson-style channel sampling, empirical price elasticity,
ROI-anchored risk appetite, post-mortem lessons).

**Consequence.** Fully reproducible tournaments; "intelligence" is measurable.
LLM-driven agents remain a possible future layer *above* the same action API.

## D-003: Discrete-choice customer model

**Context.** Needed price elasticity and competition to emerge from mechanics
rather than be parameterized directly.

**Decision.** Logit utility over consideration set:
`U = ln(fit x quality x brand x support) - lambda_seg x ln(price/budget)`,
with an outside option and a challenger trust penalty against the new entrant.

**Observed consequence.** During calibration the win rate hit **81.6%**
because competitors were static. This drove D-007 (adaptive competitor AI).
Post-fix win rates spread to 59-86% across seeds.

## D-004: Forward-looking runway guardrails

**Context.** First calibration runs showed companies dying on day ~91-92:
trailing-30d burn looked fine because revenue was ramping, then payroll landed
and cash went negative within days. Root cause: hires approved on lagging
indicators; recruiting fees + salaries committed before collections matured.

**Decision.** Phase detection and hiring gates use `runway_eff =
min(trailing_runway, forward_runway)` where forward burn = committed payroll +
current marketing pace + overhead - booked MRR. Every hire additionally must
keep post-hire runway above a floor (aggressive presets accept 5 months,
conservative 7+).

**Observed consequence.** Day-92 payroll deaths disappeared for disciplined
presets while aggressive strategies still can die by design.

## D-005: Founder draws only from genuine profit

**Context.** The CEO paid himself INR 20k/mo from day 1 despite zero revenue
because the original condition compared MRR to a zero-salary bill.

**Decision.** Founder draw requires MRR >= 30k AND trailing profitability AND
not in survive phase.

## D-006: Market expansion via customer births

**Context.** With a static pool, every strategy converged once TAM saturated
(~45% penetration by month 8) - experiment mode became meaningless.

**Decision.** Pool grows daily proportional to blended segment growth;
churned customers re-enter after cooldowns.

## D-007: Competitors that actually compete

**Context.** Static incumbents let any competent policy capture >50% share of
the universe within a year; win rates ~82%.

**Decision.** Competitors get (a) market-wide quality drift, (b)
focus-segment-aware feature shipping that accelerates when losing share
(they copy what beats them), (c) deep initial brand trust (0.42-0.62 vs our
0.02), (d) zero-sum-ish customer flows driven by relative value, (e) a 0.30
utility challenger penalty against us.

**Observed consequence.** Year-1 outcomes now range MRR 7L-48L, share 4-20%,
win rates 59-86%; near-insolvent seeds exist; strategy presets separate
cleanly in tournaments.

## D-008: Statistical organic demand & bucket lead sampling

**Context.** O(pool) daily scans and O(pool x channels) attribution loops made
runs 10x too slow at realistic market size (~9k entities).

**Decision.** Segment-day binomial draws (hash-derived uniforms preserve
determinism) replace per-customer coin flips; leads sample (state, segment)
buckets built once per day; renewals are event-driven via a day-index.

**Trade-off.** Individual awareness decay folded into aggregate brand factor -
documented approximation, statistically equivalent acquisition rates.

## D-009: Strategy identity anchoring

**Context.** The strategy agent's ROI adaptation erased preset personalities
within weeks: blitz and lean converged to identical budgets.

**Decision.** Growth-bias adaptation clamped to +/-0.15 around each preset's
initial value; presets also set their own minimum-runway tolerance (blitz 2.5
months, lean 8).

**Observed consequence.** Tournaments show persistent separation (see
FINAL_REPORT.md tables).

## D-010: Decision evaluation semantics

**Context.** "Expected outcome" fields are easy to fake post-hoc; we wanted
genuine accountability.

**Decision.** At decision time agents record quantified expectations; the
simulator captures an immediate metric baseline; when the horizon elapses the
delta is scored success/partial/fail mechanically. Failures auto-generate
lesson text by decision kind; these feed the knowledge base.

## D-011: Honest reporting of early-stage metrics

**Context.** With <20 customers and zero churn events, LTV formulas explode
(observed LTV/CAC = 179 in a 90-day smoke run).

**Decision.** LTV reported only when actives >= 20 and churn30 >= 2; gross
margin double-scaling fixed; dashboards label such metrics "too early".

## D-012: Dominance provokes counter-pressure

**Context.** The upgraded agent layer reached 55.8% market share by year 5 with
no world response - dominance was free, which is neither realistic nor
strategically interesting.

**Decision.** When our share exceeds 40%: (a) rivals treat every month as
"losing share" (faster adaptation) plus a consolidation flow bonus; (b) an
"Incumbent backlash" sentiment shock can fire, adding up to +0.22 utility
penalty against us (buyers hedge against the leader) plus scrutiny filing
costs; (c) competitor exits now redistribute their base to remaining rivals
(universe conservation).

**Observed consequence.** Backlash fired at day 1305 of the flagship run;
share plateaued ~50-53% instead of running away.

## D-013: Revenue metrics read from the ledger only

**Context.** A snapshot window mixed billing *events* with *days* (last 30
events != last 30 days), flooring gross margin at 5% and corrupting LTV/CAC
across long runs - discovered by auditing "GM 5% at 98% true margin".

**Decision.** `FinanceEngine.cat_day` day-indexed sums are the single source
of truth for any trailing revenue/COGS figure; event windows deleted.

## D-014: Agent capability upgrades must be measured against the same seed

**Context.** "Smarter agents" claims are cheap; the CTO hiring deadlock fix
could have regressed other phases unnoticed.

**Decision.** Every intelligence upgrade is validated by re-running the
flagship seed and the tournament suite; deltas reported in FINAL_REPORT.md
(e.g., CTO deadlock fix: same-seed 5y MRR ₹1.24Cr → ₹2.27Cr).

## D-015: Deal-pending customers leave the evaluation pool

**Context.** The deepest mechanical bug of the build: customers with a pending
AE deal remained in `shopping`, where the daily evaluation loop re-scored them
against competitors until a loss transitioned them out - silently voiding 485
pending deals in one run ("lead vanished"). Sales-led segments (mfg, enterprise)
were effectively unplayable.

**Decision.** Evaluation skips any customer with a live deal. Additionally:
deal creation is gated on honest AE capacity (a saturated bench turns the
prospect away rather than parking them), and sales hiring follows pipeline flow
with the AE salary bill capped at ~35% of MRR.

**Observed consequence.** mfg actives 12→664, enterprise 1→179 on the flagship
seed; all five segments winnable; tournament medians dropped as inflated
duplicate evaluations disappeared.

## D-016: Investor attention is finite

**Context.** Term sheets kept arriving monthly for a profitable company that
kept declining - 56 identical rejections spamming one decision log.

**Decision.** After a decline, investors back off for 180 days.
