"""Autonomous agents - the decision layer.

Each department head is a heuristic + learning agent observing only its own
company analytics (never market ground-truth internals). They emit actions the
simulator executes causally. Major decisions are logged with reasoning, data
considered, and quantified expectations; outcomes are scored post-hoc and
lessons feed back into policy - genuine strategic intelligence.

Learning components:
  * Marketing: discounted Thompson-style sampling across channels on observed
    CAC vs payback target; nonstationarity handled by recency weighting.
  * Pricing: periodic experiments -> elasticity estimate -> guided adjustment.
  * Hiring: workload-signal policies with affordability guardrails.
  * Strategy: decision post-mortems adjust growth bias & guardrails over time.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .rng import clamp
from .config import CHANNELS, FEATURES, SEGMENTS, SALARY


def hire_affordable(c, k: dict, salary_monthly: float, min_runway_months: float | None = None) -> bool:
    """A hire is affordable only if runway INCLUDING the new committed salary
    stays above the floor. Aggressive strategies accept thinner runways."""
    if min_runway_months is None:
        min_runway_months = 5.0 if c.strategy.growth_bias > 0.8 else 7.0
    post_burn = k.get("forward_burn", k["salaries_monthly"]) + salary_monthly
    if post_burn <= 0:
        return True
    return (c.finance.cash / post_burn) >= min_runway_months \
        and c.finance.cash > c.hire_cost("engineer") * 1.5


# ---------------------------------------------------------------------------
@dataclass
class MarketView:
    """Everything agents are allowed to know about the outside world."""
    day: int
    month: int
    competitor_prices: dict = field(default_factory=dict)   # name -> price multiplier
    competitor_brands: dict = field(default_factory=dict)   # name -> rough brand 0..1
    our_brand: float = 0.0
    market_news: list = field(default_factory=list)         # public event notes
    demand_proxy: dict = field(default_factory=dict)        # segment -> share of our leads


class AgentSuite:
    """All department heads. One instance per company."""

    def __init__(self, company):
        self.c = company
        self.last_channel_update_day = -99
        self.last_price_action_day = -99

    # ------------------------------------------------------------- analytics -
    def kpis(self) -> dict:
        c = self.c
        h = c.history
        last7 = h[-7:] if h else []
        burn30 = sum((s["opex_mtd"] - s["revenue_recognized_mtd"]) for s in (h[-30:] if len(h) >= 30 else h))
        runway = c.finance.compute_runway(c.finance.cash, max(burn30, 1.0))
        # forward-looking burn: committed payroll + current spend pace - booked MRR
        mkt_pace30 = getattr(c, "_mkt_spend_trailing", 0.0)
        forward_burn = c.team.monthly_bill() + getattr(c, "founder_draw_monthly", 0) \
            + mkt_pace30 + 25_000 - c.current_mrr
        runway_fwd = c.finance.compute_runway(c.finance.cash, max(forward_burn, 1.0))
        runway_eff = min(runway, runway_fwd)
        growth = 0.0
        if len(h) >= 31 and h[-31]["mrr"] > 0:
            growth = (h[-1]["mrr"] - h[-31]["mrr"]) / h[-31]["mrr"]
        rev30_daily = sum(s["revenue_recognized_mtd"] for s in last7) / 7.0 if last7 else 0.0
        return dict(
            day=c.day, cash=c.finance.cash, mrr=c.current_mrr,
            arr=c.current_mrr * 12, customers=len(c.active_ids),
            churn_pct=h[-1]["logo_churn_pct_monthly"] if h else 0.0,
            cac=h[-1]["cac_blended"] if h else 0.0,
            ltv=h[-1]["ltv"] if h else 0.0,
            gross_margin=h[-1]["gross_margin_pct"] if h else 0.6,
            runway=runway, runway_fwd=runway_fwd, runway_eff=runway_eff,
            forward_burn=forward_burn,
            burn30=burn30, growth_mom=growth,
            daily_rev_run_rate=c.current_mrr / 30.0,
            csat=c.ops.csat, quality=c.product.quality,
            tickets=c.ops.tickets_open, brand=c.marketing.brand_awareness,
            pipeline=c.sales.pipeline_value, open_deals=len(c.sales.deals),
            unassigned=sum(1 for d in c.sales.deals.values() if d.rep_id < 0),
            team=c.team.total(), salaries_monthly=c.team.monthly_bill(),
            eval_win_rate=c.recent_eval_win_rate(30),
        )

    # ------------------------------------------------------------ entry point -
    def plan(self, view: MarketView, rng: random.Random) -> list[dict]:
        actions: list[dict] = []
        k = self.kpis()
        phase = self.ceo_phase(k)
        self.phase = phase

        self._ceo(actions, k, view, phase, rng)

        if self.c.day % 7 == 0:
            self._cmo(actions, k, phase, rng)
            self._cto(actions, k, phase)
            self._sales_lead(actions, k, phase)
            self._cpo_pricing(actions, k, rng)

        if self.c.day % 3 == 0:
            self._coo(actions, k, phase)

        self._strategy(actions, k, phase)
        return actions

    # ------------------------------------------------------------------- CEO --
    def ceo_phase(self, k: dict) -> str:
        # forward-looking runway rules phase; trailing burn alone lags payroll
        min_rw = self.c.strategy.min_runway_months
        if k["runway_eff"] < min_rw or k["cash"] < max(15_000, k["forward_burn"] / 2):
            return "survive"
        if k["mrr"] < 25_000:
            return "find_pmf"
        ltv_cac = k["ltv"] / k["cac"] if k["cac"] > 0 else 3.0
        if k["gross_margin"] > 0.45 and (ltv_cac >= 2.0 or k["growth_mom"] >= 0.12):
            return "scale" if k["arr"] > 6_000_000 else "grow"
        return "steady"

    def _ceo(self, actions, k, view, phase, rng):
        c = self.c
        s = c.strategy

        # --- crisis protocol -------------------------------------------------
        if phase == "survive":
            actions.append(dict(type="set_marketing", mode="survival"))
            if not any(a.get("type") == "fire" for a in actions) and c.day > 60 \
                    and k["team"] > 1 and k["runway"] < 3:
                # lay off the most expensive non-revenue roles first
                for role in ("growth_manager", "content_marketer", "designer",
                             "junior_engineer"):
                    if c.team.count(role) > 0:
                        n = min(c.team.count(role), 1)
                        actions.append(dict(type="fire", role=role, n=n))
                        d = c.log_decision(
                            day=c.day, agent="CEO", kind="layoff",
                            decision=f"Lay off {n}x {role}",
                            reasoning=(f"Runway {k['runway']:.1f}mo < 3mo threshold; "
                                       f"cash \u20b9{k['cash']:.0f}; monthly burn "
                                       f"\u20b9{k['burn30']:.0f}. Role is not on revenue path."),
                            data_considered={"runway": k["runway"], "cash": k["cash"],
                                             "burn30": k["burn30"], "mrr": k["mrr"]},
                            expected={"runway_months_delta": +2.5},
                            eval_horizon_days=30)
                        c.queue_evaluation(d["id"], "runway", "up", 2.0)
                        break

        # --- founder draw ----------------------------------------------------
        # Founders only get paid once the company genuinely supports it.
        profitable_enough = k["mrr"] >= 30_000 and k["burn30"] <= 0
        draw = 20_000 if (profitable_enough and phase not in ("survive",)) else 0
        actions.append(dict(type="founder_draw", monthly=draw))

        # --- fundraising -----------------------------------------------------
        stance = s.fundraising
        sheet = getattr(self.c, "_pending_term_sheet", None)
        if sheet:
            accept = False
            why = ""
            if stance == "never":
                why = "Bootstrap policy: no dilution."
            elif stance == "eager":
                accept, why = True, "Eager capital policy; accelerates roadmap."
            elif stance == "later":
                accept = k["runway"] < 7
                why = f"Accept only under runway pressure ({k['runway']:.1f}mo)."
            else:  # opportunistic
                accept = (k["runway"] < 9 and k["growth_mom"] > 0.05) or \
                         (k["arr"] > 8_000_000 and k["growth_mom"] > 0.10)
                why = ("Opportunistic: take money when traction strong but runway "
                       f"tightening (runway {k['runway']:.1f}mo, MoM {k['growth_mom']:+.1%}).")
            d = c.log_decision(
                day=c.day, agent="CEO", kind="fundraise",
                decision=("Accept" if accept else "Decline")
                         + f" term sheet: \u20b9{sheet['amount']:,.0f} @ post \u20b9{sheet['post_money']:,.0f} "
                           f"(dilute {sheet['dilution']:.1%}) from {sheet['firm']}",
                reasoning=why,
                data_considered={"cash": k["cash"], "mrr": k["mrr"], "arr": k["arr"],
                                 "growth_mom": k["growth_mom"], "runway": k["runway"],
                                 "churn_pct": k["churn_pct"], "ltv": k["ltv"],
                                 "cac": k["cac"]},
                expected={"cash_delta": sheet["amount"] if accept else 0},
                eval_horizon_days=120)
            if accept:
                c.queue_evaluation(d["id"], "cash", "up", sheet["amount"] * 0.5)
                actions.append(dict(type="accept_term_sheet"))
            else:
                actions.append(dict(type="reject_term_sheet"))
            self.c._pending_term_sheet = None

        # --- segment focus pivot ---------------------------------------------
        if c.day % 90 == 0 or c.day == 21:
            focus = self._choose_focus(view)
            if focus and focus != getattr(c, "focus_segments", None):
                old = getattr(c, "focus_segments", None)
                c.focus_segments = focus
                d = c.log_decision(
                    day=c.day, agent="CEO", kind="segment_focus",
                    decision=f"Focus GTM on segments {focus}" +
                             (f" (was {old})" if old else ""),
                    reasoning=("Highest realized fit x budget among our base and "
                               "funnel; concentrate product & marketing there."),
                    data_considered={"demand_proxy": view.demand_proxy,
                                     "customers_by_seg": c.customers_by_segment(),
                                     "avg_budget_fit": c.avg_budget_fit(focus)},
                    expected={"conversion_lift": 0.10, "cac_reduction": 0.08},
                    eval_horizon_days=60)
                c.queue_evaluation(d["id"], "cac_blended", "down", 0.08)
                actions.append(dict(type="focus_segments", segments=focus))

    def _choose_focus(self, view) -> list[str]:
        c = self.c
        seg_stats = c.segment_funnel_stats()
        if not seg_stats:
            return ["kirana_retail", "sme_services"]
        ranked = sorted(seg_stats.items(),
                        key=lambda kv: kv[1].get("active", 0) * kv[1].get("budget", 0)
                                        * (1 - kv[1].get("churn", 0.2)),
                        reverse=True)
        top = [r[0] for r in ranked[:2]]
        return top

    # ------------------------------------------------------------------- CMO --
    def _cmo(self, actions, k, phase, rng):
        c = self.c
        s = c.strategy
        guard = getattr(c, "cfo_guard_marketing_multiplier", 1.0)

        # ---- weekly channel score update (discounted Thompson sampling) -----
        if c.day - self.last_channel_update_day >= 7:
            self._update_channel_scores()
            self.last_channel_update_day = c.day

        # ---- budget ----------------------------------------------------------
        rev_run = k["daily_rev_run_rate"]
        if phase == "survive":
            budget = max(150.0, rev_run * 0.10)
        elif phase == "find_pmf":
            budget = clamp(rev_run * 0.55 * (0.4 + s.growth_bias), 250.0, 3_500.0)
        elif phase == "grow":
            budget = clamp(rev_run * (0.35 + 0.55 * s.growth_bias), 800.0, 25_000.0)
        elif phase == "scale":
            budget = clamp(rev_run * (0.45 + 0.65 * s.growth_bias), 3_000.0, 60_000.0)
        else:
            budget = clamp(rev_run * 0.30, 400.0, 12_000.0)

        budget *= guard
        cash_cap = c.finance.cash * s.max_marketing_share_of_cash_daily
        budget = min(budget, max(cash_cap, 100.0))
        # hard floor rule: never let ads starve payroll
        if c.finance.cash < max(30_000, k["salaries_monthly"] * 1.2):
            budget = min(budget, 150.0)
        budget = round(budget, 0)

        alloc = self._allocate(budget, phase, rng)
        actions.append(dict(type="set_marketing", daily_budget=budget, allocation=alloc))
        if c.day % 28 == 0:
            c.log_decision(
                day=c.day, agent="CMO", kind="marketing_plan",
                decision=f"Weekly plan: \u20b9{budget:,.0f}/day across channels",
                reasoning=(f"Phase={phase}; run-rate rev \u20b9{rev_run*30:,.0f}/mo; "
                           f"growth_bias {s.growth_bias:.2f}; blended CAC target "
                           f"\u2248 LTV/3=\u20b9{k['ltv']/3:,.0f}. Allocation follows "
                           f"sampling over observed per-channel CAC."),
                data_considered={"channel_cacs": {ch: round(st.observed_cac)
                                                  for ch, st in c.marketing.channels.items()},
                                 "brand": round(c.marketing.brand_awareness, 3)},
                expected={"leads_per_week": budget * 7 / 220.0,
                          "cac_within_target": k["ltv"] / 3.0},
                eval_horizon_days=30)

    def _update_channel_scores(self):
        c = self.c
        ltv = max(50_000.0, (self.kpis()["ltv"] or 60_000))
        target_cac = ltv / 3.0     # ~33% payback ratio rule
        for ch, st in c.marketing.channels.items():
            conv = c.channel_conversions_30d(ch)
            spend = st.spend_trailing30
            obs = None
            if conv >= 1 and spend > 0:
                obs = target_cac / (spend / conv)          # efficiency vs target
            elif spend > 2000 and st.leads_trailing30 > 0:
                # proxy while too early to see conversions: lead economics
                proxy_conv = 0.18
                obs = target_cac / (spend / max(st.leads_trailing30 * proxy_conv, 0.3)) * 0.85
            if obs is not None:
                st.bandit_score = clamp(0.70 * st.bandit_score + 0.30 * clamp(obs, 0.03, 2.5),
                                        0.03, 2.8)

    def _allocate(self, budget: float, phase: str, rng: random.Random) -> dict:
        c = self.c
        policy = c.strategy.channel_policy
        chs = {k: st for k, st in c.marketing.channels.items()}

        if policy == "plg_referral":
            weights = {"referral_program": 0.42, "content_seo": 0.30,
                       "whatsapp_outreach": 0.14, "google_ads": 0.09,
                       "meta_ads": 0.05, "events_partnerships": 0.0}
        elif policy == "cheap_first":
            order = sorted(chs.values(), key=lambda st: (st.observed_cac or 9999))
            weights = {}
            cum = 0.0
            for i, st in enumerate(order):
                weights[st.key] = max(0.02, 1.0 - i * 0.16)
        elif policy == "quality_first":
            q = {k: CHANNELS[k]["quality"] for k in chs}
            weights = {k: v ** 2 for k, v in q.items()}
        else:
            explore = 0.25 if policy == "bandit_aggressive" else c.cfg.bandit_exploration
            sampled = {}
            for key, st in chs.items():
                mu = st.bandit_score
                sigma = 0.30 * max(mu, 0.15)
                sampled[key] = max(0.01, rng.gauss(mu, sigma))
            total = sum(sampled.values()) or 1.0
            weights = {key: (v / total) * (1 - explore) for key, v in sampled.items()}
            for key in weights:
                weights[key] += explore / len(weights)

        # zero-out tiny budgets on expensive channels when broke
        if budget < 800:
            weights = {k: (w if CHANNELS[k]["base_cpl"] <= 200 else w * 0.25)
                       for k, w in weights.items()}
        tot = sum(weights.values()) or 1.0
        alloc = {k: round(w / tot, 4) for k, w in weights.items()}
        return alloc

    # ------------------------------------------------------------------- CTO --
    def _cto(self, actions, k, phase):
        c = self.c
        p = c.product
        eng_n = sum(c.eng_headcount().values())

        # allocation shares
        qual_need = clamp((0.62 - p.quality) * 2.2, 0, 0.55)
        debt_need = clamp(p.tech_debt / 900.0, 0, 0.4)
        feat_share = clamp(1.0 - qual_need - debt_need, 0.25, 0.85)
        norm = feat_share + qual_need + debt_need
        actions.append(dict(type="set_eng_alloc",
                            features=feat_share / norm, quality=qual_need / norm,
                            debt=debt_need / norm))

        # pin next feature by focus segments' biggest uncovered need
        pin = self._next_best_feature()
        if pin:
            actions.append(dict(type="pin_feature", feature=pin))

        # hiring engineers: only once there is revenue signal or deep pockets
        afford = (k["runway_eff"] > 7 or k["burn30"] < 0) and k["cash"] > 80_000
        salary = SALARY["engineer"]
        revenue_signal = k["mrr"] >= 20_000
        eag = c.strategy.hire_eagerness
        want_more = (p.quality > 0.5 and eng_n < 2 + int(k["customers"] / 40)) or eng_n == 1
        if phase in ("grow", "scale") and afford and want_more \
                and hire_affordable(c, k, salary) and rng_ok(c, "hire_eng", 30):
            role = "junior_engineer" if p.quality < 0.5 and k["cash"] < 150_000 else "engineer"
            actions.append(dict(type="hire", role=role, n=1))
            d = c.log_decision(
                day=c.day, agent="CTO", kind="hire",
                decision=f"Hire 1x {role} (\u20b9{(82_000 if role=='engineer' else 52_000):,.0f}/mo)",
                reasoning=(f"Phase {phase}: feature coverage gap on focus segments; "
                           f"capacity {eng_n} eng; quality {p.quality:.2f}; MRR "
                           f"\u20b9{k['mrr']:,.0f} covers ramp; runway "
                           f"{k['runway']:.1f}mo supports it."),
                data_considered={"quality": p.quality, "tech_debt": round(p.tech_debt),
                                 "features": len(p.features), "cash": k["cash"],
                                 "mrr": k["mrr"]},
                expected={"points_shipped_30d": +200},
                eval_horizon_days=45)
            c.queue_evaluation(d["id"], "points_shipped_30d", "up", 200)

        # quality push if incidents burning us
        if p.n_incidents_30d >= 3 and qual_need < 0.25:
            actions.append(dict(type="set_eng_alloc", features=0.5, quality=0.38, debt=0.12))

    def _next_best_feature(self) -> str | None:
        c = self.c
        focus = getattr(c, "focus_segments", None) or list(SEGMENTS.keys())
        best, best_score = None, -1.0
        for f, meta in FEATURES.items():
            if f in c.product.features:
                continue
            score = 0.0
            for seg in focus:
                spec = SEGMENTS[seg]
                w = spec["needs"].get(f, 0.0)
                active = c.customers_in_segment(seg)
                pool_frac = spec["pool"] / 2220.0
                score += w * (0.4 + active / 40.0) * pool_frac * (spec["budget_mean"] / 2300.0) ** 0.5
            score /= max(meta["cost"] / 180.0, 0.5)      # value per dev cost
            if score > best_score:
                best_score, best = score, f
        return best

    # ------------------------------------------------------------- sales lead -
    def _sales_lead(self, actions, k, phase):
        c = self.c
        aes = sum(1 for r in c.sales.reps if r.role == "account_exec")
        unassigned = k["unassigned"]
        open_deals = k["open_deals"]
        afford = (k["runway_eff"] > 7.5 or k["burn30"] < 0) and k["cash"] > 90_000
        load_ratio = open_deals / max(1.0, aes * c.sales.MAX_DEALS_PER_AE)

        if phase in ("grow", "scale") and (unassigned > 0 or load_ratio > 0.85) and afford \
                and hire_affordable(c, k, SALARY["account_exec"]) \
                and c.strategy.hire_eagerness > 0.3 and rng_ok(c, "hire_ae", 45):
            actions.append(dict(type="hire_sales", role="account_exec", n=1))
            d = c.log_decision(
                day=c.day, agent="Sales Lead", kind="hire",
                decision="Hire 1x Account Executive (\u20b968,000/mo + 10% commission)",
                reasoning=(f"{unassigned} unassigned deals; AE utilization "
                           f"{load_ratio:.0%}; sales-led deals leaking."),
                data_considered={"open_deals": open_deals, "pipeline": k["pipeline"],
                                 "cash": k["cash"], "runway": k["runway"]},
                expected={"close_rate_30d": 0.35, "pipeline_conversion_delta": 0.15},
                eval_horizon_days=60)
            c.queue_evaluation(d["id"], "closed_won_30d", "up", 1.0)

    # -------------------------------------------------------------------- CPO -
    def _cpo_pricing(self, actions, k, rng):
        c = self.c
        ps = c.price_test_state
        today = c.day

        # ---- during test: evaluate after >= 14 days ----
        if ps.get("active"):
            elapsed = today - ps["start_day"]
            if elapsed >= 21:
                win_rate_during = c.recent_eval_win_rate(days=elapsed)
                baseline = ps.get("baseline_win_rate", 0.3)
                pr_old, pr_new = ps["baseline_price"], ps["test_price"]
                rev_old = baseline * pr_old
                rev_new = win_rate_during * pr_new
                keep = rev_new >= rev_old * 0.98
                # elasticity update
                try:
                    eps = math.log(max(win_rate_during, 1e-4) / max(baseline, 1e-4)) / \
                          math.log(pr_new / pr_old)
                    c.price_elasticity_est = clamp(
                        0.6 * c.price_elasticity_est + 0.4 * eps, -3.5, -0.15)
                except Exception:
                    pass
                new_mult = ps["mult"] if keep else ps["baseline_mult"]
                actions.append(dict(type="set_price_mult", mult=new_mult))
                d = c.log_decision(
                    day=today, agent="CPO", kind="pricing_test_result",
                    decision=(f"{'Keep' if keep else 'Revert'} price multiplier "
                              f"{new_mult:.2f} (tested {ps['mult']:.2f})"),
                    reasoning=(f"Win rate {win_rate_during:.1%} vs baseline "
                               f"{baseline:.1%}; revenue-per-evaluation "
                               f"\u20b9{rev_new:.0f} vs \u20b9{rev_old:.0f}; "
                               f"elasticity est now {c.price_elasticity_est:.2f}."),
                    data_considered={"baseline_win_rate": baseline,
                                     "during_win_rate": win_rate_during,
                                     "elasticity_prior": round(c.price_elasticity_est, 2)},
                    expected={"revenue_per_eval_delta": (rev_new / rev_old - 1)},
                    eval_horizon_days=30)
                c.queue_evaluation(d["id"], "eval_win_rate", "up", 0.0)
                ps.update(active=False)
                self.last_price_action_day = today
            return

        # ---- start new test occasionally ----
        if today - max(self.last_price_action_day, 30) >= 45 and k["customers"] >= 8 \
                and c.recent_eval_count(30) >= 12:
            est = c.price_elasticity_est
            direction_up = est > -1.0        # inelastic-ish -> raise
            step = 0.10 if abs(est) > 1.2 else 0.06
            mult = (1 + step) if direction_up else (1 - step)
            new_mult = clamp(ps["mult"] * mult, 0.78, 1.38)
            ps.update(active=True, start_day=today,
                      baseline_mult=ps["mult"], mult=new_mult,
                      baseline_win_rate=c.recent_eval_win_rate(30),
                      baseline_price=c.product.effective_prices[1],
                      test_price=c.product.effective_prices[1] * (new_mult / ps["mult"]))
            actions.append(dict(type="set_price_mult", mult=new_mult, test=True))
            d = c.log_decision(
                day=today, agent="CPO", kind="pricing_test_start",
                decision=f"Start price experiment: multiplier -> {new_mult:.2f} "
                         f"({'up' if direction_up else 'down'} from {ps['mult']:.2f})",
                reasoning=(f"Elasticity estimate {est:.2f} suggests {'raising' if direction_up else 'cutting'} "
                           f"price should raise revenue-per-evaluation; enough "
                           f"evaluation volume to read signal in ~3 weeks."),
                data_considered={"evaluations_30d": c.recent_eval_count(30),
                                 "win_rate_30d": c.recent_eval_win_rate(30),
                                 "elasticity_est": est},
                expected={"revenue_per_eval_delta": 0.04 if direction_up else 0.05,
                          "win_rate_delta": -0.03 if direction_up else +0.04},
                eval_horizon_days=45)
            c.queue_evaluation(d["id"], "eval_win_rate", "up", 0.0)

    # -------------------------------------------------------------------- COO -
    def _coo(self, actions, k, phase):
        c = self.c
        support_n = c.support_headcount()
        capacity = c.ops.resolution_capacity_daily(support_n, founder_supporting=True)
        backlog_days = c.ops.tickets_open / max(capacity, 1)
        afford = (k["runway_eff"] > 7 or k["burn30"] < 0) and k["cash"] > 80_000
        if k["customers"] >= 12 and phase not in ("survive",) \
                and backlog_days > 2.5 and support_n < 1 + int(k["customers"] / 80) \
                and hire_affordable(c, k, SALARY["support"]) \
                and rng_ok(c, "hire_support", 30):
            actions.append(dict(type="hire", role="support", n=1))
            d = c.log_decision(
                day=c.day, agent="COO", kind="hire",
                decision="Hire 1x Support Associate (\u20b932,000/mo)",
                reasoning=(f"Ticket backlog {c.ops.tickets_open} = {backlog_days:.1f} days "
                           f"of capacity; CSAT {c.ops.csat:.2f} eroding retention."),
                data_considered={"tickets_open": c.ops.tickets_open,
                                 "csat": c.ops.csat, "customers": k["customers"]},
                expected={"csat_delta": +0.05, "churn_delta": -0.004},
                eval_horizon_days=45)
            c.queue_evaluation(d["id"], "csat", "up", 0.03)

    # ---------------------------------------------------------------- strategy -
    def _strategy(self, actions, k, phase):
        c = self.c
        if c.day % 14 != 0 or c.day < 28:
            return
        # ROI of recent growth spend adjusts risk appetite - but anchored to
        # the preset's identity so strategies stay distinct over time.
        mkt_spend30 = abs(c.finance.sum_category("marketing", c.day - 30, c.day))
        delta_mrr = c.current_mrr - (c.history[-31]["mrr"] if len(c.history) >= 31 else 0)
        roi = delta_mrr / max(mkt_spend30, 1.0)     # incremental MRR per rupee spent
        c._last_roi = roi
        s = c.strategy
        anchor = getattr(s, "_initial_growth_bias", s.growth_bias)
        lo, hi = max(0.05, anchor - 0.15), min(0.97, anchor + 0.15)
        old_bias = s.growth_bias
        if roi > 0.35:
            s.growth_bias = clamp(s.growth_bias + 0.04, lo, hi)
        elif roi < 0.10 and phase not in ("survive",):
            s.growth_bias = clamp(s.growth_bias - 0.06, lo, hi)
        if abs(s.growth_bias - old_bias) > 1e-6:
            predicted = clamp(roi * (1.15 if s.growth_bias > old_bias else 0.95), 0.02, 1.5)
            d = c.log_decision(
                day=c.day, agent="Strategy", kind="risk_appetite_update",
                decision=f"Growth bias {old_bias:.2f} -> {s.growth_bias:.2f}",
                reasoning=(f"Incremental MRR \u20b9{delta_mrr:,.0f} on marketing spend "
                           f"\u20b9{mkt_spend30:,.0f} => ROI {roi:.2f} MRR/\u20b9. "
                           f"{'Scale up' if s.growth_bias > old_bias else 'Pull back'} aggressiveness."),
                data_considered={"roi_mrr_per_rupee": round(roi, 3),
                                 "mkt_spend30": round(mkt_spend30),
                                 "delta_mrr30": round(delta_mrr)},
                expected={"roi_next_30d": round(predicted, 3)},
                eval_horizon_days=30)
            c.queue_evaluation(d["id"], "roi_mrr_per_rupee", "up", predicted - roi)


# --------------------------------------------------------------------------
def rng_ok(company, key: str, cooldown_days: int) -> bool:
    """Debounce repeated decisions of same kind."""
    last = company.__dict__.get("_last_" + key, -9999)
    if company.day - last >= cooldown_days:
        company.__dict__["_last_" + key] = company.day
        return True
    return False
