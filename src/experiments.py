"""Experiment mode: clone companies, vary strategy, compare honestly.

All variants face the SAME seeded market path per seed; only their decisions
differ. Outcomes therefore measure strategy quality, not luck asymmetry.
"""
from __future__ import annotations

import json
import os
import statistics as st
import time

from .config import SimConfig, STRATEGY_PRESETS
from .company import Company, StrategyParams
from .simulator import World
from .knowledge import KnowledgeBase


def run_variant(cfg: SimConfig, preset: str, knowledge: KnowledgeBase | None):
    comp = Company(cfg)
    pdef = STRATEGY_PRESETS[preset]
    params = StrategyParams(
        **{k: v for k, v in pdef.items() if k in StrategyParams.__dataclass_fields__})
    params.preset = preset
    comp.set_strategy(params)
    if knowledge is not None:
        knowledge.apply_to(comp)
    world = World(cfg, company=comp)
    comp_out = world.run(cfg.days)
    return world, comp_out


def run_tournament(days: int, seeds: int, presets: str = "all",
                   out_dir: str = "runs/experiments",
                   knowledge_path: str | None = None,
                   quiet: bool = False) -> dict:
    preset_names = (list(STRATEGY_PRESETS.keys()) if presets == "all"
                    else [p.strip() for p in presets.split(",")])
    kb = KnowledgeBase(knowledge_path) if knowledge_path else None

    results = []
    t0 = time.time()
    for seed_i in range(seeds):
        seed = 1000 + seed_i * 137          # tournament seeds independent of CLI runs
        for pname in preset_names:
            cfg = SimConfig(seed=seed, days=days)
            world, comp = run_variant(cfg, pname, kb)
            from .reporting import serialize_run
            res = serialize_run(cfg, world, f"{pname}_s{seed}")
            res["tournament_seed"] = seed
            results.append(res)
            h = comp.history[-1]
            if not quiet:
                tag = "OK  " if comp.alive else "DEAD"
                print(f"[t] {pname:>16} seed={seed} {tag} "
                      f"mrr={h['mrr']/1e5:>5.1f}L cash={h['cash']/1e5:>6.1f}L "
                      f"cust={h['active_customers']:>5} ({time.time()-t0:.0f}s)",
                      flush=True)

    # aggregate
    agg = {}
    for pname in preset_names:
        rs = [r for r in results if r["strategy"] == pname]
        alive = [r for r in rs if r["alive"]]
        mrrs = [r["final"]["mrr"] for r in alive]
        cash = [r["final"]["cash"] for r in rs]
        vals = [r["final"]["valuation_proxy"] for r in alive]
        mults = [(r["final"]["mrr"] / 100_000.0) for r in alive]
        sc_all = [r["decision_scorecard"] for r in rs]
        agg[pname] = dict(
            runs=len(rs),
            survival_rate=len(alive) / len(rs) if rs else 0.0,
            median_mrr=st.median(mrrs) if mrrs else 0.0,
            mean_mrr=st.mean(mrrs) if mrrs else 0.0,
            max_mrr=max(mrrs) if mrrs else 0.0,
            median_cash=st.median(cash) if cash else 0.0,
            median_valuation=st.median(vals) if vals else 0.0,
            median_mrr_multiple=st.median(mults) if mults else 0.0,
            decision_success_rate=(sum(s["success"] for s in sc_all)
                                   / max(sum(s["total"] for s in sc_all), 1)),
            decision_fail_rate=(sum(s["fail"] for s in sc_all)
                                / max(sum(s["total"] for s in sc_all), 1)),
        )

    ranking = sorted(agg.items(), key=lambda kv: kv[1]["median_mrr_multiple"],
                     reverse=True)

    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    # downsampled trajectories for the comparison dashboard
    runs_compact = []
    for r in results:
        series = r.get("kpi_series") or []
        runs_compact.append(dict(
            name=r["name"], strategy=r["strategy"],
            tournament_seed=r["tournament_seed"], alive=r["alive"],
            final=r["final"], scorecard=r["decision_scorecard"],
            series=[dict(day=s["day"], mrr=round(s["mrr"]),
                         cash=round(s["cash"]), cust=s["active_customers"])
                    for s in series if s["day"] % 14 == 0 or s["day"] == 1],
        ))
    out = dict(schema=1, created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               days=days, seeds=seeds, presets=preset_names,
               aggregate=agg, ranking=[r[0] for r in ranking],
               runs=runs_compact)
    with open(os.path.join(out_dir, f"tournament_{stamp}.json"), "w") as f:
        json.dump(out, f, indent=1)
    with open(os.path.join(out_dir, "latest.json"), "w") as f:
        json.dump(out, f, indent=1)
    md = _tournament_markdown(out)
    with open(os.path.join(out_dir, f"tournament_{stamp}.md"), "w") as f:
        f.write(md)
    with open(os.path.join(out_dir, "latest.md"), "w") as f:
        f.write(md)

    # comparison dashboard
    try:
        from .dashboard_gen import generate_tournament_dashboard
        generate_tournament_dashboard(os.path.join(out_dir, "latest.json"),
                                      os.path.join(out_dir, "compare.html"))
    except Exception:
        pass

    if kb is not None:
        for r in results:
            kb.observe_run(r)
        kb.save()

    if not quiet:
        print("\n=== RANKING (median MRR multiple on survivors) ===")
        for i, (pname, a) in enumerate(ranking, 1):
            print(f" {i}. {pname:<16} x{a['median_mrr_multiple']:<6.1f} "
                  f"survive {a['survival_rate']:.0%} medMRR "
                  f"\u20b9{a['median_mrr']/1e5:.1f}L")
    return out


def _tournament_markdown(t: dict) -> str:
    L = []
    A = L.append
    A(f"# Strategy Tournament - {t['days']} days x {t['seeds']} seeds")
    A("")
    A("Same seeded market path per seed; only strategy differs.")
    A("")
    A("| Rank | Strategy | Survival | Median MRR | Median Cash | Med Valuation | "
      "Decisions success/fail |")
    A("|---|---|---|---|---|---|---|")
    for i, (pname, a) in enumerate(sorted(t["aggregate"].items(),
                                          key=lambda kv: kv[1]["median_mrr_multiple"],
                                          reverse=True), 1):
        A(f"| {i} | {pname} | {a['survival_rate']:.0%} | "
          f"\u20b9{a['median_mrr']/1e5:.1f}L | \u20b9{a['median_cash']/1e5:.1f}L | "
          f"\u20b9{a['median_valuation']/1e7:.1f}Cr | "
          f"{a['decision_success_rate']:.0%}/{a['decision_fail_rate']:.0%} |")
    A("")
    A("## Per-run outcomes")
    A("")
    A("| Strategy | Seed | Alive | MRR | Cash | Customers | Share |")
    A("|---|---|---|---|---|---|---|")
    for r in t["runs"]:
        A(f"| {r['strategy']} | {r['tournament_seed']} | "
          f"{'yes' if r['alive'] else '**DEAD**'} | "
          f"\u20b9{r['final']['mrr']/1e5:.1f}L | \u20b9{r['final']['cash']/1e5:.1f}L | "
          f"{r['final']['active_customers']} | {r['final']['market_share_pct']:.1f}% |")
    return "\n".join(L) + "\n"
