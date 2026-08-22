"""Sales: pipeline of deals worked by reps; capacity constraints are real -
unworked leads decay. Self-serve conversions bypass the pipeline.
"""
from __future__ import annotations

import random

from dataclasses import dataclass, field

from .rng import clamp


@dataclass(slots=True)
class Deal:
    did: int
    cid: int                 # customer id
    segment: str
    tier: int
    mrr_value: float
    created_day: int
    close_due_day: int
    rep_id: int = -1         # -1 unassigned
    stage: str = "new"       # new -> demo -> negotiation -> won/lost
    win_prob: float = 0.5
    lost_reason: str = ""


@dataclass
class SalesRep:
    rid: int
    role: str                # 'sd_r' prospecting or 'account_exec' closing
    hired_day: int
    skill: float = 0.55      # improves with experience
    ramp_days_left: int = 30 # productivity ramps from 35% to 100%

    def productivity(self) -> float:
        if self.ramp_days_left > 0:
            return clamp(0.35 + 0.65 * (1 - self.ramp_days_left / 45.0), 0.35, 1.0)
        return 1.0

    def tick(self):
        if self.ramp_days_left > 0:
            self.ramp_days_left -= 1
        self.skill = min(0.95, self.skill + 0.0006)


class SalesSystem:
    MAX_DEALS_PER_AE = 12
    LEAD_DECAY_DAYS = 21     # unworked lead-pool patience before cooling off

    def __init__(self):
        self.deals: dict[int, Deal] = {}
        self.reps: list[SalesRep] = []
        self._next_did = 1
        self.closed_won_trailing30: int = 0
        self.pipeline_value: float = 0.0
        self.unworked_leads_today: int = 0

    def hiring_plan_ok(self) -> bool:
        return True

    def add_deal(self, cid: int, segment: str, tier: int, mrr: float,
                 day: int, cycle_days: int) -> Deal:
        d = Deal(did=self._next_did, cid=cid, segment=segment, tier=tier,
                 mrr_value=mrr, created_day=day,
                 close_due_day=day + max(3, cycle_days))
        self._next_did += 1
        self.deals[d.did] = d
        return d

    def ae_capacity(self) -> float:
        """Total concurrent-deal slots across productive AEs."""
        n_ae = sum(1 for r in self.reps if r.role == "account_exec")
        if n_ae == 0:
            return 0.0
        prod = sum(r.productivity() for r in self.reps if r.role == "account_exec")
        return prod * self.MAX_DEALS_PER_AE

    def assign_reps(self, rng: random.Random) -> None:
        """Round-robin unassigned deals onto AEs with free slots."""
        aes = [r for r in self.reps if r.role == "account_exec"]
        if not aes:
            return
        load: dict[int, int] = {r.rid: 0 for r in aes}
        for d in self.deals.values():
            if d.rep_id >= 0 and d.stage not in ("won", "lost"):
                load[d.rep_id] = load.get(d.rep_id, 0) + 1
        for d in sorted(self.deals.values(), key=lambda x: x.mrr_value, reverse=True):
            if d.stage in ("won", "lost"):
                continue
            if d.rep_id < 0 or load.get(d.rep_id, 99) > self.MAX_DEALS_PER_AE:
                best = min(aes, key=lambda r: load[r.rid])
                if load[best.rid] < self.MAX_DEALS_PER_AE * best.productivity():
                    d.rep_id = best.rid
                    load[best.rid] += 1
                    if d.stage == "new":
                        d.stage = "demo"

    def snapshot(self) -> dict:
        open_deals = [d for d in self.deals.values() if d.stage not in ("won", "lost")]
        return dict(
            open_deals=len(open_deals),
            pipeline_value=round(sum(d.mrr_value for d in open_deals)),
            reps=len(self.reps),
        )
