"""The simulation engine: a strict causal day loop.

Order of operations each day:
  1. market evolves (demand, trends, shocks, channel health)
  2. competitors adapt (monthly) and may enter/exit
  3. agents observe their analytics -> emit actions; actions execute
  4. marketing spend converts to leads (pool members flip to shopping)
  5. customers evaluate offers, start trials, convert, renew or churn
  6. sales pipeline advances; deals close with rep capacity constraints
  7. incidents & support resolution affect satisfaction
  8. finance settles every rupee through the ledger
  9. KPI snapshot recorded; decision outcomes evaluated; bankruptcy checked

Nothing about outcomes is scripted: agents choose actions; the market decides.
"""
from __future__ import annotations

import math
import random
from collections import deque

from .rng import RngManager, clamp, fmt_inr
from .config import SimConfig, SEGMENTS, CHANNELS, FEATURES, TIER_NAMES, \
    BASE_MONTHLY_TOOLS, INFRA_COST_PER_ACCOUNT, PAYMENT_GATEWAY_RATE, COMMISSION_RATE
from .market import Market
from .customers import (CustomerPool, Customer, Offer, evaluate_offer,
                        choice_probability, STATE_DORMANT, STATE_SHOPPING,
                        STATE_TRIAL, STATE_ACTIVE, STATE_CHURNED)
from .competitors import Competitor, DEFAULT_COMPETITORS
from .company import Company
from .agents import AgentSuite, MarketView
from .investors import maybe_term_sheet
from .finance import FinanceEngine


OUTSIDE_UTILITY = -1.55          # value of "do nothing" - SMBs are hard to convert
TRIAL_BASE_CONV = 0.24


