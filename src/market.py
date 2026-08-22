"""Market simulation: segments, demand evolution, trends, shocks, competitors.

Ground truth of the economy. The company observes only noisy/derived signals
of this (through its own analytics) - never the raw internals.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .rng import RngManager, clamp
from .config import SEGMENTS


DAYS_PER_YEAR = 365.0

# ------------------------------------------------------------- event catalog -
# Each shock: (name, kind, duration_days_range, magnitude_range, affected)
# kind: 'demand_mult' (segment demand multiplier), 'price_sens_mult',
#       'channel_mult' (all channels effectiveness), 'new_entrant'
EVENT_TEMPLATES = [
    dict(name="Funding winter", kind="demand_mult", segs=None, dur=(60, 150),
         mag=(0.75, 0.90), weight=1.0,
         note="VC funding tightens; SMBs defer software spend."),
    dict(name="GST compliance deadline", kind="demand_mult", segs=["kirana_retail", "sme_services", "mfg_sme"],
         dur=(30, 60), mag=(1.15, 1.45), weight=1.2,
         note="Compliance rush boosts demand for billing tools."),
    dict(name="Festive season e-commerce boom", kind="demand_mult",
         segs=["d2c_brands"], dur=(25, 50), mag=(1.20, 1.60), weight=1.5,
         note="Diwali sales surge; D2C brands scale operations."),
    dict(name="Recession fears", kind="price_sens_mult", segs=None, dur=(90, 200),
         mag=(1.15, 1.40), weight=1.0,
         note="Buyers become more price sensitive."),
    dict(name="Ad platform CPM spike", kind="channel_mult", segs=None, dur=(30, 70),
         mag=(0.70, 0.85), weight=1.0,
         note="Digital ad costs rise sharply."),
    dict(name="Viral productivity trend", kind="demand_mult", segs=None, dur=(30, 80),
         mag=(1.10, 1.35), weight=0.8,
         note="SMB digitization goes viral; software interest spikes."),
    dict(name="New funded competitor enters", kind="new_entrant", segs=None,
         dur=(1, 1), mag=(1.0, 1.0), weight=0.6,
         note="A VC-funded rival starts spending aggressively."),
    dict(name="UPI network outage wave", kind="demand_mult",
         segs=["kirana_retail"], dur=(7, 20), mag=(0.85, 0.95), weight=0.4,
         note="Payment friction hurts retail sentiment."),
]


@dataclass
class ActiveShock:
    name: str
    kind: str
    segs: Optional[list]
    end_day: int
    magnitude: float
    note: str = ""


@dataclass
class MarketEventLog:
    day: int
    name: str
    note: str
    magnitude: float


class Market:
    """Simulates aggregate demand intensity per segment and environmental multipliers."""

    def __init__(self, cfg, rng: RngManager):
        self.cfg = cfg
        self.rng = rng.stream("market")
        self.day = 0
        # baseline demand intensity (fraction of pool actively shopping per month)
        self.base_intensity = {s: 0.032 for s in SEGMENTS}
        self.demand_state: dict[str, float] = {s: 1.0 for s in SEGMENTS}
        self.shocks: list[ActiveShock] = []
        self.event_log: list[MarketEventLog] = []
        # channel effectiveness multipliers evolve over time (nonstationary world)
        self.channel_health: dict[str, float] = {}
        self.channel_trend: dict[str, float] = {}
        self.competitor_entry_pending = False
        self._init_channel_dynamics()

    # ------------------------------------------------------------------ setup
    def _init_channel_dynamics(self):
        r = self.rng
        for ch in ("content_seo", "google_ads", "meta_ads", "whatsapp_outreach",
                   "referral_program", "events_partnerships"):
            self.channel_health[ch] = r.uniform(0.85, 1.15)
            self.channel_trend[ch] = r.uniform(-0.0008, 0.0008)

    # ------------------------------------------------------------------ tick
    def advance_day(self, day: int) -> None:
        self.day = day
        r = self.rng

        # demand random walk per segment (mean-reverting AR(1)) + growth drift
        month = self.month_of(day)
        for seg, spec in SEGMENTS.items():
            drift = (spec["demand_growth_yr"] / DAYS_PER_YEAR)
            seasonal = spec["seasonality"] * math.sin(
                2 * math.pi * ((month - spec["season_peak_month"]) % 12) / 12.0 + math.pi / 2)
            shock = r.gauss(0.0, 0.014)
            prev = self.demand_state[seg]
            mean_rev = 0.02 * (1.0 - prev)
            self.demand_state[seg] = max(0.55, min(1.9, prev + drift + mean_rev + seasonal / 30.0 * 0.3 + shock))

        # channel health slow evolution
        for ch in self.channel_health:
            self.channel_health[ch] *= (1.0 + self.channel_trend[ch])
            self.channel_health[ch] += r.gauss(0.0, 0.004)
            self.channel_health[ch] = clamp(self.channel_health[ch], 0.45, 1.8)

        # maybe trigger a shock
        if r.random() < self.cfg.shock_probability_daily:
            self._trigger_shock(day)

        # expire shocks
        still = []
        for s in self.shocks:
            if day < s.end_day:
                still.append(s)
            else:
                self.event_log.append(MarketEventLog(day, f"{s.name} ended", s.note, s.magnitude))
        self.shocks = still

    def _trigger_shock(self, day: int) -> None:
        r = self.rng
        weights = [t["weight"] for t in EVENT_TEMPLATES]
        total = sum(weights)
        pick = r.random() * total
        acc = 0.0
        tmpl = EVENT_TEMPLATES[-1]
        for t, w in zip(EVENT_TEMPLATES, weights):
            acc += w
            if pick <= acc:
                tmpl = t
                break
        dur = r.randint(*tmpl["dur"])
        mag = r.uniform(*tmpl["mag"])
        if tmpl["kind"] == "new_entrant":
            self.competitor_entry_pending = True
            mag = 1.0
        self.shocks.append(ActiveShock(tmpl["name"], tmpl["kind"], tmpl["segs"],
                                       day + dur, mag, tmpl["note"]))
        self.event_log.append(MarketEventLog(day, tmpl["name"], tmpl["note"], mag))

    # --------------------------------------------------------------- queries
    def month_of(self, day: int) -> int:
        return ((day // 30) % 12) + 1  # simplified 30-day months

    def date_label(self, day: int) -> str:
        y = day // 360 + 2026
        m = self.month_of(day)
        d = day % 30 + 1
        return f"{y:04d}-{m:02d}-{d:02d}"

    def demand_multiplier(self, seg: str) -> float:
        m = self.demand_state[seg]
        for s in self.shocks:
            if s.kind == "demand_mult" and (s.segs is None or seg in s.segs):
                m *= s.magnitude
        return m

    def price_sensitivity_multiplier(self, seg: str) -> float:
        base = SEGMENTS[seg]["price_sensitivity"]
        mult = 1.0
        for s in self.shocks:
            if s.kind == "price_sens_mult" and (s.segs is None or seg in s.segs):
                mult *= s.magnitude
        return base * mult

    def channel_effectiveness(self, channel: str) -> float:
        return self.channel_health[channel] * self.global_channel_multiplier()

    def global_channel_multiplier(self) -> float:
        m = 1.0
        for s in self.shocks:
            if s.kind == "channel_mult" and s.segs is None:
                m *= s.magnitude
        return m

    def backlash_penalty(self) -> float:
        """Extra utility penalty against the market leader while backlash
        sentiment is active (buyers hedge against dominance)."""
        p = 0.0
        for s in self.shocks:
            if s.kind == "trust_backlash":
                p += s.magnitude
        return p

    def monthly_shopping_rate(self, seg: str) -> float:
        """Probability a given pool member starts shopping in a given day."""
        base = self.base_intensity[seg]
        dm = self.demand_multiplier(seg)
        return clamp(base * dm / 30.0, 0.0002, 0.02)

    def summary(self) -> dict:
        return dict(
            demand={k: round(v, 3) for k, v in self.demand_state.items()},
            active_shocks=[dict(name=s.name, ends_in=s.end_day - self.day,
                                magnitude=round(s.magnitude, 2)) for s in self.shocks],
            channel_health={k: round(v, 2) for k, v in self.channel_health.items()},
        )
