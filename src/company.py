"""Company aggregate: owns all subsystems, team, capital and memory.

A Company is deep-copyable so experiment mode can clone it and vary only its
strategy parameters while facing an identical market path.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .finance import FinanceEngine
from .product import ProductState, EngineeringSystem
from .marketing import MarketingSystem
from .sales import SalesSystem
from .ops import OpsState
from .config import SALARY
from .rng import clamp


@dataclass
class Team:
    """Headcount by role. The founder-engineer is always present."""
    headcount: dict = field(default_factory=lambda: {"founder_eng": 1})
    hiring_in_progress: list = field(default_factory=list)  # (day_available, role)

    def count(self, role: str) -> int:
        return self.headcount.get(role, 0)

    def total(self) -> int:
        return sum(self.headcount.values())

    def monthly_bill(self) -> float:
        return sum(SALARY.get(r, 0) * n for r, n in self.headcount.items())


@dataclass
class StrategyParams:
    """Tunable policy knobs - what experiment mode varies."""
    preset: str = "balanced"
    growth_bias: float = 0.5          # willingness to spend ahead of revenue
    price_stance: float = 0.0         # multiplier offset on list prices
    hire_eagerness: float = 0.5
    channel_policy: str = "bandit"
    fundraising: str = "opportunistic"  # never | opportunistic | eager | later
    max_marketing_share_of_cash_daily: float = 0.02
    target_runway_months: float = 6.0
    min_runway_months: float = 4.0    # below this => survive protocol
    referral_enabled: bool = True


class Company:
    def __init__(self, cfg, name="NayaVault"):
        self.cfg = cfg
        self.name = name
        self.finance = FinanceEngine(cfg.starting_capital)
        self.product = ProductState()
        self.engineering = EngineeringSystem(self.product)
        self.marketing = MarketingSystem(cfg)
        self.sales = SalesSystem()
        self.ops = OpsState()
        self.team = Team()
        self.strategy = StrategyParams()

        self.day = 0
        self.alive = True
        self.death_reason: str = ""
        self.current_mrr: float = 0.0
        self.active_ids: set = set()
        self.pool = None                       # CustomerPool (set by world)
        self.focus_segments: list[str] | None = None
        self.cfo_guard_marketing_multiplier: float = 1.0
        # rolling decision-relevant counters (filled by simulator)
        self.eval_events: list[tuple[int, bool]] = []       # (day, chose_us)
        self.channel_conversions: dict[str, list] = {k: [] for k in self.marketing.channels}
        self.history: list[dict] = []          # DailySnapshot dicts
        self.decision_log: list[dict] = []     # CEO+dept major decisions
        self.company_events: list[dict] = []   # hires, raises, incidents, exits...
        self.pending_evaluations: list[dict] = []

        # learned state (persists into future runs through KnowledgeBase)
        self.channel_scores: dict[str, float] = {k: 1.0 for k in self.marketing.channels}
        self.price_elasticity_est: float = -1.3     # prior
        self.price_test_state: dict = {"active": False, "mult": 1.0,
                                       "start_day": 0, "baseline_conv": None}
        self.churn_ema: float = 0.06
        self.conv_ema: float = 0.25
        self.last_mrr_samples: list[float] = []     # for growth calc
        self._churn_by_seg: dict[str, float] = {}
        self._last_roi: float = 0.0

    # ----------------------------------------------------------------- clone -
    def clone(self) -> "Company":
        c = copy.deepcopy(self)
        return c

    def set_strategy(self, params: "StrategyParams") -> None:
        """Apply a strategy preset, including its pricing stance."""
        from .rng import clamp
        self.strategy = params
        params._initial_growth_bias = params.growth_bias   # anchor for adaptation
        self.product.price_mult = clamp(1.0 + params.price_stance, 0.70, 1.45)

    # ------------------------------------------------------------- workforce -
    def eng_headcount(self) -> dict:
        roles = ("founder_eng", "sr_engineer", "engineer", "junior_engineer", "designer")
        return {r: self.team.count(r) for r in roles if self.team.count(r) > 0}

    def support_headcount(self) -> int:
        return self.team.count("support")

    def hire_cost(self, role: str) -> float:
        return SALARY.get(role, 45_000) * 0.5      # recruiter fee

    def severance_cost(self, role: str) -> float:
        return SALARY.get(role, 45_000) * 1.0

    # -------------------------------------------------------------- decisions -
    def log_decision(self, day: int, agent: str, kind: str, decision: str,
                     reasoning: str, data_considered: dict,
                     expected: dict, eval_horizon_days: int = 60) -> dict:
        d = dict(id=len(self.decision_log) + 1, day=day, agent=agent, kind=kind,
                 decision=decision, reasoning=reasoning,
                 data_considered={k: (round(v, 4) if isinstance(v, float) else v)
                                  for k, v in data_considered.items()},
                 expected=expected,
                 actual=None, verdict=None, lesson=None,
                 eval_due_day=day + eval_horizon_days)
        self.decision_log.append(d)
        if len(self.decision_log) > 4000:
            self.decision_log = self.decision_log[-3000:]
        return d

    def queue_evaluation(self, decision_id: int, metric: str, direction: str,
                         magnitude: float):
        for d in self.decision_log:
            if d["id"] == decision_id:
                d["_eval_metric"] = metric
                d["_eval_direction"] = direction
                d["_eval_magnitude"] = magnitude
                break

    def company_event(self, day: int, kind: str, note: str, **kw) -> None:
        e = dict(day=day, kind=kind, note=note)
        e.update(kw)
        self.company_events.append(e)

    # ------------------------------------------------------------- analytics -
    # Helpers used by agents; computed from the company's own customer base
    # and funnel counters only.
    def customers_in_segment(self, seg: str) -> int:
        if self.pool is None:
            return 0
        n = 0
        for cid in self.active_ids:
            if self.pool.customers[cid].segment == seg:
                n += 1
        return n

    def customers_by_segment(self) -> dict:
        out: dict[str, int] = {}
        if self.pool is None:
            return out
        for cid in self.active_ids:
            seg = self.pool.customers[cid].segment
            out[seg] = out.get(seg, 0) + 1
        return out

    def avg_budget_fit(self, segs: list[str] | None) -> float:
        """Avg (budget / price paid) of active customers in focus segments."""
        segs = set(segs or [])
        ratios = []
        if self.pool is not None:
            for cid in self.active_ids:
                cust = self.pool.customers[cid]
                if not segs or cust.segment in segs:
                    ratios.append(cust.budget / max(cust.monthly_fee, 1.0))
        return sum(ratios) / len(ratios) if ratios else 1.0

    def segment_funnel_stats(self) -> dict:
        """Per-segment: actives, avg budget, churn estimate from own history."""
        stats: dict[str, dict] = {}
        if self.pool is None:
            return stats
        h = self.history
        for seg in {self.pool.customers[cid].segment for cid in self.active_ids}:
            budgets = [self.pool.customers[cid].budget for cid in self.active_ids
                       if self.pool.customers[cid].segment == seg]
            stats[seg] = dict(active=len(budgets),
                              budget=sum(budgets) / max(len(budgets), 1))
        churn_days_by_seg = getattr(self, "_churn_by_seg", {})
        for seg, st in stats.items():
            days_list = churn_days_by_seg.get(seg, [])
            if isinstance(days_list, list):
                cutoff = self.day - 60
                recent = sum(1 for d in days_list if d >= cutoff)
                st["churn"] = clamp(recent / max(st["active"] + recent, 1), 0.0, 0.9)
            else:
                st["churn"] = float(days_list)
        return stats

    def recent_eval_count(self, days: int) -> int:
        cutoff = self.day - days
        return sum(1 for d, _ in self.eval_events if d >= cutoff)

    def recent_eval_win_rate(self, days: int) -> float:
        cutoff = self.day - days
        wins = tot = 0
        for d, won in self.eval_events:
            if d >= cutoff:
                tot += 1
                wins += 1 if won else 0
        return wins / tot if tot else 0.30

    def channel_conversions_30d(self, ch: str) -> int:
        events = self.channel_conversions.get(ch, [])
        cutoff = self.day - 30
        return sum(1 for d, _ in events if d >= cutoff)

    def dormant_fraction(self) -> float:
        """Share of the addressable universe still unpenetrated & available."""
        if self.pool is None or self.pool.total_size == 0:
            return 1.0
        return len(self.pool.ids_in_state("dormant")) / self.pool.total_size
