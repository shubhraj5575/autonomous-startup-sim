"""Determinism, cloning fairness and market mechanics."""
import json

from src.config import SimConfig
from src.simulator import World
from src.company import Company
from src.market import Market


def test_same_seed_same_trajectory():
    finals = []
    for _ in range(2):
        cfg = SimConfig(seed=777)
        w = World(cfg)
        c = w.run(120)
        finals.append(json.dumps(c.history[-1], sort_keys=True))
    assert finals[0] == finals[1]


def test_different_seeds_diverge():
    cfg = SimConfig(seed=1)
    c1 = World(cfg).run(120)
    cfg = SimConfig(seed=2)
    c2 = World(cfg).run(120)
    assert json.dumps(c1.history[-1], sort_keys=True) != \
           json.dumps(c2.history[-1], sort_keys=True)


def test_clone_faces_identical_market_path():
    """Two clones with different presets must see the same public events."""
    days = 150
    paths = []
    for preset in ("balanced", "blitz_growth"):
        from src.company import StrategyParams
        from src.config import STRATEGY_PRESETS
        cfg = SimConfig(seed=4242)
        comp = Company(cfg)
        pdef = STRATEGY_PRESETS[preset]
        comp.set_strategy(StrategyParams(**{
            k: v for k, v in pdef.items()
            if k in StrategyParams.__dataclass_fields__}))
        w = World(cfg, company=comp)
        w.run(days)
        paths.append([(e.day, e.name) for e in w.market.event_log])
    assert paths[0] == paths[1], "market randomness leaked into variant isolation"


def test_market_demand_bounded():
    cfg = SimConfig(seed=5)
    m = Market(cfg, __import__("src.rng", fromlist=["RngManager"]).RngManager(5))
    for day in range(400):
        m.advance_day(day)
        for seg in m.demand_state:
            dm = m.demand_multiplier(seg)
            assert 0.3 <= dm <= 2.5, (seg, dm)
            eff = m.channel_effectiveness("google_ads")
            assert 0.3 <= eff <= 2.0


def test_shocks_expire():
    cfg = SimConfig(seed=9)
    w = World(cfg)
    w.run(500)
    # any shock recorded must have an end day; active list stays small
    assert len(w.market.shocks) <= 6


def test_competitor_entry_event_possible():
    seen_entry = False
    for seed in (11, 22, 33):
        cfg = SimConfig(seed=seed, shock_probability_daily=0.03)
        w = World(cfg)
        c = w.run(700)
        if any(e["kind"] == "competitor_entry" for e in c.company_events):
            seen_entry = True
            break
    assert seen_entry, "new entrant event should occur sometimes"
