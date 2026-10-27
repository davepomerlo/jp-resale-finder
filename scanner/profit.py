"""Profit maths. Pure functions so they are easy to test."""
import math
from datetime import date

from textutil import median, percentile


def ems_rate(cfg_shipping, zone: int, weight_g: int, on: date = None):
    """Japan Post EMS price for a zone and packed weight, using the table valid on `on`."""
    on = on or date.today()
    tables = sorted(cfg_shipping["tables"], key=lambda t: t["valid_from"])
    table = tables[0]
    for t in tables:
        if date.fromisoformat(t["valid_from"]) <= on:
            table = t
    bands = {int(k): v for k, v in table[f"zone{zone}"].items()}
    for limit in sorted(bands):
        if weight_g <= limit:
            return bands[limit]
    return None  # heavier than table — caller should flag it


def sale_price(jp_comps, all_comps, ebay_cfg):
    """Target listing price in the marketplace's currency: median of Japan-located
    competitors (if enough of them), otherwise of all sellers, slightly undercut."""
    use = jp_comps if len(jp_comps) >= ebay_cfg["min_jp_comps"] else all_comps
    basis = "Japan-based sellers" if use is jp_comps else "all sellers"
    totals = [c["total"] for c in use if c.get("total")]
    med = median(totals)
    if med is None:
        return None, {"basis": "none", "count": 0}
    return round(med * ebay_cfg["undercut"], 2), {
        "basis": basis,
        "count": len(totals),
        "median": round(med, 2),
        "p25": round(percentile(totals, 0.25), 2),
        "p75": round(percentile(totals, 0.75), 2),
    }


def points_value(price_jpy, shop_rate_pct, cfg_points):
    """楽天ポイント (Rakuten points) earned, valued in yen. Points are calculated on the tax-excluded price."""
    if not cfg_points or not cfg_points.get("enabled"):
        return 0
    rate = (shop_rate_pct or 1) + cfg_points.get("extra_rate_pct", 0)
    pts = math.floor(price_jpy / 1.1 * rate / 100)
    return round(pts * cfg_points.get("point_value_jpy", 1.0))


def compute(buy_jpy, postage_included, sale_jpy, dest, weight_g, category, cfg, per_order_jpy,
            points_jpy=0, shipping_override_jpy=None, on: date = None):
    """Full cost breakdown for one destination. sale_jpy = listing price converted to yen."""
    e = cfg["ebay"]
    fvf = e["final_value_fee_by_category"].get(category, e["final_value_fee"])
    fees_jpy = (sale_jpy * (fvf + e["international_fee"]) + per_order_jpy) * (1 + e["fee_tax"])
    revenue_jpy = sale_jpy * (1 - cfg["fx"]["conversion_cost"])
    ship_jpy = shipping_override_jpy if shipping_override_jpy is not None else \
        ems_rate(cfg["shipping"], dest["zone"], weight_g, on)
    if ship_jpy is None:
        return {"ok": False, "reason": f"{weight_g} g is over the shipping table"}
    duty_jpy = sale_jpy * dest.get("duty", 0) + (dest.get("ddp_prepay_fee_jpy", 0) if dest.get("duty") else 0)
    domestic = 0 if postage_included else cfg["costs"]["rakuten_domestic_postage_jpy"]
    cost_jpy = buy_jpy + domestic - points_jpy
    pack = cfg["costs"]["packaging_jpy"]

    profit = revenue_jpy - fees_jpy - ship_jpy - duty_jpy - cost_jpy - pack
    return {
        "ok": True,
        "sale_jpy": round(sale_jpy),
        "revenue_jpy": round(revenue_jpy),
        "ebay_fees_jpy": round(fees_jpy),
        "shipping_jpy": round(ship_jpy),
        "duty_jpy": round(duty_jpy),
        "buy_jpy": buy_jpy,
        "points_jpy": points_jpy,
        "domestic_postage_jpy": domestic,
        "packaging_jpy": pack,
        "profit_jpy": round(profit),
        "margin": round(profit / revenue_jpy, 4) if revenue_jpy else 0,
        "roi": round(profit / cost_jpy, 4) if cost_jpy > 0 else 0,
    }
