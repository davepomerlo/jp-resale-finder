"""Rakuten sale windows and the scan gate.

The workflow runs at 05:07 and 20:07 JST every day, plus hourly 20:37–23:37 JST.
The hourly runs only scan when a Rakuten sale is on.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
HOURLY_CRON = "37 11-14 * * *"


def _at(year, month, day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime(year, month, day, h, m, tzinfo=JST)


def windows(cfg_sales, around: datetime):
    """All sale windows for the year of `around` (and neighbours)."""
    out = []
    ss = (cfg_sales or {}).get("super_sale")
    if ss:
        for y in (around.year - 1, around.year, around.year + 1):
            for mth in ss["months"]:
                out.append({
                    "name": "楽天スーパーSALE (Rakuten Super Sale)",
                    "start": _at(y, mth, ss["start"]["day"], ss["start"]["time"]),
                    "end": _at(y, mth, ss["end"]["day"], ss["end"]["time"]),
                })
    for w in (cfg_sales or {}).get("windows") or []:
        out.append({
            "name": w["name"],
            "start": datetime.strptime(w["start"], "%Y-%m-%d %H:%M").replace(tzinfo=JST),
            "end": datetime.strptime(w["end"], "%Y-%m-%d %H:%M").replace(tzinfo=JST),
        })
    return sorted(out, key=lambda w: w["start"])


def current(cfg_sales, now: datetime = None):
    now = (now or datetime.now(JST)).astimezone(JST)
    for w in windows(cfg_sales, now):
        if w["start"] <= now <= w["end"]:
            return w
    return None


def upcoming(cfg_sales, now: datetime = None):
    now = (now or datetime.now(JST)).astimezone(JST)
    for w in windows(cfg_sales, now):
        if w["start"] > now:
            return w
    return None


def as_json(w):
    return None if not w else {"name": w["name"], "start": w["start"].isoformat(), "end": w["end"].isoformat()}


if __name__ == "__main__":
    # Gate used by the GitHub workflow: prints run=true/false to $GITHUB_OUTPUT.
    import yaml
    from pathlib import Path
    cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))
    schedule = os.environ.get("SCHEDULE", "")
    sale = current(cfg.get("sales"))
    run = schedule != HOURLY_CRON or sale is not None
    msg = f"schedule={schedule or 'manual/push'} sale={'yes: ' + sale['name'] if sale else 'no'} -> run={run}"
    print(msg)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"run={'true' if run else 'false'}\n")
    sys.exit(0)
