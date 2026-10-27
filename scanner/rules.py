"""Turns rules.yaml into warnings for one opportunity."""
from textutil import contains_any


def warnings_for(item_cfg, title_ja, title_en, rules, dest_codes):
    out = []
    cat = rules["categories"].get(item_cfg["category"], {})

    for w in cat.get("warnings") or []:
        out.append({**w, "scope": "category"})
    if cat.get("id_check_any_price"):
        out.append({
            "level": "caution", "scope": "licence",
            "text": "Buying from individuals: ID check and ledger entry required at ANY price for this category "
                    "(not just ¥10,000+).",
            "source": "https://www.keishicho.metro.tokyo.lg.jp/tetsuzuki/kobutsu/kaisetsu/kobutsu_sekoukisoku.html",
        })
    if cat.get("kobutsu"):
        out.append({"level": "info", "scope": "licence",
                    "text": f"古物商 category (licence item category): {cat['kobutsu']}"})

    blocked = {}
    for code, reason in (cat.get("blocked_destinations") or {}).items():
        blocked[code] = reason
        out.append({"level": "block", "scope": "country", "country": code, "text": reason})

    text = f"{title_ja} {title_en or ''}"
    for k in rules.get("keywords") or []:
        if contains_any(text, k["match"]):
            out.append({"level": k["level"], "scope": "keyword", "text": k["text"],
                        **({"source": k["source"]} if k.get("source") else {})})

    for code in dest_codes:
        for w in (rules.get("destinations") or {}).get(code, []):
            out.append({**w, "scope": "country", "country": code})

    return out, blocked
