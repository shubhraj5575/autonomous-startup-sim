"""Run persistence & reporting: JSON artifacts + markdown summaries."""
from __future__ import annotations

import json
import os
import statistics as st
from datetime import datetime

from .rng import fmt_inr
from .config import TIER_NAMES


def _clean(obj):
    """Make an object JSON-safe (sets -> lists etc)."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(x) for x in obj]
    if isinstance(obj, set):
        return sorted(list(obj))
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return round(obj, 4)
    return obj


def serialize_run(cfg, world, name: str) -> dict:
    c = world.company
    mkt = world.market
    h = c.history
    # downsample history for storage: keep daily for first 120d then weekly
    keep = []
    for i, s in enumerate(h):
        if s["day"] <= 120 or s["day"] % 7 == 0 or s["day"] == h[-1]["day"]:
            keep.append(s)
    final = h[-1] if h else {}
    verdicts = [d.get("verdict") for d in c.decision_log if d.get("verdict")]
    data = dict(
        schema=1,
        name=name,
        created_utc=datetime.utcnow().isoformat(),
        config=_clean(cfg.to_dict()),
        alive=c.alive,
        death_reason=c.death_reason,
        days_run=c.day,
        strategy=c.strategy.preset,
        final=dict(
            cash=final.get("cash", 0.0),
            mrr=final.get("mrr", 0.0),
            arr=final.get("arr", 0.0),
            active_customers=final.get("active_customers", 0),
            valuation_proxy=final.get("valuation_proxy", 0.0),
            market_share_pct=final.get("market_share_pct", 0.0),
            logo_churn_pct_monthly=final.get("logo_churn_pct_monthly", 0.0),
            cac_blended=final.get("cac_blended", 0.0),
            ltv=final.get("ltv", 0.0),
            ltv_cac=final.get("ltv_cac", 0.0),
            gross_margin_pct=final.get("gross_margin_pct", 0.0),
            runway_months=final.get("runway_months"),
            headcount=final.get("headcount", 0),
            founder_equity=c.finance.founder_equity,
            quality=c.product.quality,
            tech_debt=c.product.tech_debt,
            features=sorted(c.product.features),
            tier_prices=c.product.tier_prices,
            price_mult=c.product.price_mult,
            brand=c.marketing.brand_awareness,
            elasticity_est=c.price_elasticity_est,
        ),
        kpi_series=keep,
        decisions=_clean(c.decision_log),
        company_events=_clean(c.company_events),
        market_events=_clean([dict(day=e.day, name=e.name, note=e.note,
                                   magnitude=e.magnitude) for e in mkt.event_log]),
        competitors_final=[dict(name=cp.name, archetype=cp.archetype,
                                customers=cp.customers, quality=round(cp.quality, 3),
                                price_mult=round(cp.price_mult, 3),
                                brand=round(cp.brand, 3), features=sorted(cp.features))
                           for cp in world.competitors],
        customer_states=c.pool.counts(),
        pool_size=c.pool.total_size,
        decision_scorecard=dict(
            total=len(verdicts),
            success=verdicts.count("success"),
            partial=verdicts.count("partial"),
            fail=verdicts.count("fail"),
        ),
        channel_summary={k: dict(spend30=round(st_.spend_trailing30),
                                 leads30=round(st_.leads_trailing30, 1),
                                 observed_cpl=round(st_.observed_cac, 1),
                                 score=round(st_.bandit_score, 3),
                                 cum_spend=round(st_.cumulative_spend))
                         for k, st_ in c.marketing.channels.items()},
    )
    return data


def save_run(cfg, world, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    data = serialize_run(cfg, world, name)
    path = os.path.join(out_dir, "result.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    with open(os.path.join(out_dir, "summary.md"), "w") as f:
        f.write(markdown_summary(data))
    with open(os.path.join(out_dir, "config.json"), "w") as f:
        json.dump(data["config"], f, indent=1)
    return path


def markdown_summary(data: dict) -> str:
    fin = data["final"]
    sc = data["decision_scorecard"]
    lines = []
    A = lines.append
    A(f"# Run report: {data['name']}")
    A("")
    A(f"- Strategy preset: **{data['strategy']}** | seed: {data['config']['seed']} "
      f"| days run: {data['days_run']}")
    A(f"- Outcome: **{'ALIVE' if data['alive'] else 'DEAD'}**"
      + (f" - {data['death_reason']}" if data['death_reason'] else ""))
    A("")
    A("## Final state")
    A("")
    A(f"| Metric | Value |")
    A(f"|---|---|")
    A(f"| Cash | {fmt_inr(fin['cash'])} |")
    A(f"| MRR / ARR | {fmt_inr(fin['mrr'])} / {fmt_inr(fin['arr'])} |")
    A(f"| Customers | {fin['active_customers']:,} |")
    A(f"| Market share | {fin['market_share_pct']:.1f}% |")
    A(f"| Valuation proxy | {fmt_inr(fin['valuation_proxy'])} |")
    A(f"| Logo churn (monthly) | {fin['logo_churn_pct_monthly']:.1f}% |")
    if fin.get("ltv_cac") is None:
        A(f"| CAC / LTV | {fmt_inr(fin['cac_blended'])} / n/a (too early) |")
    else:
        A(f"| CAC / LTV / ratio | {fmt_inr(fin['cac_blended'])} / "
          f"{fmt_inr(fin['ltv'])} / {fin['ltv_cac']:.2f} |")
    A(f"| Gross margin | {fin['gross_margin_pct']:.0f}% |")
    A(f"| Product quality / debt | {fin['quality']:.2f} / {fin['tech_debt']:.0f} |")
    A(f"| Team size | {fin['headcount']} |")
    A(f"| Founder equity retained | {fin['founder_equity']:.1%} |")
    A("")
    A("## Decision scorecard")
    A("")
    A(f"{sc['total']} major decisions logged: "
      f"**{sc['success']} success**, {sc['partial']} partial, **{sc['fail']} fail**.")
    fails = [d for d in data["decisions"] if d.get("verdict") == "fail"]
    if fails:
        A("")
        A("### Failed decisions (lessons)")
        A("")
        for d in fails[:12]:
            A(f"- Day {d['day']} [{d['agent']}/{d['kind']}]: {d['decision']}")
            if d.get("lesson"):
                A(f"  - Lesson: {d['lesson']}")
    A("")
    A("## Major events")
    A("")
    for e in data["company_events"]:
        if e["kind"] in ("funding_closed", "funding_declined", "bankruptcy",
                         "competitor_entry", "competitor_exit"):
            A(f"- Day {e['day']}: {e['note']}")
    for e in data["market_events"][:10]:
        A(f"- Day {e['day']} (market): {e['name']}")
    A("")
    A("## Channels (trailing 30d at end)")
    A("")
    A("| Channel | Spend | Leads | CPL | Learned score |")
    A("|---|---|---|---|---|")
    names = dict(content_seo="Content/SEO", google_ads="Google Ads",
                 meta_ads="Meta Ads", whatsapp_outreach="WhatsApp Outreach",
                 referral_program="Referral", events_partnerships="Events")
    for k, v in data["channel_summary"].items():
        A(f"| {names.get(k,k)} | {fmt_inr(v['spend30'])} | {v['leads30']:.0f} | "
          f"{fmt_inr(v['observed_cpl'])} | {v['score']:.2f} |")
    return "\n".join(lines) + "\n"
