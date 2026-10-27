"""Price history built from the app's own scans, and the deal tags derived from it.

Stored in docs/data/history.json (the app also reads it for the price charts):
{
  "mode": "live" | "sample",
  "items":    {item_id: {"YYYY-MM-DD": {"rak_min": ¥, "rak_med": ¥, "ebay_jpy": {"US": ¥, ...}}}},
  "listings": {listing_id: {"first_seen": date, "last_seen": date, "last_price": ¥, "low": ¥}}
}
Rakuten has no price-history API, so history starts with your first scan.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from textutil import median

FILE = Path(__file__).resolve().parent.parent / "docs" / "data" / "history.json"
SAMPLE = Path(__file__).parent / "fixtures" / "history_sample.json"


def load(mode: str, today: date):
    if mode == "sample":
        raw = json.loads(SAMPLE.read_text(encoding="utf-8")) if SAMPLE.exists() else {}
        # sample file stores day offsets ("-1", "-2", ...) so it always lines up with today
        items = {iid: {(today + timedelta(days=int(k))).isoformat(): v for k, v in days.items()}
                 for iid, days in raw.get("items", {}).items()}
        return {"mode": "sample", "items": items, "listings": {}}
    try:
        h = json.loads(FILE.read_text(encoding="utf-8"))
        if h.get("mode") == "live":
            h["_had_listings"] = bool(h.get("listings"))
            return h
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"mode": "live", "items": {}, "listings": {}}  # never mix sample history into live data


def _past(hist, item_id, today, window):
    start = (today - timedelta(days=window)).isoformat()
    days = hist["items"].get(item_id, {})
    return {d: v for d, v in days.items() if start <= d < today.isoformat()}


def tags_for(hist, item_id, listing_id, price, today: date, cfg_h, now: datetime = None):
    """Deal tags for one Rakuten listing, comparing against previous days only."""
    window, min_days = cfg_h["window_days"], cfg_h["min_days"]
    past = _past(hist, item_id, today, window)
    out = {"tags": [], "great": False, "pct_below_typical": None, "typical": None, "low": None,
           "history_days": len(past)}

    lst = hist["listings"].get(listing_id)
    now = now or datetime.now(timezone.utc)
    flash = None
    if lst:
        day_ago = (now - timedelta(hours=24)).isoformat()
        recent = [(t, p) for t, p in lst.get("recent", []) if t >= day_ago]
        if recent:
            t_hi, p_hi = max(recent, key=lambda tp: tp[1])
            if price <= p_hi * (1 - cfg_h.get("flash_drop_min", 0.05)):
                jst = datetime.fromisoformat(t_hi).astimezone(timezone(timedelta(hours=9)))
                flash = {"kind": "flash", "text": f"⚡ Price cut {1 - price / p_hi:.0%} since {jst:%H:%M} JST — may be time-limited"}
                out["tags"].append(flash)
                out["flash"] = True
    if flash:
        pass
    elif lst and lst["last_price"] and price <= lst["last_price"] * (1 - cfg_h["price_drop_min"]):
        out["tags"].append({"kind": "drop",
                            "text": f"↓ ¥{lst['last_price'] - price:,} since {lst['last_seen']}"})
    elif not lst and hist.get("_had_listings") and len(past) >= 1:
        out["tags"].append({"kind": "new", "text": "🆕 New listing"})

    if len(past) < min_days:
        out["tags"].append({"kind": "building", "text": f"Price history: {len(past)} of {min_days} days"})
        return out

    typical = median([v["rak_med"] for v in past.values() if v.get("rak_med")])
    low = min(v["rak_min"] for v in past.values() if v.get("rak_min"))
    out.update(typical=round(typical), low=low)
    below = 1 - price / typical if typical else 0
    out["pct_below_typical"] = round(below, 4)
    if below >= cfg_h["great_deal_below_typical"]:
        out["great"] = True
        out["tags"].append({"kind": "great",
                            "text": f"🔥 Great deal: {below:.0%} below the {window}-day typical (¥{round(typical):,})"})
    if price < low:
        out["tags"].append({"kind": "lowest", "text": f"📉 Lowest price in {window} days (previous low ¥{low:,})"})
    elif below <= -0.05:
        out["tags"].append({"kind": "high", "text": f"{-below:.0%} above the {window}-day typical price"})
    return out


def ebay_trend(hist, item_id, code, now_jpy, today: date, window: int):
    """Change in the eBay sell price vs. the start of the window, or None."""
    past = _past(hist, item_id, today, window)
    vals = [v.get("ebay_jpy", {}).get(code) for _, v in sorted(past.items())]
    vals = [v for v in vals if v]
    if len(vals) < 5 or not now_jpy:
        return None
    base = median(vals[: max(3, len(vals) // 3)])
    return round(now_jpy / base - 1, 4)


def update(hist, item_id, today: date, matched_prices, ebay_jpy, listing_prices, now: datetime = None):
    d = today.isoformat()
    day = hist["items"].setdefault(item_id, {}).get(d, {})
    if matched_prices:
        day["rak_min"] = min([day.get("rak_min") or 10**12] + list(matched_prices))
        day["rak_med"] = round(median(matched_prices))
    day["ebay_jpy"] = {**day.get("ebay_jpy", {}), **{k: round(v) for k, v in ebay_jpy.items() if v}}
    hist["items"][item_id][d] = day
    now = now or datetime.now(timezone.utc)
    stamp, keep_after = now.isoformat(timespec="minutes"), (now - timedelta(hours=48)).isoformat()
    for lid, p in listing_prices.items():
        rec = hist["listings"].get(lid)
        if rec:
            rec.update(last_seen=d, last_price=p, low=min(rec["low"], p))
        else:
            rec = hist["listings"][lid] = {"first_seen": d, "last_seen": d, "last_price": p, "low": p}
        rec["recent"] = [tp for tp in rec.get("recent", []) if tp[0] >= keep_after] + [[stamp, p]]


def series(hist, item_id, today: date, window: int):
    """Compact series for the app's mini chart: [[date, rak_min, rak_med, ebay_us_jpy], ...]."""
    start = (today - timedelta(days=window)).isoformat()
    days = hist["items"].get(item_id, {})
    return [[d, v.get("rak_min"), v.get("rak_med"), v.get("ebay_jpy", {}).get("US")]
            for d, v in sorted(days.items()) if d >= start]


def save(hist, today: date, keep_days: int):
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    for iid in list(hist["items"]):
        hist["items"][iid] = {d: v for d, v in hist["items"][iid].items() if d >= cutoff}
    hist["listings"] = {k: v for k, v in hist["listings"].items() if v["last_seen"] >= cutoff}
    hist = {k: v for k, v in hist.items() if not k.startswith("_")}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
