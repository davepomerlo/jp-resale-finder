"""Small text helpers shared by the scanner."""
import unicodedata


def norm(text: str) -> str:
    """Normalise for matching: full-width → half-width, lower-case, collapse spaces."""
    if text is None or text == "":
        return ""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    return " ".join(t.split())


def contains_all(title: str, words) -> bool:
    t = norm(title)
    return all(norm(w) in t for w in (words or []))


def contains_any(title: str, words) -> bool:
    t = norm(title)
    return any(norm(w) in t for w in (words or []))


def median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2


def percentile(values, p):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
