"""Japan Resale Finder — daily scan.

For each watchlist item:
  1. find the cheapest matching listings on 楽天市場 (Rakuten Ichiba)
  2. find comparable eBay listings (Japan-based sellers first, then all sellers)
  3. estimate a realistic eBay sale price, then profit per destination country
  4. attach legal / shipping / practical warnings from rules.yaml
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
import profit  # noqa: E402
import rules as rules_mod  # noqa: E402
import sources  # noqa: E402
from textutil import contains_all, contains_any, median  # noqa: E402
from translate import Translator  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).parent
OUT = ROOT / "docs" / "data" / "results.json"


def load(name):
    return yaml.safe_load((HERE / name).read_text(encoding="utf-8"))


def ebay_links(q):
    base = "https://www.ebay.com/sch/i.html?_nkw=" + quote_plus(q)
    return {
        "active_url": base,
        "sold_url": base + "&LH_Sold=1&LH_Complete=1",
    }


def run(mock=False, today=None):
    cfg, watch, rules = load("config.yaml"), load("watchlist.yaml"), load("rules.yaml")
    today = today or date.today()
    rak = sources.MockRakuten() if mock else sources.Rakuten()
    ebay = sources.MockEbay() if mock else sources.Ebay(cfg["ebay"]["marketplace"])
    fx, fx_src = sources.usd_jpy(cfg["fx"]["fallback_usd_jpy"], mock=mock)
    tr = Translator(mock=mock)
    dests = cfg["destinations"]

    items_out, opps, errors = [], [], []

    for it in watch["items"]:
        info = {k: it.get(k) for k in ("id", "name", "category", "rakuten", "ebay")}
        info["label"] = rules["categories"].get(it["category"], {}).get("label", it["category"])
        info.update(ebay_links(it["ebay"]))
        info["rakuten_search_url"] = "https://search.rakuten.co.jp/search/mall/" + quote_plus(it["rakuten"]) + "/"
        try:
            # --- eBay comps
            cond = it.get("condition", "ANY")
            all_c = ebay.search(it["ebay"], price_usd=it.get("price_usd"), condition=cond,
                                limit=cfg["scan"]["ebay_limit"])
            jp_c = ebay.search(it["ebay"], price_usd=it.get("price_usd"), condition=cond,
                               location_jp=True, limit=cfg["scan"]["ebay_limit"])
            keep = lambda c: contains_all(c["title"], it.get("must_include")) and not contains_any(  # noqa: E731
                c["title"], it.get("exclude"))
            all_c, jp_c = [c for c in all_c if keep(c)], [c for c in jp_c if keep(c)]
            sale_usd, comp_stats = profit.sale_price_usd(jp_c, all_c, cfg["ebay"])
            comp_stats.update({"jp_count": len(jp_c), "all_count": len(all_c),
                               "non_jp_count": len([c for c in all_c if c.get("country") != "JP"])})
            comp_stats["examples"] = [
                {k: c[k] for k in ("title", "total_usd", "url", "country", "condition")}
                for c in sorted(jp_c or all_c, key=lambda c: c["total_usd"])[:5]
            ]
            info["comps"] = comp_stats
            info["sale_usd"] = sale_usd

            # --- Rakuten candidates
            pr = it.get("price_jpy") or [None, None]
            found = rak.search(it["rakuten"], exclude=it.get("exclude"), min_price=pr[0], max_price=pr[1],
                               hits=cfg["scan"]["rakuten_hits"])
            matched = [r for r in found if contains_all(r["title"], it.get("must_include"))
                       and not contains_any(r["title"], it.get("exclude"))
                       and (not pr[0] or r["price_jpy"] >= pr[0]) and (not pr[1] or r["price_jpy"] <= pr[1])]
            info["rakuten_found"], info["rakuten_matched"] = len(found), len(matched)
            info["status"] = "ok" if matched and sale_usd else ("no eBay comps" if not sale_usd else "no Rakuten match")
            items_out.append(info)
            if not (matched and sale_usd):
                continue

            rak_median = median([r["price_jpy"] for r in matched])
            cands = sorted(matched, key=lambda r: r["price_jpy"])[: cfg["scan"]["candidates_per_item"]]
            translations = tr.translate_many([c["title"] for c in cands])

            for c in cands:
                title_en = translations.get(c["title"])
                warns, blocked = rules_mod.warnings_for(it, c["title"], title_en, rules, list(dests))
                per = {}
                for code, d in dests.items():
                    res = profit.compute(c["price_jpy"], c["postage_included"], sale_usd, fx, d,
                                         it["weight_g"], it["category"], cfg,
                                         it.get("shipping_override_jpy"), on=today)
                    res["blocked"] = code in blocked
                    per[code] = res
                allowed = {k: v for k, v in per.items() if v["ok"] and not v["blocked"]}
                best_code = max(allowed, key=lambda k: allowed[k]["profit_jpy"]) if allowed else None
                best = allowed.get(best_code) if best_code else None

                if comp_stats["count"] < 3:
                    warns.append({"level": "caution", "scope": "data",
                                  "text": f"Only {comp_stats['count']} comparable eBay listings — price estimate is shaky. Check sold prices."})
                if rak_median and c["price_jpy"] < 0.6 * rak_median and len(matched) >= 3:
                    warns.append({"level": "caution", "scope": "data",
                                  "text": "Much cheaper than other Rakuten matches — make sure it's the same item, not a part or used/damaged."})
                if best and best["margin"] < cfg["scan"]["thin_margin_warning"]:
                    warns.append({"level": "info", "scope": "profit",
                                  "text": f"Thin margin ({best['margin']:.0%}). Fee or rate changes could wipe it out."})
                if comp_stats.get("non_jp_count", 0) >= 10:
                    warns.append({"level": "info", "scope": "data",
                                  "text": f"{comp_stats['non_jp_count']} listings from sellers outside Japan — item may not be Japan-only."})

                opps.append({
                    "id": f"{it['id']}::{c.get('item_code') or c['url']}",
                    "item_id": it["id"], "item_name": it["name"], "category": it["category"],
                    "title_ja": c["title"], "title_en": title_en,
                    "image": c["image"], "url": c["url"], "shop": c["shop"],
                    "buy_jpy": c["price_jpy"], "postage_included": c["postage_included"],
                    "sale_usd": sale_usd, "weight_g": it["weight_g"],
                    "per_dest": per,
                    "best": {"country": best_code, **(best or {})} if best else None,
                    "warnings": warns, "blocked": sorted(blocked),
                })
        except Exception as e:
            info["status"] = "error"
            info["error"] = str(e)
            items_out.append(info)
            errors.append({"item": it["id"], "error": str(e)})
            traceback.print_exc()

    tr.save()
    opps.sort(key=lambda o: (o["best"] or {}).get("profit_jpy", -10**9), reverse=True)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "sample" if mock else "live",
        "fx": {"usd_jpy": round(fx, 2), "source": fx_src},
        "translation": "sample" if mock else ("DeepL" if tr.key else "off"),
        "assumptions": {
            "ebay": cfg["ebay"], "fx_conversion_cost": cfg["fx"]["conversion_cost"],
            "costs": cfg["costs"], "shipping_service": cfg["shipping"]["service"],
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
    print(f"Wrote {OUT} — {len(opps)} opportunities, {len(errors)} errors")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="use sample fixtures instead of live APIs")
    a = ap.parse_args()
    res = run(mock=a.mock or os.environ.get("SCANNER_MOCK") == "1")
    # fail the GitHub Action only if every item errored (e.g. bad keys)
    if res["items"] and all(i.get("status") == "error" for i in res["items"]):
        sys.exit(1)
