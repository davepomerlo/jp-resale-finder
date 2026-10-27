"""Seller trust: score Rakuten listings and clean eBay comparison listings."""
from datetime import date, datetime

from textutil import contains_any, norm


def rakuten_score(listing, cfg_trust):
    """Return (score, reasons[], hidden) for one Rakuten listing.

    +3 shop on your trusted list            -5 shop on your blocked list
    +2 楽天ショップ・オブ・ザ・イヤー (Shop of the Year)
    +1 10+ reviews averaging 4.0+            -2 5+ reviews averaging under 3.5
    -2 back-order / overseas-shipping words (drop-ship signs) in title or description
    -1 no reviews at all and not Shop of the Year
    """
    t = (cfg_trust or {}).get("rakuten", {})
    score, reasons = 0, []
    shop_keys = {norm(listing.get("shop")), norm(listing.get("shop_code"))}
    if shop_keys & {norm(s) for s in t.get("trusted_shops") or []}:
        score += 3
        reasons.append(("good", "On your trusted shops list"))
    if shop_keys & {norm(s) for s in t.get("blocked_shops") or []}:
        score -= 5
        reasons.append(("bad", "On your blocked shops list"))
    if listing.get("shop_of_year"):
        score += 2
        reasons.append(("good", "楽天ショップ・オブ・ザ・イヤー (Rakuten Shop of the Year)"))
    n, avg = listing.get("review_count") or 0, listing.get("review_avg") or 0
    if n >= 10 and avg >= 4.0:
        score += 1
        reasons.append(("good", f"★{avg:.1f} from {n} reviews"))
    elif n >= 5 and avg < 3.5:
        score -= 2
        reasons.append(("bad", f"Poor reviews: ★{avg:.1f} from {n}"))
    elif n == 0 and not listing.get("shop_of_year"):
        score -= 1
        reasons.append(("meh", "No reviews yet"))
    text = f"{listing.get('title', '')} {listing.get('caption', '')}"
    hits = [w for w in t.get("dropship_words") or [] if norm(w) in norm(text)]
    if hits:
        score -= 2
        reasons.append(("bad", "Possible drop-ship / back-order: " + ", ".join(hits[:3])))
    hidden = score < t.get("hide_below_score", -2)
    return score, reasons, hidden


def _days_until(iso, today):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
        return (d - today).days
    except (AttributeError, ValueError):
        return None


def clean_ebay(comps, cfg_trust, today: date = None):
    """Drop comparison listings that look like drop-shippers or weak sellers.
    Returns (kept, removed_counts_by_reason)."""
    t = (cfg_trust or {}).get("ebay", {})
    today = today or date.today()
    excluded = {s.lower() for s in t.get("exclude_sellers") or []}
    kept, removed = [], {}

    def drop(reason):
        removed[reason] = removed.get(reason, 0) + 1

    for c in comps:
        seller = (c.get("seller") or "").lower()
        if seller and seller in excluded:
            drop("excluded seller"); continue
        fs, fp = c.get("feedback_score"), c.get("feedback_pct")
        if fs is not None and fs < t.get("min_feedback_score", 0):
            drop("low feedback count"); continue
        if fp is not None and fp < t.get("min_feedback_pct", 0):
            drop("low feedback %"); continue
        if contains_any(c.get("title", ""), t.get("dropship_words")):
            drop("pre-order / drop-ship words"); continue
        days = _days_until(c.get("max_delivery"), today) if c.get("max_delivery") else None
        if days is not None and days > t.get("max_delivery_days", 999):
            drop("slow delivery"); continue
        kept.append(c)

    if t.get("one_listing_per_seller") and kept:
        best = {}
        for c in kept:
            key = (c.get("seller") or c.get("url") or id(c))
            if key not in best or c["total"] < best[key]["total"]:
                best[key] = c
        n_dup = len(kept) - len(best)
        if n_dup:
            removed["duplicate listings from same seller"] = n_dup
        kept = list(best.values())
    return kept, removed
