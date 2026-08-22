"""CLI: run simulations, strategy experiments, dashboards and reports.

Usage:
  python3 -m src.cli run --days 365 --seed 42 --name run365
  python3 -m src.cli run --horizon year
  python3 -m src.cli experiment --days 365 --seeds 6 --presets all
  python3 -m src.cli dashboard --run runs/run365
"""
from __future__ import annotations

import argparse
import json
import os
import time

from .config import SimConfig, STRATEGY_PRESETS
from .company import Company, StrategyParams
from .simulator import World
from .reporting import save_run


HORIZONS = {"30d": 30, "90d": 90, "half": 182, "year": 365, "2y": 730,
            "5y": 1825}


def _make_company(cfg, preset: str | None) -> Company:
    comp = Company(cfg)
    if preset:
        pdef = STRATEGY_PRESETS[preset]
        params = StrategyParams(
            **{k: v for k, v in pdef.items()
               if k in StrategyParams.__dataclass_fields__})
        params.preset = preset
        comp.set_strategy(params)
    return comp


def cmd_run(args):
    days = HORIZONS.get(args.horizon, args.days) if args.horizon else args.days
    cfg = SimConfig(seed=args.seed, days=days,
                    starting_capital=args.capital or 100_000.0)
    name = args.name or f"run_s{args.seed}_d{days}"
    out_dir = os.path.join(args.outdir, name)
    t0 = time.time()
    comp = _make_company(cfg, args.preset)
    world = World(cfg, company=comp)
    print(f"[run] name={name} seed={args.seed} days={days} preset={args.preset or 'balanced'}")
    comp_out = world.run(days, progress_every=max(30, days // 20), verbose=not args.quiet)
    path = save_run(cfg, world, out_dir, name)
    h = comp_out.history[-1]
    tag = "ALIVE" if comp_out.alive else "DEAD"
    print(f"[done] {tag} in {time.time()-t0:.1f}s -> {path}")
    print(f"       cash={h['cash']:,.0f} mrr={h['mrr']:,.0f} cust={h['active_customers']} "
          f"share={h['market_share_pct']:.1f}% val={h['valuation_proxy']:,.0f}")
    return 0 if comp_out.alive or not args.fail_on_death else 1


def cmd_experiment(args):
    from .experiments import run_tournament
    run_tournament(days=args.days, seeds=args.seeds,
                   presets=args.presets, out_dir=args.outdir,
                   knowledge_path=args.knowledge, quiet=args.quiet)
    return 0


def cmd_dashboard(args):
    from .dashboard_gen import generate_dashboard
    out = generate_dashboard(run_dir=args.run, out_file=args.out)
    print(f"[dashboard] wrote {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="autonomous-startup-sim")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run one simulation")
    r.add_argument("--days", type=int, default=365)
    r.add_argument("--horizon", choices=sorted(HORIZONS.keys()))
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--capital", type=float, default=100_000.0)
    r.add_argument("--preset", choices=sorted(STRATEGY_PRESETS.keys()))
    r.add_argument("--name")
    r.add_argument("--outdir", default="runs")
    r.add_argument("--quiet", action="store_true")
    r.add_argument("--fail-on-death", action="store_true")

    e = sub.add_parser("experiment", help="strategy tournament via cloned companies")
    e.add_argument("--days", type=int, default=365)
    e.add_argument("--seeds", type=int, default=5, help="number of seeds per variant")
    e.add_argument("--presets", default="all",
                   help="comma list or 'all' of: " + ",".join(STRATEGY_PRESETS))
    e.add_argument("--outdir", default="runs/experiments")
    e.add_argument("--knowledge", default="data/knowledge.json")
    e.add_argument("--quiet", action="store_true")

    d = sub.add_parser("dashboard", help="generate self-contained dashboard HTML")
    d.add_argument("--run", required=True, help="run dir containing result.json")
    d.add_argument("--out", default=None)

    args = ap.parse_args(argv)
    return {"run": cmd_run, "experiment": cmd_experiment,
            "dashboard": cmd_dashboard}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
