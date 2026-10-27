"""Profit maths. Pure functions so they are easy to test."""
import math
from datetime import date

from textutil import median, percentile


def _table_rate(tables, zone: int, weight_g: int, on: date):
    tables = sorted(tables, key=lambda t: t["valid_from"])
    table = tables[0]
    for t in tables:
        if date.fromisoformat(t["valid_from"]) <= on:
            table = t
    bands = {int(k): v for k, v in table.get(f"zone{zone}", {}).items()}
    for limit in sorted(bands):
        if weight_g <= limit:
            return bands[limit]
    return None


def service_rate(cfg_shipping, service: str, zone: int, weight_g: int, on: date = None):
    """Price of one Japan Post service for a zone and packed weight, using the table valid on `on`."""
    svc = cfg_shipping["services"][service]
    return _table_rate(svc["tables"], zone, weight_g, on or date.today())


def ems_rate(cfg_shipping, zone, weight_g, on=None):
    return service_rate(cfg_shipping, "EMS", zone, weight_g, on)


def cheapest_shipping(cfg_shipping, zone: int, weight_g: int, on: date = None):
    """(price, service_key) of the cheapest allowed service, or (None, None)."""
    best = (None, None)
    for svc in cfg_shipping.get("allowed_services") or ["EMS"]:
        p = service_rate(cfg_shipping, svc, zone, weight_g, on)
        if p is not None and (best[0] is None or p < best[0]):
            best = (p, svc)
    return best


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
            points_jpy=0, shipping_override_jpy=None, on: date = None, cal=None):
    """Full cost breakdown for one destination. sale_jpy = listing price converted to yen.
    `cal` = calibration overrides from your own sales: {"fee_rate", "shipping_jpy", "reserve"}."""
    cal = cal or {}
    e = cfg["ebay"]
    if cal.get("fee_rate") is not None:
        fees_jpy = sale_jpy * cal["fee_rate"]
        fee_source = "your sales"
        fee_tax_part = fees_jpy * e["fee_tax"] / (1 + e["fee_tax"])
    else:
        fvf = e["final_value_fee_by_category"].get(category, e["final_value_fee"])
        pre_tax = sale_jpy * (fvf + e["international_fee"]) + per_order_jpy
        fees_jpy = pre_tax * (1 + e["fee_tax"])
        fee_tax_part = pre_tax * e["fee_tax"]
        fee_source = "assumed rates"
    revenue_jpy = sale_jpy * (1 - cfg["fx"]["conversion_cost"])

    if shipping_override_jpy is not None:
        ship_jpy, service, ship_source = shipping_override_jpy, "fixed", "watchlist"
    elif cal.get("shipping_jpy") is not None:
        ship_jpy, service, ship_source = cal["shipping_jpy"], "your average", "your sales"
    else:
        ship_jpy, service = cheapest_shipping(cfg["shipping"], dest["zone"], weight_g, on)
        ship_source = "Japan Post rates"
    if ship_jpy is None:
        return {"ok": False, "reason": f"{weight_g} g is over the shipping tables"}

    duty_jpy = sale_jpy * dest.get("duty", 0) + (dest.get("ddp_prepay_fee_jpy", 0) if dest.get("duty") else 0)
    domestic = 0 if postage_included else cfg["costs"]["rakuten_domestic_postage_jpy"]
    pack = cfg["costs"]["packaging_jpy"]
    reserve_rate = cal.get("reserve")
    if reserve_rate is None:
        rb = (cfg.get("risk") or {}).get("reserve_by_category", {})
        reserve_rate = rb.get(category, rb.get("default", 0))
    reserve_jpy = sale_jpy * reserve_rate

    refund_jpy = 0
    if (cfg.get("tax") or {}).get("consumption_tax_refund"):
        # input tax in Rakuten price, domestic postage, packaging and eBay fees (international postage is tax-exempt)
        refund_jpy = (buy_jpy + domestic + pack) * 10 / 110 + fee_tax_part

    cost_jpy = buy_jpy + domestic - points_jpy
    profit = revenue_jpy - fees_jpy - ship_jpy - duty_jpy - cost_jpy - pack - reserve_jpy + refund_jpy
    return {
        "ok": True,
        "sale_jpy": round(sale_jpy),
        "revenue_jpy": round(revenue_jpy),
        "ebay_fees_jpy": round(fees_jpy), "fee_source": fee_source,
        "shipping_jpy": round(ship_jpy), "shipping_service": service, "shipping_source": ship_source,
        "duty_jpy": round(duty_jpy),
        "buy_jpy": buy_jpy,
        "points_jpy": points_jpy,
        "domestic_postage_jpy": domestic,
        "packaging_jpy": pack,
        "reserve_jpy": round(reserve_jpy), "reserve_rate": reserve_rate,
        "tax_refund_jpy": round(refund_jpy),
        "profit_jpy": round(profit),
        "margin": round(profit / revenue_jpy, 4) if revenue_jpy else 0,
        "roi": round(profit / cost_jpy, 4) if cost_jpy > 0 else 0,
    }
