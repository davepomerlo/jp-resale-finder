"""Japan Resale Finder — scan.

For each watchlist item:
  1. find the cheapest matching listings on 楽天市場 (Rakuten Ichiba), incl. 楽天ポイント (points)
  2. for every destination, find comparable listings on that country's eBay site
     (eBay.com, .ca, .co.uk, .com.au, .de) — Japan-based sellers first — in local currency
  3. convert to yen and estimate profit per destination
  4. attach legal / shipping / practical warnings from rules.yaml
  5. send push alerts for new strong deals (ntfy)
Writes docs/data/results.json for the app.

Usage:
  python scanner/scan.py          # live (needs API keys in env)
  python scanner/scan.py --mock   # sample data from scanner/fixtures/
"""
import argparse
import json
import os
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import alerts  # noqa: E402
import history  # noqa: E402
import profit  # noqa: E402
import rules as rules_mod  # noqa: E402
import saleinfo  # noqa: E402
import sources  # noqa: E402
import trust  # noqa: E402
from textutil import contains_all, contains_any, median  # noqa: E402
from translate import Translator  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).parent
OUT = ROOT / "docs" / "data" / "results.json"


def load(name):
    return yaml.safe_load((HERE / name).read_text(encoding="utf-8"))


def ebay_links(site, q):
    base = f"https://{site}/sch/i.html?_nkw=" + quote_plus(q)
    return {"active_url": base, "sold_url": base + "&LH_Sold=1&LH_Complete=1"}


def local_band(price_usd, cur, jpy):
    """Convert the watchlist's USD price band into a marketplace's currency (a little wider)."""
    if not price_usd:
        return None
    k = jpy["USD"] / jpy[cur]
    return [price_usd[0] * k * 0.8, price_usd[1] * k * 1.2]


