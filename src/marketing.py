"""Marketing: channel mechanics, brand awareness, lead generation.

Spend -> leads follows a saturating power curve per channel; channel health
drifts over time (nonstationary), so the marketing agent must keep learning.
Leads are realized by flipping dormant pool members into the 'shopping' state
with source attribution - marketing genuinely causes acquisition.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import CHANNELS
from .rng import clamp


@dataclass
class ChannelState:
    key: str
    spend_today: float = 0.0
    spend_trailing30: float = 0.0
    leads_trailing30: float = 0.0
    customers_attributed_trailing30: float = 0.0
    cumulative_spend: float = 0.0
    cumulative_leads: float = 0.0
    observed_cac: float = 0.0        # EMA of spend/new-customers
    bandit_score: float = 1.0        # learned attractiveness (payback-adjusted)
    enabled: bool = True


class MarketingSystem:
    def __init__(self, cfg):
        self.cfg = cfg
        self.channels: dict[str, ChannelState] = {
            k: ChannelState(key=k) for k in CHANNELS
        }
        self.brand_awareness = 0.02       # 0..1 average across whole pool
        self.brand_spend_ema = 0.0
        self.leads_today_total = 0

    # ------------------------------------------------------------------ core -
    def leads_from_spend(self, ch_key: str, spend: float, market,
                         seg_mix_quality: float) -> float:
        """Diminishing-returns lead curve for one day of spend.

        Calibrated so that at `ref_daily_spend` the marginal CPL equals
        `base_cpl`; below/above that, CPL falls/rises with exponent alpha.
        """
        if spend <= 0:
            return 0.0
        spec = CHANNELS[ch_key]
        st = self.channels[ch_key]
        eff = market.channel_effectiveness(ch_key)
        alpha = spec["saturation"]
        ref = spec["ref_daily_spend"]
        leads_ref = ref / max(spec["base_cpl"], 1.0)
        ramp = clamp((st.cumulative_spend / 40_000.0) ** 0.4, 0.30, 1.5) \
            if ch_key == "content_seo" else \
            clamp(0.55 + st.cumulative_spend / 120_000.0, 0.55, 1.2) \
            if ch_key == "events_partnerships" else 1.0
        scale = (spend / ref) ** alpha
        leads = leads_ref * scale * eff * ramp * seg_mix_quality
        return max(0.0, leads)

    def record_results(self, ch_key: str, spend: float, leads: float) -> None:
        st = self.channels[ch_key]
        st.spend_today = spend
        st.cumulative_spend += spend
        st.cumulative_leads += leads
        if leads > 0:
            inst_cac_proxy = spend / leads      # cost per LEAD as fast signal
            alpha = 0.15
            prior = st.observed_cac if st.observed_cac > 0 else inst_cac_proxy
            st.observed_cac = (1 - alpha) * prior + alpha * inst_cac_proxy

    def update_brand(self, daily_marketing_spend: float) -> None:
        """Brand accumulates from spend (log, capped) and decays ~5%/mo."""
        self.brand_spend_ema = 0.92 * self.brand_spend_ema + 0.08 * daily_marketing_spend
        gain = math.log1p(self.brand_spend_ema / 1400.0) * 0.0042
        self.brand_awareness = clamp(self.brand_awareness * 0.9984 + gain, 0.0, 0.85)

    def snapshot(self) -> dict:
        return {k: dict(spend30=round(st.spend_trailing30),
                        leads30=round(st.leads_trailing30, 1),
                        cac=round(st.observed_cac),
                        score=round(st.bandit_score, 3),
                        enabled=st.enabled)
                for k, st in self.channels.items()}
