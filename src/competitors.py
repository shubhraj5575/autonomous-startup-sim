"""Competitor firms. Each is an autonomous agent with an archetype that adapts
price / quality / marketing over time and can enter or exit the market.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


ARCHETYPES = {
    "discount_disruptor": dict(price_bias=0.75, qual_bias=0.55, mkt_bias=1.1,
                               adapt="cut_price_when_losing"),
    "premium_incumbent": dict(price_bias=1.35, qual_bias=0.85, mkt_bias=0.9,
                              adapt="improve_quality"),
    "marketing_blitzer": dict(price_bias=1.0, qual_bias=0.6, mkt_bias=1.5,
                              adapt="spend_more_when_losing"),
    "niche_specialist": dict(price_bias=1.05, qual_bias=0.7, mkt_bias=0.6,
                             adapt="deepen_features"),
}

# Competitor focus segments drive which features they prioritise when they
# copy the challenger's winning moves.
COMPETITOR_FOCUS = {
    "KhataKing": "kirana_retail",
    "LedgerLyf": "sme_services",
    "BizzBoost": "d2c_brands",
    "FactoryDesk": "mfg_sme",
}


@dataclass
class Competitor:
    cid: str
    name: str
    archetype: str
    features: set = field(default_factory=set)
    quality: float = 0.45
    price_mult: float = 1.0          # applied to our tier prices as reference
    brand: float = 0.25              # market awareness 0..1
    customers: int = 120             # active subscriber count in simulated universe
    mrr: float = 300_000.0           # hidden book MRR (INR)
    health: int = 100                # >0 alive; burns when unprofitable
    months_alive: int = 0
    entry_day: int = 0

    # ------------------------------------------------------------------ tick -
    def monthly_update(self, rng: random.Random, share_lost: bool, day: int,
                       allow_exit: bool = True) -> str | None:
        """Adapt strategy; return action note or None."""
        a = ARCHETYPES[self.archetype]
        self.months_alive += 1
        notes = []

        # profitability proxy: rough margin on book
        cogs_rate = 0.30
        est_profit = self.mrr * (1 - cogs_rate) - 250_000 * a["mkt_bias"]
        if est_profit < 0:
            self.health -= 12 if not self._is_funded(day) else 4
        else:
            self.health = min(100, self.health + 8)

        # market-wide SaaS maturity: everyone's product gets better over time
        self.quality = min(0.93, self.quality + rng.uniform(0.0015, 0.005))

        if a["adapt"] == "cut_price_when_losing" and share_lost:
            self.price_mult = max(0.62, self.price_mult * rng.uniform(0.93, 0.97))
            notes.append("price cut")
        elif a["adapt"] == "improve_quality":
            self.quality = min(0.95, self.quality + rng.uniform(0.004, 0.010))
            if share_lost and rng.random() < 0.4:
                self.price_mult *= rng.uniform(0.96, 0.99)
                notes.append("selective discounting")
        elif a["adapt"] == "spend_more_when_losing" and share_lost:
            self.brand = min(0.95, self.brand + rng.uniform(0.02, 0.06))
            notes.append("ad blitz")
        elif a["adapt"] == "deepen_features":
            self.quality = min(0.92, self.quality + rng.uniform(0.004, 0.014))

        # feature shipping: faster when losing; they copy what wins against them
        ship_p = 0.30 if share_lost else 0.16
        if rng.random() < ship_p and len(self.features) < 11:
            new_feat = self._pick_feature(rng)
            if new_feat:
                self.features.add(new_feat)
                notes.append(f"shipped {new_feat}")

        # brand decays slowly without spend pressure
        self.brand = max(0.10, min(0.95, self.brand * (0.988 if not share_lost else 1.0)))

        if allow_exit and self.health <= 0:
            return "exit"
        return "; ".join(notes) if notes else None

    def _pick_feature(self, rng: random.Random) -> str | None:
        """Prefer features their focus segment actually needs and lacks."""
        from .config import SEGMENTS
        focus_seg = COMPETITOR_FOCUS.get(self.name)
        candidates: list[tuple[str, float]] = []
        generic = ["core_billing", "inventory_basic", "payments_upi", "orders_sync",
                   "analytics_dash", "crm_lite", "whatsapp_deep", "inventory_advanced",
                   "bom_manufacturing", "mobile_app", "api_access"]
        pool = generic if not focus_seg else \
            list(SEGMENTS[focus_seg]["needs"].keys()) + [g for g in generic
                                                         if g not in SEGMENTS.get(focus_seg, {}).get("needs", {})]
        for f in pool:
            if f in self.features or f == "sla_support":
                continue
            w = 1.0
            if focus_seg:
                w = 0.35 + float(SEGMENTS[focus_seg]["needs"].get(f, 0.0))
            candidates.append((f, w))
        if not candidates:
            return None
        feats = [c[0] for c in candidates]
        wts = [c[1] for c in candidates]
        return rng.choices(feats, weights=wts, k=1)[0]

    def _is_funded(self, day: int) -> bool:
        return (day - self.entry_day) < 400 and self.archetype == "marketing_blitzer"

    def offer_view(self, tier_prices_ref: list[float]) -> tuple:
        """Build the Offer tuple used by customer evaluation."""
        prices = [p * self.price_mult for p in tier_prices_ref]
        return prices


DEFAULT_COMPETITORS = [
    ("KhataKing", "discount_disruptor",
     {"core_billing", "inventory_basic", "payments_upi"}),
    ("LedgerLyf", "premium_incumbent",
     {"core_billing", "analytics_dash", "crm_lite"}),
    ("BizzBoost", "marketing_blitzer",
     {"core_billing", "inventory_basic", "crm_lite"}),
    ("FactoryDesk", "niche_specialist",
     {"core_billing", "inventory_advanced", "bom_manufacturing"}),
]
