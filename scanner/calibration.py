"""Read your real sales and turn them into overrides for the profit estimate: actual eBay fee rate,
actual shipping per item and country, return/damage rate, and how fast each item sells.

Accepts either:
  * the "Sales" tab of the Google Sheet downloaded as CSV (title rows above the headings are skipped), or
  * a plain CSV with these columns:
    date_sold,item_id,country,currency,sale_local,sale_jpy,ebay_fees_jpy,shipping_jpy,duty_jpy,buy_jpy,days_to_sell,returned
"""
import csv
from pathlib import Path

from textutil import median

HERE = Path(__file__).parent


def _num(v):
    if v is None:
        return None
    s = str(v).replace("¥", "").replace(",", "").replace("$", "").strip()
    if s in ("", "-", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _yes(v):
    return str(v or "").strip().lower() in ("yes", "y", "true", "1", "はい", "返品")


# Google Sheet "Sales" headings -> plain column names (matched by the start of the heading)
SHEET_HEADINGS = {
    "date sold": "date_sold", "watchlist id": "item_id", "country": "country", "currency": "currency",
    "sale price incl": "sale_local", "sale ¥": "sale_jpy", "ebay fees": "ebay_fees_jpy",
    "shipping paid": "shipping_jpy", "duty prepaid": "duty_jpy", "item cost": "buy_jpy",
    "days to sell": "days_to_sell", "returned": "returned",
}


def _records(f):
    """Yield dicts keyed by the plain column names, from either CSV layout."""
    rows = list(csv.reader(f))
    for i, row in enumerate(rows):
        cells = [c.strip().lower() for c in row]
        if "date_sold" in cells:                       # plain layout
            keys = cells
            break
        if "date sold" in cells and "sale ¥" in cells:  # Google Sheet "Sales" tab
            keys = []
            for c in cells:
                keys.append(next((v for k, v in SHEET_HEADINGS.items() if c.startswith(k)), c))
            break
    else:
        return
    for row in rows[i + 1:]:
        yield {k: (row[j] if j < len(row) else "") for j, k in enumerate(keys)}


def load(cfg):
    c = cfg.get("calibration") or {}
    path = HERE / c.get("file", "calibration/sales.csv")
    rows = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            for r in _records(f):
                if not (r.get("item_id") and _num(r.get("sale_jpy"))):
                    continue
                rows.append({
                    "date": (r.get("date_sold") or "").strip(),
                    "item_id": r["item_id"].strip(),
                    "country": (r.get("country") or "").strip().upper(),
                    "sale_jpy": _num(r.get("sale_jpy")),
                    "fees": _num(r.get("ebay_fees_jpy")),
                    "ship": _num(r.get("shipping_jpy")),
                    "days": _num(r.get("days_to_sell")),
                    "returned": _yes(r.get("returned")),
                })
    return summarise(rows, c)


def summarise(rows, c):
    out = {"sales": len(rows), "fee_rate": None, "return_rate": None, "items": {}}
    fee_rows = [r for r in rows if r["fees"] is not None]
    if len(fee_rows) >= c.get("min_sales_for_fees", 5):
        out["fee_rate"] = round(sum(r["fees"] for r in fee_rows) / sum(r["sale_jpy"] for r in fee_rows), 4)
    if len(rows) >= c.get("min_sales_for_returns", 10):
        out["return_rate"] = round(sum(1 for r in rows if r["returned"]) / len(rows), 4)
    for r in rows:
        it = out["items"].setdefault(r["item_id"], {"sales": 0, "_days": [], "_ship": {}, "last": None})
        it["sales"] += 1
        if r["days"] is not None:
            it["_days"].append(r["days"])
        if r["ship"] is not None and r["country"]:
            it["_ship"].setdefault(r["country"], []).append(r["ship"])
        if not it["last"] or r["date"] >= it["last"]["date"]:
            it["last"] = {"date": r["date"], "country": r["country"], "sale_jpy": round(r["sale_jpy"])}
    for it in out["items"].values():
        it["days_to_sell"] = median(it.pop("_days")) if it["_days"] else None
        it["shipping_by_country"] = {k: round(sum(v) / len(v)) for k, v in it.pop("_ship").items()}
    return out


def overrides(cal, item_id, country):
    """Values to pass to profit.compute(cal=...) for one item and destination."""
    it = cal["items"].get(item_id, {})
    return {
        "fee_rate": cal.get("fee_rate"),
        "shipping_jpy": it.get("shipping_by_country", {}).get(country),
        "reserve": cal.get("return_rate"),
    }


def sell_speed(cal, item_cfg):
    """(days_to_sell, source) from your sales first, else the watchlist's manual value (e.g. from Terapeak)."""
    it = cal["items"].get(item_cfg["id"], {})
    if it.get("days_to_sell") is not None:
        return it["days_to_sell"], f"your {it['sales']} sale{'s' if it['sales'] != 1 else ''}"
    if item_cfg.get("days_to_sell"):
        return float(item_cfg["days_to_sell"]), "watchlist estimate"
    return None, None
