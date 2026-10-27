"""Push alerts through ntfy (https://ntfy.sh).

Install the free ntfy app on Android, subscribe to a long random topic name,
and store that same name in the NTFY_TOPIC repository secret.
Anyone who knows the topic name can read it, so make it hard to guess.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

STATE = Path(__file__).parent / "cache" / "alerted.json"


def _load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def pick(opps, cfg_alerts, state, now=None):
    """Choose which opportunities deserve a notification (pure, testable)."""
    now = now or datetime.now(timezone.utc)
    chosen = []
    for o in opps:
        b = o.get("best")
        if not b or b["profit_jpy"] < cfg_alerts["min_profit_jpy"] or b["margin"] < cfg_alerts["min_margin"]:
            continue
        if any(w["level"] == "block" and not w.get("country") for w in o["warnings"]):
            continue
        prev = state.get(o["id"])
        if prev and b["profit_jpy"] < prev["profit_jpy"] * (1 + cfg_alerts["realert_if_profit_up"]):
            continue
        chosen.append(o)
    chosen.sort(key=lambda o: ((o.get("deal") or {}).get("great", False), o["best"]["profit_jpy"]), reverse=True)
    return chosen[: cfg_alerts["max_per_run"]]


def _message(o, dest_names, app_url, sale):
    b = o["best"]
    great = (o.get("deal") or {}).get("great")
    title = ("🔥 " if great else "") + f"¥{b['profit_jpy']:,} profit · {o['item_name']}"
    body = (f"{o.get('title_en') or o['title_ja']}\n"
            f"Buy ¥{o['buy_jpy']:,} on Rakuten → sell to {dest_names.get(b['country'], b['country'])} "
            f"(margin {b['margin']:.0%}).")
    for t in (o.get("deal") or {}).get("tags", []):
        if t["kind"] in ("great", "lowest", "drop"):
            body += "\n" + t["text"]
    if o.get("points_jpy"):
        body += f" Includes ¥{o['points_jpy']:,} in points."
    if sale:
        body += f"\n{sale['name']} is on."
    body += "\nCheck eBay sold prices before buying."
    return {
        "title": title, "message": body, "click": o["url"], "tags": ["moneybag"],
        "priority": 5 if great else (4 if b["margin"] >= 0.25 else 3),
        "actions": [{"action": "view", "label": "Open app", "url": app_url},
                    {"action": "view", "label": "Rakuten", "url": o["url"]}],
    }


def send(opps, cfg, dest_names, sale=None, mock=False):
    """Send alerts and update state. Returns a summary dict for results.json."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    a = cfg["alerts"]
    if mock or not topic:
        return {"enabled": False, "sent": 0, "reason": "sample data" if mock else "NTFY_TOPIC not set"}
    state = _load()
    now = datetime.now(timezone.utc)
    chosen = pick(opps, a, state, now)
    sent = 0
    for o in chosen:
        msg = {"topic": topic, **_message(o, dest_names, a["app_url"], sale)}
        try:
            r = requests.post(server + "/", data=json.dumps(msg).encode("utf-8"),
                              headers={"Content-Type": "application/json"}, timeout=15)
            r.raise_for_status()
            sent += 1
            state[o["id"]] = {"profit_jpy": o["best"]["profit_jpy"], "at": now.isoformat(timespec="seconds")}
        except requests.RequestException as e:
            print(f"[alerts] failed: {e}")
    # forget entries older than 30 days so a listing can alert again later
    cutoff = now - timedelta(days=30)
    state = {k: v for k, v in state.items() if datetime.fromisoformat(v["at"]) >= cutoff}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"enabled": True, "sent": sent, "candidates": len(chosen)}