class World:
    def __init__(self, cfg: SimConfig, company: Company | None = None):
        self.cfg = cfg
        self.rng = RngManager(cfg.seed)
        self.market = Market(cfg, self.rng)
        self.pool = CustomerPool(cfg, self.rng)
        self.company = company or Company(cfg)
        self.company.pool = self.pool
        self.competitors: list[Competitor] = []
        for name, arch, feats in DEFAULT_COMPETITORS[:cfg.n_competitors]:
            r = self.rng.stream(f"comp_{name}")
            cust0 = int(r.uniform(1300, 2600))
            self.competitors.append(Competitor(
                cid=name.lower().replace(" ", "_"), name=name, archetype=arch,
                features=set(feats), quality=r.uniform(0.38, 0.54),
                price_mult=r.uniform(0.9, 1.25), brand=r.uniform(0.42, 0.62),
                customers=cust0, mrr=cust0 * 1900.0 * r.uniform(0.9, 1.25),
                entry_day=0))
        self.agents = AgentSuite(self.company)
        self.sim_rng = self.rng.stream("sim")
        self.sales_rng = self.rng.stream("sales")

        # marketing plan state (set by CMO actions)
        self.mkt_daily_budget = 0.0
        self.mkt_alloc = {k: (1.0 / len(CHANNELS)) for k in CHANNELS}
        self.referral_enabled = True

        # rolling windows for metrics
        self.new_customers_window: deque = deque()      # (day,)
        self.churned_window: deque = deque()
        self.cash_collected_window: deque = deque()
        self.points_shipped_window: deque = deque()
        self.closed_won_window: deque = deque()
        # fast indexes
        self._renewals_due: dict[int, set] = {}
        self._mrr_book: float = 0.0

    # ================================================================= run ==
    def run(self, days: int, progress_every: int = 30, verbose=False) -> Company:
        end = self.company.day + days
        while self.company.alive and self.company.day < end:
            self.tick()
            if verbose and self.company.day % progress_every == 0:
                c = self.company
                print(f"  day {c.day:>4} cash={fmt_inr(c.finance.cash):>10} "
                      f"mrr={fmt_inr(c.current_mrr):>10} cust={len(c.active_ids):>4} "
                      f"phase={getattr(self.agents, 'phase', '?')}")
        return self.company

    def tick(self):
        c, mkt = self.company, self.market
        c.day += 1
        day = c.day
        mkt.advance_day(day)

        if mkt.competitor_entry_pending:
            mkt.competitor_entry_pending = False
            self._spawn_competitor(day)

        if day % 30 == 15:
            self._competitor_monthly(day)

        # ---- agents ------------------------------------------------------
        view = self.build_market_view()
        actions = self.agents.plan(view, self.sim_rng)
        self.execute_actions(actions)
        self._capture_eval_baselines()

        # ---- product build -------------------------------------------------
        c.engineering.priority_feature = getattr(c, "pinned_feature", None)
        c.engineering.execute_day(c.eng_headcount())

        # ---- marketing execution ----------------------------------------
        self.execute_marketing(day)

        # ---- customer lifecycle ------------------------------------------
        self.process_customers(day)

        # ---- sales pipeline ----------------------------------------------
        self.advance_pipeline(day)

        # ---- incidents & support -----------------------------------------
        self.roll_incidents(day)
        self.resolve_support(day)

        # ---- finance settlement -------------------------------------------
        self.settle_finance(day)

        # ---- investors -----------------------------------------------------
        if day % 30 == 10 and not getattr(c, "_pending_term_sheet", None):
            sheet = maybe_term_sheet(c, view, self.sim_rng)
            if sheet:
                c._pending_term_sheet = sheet
                c.company_event(day, "term_sheet",
                                f"{sheet['firm']}: \u20b9{sheet['amount']:,.0f} @ "
                                f"\u20b9{sheet['post_money']:,.0f} post")

        # ---- book-keeping ---------------------------------------------------
        c.current_mrr = self._mrr_book
        self._market_births(day)
        self.snapshot(day)
        self.evaluate_due_decisions(day)
        self.check_bankruptcy(day)

    def _market_births(self, day):
        """New businesses enter the market as the economy grows."""
        blended_growth = sum(s["demand_growth_yr"] for s in SEGMENTS.values()) / len(SEGMENTS)
        expected = self.pool.total_size * blended_growth / 365.0
        self._birth_frac = getattr(self, "_birth_frac", 0.0) + expected
        n = int(self._birth_frac)
        if n > 0:
            self._birth_frac -= n
            self.pool.birth_customers(n)

    # ========================================================== competitors ==
    def _spawn_competitor(self, day):
        r = self.sim_rng
        names = ["ZorroBiz", "VyaparX", "DhandhaHQ", "SetuFlow", "LedgerLion"]
        taken = {c_.name for c_ in self.competitors}
        avail = [n for n in names if n not in taken] or [f"Rival{len(self.competitors)}"]
        name = avail[0]
        comp = Competitor(cid=name.lower(), name=name,
                          archetype=r.choice(list(["discount_disruptor", "marketing_blitzer"])),
                          features={"core_billing", "inventory_basic", "payments_upi"},
                          quality=r.uniform(0.45, 0.6), price_mult=r.uniform(0.7, 0.95),
                          brand=0.30, customers=int(r.uniform(60, 140)),
                          mrr=r.uniform(120_000, 300_000), entry_day=day)
        self.competitors.append(comp)
        self.company.company_event(day, "competitor_entry",
                                   f"{name} entered with aggressive pricing", name=name)

    def _competitor_monthly(self, day):
        c = self.company
        total_universe = sum(cp.customers for cp in self.competitors) + len(c.active_ids) + 1
        our_share = len(c.active_ids) / max(total_universe, 1)
        # dominance provokes coordination: rivals adapt harder when we lead big
        leader_pressure = max(0.0, our_share - 0.40) / 0.60
        if leader_pressure > 0 and self.sim_rng.random() < 0.10 + leader_pressure * 0.3 \
                and not any(s.kind == "trust_backlash" for s in self.market.shocks):
            dur = self.sim_rng.randint(90, 200)
            mag = self.sim_rng.uniform(0.10, 0.22)
            from .market import ActiveShock
            self.market.shocks.append(ActiveShock(
                "Incumbent backlash vs leader", "trust_backlash", None,
                day + dur, mag,
                "Incumbents warn the market about the dominant newcomer; buyers hedge."))
            self.market.event_log.append(self.market.event_log[-1].__class__(
                day, "Incumbent backlash vs leader",
                "Market sentiment turns wary of the category leader.", mag))
            c.finance.record(day, "legal_compliance", 25_000, "dominance scrutiny filings")
            c.company_event(day, "backlash", "Market leader scrutiny: trust penalty active")
        our_value = (c.product.quality + 0.5 * c.marketing.brand_awareness
                     + 0.3 * max(0.0, 1.15 - c.product.price_mult))
        exited = []
        for cp in self.competitors:
            prev_share = getattr(cp, "_prev_share", None)
            share_now = cp.customers / max(total_universe, 1)
            share_lost = (prev_share is not None and share_now < prev_share * 0.995) \
                or leader_pressure > 0
            cp._prev_share = share_now
            note = cp.monthly_update(self.rng.stream("comp_ai"), share_lost, day)
            # zero-sum-ish flow: market growth minus what we take from them;
            # under leader pressure rivals also consolidate dissatisfied defectors
            comp_value = (cp.quality + 0.5 * cp.brand
                          + 0.3 * max(0.0, 1.15 - cp.price_mult))
            advantage = clamp((comp_value - our_value) * 2.2, -1.8, 1.8)
            seg_growth_mo = sum(s["demand_growth_yr"] for s in SEGMENTS.values()) / len(SEGMENTS) / 12.0
            g = seg_growth_mo + 0.035 * math.tanh(advantage) \
                + 0.010 * leader_pressure + self.sim_rng.gauss(0.0, 0.014)
            cp.customers = max(20, int(cp.customers * (1 + g)))
            cp.mrr = cp.customers * 1900.0 * cp.price_mult
            if note == "exit":
                exited.append(cp)
        for cp in exited:
            # their base scatters to remaining rivals (universe is conserved)
            others = [x for x in self.competitors if x is not cp]
            if others:
                per = cp.customers // len(others)
                for o in others:
                    o.customers += per
                    o.mrr += per * 1900.0 * o.price_mult
            self.competitors.remove(cp)
            self.company.company_event(
                day, "competitor_exit",
                f"{cp.name} shut down (burned out); its customers scatter to rivals",
                name=cp.name)

    def build_market_view(self) -> MarketView:
        c = self.company
        news = [e.note for e in self.market.event_log[-3:]] if self.market.event_log else []
        demand_proxy = {}
        counts: dict[str, int] = {}
        for cid in self.pool.ids_in_state(STATE_SHOPPING):
            cust = self.pool.get(cid)
            counts[cust.segment] = counts.get(cust.segment, 0) + 1
        tot = sum(counts.values()) or 1
        for seg, n in counts.items():
            demand_proxy[seg] = round(n / tot, 3)
        return MarketView(
            day=c.day, month=self.market.month_of(c.day),
            competitor_prices={cp.name: round(cp.price_mult, 2) for cp in self.competitors},
            competitor_brands={cp.name: round(clamp(cp.brand + self.sim_rng.uniform(-0.08, 0.08), 0, 1), 2)
                               for cp in self.competitors},
            our_brand=round(c.marketing.brand_awareness, 3),
            market_news=news,
            demand_proxy=demand_proxy,
        )

    # ============================================================== actions ==
    def execute_actions(self, actions):
        c = self.company
        fin = c.finance
        for a in actions:
            t = a["type"]
            if t == "set_marketing":
                if a.get("mode") == "survival":
                    self.mkt_daily_budget = min(self.mkt_daily_budget, max(150.0, c.current_mrr / 300.0))
                else:
                    self.mkt_daily_budget = float(a.get("daily_budget", self.mkt_daily_budget))
                    alloc = a.get("allocation")
                    if alloc:
                        s = sum(alloc.values()) or 1.0
                        self.mkt_alloc = {k: alloc.get(k, 0.0) / s for k in self.mkt_alloc}
            elif t == "set_price_mult":
                c.product.price_mult = clamp(float(a["mult"]), 0.70, 1.45)
            elif t == "set_tier_price":
                ti = int(a["tier"]); c.product.tier_prices[ti] = max(49.0, float(a["price"]))
            elif t == "set_eng_alloc":
                f_, q_, d_ = a["features"], a["quality"], a["debt"]
                norm = max(f_ + q_ + d_, 1e-6)
                c.engineering.alloc_features, c.engineering.alloc_quality, c.engineering.alloc_debt = \
                    f_ / norm, q_ / norm, d_ / norm
            elif t == "pin_feature":
                c.pinned_feature = a["feature"]
            elif t == "hire":
                role, n = a["role"], int(a["n"])
                fee = c.hire_cost(role) * n
                if fin.cash >= fee + 20_000 or True:
                    fin.record(c.day, "recruiting", fee, f"hire {role}")
                    notice = {"support": 10}.get(role, 21)
                    for i in range(n):
                        c.team.hiring_in_progress.append([c.day + notice, role])
                    c.company_event(c.day, "hire_started", f"{n}x {role} (joins in {notice}d)", role=role)
            elif t == "hire_sales":
                role, n = a["role"], int(a["n"])
                fee = c.hire_cost(role) * n
                fin.record(c.day, "recruiting", fee, f"hire {role}")
                for i in range(n):
                    c.team.hiring_in_progress.append([c.day + 21, role])
                c.company_event(c.day, "hire_started", f"{n}x {role} (joins in 21d)", role=role)
            elif t == "fire":
                role, n = a["role"], int(a["n"])
                have = c.team.count(role)
                n = min(n, have)
                if n > 0:
                    c.team.headcount[role] -= n
                    sev = c.severance_cost(role) * n
                    fin.record(c.day, "severance", sev, f"severance {role}")
                    c.sales.reps = [r for r in c.sales.reps if not (r.role == role)] \
                        if role in ("account_exec", "sd_r") else c.sales.reps
                    c.company_event(c.day, "layoff", f"{n}x {role} let go", role=role)
            elif t == "founder_draw":
                c.founder_draw_monthly = float(a.get("monthly", 0))
            elif t == "accept_term_sheet":
                sh = getattr(c, "_pending_term_sheet", None)
                if sh:
                    fin.raise_equity(c.day, sh["amount"], sh["dilution"], sh["post_money"])
                    c.company_event(c.day, "funding_closed",
                                    f"Raised \u20b9{sh['amount']:,.0f} from {sh['firm']} "
                                    f"@ \u20b9{sh['post_money']:,.0f} post "
                                    f"(diluted {sh['dilution']:.1%})",
                                    amount=sh["amount"], post_money=sh["post_money"])
                    c._pending_term_sheet = None
            elif t == "reject_term_sheet":
                sh = getattr(c, "_pending_term_sheet", None)
                if sh:
                    c.company_event(c.day, "funding_declined",
                                    f"Declined {sh['firm']}'s \u20b9{sh['amount']:,.0f} sheet")
                    c._pending_term_sheet = None
            elif t == "focus_segments":
                c.focus_segments = list(a["segments"])

        # onboarding queue: hires become productive
        still = []
        for item in c.team.hiring_in_progress:
            due, role = item
            if c.day >= due:
                c.team.headcount[role] = c.team.headcount.get(role, 0) + 1
                if role in ("account_exec", "sd_r"):
                    from .sales import SalesRep
                    c.sales.reps.append(SalesRep(rid=len(c.sales.reps) + 1, role=role,
                                                 hired_day=c.day))
                c.company_event(c.day, "joined", f"{role} joined the team", role=role)
            else:
                still.append(item)
        c.team.hiring_in_progress = still

    # ============================================================= marketing ==
    def _build_lead_buckets(self) -> dict:
        """Once-per-day candidate buckets for lead realization."""
        day = self.company.day
        buckets: dict[tuple, list] = {}
        for seg in SEGMENTS:
            dorm = [cid for cid in self.pool.seg_bucket(seg, STATE_DORMANT)
                    if self.pool.get(cid).cooldown_until <= day]
            chn = [cid for cid in self.pool.seg_bucket(seg, STATE_CHURNED)
                   if self.pool.get(cid).cooldown_until <= day]
            if dorm:
                buckets[("dormant", seg)] = dorm
            if chn:
                buckets[("churned", seg)] = chn
        return buckets

    def execute_marketing(self, day):
        c = self.company
        budget = self.mkt_daily_budget
        total_spend = 0.0
        focus = set(getattr(c, "focus_segments", None) or SEGMENTS.keys())
        buckets = self._build_lead_buckets()

        for ch_key, st in c.marketing.channels.items():
            share = self.mkt_alloc.get(ch_key, 0.0)
            spend = budget * share
            if spend <= 1.0:
                st.spend_today = 0.0
                continue
            spec = CHANNELS[ch_key]
            mix_q = sum(spec["seg_affinity"].get(s, 0.2) *
                        (1.4 if s in focus else 1.0) for s in SEGMENTS) / len(SEGMENTS)
            leads = c.marketing.leads_from_spend(ch_key, spend, self.market, mix_q)
            realized = self.realize_leads(ch_key, leads, focus, buckets)
            c.marketing.record_results(ch_key, spend, realized)
            c.finance.record(day, "marketing", spend, ch_key)
            total_spend += spend
            st.leads_trailing30 = 0.93 * st.leads_trailing30 + 0.07 * (realized * 30)
            st.spend_trailing30 = 0.93 * st.spend_trailing30 + 0.07 * (spend * 30)
        c.marketing.update_brand(total_spend)
        c._mkt_spend_trailing = total_spend * 30.0

    def realize_leads(self, ch_key: str, expected_leads: float, focus,
                      buckets: dict) -> int:
        """Convert expected lead count into pool members flipping to shopping.

        Bucket-based sampling: choose (kind, segment) proportional to aggregate
        affinity x availability, then a uniform member - O(leads), not O(pool).
        """
        if expected_leads <= 0.001 or not buckets:
            return 0
        r = self.sim_rng
        n_full = int(expected_leads)
        frac = expected_leads - n_full
        count = n_full + (1 if r.random() < frac else 0)
        spec = CHANNELS[ch_key]

        options = []
        weights = []
        for key, ids in buckets.items():
            kind, seg = key
            aff = spec["seg_affinity"].get(seg, 0.15)
            if seg in focus:
                aff *= 1.5
            w = len(ids) * aff * (0.35 if kind == "churned" else 1.0)
            if w > 0:
                options.append(ids)
                weights.append(w)
        if not options:
            return 0

        made = 0
        today = self.company.day
        for _ in range(count):
            idx = r.choices(range(len(options)), weights=weights, k=1)[0]
            ids = options[idx]
            cid = ids[r.randrange(len(ids))]
            cust = self.pool.get(cid)
            if cust.state not in (STATE_DORMANT, STATE_CHURNED) \
                    or cust.cooldown_until > today:
                # small retry within same bucket
                tries = 0
                while tries < 3 and (cust.state not in (STATE_DORMANT, STATE_CHURNED)
                                     or cust.cooldown_until > today):
                    cid = ids[r.randrange(len(ids))]
                    cust = self.pool.get(cid)
                    tries += 1
                if cust.state not in (STATE_DORMANT, STATE_CHURNED) \
                        or cust.cooldown_until > today:
                    continue
            cust.source = ch_key
            cust.awareness = clamp(max(cust.awareness, 0.55 + r.random() * 0.3), 0, 1)
            cust.shopping_since = today
            cust.cooldown_until = 0
            self.pool.transition(cust, STATE_SHOPPING)
            made += 1
        return made

    # ============================================================ customers ==
    def our_offer(self) -> Offer:
        c = self.company
        return Offer(vendor_id="us", name=c.name, features=set(c.product.features),
                     quality=c.product.quality, brand=c.marketing.brand_awareness,
                     tier_prices=c.product.effective_prices,
                     support_quality=c.ops.csat)

    def competitor_offers(self) -> dict[str, Offer]:
        out = {}
        ref = [499.0, 1999.0, 5999.0, 49999.0]
        ftiers = {f: meta["tier"] for f, meta in FEATURES.items()}
        for cp in self.competitors:
            out[cp.cid] = Offer(vendor_id=cp.cid, name=cp.name,
                                features=set(cp.features), quality=cp.quality,
                                brand=cp.brand,
                                tier_prices=[p * cp.price_mult for p in ref],
                                support_quality=0.55 + cp.quality * 0.25)
        return out

    def process_customers(self, day):
        c = self.company
        offer = self.our_offer()
        comps = self.competitor_offers()
        ftiers = c.product.feature_tiers
        r = self.sim_rng
        brand = c.marketing.brand_awareness
        new_today = 0
        churn_today = 0
        referrals = 0

        # --- organic demand: segment-level Poisson flips (fast path) ------
        for seg, spec in SEGMENTS.items():
            bucket = self.pool.seg_bucket(seg, STATE_DORMANT)
            n_dorm = len(bucket)
            if n_dorm == 0:
                continue
            p_day = self.market.monthly_shopping_rate(seg) * (0.35 + 1.3 * brand) * 2.2
            mean = n_dorm * p_day
            if mean < 1e-6:
                continue
            u1, u2 = _hash_uniforms(self.cfg.seed, "orgflip", seg, day)
            z = math.sqrt(-2.0 * math.log(max(u1, 1e-12))) * math.cos(2 * math.pi * u2)
            sd = math.sqrt(n_dorm * p_day * max(1e-9, 1 - p_day))
            k = int(round(mean + z * sd))
            k = max(0, min(k, n_dorm))
            if k == 0:
                continue
            elig = [cid for cid in bucket
                    if self.pool.get(cid).cooldown_until <= day]
            if not elig:
                continue
            for cid in r.sample(elig, min(k, len(elig))):
                cust = self.pool.get(cid)
                cust.source = "organic"
                cust.shopping_since = day
                self.pool.transition(cust, STATE_SHOPPING)

        # --- shopping evaluations ----------------------------------------
        for cid in list(self.pool.ids_in_state(STATE_SHOPPING)):
            cust = self.pool.get(cid)
            delay = 2 if SEGMENTS[cust.segment]["sales_mode"] == "self_serve" else 3
            if day - cust.shopping_since < delay:
                continue
            lam = self.market.price_sensitivity_multiplier(cust.segment)
            util_us, tier = evaluate_offer(
                cust, offer, ftiers, price_mult=1.0, lam=lam,
                challenger_penalty=0.30 + self.market.backlash_penalty())
            considered = [("us", util_us, tier)]
            brand_weights = [cp.brand for cp in self.competitors] or [1.0]
            k = min(len(self.competitors), 2)
            picked_idx = set()
            for _ in range(k):
                try:
                    idx = r.choices(range(len(self.competitors)), weights=brand_weights, k=1)[0]
                except IndexError:
                    break
                if idx in picked_idx:
                    continue
                picked_idx.add(idx)
                cp = self.competitors[idx]
                coffer = comps[cp.cid]
                u, t = evaluate_offer(cust, coffer, ftiers, lam=lam)
                considered.append((cp.cid, u, t))
            best_vendor, best_util, best_tier = max(considered, key=lambda x: x[1])

            won = best_vendor == "us" and choice_probability(best_util) > r.random()
            c.eval_events.append((day, won))
            if len(c.eval_events) > 600:
                del c.eval_events[:200]

            if won:
                mode = SEGMENTS[cust.segment]["sales_mode"]
                cust.vendor = "us"; cust.tier = best_tier
                cust.monthly_fee = c.product.effective_prices[best_tier]
                cust.last_eval_day = day
                if mode == "sales_led" or (mode == "hybrid" and r.random() < 0.45):
                    cyc = SEGMENTS[cust.segment]["cycle_days"]
                    d = c.sales.add_deal(cust.cid, cust.segment, best_tier,
                                         cust.monthly_fee, day,
                                         r.randint(*cyc))
                    cust.cooldown_until = day + 45     # patience window
                else:
                    cust.trial_end_day = day + SEGMENTS[cust.segment]["trial_days"]
                    self.pool.transition(cust, STATE_TRIAL)
            else:
                lost_to = best_vendor
                cust.cooldown_until = day + r.randint(25, 60)
                cust.awareness *= 0.8
                self.pool.transition(cust, STATE_DORMANT)

        # --- trials resolving --------------------------------------------
        for cid in list(self.pool.ids_in_state(STATE_TRIAL)):
            cust = self.pool.get(cid)
            fitv = _fit(cust, offer.features)
            if day < cust.trial_end_day:
                cust.satisfaction = clamp(0.30 + 0.45 * fitv + 0.25 * offer.quality
                                          - max(0.0, cust.monthly_fee / max(cust.budget, 1) - 0.8) * 0.3,
                                          0.05, 0.98)
                continue
            fitv = _fit(cust, offer.features)
            price_ratio = cust.monthly_fee / max(cust.budget, 50.0)
            p_conv = clamp(TRIAL_BASE_CONV + 0.55 * fitv * (0.4 + 0.6 * offer.quality)
                           + 0.15 * (offer.support_quality - 0.5)
                           - max(0.0, price_ratio - 0.85) * 0.35, 0.03, 0.93)
            if r.random() < p_conv:
                self.activate_customer(cust, day)
                new_today += 1
            else:
                cust.cooldown_until = day + r.randint(40, 90)
                self.pool.transition(cust, STATE_DORMANT)

        # --- actives: renewal / churn / expansion (event-driven) ----------
        due = self._renewals_due.pop(day, None) or set()
        for cid in list(due):
            cust = self.pool.get(cid)
            if cust.state != STATE_ACTIVE:
                continue
            fee = cust.monthly_fee
            c.finance.record(day, "subscription", fee, f"renewal c{cust.cid}")
            c.finance.record(day, "payment_fees", fee * PAYMENT_GATEWAY_RATE, "")
            cust.total_paid += fee
            cust.months_paid += 1

            # satisfaction recomputed from equilibrium minus incident damage
            eq = self.satisfaction_equilibrium(cust, offer)
            penalty = 0.10 * min(cust.incidents_experienced, 4)
            cust.satisfaction = clamp(eq - penalty, 0.02, 0.99)

            hazard = self.churn_hazard(cust, offer, comps, ftiers)
            cust.churn_prob_est = hazard
            if r.random() < hazard:
                self.pool.transition(cust, STATE_CHURNED)
                cust.vendor = ""
                c.active_ids.discard(cid)
                self._mrr_book -= fee
                churn_today += 1
                seg_list = c._churn_by_seg.setdefault(cust.segment, [])
                seg_list.append(day)
                if len(seg_list) > 200:
                    del seg_list[:100]
                continue
            # expansion: happy customers upgrade tier (NRR > 100%)
            if cust.satisfaction > 0.68 and r.random() < 0.02 and cust.tier < 2:
                nt = cust.tier + 1
                req = min_required_tier_expansion(cust, ftiers, nt)
                if req <= nt:
                    old_fee = cust.monthly_fee
                    cust.tier = nt
                    cust.monthly_fee = c.product.effective_prices[nt]
                    self._mrr_book += cust.monthly_fee - old_fee
                    c.company_event(day, "expansion",
                                    f"c{cust.cid} upgraded to {TIER_NAMES[nt]}")
            cust.incidents_experienced = 0
            cust.renewal_due_day = day + 30
            self._renewals_due.setdefault(day + 30, set()).add(cid)

        # --- WOM referrals: segment-level draws ----------------------------
        if c.strategy.referral_enabled:
            for seg in SEGMENTS:
                n_active_seg = sum(1 for cid in c.active_ids
                                   if self.pool.get(cid).segment == seg)
                if n_active_seg < 5:
                    continue
                mean = n_active_seg * 0.45 * 0.0026
                u1, u2 = _hash_uniforms(self.cfg.seed, "wom", seg, day)
                z = math.sqrt(-2.0 * math.log(max(u1, 1e-12))) * math.cos(2 * math.pi * u2)
                k = int(round(mean + z * math.sqrt(mean)))
                k = max(0, min(k, 25))
                if k == 0:
                    continue
                elig = [cid for cid in self.pool.seg_bucket(seg, STATE_DORMANT)
                        if self.pool.get(cid).cooldown_until <= day]
                if not elig:
                    continue
                for tgt_id in r.sample(elig, min(k, len(elig))):
                    tgt = self.pool.get(tgt_id)
                    tgt.source = "referral"
                    tgt.awareness = clamp(tgt.awareness + 0.35, 0, 1)
                    tgt.shopping_since = day
                    self.pool.transition(tgt, STATE_SHOPPING)
                    referrals += 1
        self.new_customers_window.append((day, new_today))
        self.churned_window.append((day, churn_today))
        self._today_new, self._today_churn, self._today_referrals = new_today, churn_today, referrals

    def activate_customer(self, cust: Customer, day: int):
        c = self.company
        self.pool.transition(cust, STATE_ACTIVE)
        cust.start_day = day
        cust.renewal_due_day = day + 30
        cust.months_paid = 0
        c.active_ids.add(cust.cid)
        self._mrr_book += cust.monthly_fee
        self._renewals_due.setdefault(day + 30, set()).add(cust.cid)
        c.finance.record(day, "subscription", cust.monthly_fee, f"signup c{cust.cid}")
        c.finance.record(day, "payment_fees", cust.monthly_fee * PAYMENT_GATEWAY_RATE, "")
        cust.total_paid += cust.monthly_fee
        src = cust.source or "organic"
        conv_log = c.channel_conversions.setdefault(src, [])
        conv_log.append((day, 1))
        if len(conv_log) > 500:
            del conv_log[:250]

    def satisfaction_equilibrium(self, cust: Customer, offer: Offer) -> float:
        fitv = _fit(cust, offer.features)
        fairness = clamp(cust.budget / max(cust.monthly_fee, 1.0), 0.4, 1.6)
        eq = (0.16 + 0.34 * fitv + 0.22 * offer.quality
              + 0.14 * offer.support_quality + 0.14 * (fairness - 0.4) / 1.2)
        if cust.incidents_experienced > 0:
            eq -= 0.04 * min(cust.incidents_experienced, 4)
        return clamp(eq, 0.05, 0.97)

    def churn_hazard(self, cust: Customer, offer: Offer, comps, ftiers) -> float:
        sat = cust.satisfaction
        base = 0.068
        if sat >= 0.75:
            base *= 0.35
        elif sat >= 0.55:
            base *= 1.0
        elif sat < 0.35:
            base *= 3.2
        # competitor poach pressure at renewal
        lam = self.market.price_sensitivity_multiplier(cust.segment)
        my_u, _ = evaluate_offer(cust, offer, ftiers, lam=lam)
        best_comp_u = None
        for o in comps.values():
            if o.vendor_id == cust.vendor:
                continue
            u, _ = evaluate_offer(cust, o, ftiers, lam=lam)
            best_comp_u = u if best_comp_u is None else max(best_comp_u, u)
        if best_comp_u is not None and best_comp_u - my_u > 0.25:
            base *= 1.9
        # price fairness
        if cust.monthly_fee > cust.budget * 1.05:
            base *= 1.5
        return clamp(base, 0.004, 0.65)

    # ================================================================ sales ==
    def advance_pipeline(self, day):
        c = self.company
        c.sales.assign_reps(self.sales_rng)
        for d in list(c.sales.deals.values()):
            if d.stage in ("won", "lost"):
                continue
            cust = self.pool.get(d.cid)
            if cust.state != STATE_SHOPPING:
                # lead evaporated (shouldn't happen often); close as lost
                d.stage, d.lost_reason = "lost", "lead vanished"
                continue
            if day >= d.close_due_day:
                rep = next((r for r in c.sales.reps if r.rid == d.rep_id), None)
                if rep is None:
                    if day >= d.close_due_day + 7:
                        d.stage, d.lost_reason = "lost", "no AE capacity"
                        cust.cooldown_until = day + 40
                        self.pool.transition(cust, STATE_DORMANT)
                    continue
                fitv = _fit(cust, c.product.features)
                price_ratio = d.mrr_value / max(cust.budget, 50.0)
                p_win = clamp((0.30 + 0.25 * rep.skill) * rep.productivity()
                              * (0.55 + 0.45 * fitv) * (1.15 - max(0.0, price_ratio - 0.8)),
                              0.04, 0.92)
                if self.sales_rng.random() < p_win:
                    d.stage = "won"
                    cust.tier = d.tier
                    cust.monthly_fee = d.mrr_value
                    self.activate_customer(cust, day)
                    comm = d.mrr_value * 12 * COMMISSION_RATE
                    c.finance.record(day, "commission", comm, f"deal d{d.did}")
                    self.closed_won_window.append(day)
                else:
                    d.stage, d.lost_reason = "lost", "lost deal"
                    cust.cooldown_until = day + 50
                    self.pool.transition(cust, STATE_DORMANT)
                cust.last_eval_day = day
        # prune old closed deals
        if len(c.sales.deals) > 800:
            done = [did for did, dd in c.sales.deals.items() if dd.stage in ("won", "lost")]
            for did in done[: len(done) // 2]:
                del c.sales.deals[did]

    # ================================================ incidents & support ====
    def roll_incidents(self, day):
        c = self.company
        p = c.product.incident_probability_daily(len(c.active_ids))
        if p > 0 and self.sim_rng.random() < p:
            actives = list(c.active_ids)
            n_aff = max(1, int(len(actives) * self.sim_rng.uniform(0.03, 0.12))) if actives else 0
            affected = self.sim_rng.sample(actives, min(n_aff, len(actives)))
            for cid in affected:
                cust = self.pool.get(cid)
                cust.satisfaction = clamp(cust.satisfaction - 0.10, 0.02, 0.99)
                cust.incidents_experienced += 1
            c.ops.tickets_open += max(1, int(n_aff * 0.4))
            c.ops.incidents_30d = min(30, c.ops.incidents_30d + 1)
            c.company_event(day, "incident",
                            f"Outage affected {n_aff} customers; tickets +{max(1,int(n_aff*0.4))}")

    def resolve_support(self, day):
        c = self.company
        founder_helps = c.team.total() <= 3
        cap = c.ops.resolution_capacity_daily(c.support_headcount(), founder_supporting=founder_helps)
        # organic ticket inflow scales with the installed base
        expected = len(c.active_ids) * 0.010
        opened = int(expected)
        if self.sim_rng.random() < (expected - opened):
            opened += 1
        c.ops.tickets_open += opened
        resolved = min(c.ops.tickets_open, cap)
        c.ops.tickets_open -= resolved
        backlog_days = c.ops.tickets_open / max(cap, 1)
        target_csat = clamp(0.80 + 0.12 * c.product.quality - 0.10 * min(backlog_days, 2.5), 0.25, 0.95)
        c.ops.csat += 0.10 * (target_csat - c.ops.csat)
        if day % 30 == 0:
            c.ops.incidents_30d = int(c.ops.incidents_30d * 0.5)

    # =============================================================== finance ==
    def settle_finance(self, day):
        if len(self.closed_won_window) > 2000:
            del self.closed_won_window[:1000]
        c = self.company
        fin = c.finance
        n_active = len(c.active_ids)
        fin.record(day, "infra", n_active * INFRA_COST_PER_ACCOUNT / 30.0, "cloud+sms")
        tools = BASE_MONTHLY_TOOLS / 30.0 + 900.0 * max(0, c.team.total() - 1) / 30.0
        fin.record(day, "tools", tools, "saas stack")
        if day % 30 == 1:
            bill = c.team.monthly_bill()
            if bill > 0:
                fin.record(day, "salaries", bill, "payroll")
            draw = getattr(c, "founder_draw_monthly", 0)
            if draw > 0:
                fin.record(day, "founder_draw", draw, "founder salary")
        if day % 90 == 5:
            fin.record(day, "legal_compliance", 4_000, "quarterly ROC/GST filings")
        self.points_shipped_window.append((day, c.engineering.points_shipped_today))

    # =============================================================== metrics ==
    def compute_mrr(self) -> float:
        c = self.company
        return sum(self.pool.get(cid).monthly_fee for cid in c.active_ids)

    def snapshot(self, day):
        c = self.company
        h = c.history
        rev30 = abs(c.finance.sum_category("subscription", day - 30, day))
        mkt30 = abs(c.finance.sum_category("marketing", day - 30, day))
        sal30 = abs(c.finance.sum_category("salaries", day - 30, day)) \
            + abs(c.finance.sum_category("commission", day - 30, day)) \
            + abs(c.finance.sum_category("founder_draw", day - 30, day))
        other30 = abs(c.finance.sum_category("tools", day - 30, day)) \
            + abs(c.finance.sum_category("infra", day - 30, day)) \
            + abs(c.finance.sum_category("payment_fees", day - 30, day)) \
            + abs(c.finance.sum_category("recruiting", day - 30, day)) \
            + abs(c.finance.sum_category("severance", day - 30, day)) \
            + abs(c.finance.sum_category("legal_compliance", day - 30, day))
        new30 = sum(n for _, n in list(self.new_customers_window)[-30:]) or 0
        churn30 = sum(n for _, n in list(self.churned_window)[-30:]) or 0
        base_prev = h[-31]["active_customers"] if len(h) >= 31 else max(new30 + churn30, 1)
        logo_churn_pct = (churn30 / max(base_prev, 1)) * 100.0
        cac = mkt30 / max(new30, 1) if new30 >= 1 else 0.0
        mrr = c.current_mrr
        arpu = mrr / max(len(c.active_ids), 1)
        cogs30 = abs(c.finance.sum_category("payment_fees", day - 30, day)) \
            + abs(c.finance.sum_category("infra", day - 30, day))
        # ledger is the single source of truth for recognized revenue
        rev_total30 = abs(c.finance.sum_category("subscription", day - 30, day))
        gross_margin = clamp(1.0 - cogs30 / max(rev_total30, 1.0), 0.05, 0.98)
        churn_rate_monthly = clamp(churn30 / max(len(c.active_ids) + churn30, 1), 0.001, 0.9)
        # LTV is only meaningful once there is churn signal and a real base
        if len(c.active_ids) >= 20 and churn30 >= 2:
            ltv = arpu * gross_margin / churn_rate_monthly
        else:
            ltv = None
        opex30 = mkt30 + sal30 + other30
        net_burn30 = opex30 - rev_total30
        runway = FinanceEngine.compute_runway(c.finance.cash, net_burn30)
        growth_ann = self._annualized_growth()
        # equity value = operating value + cash held (EV + net cash)
        valuation = (FinanceEngine.valuation_proxy(mrr * 12, growth_ann, gross_margin,
                                                   logo_churn_pct)
                     + max(c.finance.cash, 0.0))
        universe_mrr = sum(cp.mrr for cp in self.competitors) + mrr
        share = (mrr / universe_mrr * 100.0) if universe_mrr > 0 else 0.0
        leads30 = sum(st.leads_trailing30 for st in c.marketing.channels.values())
        snap = dict(
            day=day, date_label=self.market.date_label(day),
            cash=c.finance.cash, mrr=mrr, arr=mrr * 12,
            active_customers=len(c.active_ids),
            new_customers_today=self._today_new, churned_today=self._today_churn,
            revenue_recognized_mtd=rev_total30 / 30.0,
            opex_mtd=opex30 / 30.0,
            net_income_mtd=(rev_total30 - opex30) / 30.0,
            gross_margin_pct=gross_margin * 100.0,
            cac_blended=cac, ltv=ltv if ltv is not None else 0.0,
            ltv_cac=(ltv / cac if (ltv and cac > 0) else None),
            payback_months=(cac / max(arpu * gross_margin, 1e-9)),
            logo_churn_pct_monthly=logo_churn_pct,
            net_revenue_retention_pct=100.0 + self._nrr_delta(),
            runway_months=min(runway, 99.0),
            valuation_proxy=valuation,
            market_share_pct=share,
            headcount=c.team.total(),
            brand_awareness=c.marketing.brand_awareness,
            pipeline_value=sum(dd.mrr_value for dd in c.sales.deals.values()
                               if dd.stage not in ("won", "lost")),
            leads_trailing30=int(leads30),
        )
        h.append(snap)

    def _annualized_growth(self) -> float:
        h = self.company.history
        if len(h) < 91 or h[-91]["mrr"] <= 0:
            return 0.0
        g90 = (h[-1]["mrr"] - h[-91]["mrr"]) / max(h[-91]["mrr"], 1.0)
        return g90 * 4.0

    def _nrr_delta(self) -> float:
        c = self.company
        ups = sum(1 for e in c.company_events if e["kind"] == "expansion"
                  and e["day"] >= c.day - 30)
        return ups * 1.2

    # ==================================================== decision evaluation =
    def _capture_eval_baselines(self):
        c = self.company
        for d in reversed(c.decision_log[-8:]):
            if d.get("_eval_metric") and "_eval_baseline" not in d:
                v = self._metric_value(d["_eval_metric"])
                if isinstance(v, (int, float)):
                    d["_eval_baseline"] = float(v)

    def evaluate_due_decisions(self, day):
        c = self.company
        for d in c.decision_log:
            if d.get("verdict") is not None or not d.get("_eval_metric"):
                continue
            if day < d.get("eval_due_day", 10 ** 9):
                continue
            metric = d["_eval_metric"]
            direction = d.get("_eval_direction", "up")
            mag = float(d.get("_eval_magnitude", 0.0) or 0.0)
            base = d.pop("_eval_baseline", None)
            cur = self._metric_value(metric)
            d.pop("_eval_metric", None)
            if not isinstance(cur, (int, float)) or base is None:
                d["verdict"] = "untracked"
                d["actual"] = {"metric": metric}
                continue
            delta = float(cur) - base
            hit = abs(mag)
            if direction == "down":
                moved, full = (-delta), (-mag)
            else:
                moved, full = delta, mag
            threshold = max(full * 0.5, 1e-9)
            if moved >= threshold:
                verdict = "success"
            elif moved > 0:
                verdict = "partial"
            else:
                verdict = "fail"
            d["verdict"] = verdict
            d["actual"] = {"metric": metric, "baseline": round(base, 4),
                           "value_at_eval": round(float(cur), 4),
                           "delta": round(delta, 4),
                           "expected_magnitude": round(mag, 4)}
            if verdict == "fail":
                d["lesson"] = self._auto_lesson(d)

    def _metric_value(self, key: str):
        c = self.company
        h = c.history
        mapping = {
            "runway": lambda: self._kpis_safe("runway"),
            "cash": lambda: c.finance.cash,
            "mrr": lambda: c.current_mrr,
            "cac_blended": lambda: (h[-1]["cac_blended"] if h else 0.0),
            "csat": lambda: c.ops.csat,
            "points_shipped_30d": lambda: sum(v for _, v in list(self.points_shipped_window)[-30:]),
            "closed_won_30d": lambda: len([d0 for d0 in self.closed_won_window if d0 >= c.day - 30]),
            "roi_mrr_per_rupee": lambda: getattr(c, "_last_roi", 0.0),
            "eval_win_rate": lambda: c.recent_eval_win_rate(21),
            "growth_mom": lambda: self._kpis_safe("growth_mom"),
            "churn_pct": lambda: (h[-1]["logo_churn_pct_monthly"] if h else 0.0),
        }
        fn = mapping.get(key)
        return fn() if fn else None

    def _kpis_safe(self, key):
        k = self.agents.kpis()
        return k.get(key, 0.0)

    def _auto_lesson(self, d: dict) -> str:
        kind = d.get("kind", "")
        lessons = {
            "marketing_plan": "Channel CAC ran above target; reallocate toward measured winners before raising spend.",
            "pricing_test_start": "Price move hurt conversion more than modeled; elasticity prior was too optimistic.",
            "hire": "Hire did not produce the expected capacity/output within horizon; check ramp assumptions and workload.",
            "fundraise": "Fundraise did not translate into expected value creation within window.",
            "layoff": "Cost cut did not extend runway as much as projected; fixed costs dominate.",
            "segment_focus": "Segment focus did not lower CAC; fit assumption wrong or channels misaligned.",
            "risk_appetite_update": "Spend adjustment did not improve ROI; unit economics may be capped.",
        }
        return lessons.get(kind, "Expected effect did not materialize; revisit assumptions.")

    # ============================================================ bankruptcy ==
    def check_bankruptcy(self, day):
        c = self.company
        if c.finance.cash < -50_000:
            c.alive = False
            c.death_reason = (f"Insolvent on day {day}: cash {fmt_inr(c.finance.cash)}. "
                              f"MRR was {fmt_inr(c.current_mrr)} with "
                              f"{len(c.active_ids)} customers.")
            c.company_event(day, "bankruptcy", c.death_reason)


# ---------------------------------------------------------------- helpers -----
def _hash_uniforms(seed: int, *parts) -> tuple[float, float]:
    """Two independent uniforms derived deterministically from inputs."""
    import hashlib
    key = f"{seed}:{':'.join(map(str, parts))}".encode()
    d = hashlib.blake2b(key, digest_size=16).digest()
    a = int.from_bytes(d[:8], "big") / 2 ** 64
    b = int.from_bytes(d[8:], "big") / 2 ** 64
    return a, b


def _fit(cust: Customer, features: set) -> float:
    from .customers import fit_score
    return fit_score(cust, features)


def min_required_tier_expansion(cust: Customer, feature_tiers: dict, upto: int) -> int:
    t = 0
    for f, w in cust.needs.items():
        if w >= 0.6:
            t = max(t, feature_tiers.get(f, 0))
    return min(t, upto)
