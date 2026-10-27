"""Profit maths. Pure functions so they are easy to test."""
from datetime import date


def ems_rate(cfg_shipping, zone: int, weight_g: int, on: date = None):
    """Japan Post EMS price for a zone and packed weight, using the table valid on `on`."""
    on = on or date.today()
    tables = sorted(cfg_shipping["tables"], key=lambda t: t["valid_from"])
    table = None
    for t in tables:
        if date.fromisoformat(t["valid_from"]) <= on:
            table = t
    if table is None:
        table = tables[0]
    bands = {int(k): v for k, v in table[f"zone{zone}"].items()}
    for limit in sorted(bands):
        if weight_g <= limit:
            return bands[limit]
    return None  # heavier than table — caller should flag it


def sale_price_usd(jp_comps, all_comps, ebay_cfg):
    """Target listing price: median of Japan-located competitors (if enough), slightly undercut."""
    from textutil import median, percentile
    use = jp_comps if len(jp_comps) >= ebay_cfg["min_jp_comps"] else all_comps
    basis = "Japan-based sellers" if use is jp_comps else "all sellers"
    totals = [c["total_usd"] for c in use if c.get("total_usd")]
    med = median(totals)
    if med is None:
        return None, {"basis": "none", "count": 0}
    return round(med * ebay_cfg["undercut"], 2), {
        "basis": basis,
        "count": len(totals),
        "median_usd": round(med, 2),
        "p25_usd": round(percentile(totals, 0.25), 2),
        "p75_usd": round(percentile(totals, 0.75), 2),
    }


def compute(buy_jpy, postage_included, sale_usd, fx, dest, weight_g, category, cfg,
            shipping_override_jpy=None, on: date = None):
    """Return a dict with the full cost breakdown for one destination."""
    e = cfg["ebay"]
    fvf = e["final_value_fee_by_category"].get(category, e["final_value_fee"])
    fee_usd = sale_usd * (fvf + e["international_fee"]) + e["per_order_fee_usd"]
    fee_usd *= 1 + e["fee_tax"]

    revenue_jpy = sale_usd * fx * (1 - cfg["fx"]["conversion_cost"])
    fees_jpy = fee_usd * fx
    if shipping_override_jpy is not None:
        ship_jpy = shipping_override_jpy
    else:
        ship_jpy = ems_rate(cfg["shipping"], dest["zone"], weight_g, on)
    duty_jpy = sale_usd * fx * dest.get("duty", 0) + dest.get("ddp_prepay_fee_jpy", 0)
    domestic = 0 if postage_included else cfg["costs"]["rakuten_domestic_postage_jpy"]
    cost_jpy = buy_jpy + domestic
    pack = cfg["costs"]["packaging_jpy"]

    if ship_jpy is None:
        return {"ok": False, "reason": f"{weight_g} g is over the shipping table"}

    profit = revenue_jpy - fees_jpy - ship_jpy - duty_jpy - cost_jpy - pack
    return {
        "ok": True,
        "revenue_jpy": round(revenue_jpy),
        "ebay_fees_jpy": round(fees_jpy),
        "shipping_jpy": round(ship_jpy),
        "duty_jpy": round(duty_jpy),
        "buy_jpy": buy_jpy,
        "domestic_postage_jpy": domestic,
        "packaging_jpy": pack,
        "profit_jpy": round(profit),
        "margin": round(profit / revenue_jpy, 4) if revenue_jpy else 0,
        "roi": round(profit / cost_jpy, 4) if cost_jpy else 0,
    }
