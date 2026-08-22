"""Operations: support tickets, CSAT effects, infrastructure costs.

Support capacity is real: unresolved tickets depress satisfaction of the
affected customers, which feeds churn - ops genuinely matters.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OpsState:
    tickets_open: int = 0
    tickets_opened_30d: float = 0.0
    tickets_closed_30d: float = 0.0
    csat: float = 0.72                  # trailing support satisfaction 0..1
    incidents_30d: int = 0
    affected_recently: dict = None      # cid -> severity decay handled in sim

    def __post_init__(self):
        if self.affected_recently is None:
            self.affected_recently = {}

    def resolution_capacity_daily(self, support_headcount: int, founder_supporting: bool) -> int:
        cap = support_headcount * 14
        if founder_supporting:
            cap += 6
        return cap
