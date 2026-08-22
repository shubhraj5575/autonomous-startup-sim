"""Product & engineering: feature set, quality, pricing tiers, tech debt,
engineering capacity and incidents.

Quality and fit drive customer utility; tech debt drags capacity and raises
incident risk - real tradeoffs the CTO agent must manage.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import FEATURES, TIER_NAMES


@dataclass
class ProductState:
    features: set = None
    quality: float = 0.50            # 0..1 reliability+UX composite
    tech_debt: float = 0.0           # points; raises drag & incident risk
    tier_prices: list = None         # monthly INR
    price_mult: float = 1.0          # global experiment multiplier
    n_incidents_30d: int = 0

    def __post_init__(self):
        if self.features is None:
            # Founder MVP seed: billing + basic inventory - a real v1 scope.
            self.features = {"core_billing", "inventory_basic"}
        if self.tier_prices is None:
            self.tier_prices = list([499.0, 1999.0, 5999.0, 49999.0])

    @property
    def effective_prices(self) -> list:
        return [p * self.price_mult for p in self.tier_prices]

    @property
    def feature_tiers(self) -> dict:
        return {f: meta["tier"] for f, meta in FEATURES.items()}

    def coverage(self, seg_needs: dict) -> float:
        tot = sum(seg_needs.values())
        cov = sum(w for f, w in seg_needs.items() if f in self.features)
        return cov / max(tot, 1e-9)

    def incident_probability_daily(self, active_customers: float) -> float:
        """More surface area + lower quality + debt => more incidents."""
        if active_customers <= 0:
            return 0.0
        surface = len(self.features) ** 0.5
        p = (surface * (1.15 - self.quality) * (1.0 + self.tech_debt / 1500.0)
             * min(active_customers, 800) / 800.0 * 0.05)
        return max(0.0005, min(p, 0.35))


class EngineeringSystem:
    """Converts headcount into shipped points split across work streams."""

    POINTS_PER_ENGINEER_DAY = {
        "founder_eng": 12.0, "sr_engineer": 11.0, "engineer": 8.5,
        "junior_engineer": 5.5, "designer": 4.0,
    }

    def __init__(self, product: ProductState):
        self.product = product
        # allocation shares decided weekly by CTO agent
        self.alloc_features = 0.70
        self.alloc_quality = 0.20
        self.alloc_debt = 0.10
        self.points_shipped_today = 0.0
        self.features_completed_total = 0

    def capacity(self, eng_headcount: dict) -> float:
        cap = 0.0
        for role, n in eng_headcount.items():
            cap += self.POINTS_PER_ENGINEER_DAY.get(role, 6.0) * n
        drag = min(0.40, self.product.tech_debt / 1200.0)
        return cap * (1.0 - drag)

    def execute_day(self, eng_headcount: dict) -> None:
        cap = self.capacity(eng_headcount)
        pts_f = cap * self.alloc_features
        pts_q = cap * self.alloc_quality
        pts_d = cap * self.alloc_debt

        # quality improves with diminishing returns; decays as scope grows,
        # and unmanaged debt slowly rots reliability
        q = self.product.quality
        q += pts_q / 2200.0
        q -= len(self.product.features) * 0.00010
        q -= self.product.tech_debt / 60000.0
        self.product.quality = max(0.15, min(0.97, q))

        # debt: grows with feature shipping, shrinks with debt allocation
        self.product.tech_debt = max(0.0,
                                     self.product.tech_debt + pts_f * 0.35 - pts_d * 1.0)

        # feature completion: cheapest unfinished features complete over time
        self._progress_backlog(pts_f)
        self.points_shipped_today = cap

    def _progress_backlog(self, pts_available: float) -> None:
        """Spend feature points on cheapest unfinished features first (CPO may
        reorder priorities via `pinned_features`)."""
        wip = getattr(self, "_wip", {})
        budget = pts_available
        remaining = [f for f in FEATURES if f not in self.product.features]
        remaining.sort(key=lambda f: FEATURES[f]["cost"] - wip.get(f, 0.0))
        while budget > 0 and remaining:
            f = remaining[0]
            need = FEATURES[f]["cost"] - wip.get(f, 0.0)
            if budget >= need:
                self.product.features.add(f)
                budget -= need
                wip.pop(f, None)
                remaining.pop(0)
                self.features_completed_total += 1
            else:
                wip[f] = wip.get(f, 0.0) + budget
                budget = 0.0
        self._wip = wip
