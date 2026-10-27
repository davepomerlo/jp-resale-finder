"""Weekly ideas for new watchlist items.

For each discovery keyword, take Rakuten's most-reviewed listings (a proxy for popular items),
skip anything already on your watchlist, build an English eBay query from the brand and model
in the title, and check eBay.com listings from Japan-based sellers for a rough profit.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import profit
import trust
from textutil import contains_any, norm

FILE = Path(__file__).resolve().parent.parent / "docs" / "data" / "suggestions.json"
JST = timezone(timedelta(hours=9))

BRANDS = {"シマノ": "Shimano", "ダイワ": "Daiwa", "ミソノ": "Misono", "藤次郎": "Tojiro", "貝印": "Kai",
          "グローバル": "Global", "岩鋳": "Iwachu", "ボス": "BOSS", "マクソン": "Maxon", "アイバニーズ": "Ibanez",
          "堺孝行": "Sakai Takayuki", "正本": "Masamoto", "有次": "Aritsugu", "メガバス": "Megabass",
          "ジャッカル": "Jackall", "セイコー": "Seiko", "カシオ": "Casio", "鍛冶屋": "", "一竿風月": ""}
NOISE = {"mm", "cm", "no", "sale", "off", "pt", "p10", "ok", "x", "new", "jan", "set", "1", "2", "3"}


def ebay_query(title_ja):
    """'シマノ 23 ヴァンキッシュ C3000SDH' -> 'Shimano C3000SDH'"""
    t = norm(title_ja)
    brand = next((en for ja, en in BRANDS.items() if norm(ja) in t and en), None)
    tokens = []
    for w in re.findall(r"[a-z0-9][a-z0-9\-\.]*", t):
        if w in NOISE or re.fullmatch(r"\d+(\.\d+)?(mm|cm|ml|l|g|kg|m|号)?", w) and not re.fullmatch(r"\d{3,}", w):
            continue  # skip units like 21cm and years like 23, keep model numbers like 440
        tokens.append(w.upper() if any(ch.isdigit() for ch in w) else w.capitalize())
    if brand and norm(brand) not in [norm(x) for x in tokens]:
        tokens.insert(0, brand)
    q = " ".join(dict.fromkeys(tokens))
    return q if (brand or len(tokens) >= 2) and any(ch.isdigit() for ch in q) else None


def due(cfg_d, now=None, force=False):
    if force:
        return True
    now = (now or datetime.now(JST)).astimezone(JST)
    if not FILE.exists():
        return True
    return now.weekday() == cfg_d.get("weekday", 0) and now.hour < 12


def load_previous():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"generated_at": None, "items": []}


def run(cfg, watch, rak, ebay, jpy, today, cal_fn=None):
    cfg_d = cfg["discover"]
    watched = [w for it in watch["items"] for w in (it.get("must_include") or []) + [it["ebay"]]]
    dests = cfg["destinations"]
    per_order_jpy = cfg["ebay"]["per_order_fee_usd"] * jpy["USD"]
    out, seen = [], set()
    for k in cfg_d.get("keywords") or []:
        try:
            found = rak.search(k["q"], hits=30, sort="-reviewCount")
        except Exception as e:
            print(f"[discover] {k['q']}: {e}")
            continue
        n = 0
        for r in found:
            if n >= cfg_d.get("per_keyword", 10):
                break
            if trust.rakuten_score(r, cfg.get("trust"))[2] or contains_any(r["title"], watched):
                continue
            q = ebay_query(r["title"])
            if not q or q.lower() in seen:
                continue
            seen.add(q.lower())
            n += 1
            try:
                comps = ebay.search(q, marketplace="EBAY_US", currency="USD", ship_to="US",
                                    location_jp=True, limit=50)
            except Exception as e:
                print(f"[discover] eBay {q}: {e}")
                continue
            comps, _ = trust.clean_ebay(comps, cfg.get("trust"), today)
            sale_usd, stats = profit.sale_price(comps, comps, {**cfg["ebay"], "min_jp_comps": 1})
            if not sale_usd or stats["count"] < 3:
                continue
            pts = profit.points_value(r["price_jpy"], r.get("point_rate"), cfg.get("points"))
            per = {}
            for code, d in dests.items():
                res = profit.compute(r["price_jpy"], r["postage_included"], sale_usd * jpy["USD"], d,
                                     k.get("weight_g", 1000), k.get("category", "default"), cfg, per_order_jpy, pts,
                                     on=today)
                if res["ok"]:
                    per[code] = res["profit_jpy"]
            blocked = set((cfg.get("_rules", {}).get("categories", {}).get(k.get("category"), {})
                           .get("blocked_destinations") or {}).keys())
            allowed = {c: v for c, v in per.items() if c not in blocked}
            if not allowed:
                continue
            best = max(allowed, key=allowed.get)
            if allowed[best] < cfg_d.get("min_profit_jpy", 0):
                continue
            item_id = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")
            out.append({
                "keyword": k["q"], "category": k.get("category"), "title_ja": r["title"], "url": r["url"],
                "shop": r["shop"], "buy_jpy": r["price_jpy"], "ebay_query": q, "sale_usd": sale_usd,
                "comps": stats["count"], "profit_by_dest": per, "best_country": best, "best_profit_jpy": allowed[best],
                "reviews": r.get("review_count"),
                "sold_url": "https://www.ebay.com/sch/i.html?_nkw=" + q.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1",
                "yaml": (f"  - id: {item_id}\n    name: {q}\n    category: {k.get('category')}\n"
                         f"    rakuten: {r['title'][:40]}\n    ebay: {q}\n    must_include: [{q.split()[-1]}]\n"
                         f"    exclude: []\n    price_jpy: [{int(r['price_jpy'] * 0.6)}, {int(r['price_jpy'] * 1.6)}]\n"
                         f"    price_usd: [{int(sale_usd * 0.5)}, {int(sale_usd * 1.8)}]\n    condition: ANY\n"
                         f"    weight_g: {k.get('weight_g', 1000)}\n"),
            })
    out.sort(key=lambda s: s["best_profit_jpy"], reverse=True)
    res = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": out}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
