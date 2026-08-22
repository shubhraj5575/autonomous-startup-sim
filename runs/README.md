# Run artifacts

Each `run` command creates a directory here:

```
runs/<name>/
  config.json     simulation parameters used
  result.json     full serialized run (KPI series, decisions, events, finals)
  summary.md      human-readable report
  dashboard.html  self-contained offline dashboard
```

`runs/experiments/` holds strategy tournaments (`latest.md|json` plus
timestamped copies).

Flagship runs in this repo (seed 42, balanced policy):
- `flagship_30d`, `flagship_90d`, `flagship_year1`, `flagship_5y`

Regenerate any of them:
```bash
python3 -m src.cli run --horizon year --seed 42 --name flagship_year1
```
