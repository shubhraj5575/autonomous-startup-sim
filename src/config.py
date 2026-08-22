"""Central configuration: market parameters, economy constants, strategy presets.

All monetary values in INR (virtual capital). The default scenario models an
Indian SMB SaaS market ("VyaparOS" style business-ops suite) with realistic
price points, salaries and ad costs so that unit economics are genuinely tight
for a bootstrapper starting with INR 1,00,000.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json


STARTING_CAPITAL = 100_000.0  # INR virtual


# ---------------------------------------------------------------- segments ---
SEGMENTS = {
    "kirana_retail": dict(
        label="Kirana / Micro Retail",
        pool=3600,
        budget_mean=700, budget_sd=250, budget_min=250,
        price_sensitivity=1.7,          # lambda in logit utility
        needs={"core_billing": 0.9, "inventory_basic": 0.75, "whatsapp_deep": 0.65,
               "payments_upi": 0.7},
        sales_mode="self_serve", cycle_days=(2, 6), trial_days=10,
        demand_growth_yr=0.06, seasonality=0.18, season_peak_month=10,
    ),
    "d2c_brands": dict(
        label="D2C Brands",
        pool=1800,
        budget_mean=3800, budget_sd=1500, budget_min=1200,
        price_sensitivity=1.05,
        needs={"orders_sync": 0.9, "inventory_basic": 0.85, "analytics_dash": 0.8,
               "payments_upi": 0.55, "crm_lite": 0.4},
        sales_mode="hybrid", cycle_days=(5, 14), trial_days=14,
        demand_growth_yr=0.14, seasonality=0.30, season_peak_month=10,
    ),
    "sme_services": dict(
        label="Service SMEs (agencies/clinics)",
        pool=2200,
        budget_mean=2300, budget_sd=900, budget_min=700,
        price_sensitivity=1.15,
        needs={"core_billing": 0.95, "crm_lite": 0.8, "analytics_dash": 0.5},
        sales_mode="hybrid", cycle_days=(4, 12), trial_days=12,
        demand_growth_yr=0.09, seasonality=0.12, season_peak_month=3,
    ),
    "mfg_sme": dict(
        label="Small Manufacturers",
        pool=1040,
        budget_mean=8500, budget_sd=3200, budget_min=3000,
        price_sensitivity=0.8,
        needs={"inventory_advanced": 0.9, "bom_manufacturing": 0.85,
               "core_billing": 0.8, "analytics_dash": 0.65},
        sales_mode="sales_led", cycle_days=(14, 35), trial_days=21,
        demand_growth_yr=0.08, seasonality=0.15, season_peak_month=3,
    ),
    "enterprise_pilot": dict(
        label="Enterprise Pilots",
        pool=240,
        budget_mean=65000, budget_sd=25000, budget_min=30000,
        price_sensitivity=0.45,
        needs={"api_access": 0.9, "security_sso": 0.85, "sla_support": 0.9,
               "analytics_dash": 0.7, "inventory_advanced": 0.6},
        sales_mode="sales_led", cycle_days=(30, 70), trial_days=30,
        demand_growth_yr=0.10, seasonality=0.08, season_peak_month=4,
    ),
}

# ------------------------------------------------------------ feature catalog
# dev_cost in engineer-points; one founder-engineer ~ 12 pts/day.
FEATURES = {
    "core_billing":       dict(name="GST Billing & Invoicing", cost=140, tier=0),
    "inventory_basic":    dict(name="Inventory Basics",         cost=160, tier=0),
    "whatsapp_deep":      dict(name="WhatsApp Deep Integration",cost=180, tier=1),
    "payments_upi":       dict(name="UPI Auto-Collect",         cost=150, tier=1),
    "orders_sync":        dict(name="Marketplace Orders Sync",  cost=220, tier=1),
    "analytics_dash":     dict(name="Analytics Dashboard",      cost=200, tier=1),
    "crm_lite":           dict(name="CRM Lite + Follow-ups",    cost=190, tier=1),
    "inventory_advanced": dict(name="Multi-warehouse Inventory",cost=280, tier=2),
    "bom_manufacturing":  dict(name="BOM & Production Jobs",    cost=320, tier=2),
    "mobile_app":         dict(name="Mobile App",               cost=350, tier=1),
    "ai_insights":        dict(name="AI Insights & Forecasting",cost=380, tier=2),
    "api_access":         dict(name="Public API + Webhooks",    cost=240, tier=2),
    "security_sso":       dict(name="Security / SSO / Audit",   cost=260, tier=2),
    "sla_support":        dict(name="SLA-backed Support",       cost=140, tier=2),
}

# Pricing tiers: index -> monthly price. Tier gating: customer's needed feature
# set must be covered by tier or lower... (tier >= max tier of required features)
TIER_NAMES = ["Starter", "Growth", "Scale", "Enterprise"]
DEFAULT_PRICES = [499.0, 1999.0, 5999.0, 49999.0]

# ---------------------------------------------------------------- channels ---
CHANNELS = {
    "content_seo": dict(
        name="Content & SEO", ramp_days=120, base_cpl=270.0,
        ref_daily_spend=2400, saturation=0.66, quality=1.05, trend_vol=0.25, min_spend=0.0,
        seg_affinity={"kirana_retail": 0.9, "sme_services": 1.0, "d2c_brands": 0.9,
                      "mfg_sme": 0.7, "enterprise_pilot": 0.4}),
    "google_ads": dict(
        name="Google Search Ads", ramp_days=7, base_cpl=950.0,
        ref_daily_spend=4000, saturation=0.74, quality=1.0, trend_vol=0.20, min_spend=0.0,
        seg_affinity={"kirana_retail": 0.8, "sme_services": 1.0, "d2c_brands": 0.9,
                      "mfg_sme": 0.9, "enterprise_pilot": 0.7}),
    "meta_ads": dict(
        name="Meta (FB/IG) Ads", ramp_days=7, base_cpl=520.0,
        ref_daily_spend=3200, saturation=0.70, quality=0.62, trend_vol=0.30, min_spend=0.0,
        seg_affinity={"kirana_retail": 0.9, "d2c_brands": 1.0, "sme_services": 0.7,
                      "mfg_sme": 0.4, "enterprise_pilot": 0.1}),
    "whatsapp_outreach": dict(
        name="WhatsApp Outreach", ramp_days=3, base_cpl=330.0,
        ref_daily_spend=2100, saturation=0.58, quality=0.80, trend_vol=0.15, min_spend=0.0,
        seg_affinity={"kirana_retail": 1.0, "sme_services": 0.9, "d2c_brands": 0.6,
                      "mfg_sme": 0.5, "enterprise_pilot": 0.1}),
    "referral_program": dict(
        name="Referral Program", ramp_days=14, base_cpl=180.0,
        ref_daily_spend=1500, saturation=0.60, quality=1.25, trend_vol=0.10, min_spend=0.0,
        seg_affinity={"kirana_retail": 1.0, "sme_services": 1.0, "d2c_brands": 0.9,
                      "mfg_sme": 0.8, "enterprise_pilot": 0.5}),
    "events_partnerships": dict(
        name="Events & Partnerships", ramp_days=21, base_cpl=1450.0,
        ref_daily_spend=4500, saturation=0.50, quality=1.35, trend_vol=0.35, min_spend=0.0,
        seg_affinity={"kirana_retail": 0.3, "sme_services": 0.7, "d2c_brands": 0.8,
                      "mfg_sme": 1.0, "enterprise_pilot": 1.0}),
}

# ------------------------------------------------------------------ salaries -
SALARY = {  # INR / month
    "founder_eng": 0,          # sweat equity initially; draw decided by CEO
    "sr_engineer": 115_000,
    "engineer": 82_000,
    "junior_engineer": 52_000,
    "designer": 58_000,
    "sd_r": 38_000,            # SDR outbound, + commission
    "account_exec": 68_000,    # closer, + commission
    "support": 32_000,
    "content_marketer": 48_000,
    "growth_manager": 88_000,
    "ops_admin": 42_000,
}
COMMISSION_RATE = 0.10  # of first-year contract value on closed deals

# Fixed monthly overhead before any hiring: tools, incorporation compliance etc.
BASE_MONTHLY_TOOLS = 6_500.0
INFRA_COST_PER_ACCOUNT = 11.0        # INR/month cloud+SMS+payment infra
PAYMENT_GATEWAY_RATE = 0.019         # fraction of collections

# --------------------------------------------------------------- simulation --
@dataclass
class SimConfig:
    seed: int = 42
    days: int = 365
    starting_capital: float = STARTING_CAPITAL
    shock_probability_daily: float = 0.013
    # competitor count and aggressiveness
    n_competitors: int = 4
    # marketing bandit exploration
    bandit_exploration: float = 0.15
    # weekly planning cadence
    planning_cadence_days: int = 7

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# --------------------------------------------------------- strategy presets ---
# Presets parameterize agent behaviour for experiment mode. They are anchored
# (the strategy agent adapts only +/-0.15 around the initial bias) so that
# strategic identity persists across a run.
STRATEGY_PRESETS: dict[str, dict] = {
    "balanced": dict(
        desc="Default adaptive policy: cautious spend, evidence-driven scaling.",
        growth_bias=0.5, price_stance=0.0, hire_eagerness=0.5,
        channel_policy="bandit", fundraising="opportunistic",
        min_runway_months=4.0,
    ),
    "lean_profitable": dict(
        desc="Bootstrap hard: minimal burn, only revenue-funded hires.",
        growth_bias=0.18, price_stance=+0.12, hire_eagerness=0.25,
        channel_policy="cheap_first", fundraising="never",
        min_runway_months=8.0,
    ),
    "blitz_growth": dict(
        desc="Growth at all costs: aggressive ads + early hiring + raise fast.",
        growth_bias=0.95, price_stance=-0.15, hire_eagerness=0.9,
        channel_policy="bandit_aggressive", fundraising="eager",
        min_runway_months=2.5,
    ),
    "premium_first": dict(
        desc="High price / high touch: target mfg + enterprise early.",
        growth_bias=0.4, price_stance=+0.35, hire_eagerness=0.5,
        channel_policy="quality_first", fundraising="opportunistic",
        min_runway_months=5.0,
    ),
    "product_led": dict(
        desc="PLG: heavy engineering investment, self-serve motion, viral loops.",
        growth_bias=0.6, price_stance=-0.05, hire_eagerness=0.55,
        channel_policy="plg_referral", fundraising="later",
        min_runway_months=4.0,
    ),
}


def load_config(path: str) -> SimConfig:
    with open(path) as f:
        return SimConfig.from_dict(json.load(f))
