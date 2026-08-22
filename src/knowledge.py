"""Cross-run knowledge base: strategic intelligence that persists between runs.

The engine learns within a run; the KnowledgeBase carries forward what was
learned across runs - channel efficiency priors, price elasticity estimates,
and strategy-outcome statistics. Every observation is empirical (measured from
completed runs), never asserted.
"""
from __future__ import annotations

import json
import os
import statistics as st
import time


def _blank():
    return dict(
        schema=1,
        updated_utc=None,
        runs_observed=0,
        channel_scores={},
        channel_samples={},
        price_elasticity=dict(mean=-1.3, n=0),
        strategy_outcomes={},
        churn_lessons={},
    )


class KnowledgeBase:
    def __init__(self, path: str):
        self.path = path
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    self.data = json.load(f)
                # ensure all keys exist
                for k, v in _blank().items():
                    self.data.setdefault(k, v)
            except Exception:
                self.data = _blank()
        else:
            self.data = _blank()

    # ------------------------------------------------------------------ apply -
    def apply_to(self, company) -> None:
        """Seed a new company's learned state from accumulated evidence."""
        d = self.data
        for ch, score in d["channel_scores"].items():
            if ch in company.marketing.channels:
                company.marketing.channels[ch].bandit_score = float(score)
        n = d["price_elasticity"]["n"]
        if n >= 3:
            company.price_elasticity_est = d["price_elasticity"]["mean"]

    # --------------------------------------------------------------- observe --
    def observe_run(self, result: dict) -> None:
        """Update priors from one completed run's serialized result."""
        d = self.data
        d["runs_observed"] += 1
        d["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        fin = result["final"]
        days = max(result["days_run"], 1)

        # channel learning: cumulative CPL per channel this run, discounted by
        # how the run went (dead companies' data counts less)
        weight = 1.0 if result["alive"] else 0.35
        mrr_growth_quality = min(1.5, (fin["mrr"] / 100_000.0))
        for ch, cs in result.get("channel_summary", {}).items():
            cum_spend = cs.get("cum_spend", 0)
            leads30 = cs.get("leads30", 0)
            if leads30 <= 0 or cum_spend <= 0:
                continue
            eff = cs.get("score", 1.0)
            prev_n = d["channel_samples"].get(ch, 0)
            prev = d["channel_scores"].get(ch, 1.0)
            alpha = min(0.4, 2.0 / (prev_n + 2)) * weight
            target = max(0.05, min(eff * (0.7 + 0.3 * min(mrr_growth_quality, 1.5)), 3.0))
            d["channel_scores"][ch] = (1 - alpha) * prev + alpha * target
            d["channel_samples"][ch] = prev_n + 1

        # elasticity
        pe = d["price_elasticity"]
        est = fin.get("elasticity_est")
        if est is not None:
            k = min(0.25, 3.0 / (pe["n"] + 3))
            pe["mean"] = (1 - k) * pe["mean"] + k * est
            pe["n"] += 1

        # strategy outcomes
        so = d["strategy_outcomes"].setdefault(result.get("strategy", "balanced"),
                                               dict(runs=0, survivals=0,
                                                    mrr_multiples=[], valuations=[]))
        so["runs"] += 1
        so["survivals"] += 1 if result["alive"] else 0
        mult = fin["mrr"] / max(result["config"].get("starting_capital", 100_000), 1)
        so["mrr_multiples"].append(round(mult, 3))
        so["valuations"].append(round(fin["valuation_proxy"], 0))
        so["mrr_multiples"] = so["mrr_multiples"][-200:]
        so["valuations"] = so["valuations"][-200:]

        # failure lessons
        for dec in result.get("decisions", []):
            if dec.get("verdict") == "fail" and dec.get("lesson"):
                d["churn_lessons"][dec["lesson"]] = d["churn_lessons"].get(dec["lesson"], 0) + 1

    def best_strategy(self) -> str | None:
        """Preset with the highest median MRR multiple (min 3 runs)."""
        scored = []
        for name, so in self.data["strategy_outcomes"].items():
            if so["runs"] >= 3 and so["mrr_multiples"]:
                scored.append((st.median(so["mrr_multiples"]), name))
        return max(scored)[1] if scored else None

    def summary(self) -> dict:
        d = self.data
        out = dict(runs_observed=d["runs_observed"],
                   channel_scores={k: round(v, 3) for k, v in d["channel_scores"].items()},
                   price_elasticity=dict(mean=round(d["price_elasticity"]["mean"], 3),
                                         n=d["price_elasticity"]["n"]),
                   strategies={})
        for name, so in d["strategy_outcomes"].items():
            out["strategies"][name] = dict(
                runs=so["runs"],
                survival_rate=round(so["survivals"] / max(so["runs"], 1), 2),
                median_mrr_multiple=(round(st.median(so["mrr_multiples"]), 1)
                                     if so["mrr_multiples"] else None),
            )
        return out

    def save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=1)