def run(mock=False, today=None, now=None):
    cfg, watch, rules = load("config.yaml"), load("watchlist.yaml"), load("rules.yaml")
    today = today or date.today()
    rak = sources.MockRakuten() if mock else sources.Rakuten()
    ebay = sources.MockEbay() if mock else sources.Ebay()
    jpy, fx_src = sources.jpy_rates(cfg["fx"]["fallback_jpy_per"], mock=mock)
    tr = Translator(mock=mock)
    dests = cfg["destinations"]
    per_order_jpy = cfg["ebay"]["per_order_fee_usd"] * jpy["USD"]
    sale_now = saleinfo.current(cfg.get("sales"), now)
    hist = history.load("sample" if mock else "live", today)
    cfg_h, cfg_t = cfg["history"], cfg.get("trust", {})

    items_out, opps, errors = [], [], []

    for it in watch["items"]:
        info = {k: it.get(k) for k in ("id", "name", "category", "rakuten", "ebay")}
        info["label"] = rules["categories"].get(it["category"], {}).get("label", it["category"])
        info["rakuten_search_url"] = "https://search.rakuten.co.jp/search/mall/" + quote_plus(it["rakuten"]) + "/"
        try:
            def keeper(extra_must):
                must = list(it.get("must_include") or []) + list(extra_must or [])
                return lambda c: contains_all(c["title"], must) and not contains_any(c["title"], it.get("exclude"))
            keep = keeper(it.get("ebay_must_include"))
            keep_r = keeper(it.get("rakuten_must_include"))
            cond = it.get("condition", "ANY")

            # --- eBay comps per destination marketplace
            market = {}
            for code, d in dests.items():
                band = local_band(it.get("price_usd"), d["currency"], jpy)
                kw = dict(marketplace=d["marketplace"], currency=d["currency"], ship_to=code,
                          price_range=band, condition=cond, limit=cfg["scan"]["ebay_limit"],
                          exclude_sellers=cfg_t.get("ebay", {}).get("exclude_sellers"))
                try:
                    all_c = [c for c in ebay.search(it["ebay"], **kw) if keep(c)]
                    jp_c = [c for c in ebay.search(it["ebay"], location_jp=True, **kw) if keep(c)]
                except Exception as e:  # one marketplace failing shouldn't kill the item
                    all_c, jp_c = [], []
                    errors.append({"item": it["id"], "error": f"{d['marketplace']}: {e}"})
                all_c, removed = trust.clean_ebay(all_c, cfg_t, today)
                jp_c, _ = trust.clean_ebay(jp_c, cfg_t, today)
                local, stats = profit.sale_price(jp_c, all_c, cfg["ebay"])
                stats["filtered"] = removed
                stats.update({"jp_count": len(jp_c), "all_count": len(all_c),
                              "non_jp_count": len([c for c in all_c if c.get("country") != "JP"]),
                              "currency": d["currency"], "site": d["site"], **ebay_links(d["site"], it["ebay"])})
                stats["examples"] = [{k: c[k] for k in ("title", "total", "url", "country")}
                                     for c in sorted(jp_c or all_c, key=lambda c: c["total"])[:3]]
                market[code] = {"local": local, "stats": stats}

            us = market.get("US", {})
            us_ok = us.get("local") and us["stats"]["count"] >= 1
            for code, m in market.items():
                enough = m["local"] and m["stats"]["count"] >= cfg["ebay"]["min_local_comps"]
                if enough:
                    m["sale_jpy"] = m["local"] * jpy[dests[code]["currency"]]
                    m["price_source"] = "local"
                elif us_ok:
                    m["sale_jpy"] = us["local"] * jpy["USD"]
                    m["price_source"] = "eBay.com (too few local listings)"
                else:
                    m["sale_jpy"] = None
                    m["price_source"] = "none"

            info["comps_by_dest"] = {c: {**m["stats"], "local_price": m["local"], "price_source": m["price_source"]}
                                     for c, m in market.items()}
            info["comps"] = market["US"]["stats"] if "US" in market else {}
            info["sale_usd"] = us.get("local")
            info.update({k: info["comps"].get(k) for k in ("active_url", "sold_url")})

            # --- Rakuten candidates
            pr = it.get("price_jpy") or [None, None]
            found = rak.search(it["rakuten"], exclude=it.get("exclude"), min_price=pr[0], max_price=pr[1],
                               hits=cfg["scan"]["rakuten_hits"])
            matched = [r for r in found if keep_r(r)
                       and (not pr[0] or r["price_jpy"] >= pr[0]) and (not pr[1] or r["price_jpy"] <= pr[1])]
            hidden = []
            for r in matched:
                r["trust_score"], r["trust_reasons"], r["trust_hidden"] = trust.rakuten_score(r, cfg_t)
                if r["trust_hidden"]:
                    hidden.append({"shop": r["shop"], "title": r["title"][:60],
                                   "why": "; ".join(t for k, t in r["trust_reasons"] if k == "bad")})
            matched = [r for r in matched if not r["trust_hidden"]]
            info["rakuten_hidden"] = hidden
            have_price = any(m["sale_jpy"] for m in market.values())
            info["rakuten_found"], info["rakuten_matched"] = len(found), len(matched)
            info["status"] = "ok" if matched and have_price else ("no eBay comps" if not have_price else "no Rakuten match")
            items_out.append(info)
            if not (matched and have_price):
                history.update(hist, it["id"], today, [r["price_jpy"] for r in matched], {}, {})
                info["history"] = history.series(hist, it["id"], today, cfg_h["window_days"])
                continue

            rak_median = median([r["price_jpy"] for r in matched])
            cands = sorted(matched, key=lambda r: r["price_jpy"])[: cfg["scan"]["candidates_per_item"]]
            translations = tr.translate_many([c["title"] for c in cands])

            item_hist_series = None
            for c in cands:
                opp_id = f"{it['id']}::{c.get('item_code') or c['url']}"
                deal = history.tags_for(hist, it["id"], opp_id, c["price_jpy"], today, cfg_h)
                title_en = translations.get(c["title"])
                warns, blocked = rules_mod.warnings_for(it, c["title"], title_en, rules, list(dests))
                pts = profit.points_value(c["price_jpy"], c.get("point_rate"), cfg.get("points"))
                per = {}
                for code, d in dests.items():
                    m = market[code]
                    if not m["sale_jpy"]:
                        per[code] = {"ok": False, "reason": "no eBay price", "blocked": code in blocked}
                        continue
                    res = profit.compute(c["price_jpy"], c["postage_included"], m["sale_jpy"], d, it["weight_g"],
                                         it["category"], cfg, per_order_jpy, pts,
                                         it.get("shipping_override_jpy"), on=today)
                    res.update({"blocked": code in blocked, "price_source": m["price_source"],
                                "sale_local": m["local"] if m["price_source"] == "local" else us.get("local"),
                                "currency": d["currency"] if m["price_source"] == "local" else "USD",
                                "comp_count": m["stats"]["count"] if m["price_source"] == "local" else us["stats"]["count"],
                                "comp_basis": m["stats"]["basis"] if m["price_source"] == "local" else us["stats"]["basis"]})
                    per[code] = res
                allowed = {k: v for k, v in per.items() if v["ok"] and not v["blocked"]}
                best_code = max(allowed, key=lambda k: allowed[k]["profit_jpy"]) if allowed else None
                best = allowed.get(best_code) if best_code else None

                n_comps = (best or {}).get("comp_count", 0)
                if best and n_comps < 3:
                    warns.append({"level": "caution", "scope": "data",
                                  "text": f"Only {n_comps} comparable eBay listings — price estimate is shaky. Check sold prices."})
                if best and best["price_source"] != "local":
                    warns.append({"level": "info", "scope": "data",
                                  "text": f"Few listings on {dests[best_code]['site']} — using the eBay.com price for {dests[best_code]['name']}."})
                if rak_median and c["price_jpy"] < 0.6 * rak_median and len(matched) >= 3:
                    warns.append({"level": "caution", "scope": "data",
                                  "text": "Much cheaper than other Rakuten matches — make sure it's the same item, not a part or used/damaged."})
                if best and best["margin"] < cfg["scan"]["thin_margin_warning"]:
                    warns.append({"level": "info", "scope": "profit",
                                  "text": f"Thin margin ({best['margin']:.0%}). Fee or rate changes could wipe it out."})
                if us and us["stats"].get("non_jp_count", 0) >= 10:
                    warns.append({"level": "info", "scope": "data",
                                  "text": f"{us['stats']['non_jp_count']} eBay.com listings from sellers outside Japan — item may not be Japan-only."})
                if c["trust_score"] <= -2:
                    warns.append({"level": "caution", "scope": "trust",
                                  "text": "Shop trust is low: " + "; ".join(t for k, t in c["trust_reasons"] if k != "good")})
                if (c.get("point_rate") or 1) >= 5:
                    warns.append({"level": "info", "scope": "profit",
                                  "text": f"Shop is offering {c['point_rate']}x 楽天ポイント (Rakuten points) right now — counted in the profit."})

                opps.append({
                    "id": opp_id,
                    "trust": {"score": c["trust_score"], "reasons": [{"kind": k, "text": t} for k, t in c["trust_reasons"]],
                              "reviews": c.get("review_count"), "rating": c.get("review_avg"),
                              "shop_of_year": c.get("shop_of_year")},
                    "deal": deal,
                    "item_id": it["id"], "item_name": it["name"], "category": it["category"],
                    "title_ja": c["title"], "title_en": title_en,
                    "image": c["image"], "url": c["url"], "shop": c["shop"],
                    "buy_jpy": c["price_jpy"], "postage_included": c["postage_included"],
                    "point_rate": c.get("point_rate"), "points_jpy": pts,
                    "sale_usd": us.get("local"), "weight_g": it["weight_g"],
                    "per_dest": per,
                    "best": {"country": best_code, **best} if best else None,
                    "warnings": warns, "blocked": sorted(blocked),
                })
            # --- remember today's prices for the history / deal tags
            sale_by_dest = {code: m.get("sale_jpy") for code, m in market.items() if m.get("price_source") == "local"}
            info["ebay_trend_us"] = history.ebay_trend(hist, it["id"], "US", sale_by_dest.get("US"), today,
                                                       cfg_h["window_days"])
            history.update(hist, it["id"], today, [r["price_jpy"] for r in matched], sale_by_dest,
                           {f"{it['id']}::{r.get('item_code') or r['url']}": r["price_jpy"] for r in matched})
            info["history"] = history.series(hist, it["id"], today, cfg_h["window_days"])
        except Exception as e:
            info["status"] = "error"
            info["error"] = str(e)
            items_out.append(info)
            errors.append({"item": it["id"], "error": str(e)})
            traceback.print_exc()

    tr.save()
    history.save(hist, today, cfg_h["keep_days"])
    opps.sort(key=lambda o: (o["best"] or {}).get("profit_jpy", -10**9), reverse=True)
    result_history_mode = hist["mode"]
    alert_info = alerts.send(opps, cfg, {k: d["name"] for k, d in dests.items()},
                             sale=saleinfo.as_json(sale_now), mock=mock)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "sample" if mock else "live",
        "history_mode": result_history_mode,
        "fx": {"jpy_per": jpy, "usd_jpy": jpy["USD"], "source": fx_src},
        "translation": "sample" if mock else ("DeepL" if tr.key else "off"),
        "sale_now": saleinfo.as_json(sale_now),
        "next_sale": saleinfo.as_json(saleinfo.upcoming(cfg.get("sales"), now)),
        "schedule": {"daily_jst": ["05:07", "20:07"], "sale_hourly_jst": ["20:37", "21:37", "22:37", "23:37"]},
        "alerts": alert_info,
        "ebay_calls": getattr(ebay, "calls", None),
        "assumptions": {
            "ebay": cfg["ebay"], "fx_conversion_cost": cfg["fx"]["conversion_cost"],
            "costs": cfg["costs"], "points": cfg.get("points"), "alert_rules": cfg.get("alerts"),
            "trust": cfg_t, "history": cfg_h,
            "shipping_service": cfg["shipping"]["service"],
            "shipping_table_from": max(t["valid_from"] for t in cfg["shipping"]["tables"]
                                       if date.fromisoformat(t["valid_from"]) <= today),
        },
        "destinations": dests,
        "global_notes": rules.get("global", []),
        "rules": {"categories": rules["categories"], "keywords": rules["keywords"],
                  "destinations": rules.get("destinations", {})},
        "items": items_out,
        "opportunities": opps,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUT} — {len(opps)} opportunities, {len(errors)} errors, alerts: {alert_info}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="use sample fixtures instead of live APIs")
    a = ap.parse_args()
    res = run(mock=a.mock or os.environ.get("SCANNER_MOCK") == "1")
    # fail the GitHub Action only if every item errored (e.g. bad keys)
    if res["items"] and all(i.get("status") == "error" for i in res["items"]):
        sys.exit(1)
