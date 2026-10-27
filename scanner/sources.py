"""Data sources: Rakuten Ichiba (official API), eBay Browse API, FX rate.

Each source has a live implementation and a mock one (reads scanner/fixtures/)
so the whole pipeline can be tested without API keys.
"""
import base64
import json
import os
import time
from pathlib import Path

import requests

FIXTURES = Path(__file__).parent / "fixtures"
UA = {"User-Agent": "jp-resale-finder/1.0 (personal research tool)"}


# ---------------------------------------------------------------- Rakuten
class Rakuten:
    """Rakuten Ichiba Item Search API.

    Needs a free app from https://webservice.rakuten.co.jp/ :
      RAKUTEN_APP_ID     アプリID (application ID)
      RAKUTEN_ACCESS_KEY アクセスキー (access key) — required on the openapi endpoint
      RAKUTEN_ORIGIN     the website URL you registered for the app
                         (sent as Origin/Referer; the new endpoint rejects requests without it)
    """

    ENDPOINTS = [
        "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401",
        "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601",
        "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601",
    ]

    def __init__(self):
        self.app_id = os.environ.get("RAKUTEN_APP_ID", "")
        self.access_key = os.environ.get("RAKUTEN_ACCESS_KEY", "")
        self.origin = os.environ.get("RAKUTEN_ORIGIN", "")
        custom = os.environ.get("RAKUTEN_ENDPOINT")
        self.endpoints = [custom] if custom else list(self.ENDPOINTS)
        self._working = None

    def search(self, keyword, exclude=None, min_price=None, max_price=None, hits=30):
        if not self.app_id:
            raise RuntimeError("RAKUTEN_APP_ID is not set")
        params = {
            "applicationId": self.app_id,
            "keyword": keyword,
            "sort": "+itemPrice",
            "hits": min(hits, 30),
            "availability": 1,
            "format": "json",
            "formatVersion": 2,
        }
        if self.access_key:
            params["accessKey"] = self.access_key
        # NGKeyword only accepts plain words; drop numbers to avoid over-excluding
        ng = [str(w) for w in (exclude or []) if not str(w).isdigit()]
        if ng:
            params["NGKeyword"] = " ".join(ng)
        if min_price:
            params["minPrice"] = int(min_price)
        if max_price:
            params["maxPrice"] = int(max_price)
        headers = dict(UA)
        if self.origin:
            headers["Origin"] = self.origin
            headers["Referer"] = self.origin

        last_err = None
        for url in ([self._working] if self._working else self.endpoints):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=20)
                if r.status_code == 429:
                    time.sleep(2)
                    r = requests.get(url, params=params, headers=headers, timeout=20)
                if r.status_code >= 400:
                    last_err = f"{url} → HTTP {r.status_code}: {r.text[:200]}"
                    continue
                self._working = url
                time.sleep(1.1)  # stay under 1 request/second
                return [self._normalise(i) for i in r.json().get("Items", [])]
            except requests.RequestException as e:
                last_err = f"{url} → {e}"
        raise RuntimeError(f"Rakuten search failed: {last_err}")

    @staticmethod
    def _normalise(item):
        it = item.get("Item", item)  # formatVersion 1 wraps each item
        imgs = it.get("mediumImageUrls") or []
        img = None
        if imgs:
            img = imgs[0] if isinstance(imgs[0], str) else imgs[0].get("imageUrl")
        return {
            "source": "rakuten",
            "title": it.get("itemName", ""),
            "price_jpy": int(it.get("itemPrice") or 0),
            "postage_included": it.get("postageFlag", 0) == 0,
            "url": it.get("itemUrl"),
            "shop": it.get("shopName"),
            "image": (img or "").split("?")[0] or None,
            "item_code": it.get("itemCode"),
            "point_rate": int(it.get("pointRate") or 1),
            "shop_code": it.get("shopCode"),
            "review_count": int(it.get("reviewCount") or 0),
            "review_avg": float(it.get("reviewAverage") or 0),
            "shop_of_year": bool(int(it.get("shopOfTheYearFlag") or 0)),
            "caption": (it.get("itemCaption") or "")[:1500],
        }


class MockRakuten:
    def __init__(self):
        self.data = json.loads((FIXTURES / "rakuten.json").read_text(encoding="utf-8"))

    def search(self, keyword, **_):
        return [Rakuten._normalise(i) for i in self.data.get(keyword, [])]


# ---------------------------------------------------------------- eBay
class Ebay:
    """eBay Browse API (current listings). Needs an app from https://developer.ebay.com/ :
      EBAY_CLIENT_ID      App ID (Client ID), Production keyset
      EBAY_CLIENT_SECRET  Cert ID (Client Secret)
    One token works for every marketplace (eBay.com, .co.uk, .com.au, .de, .ca).
    """

    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

    def __init__(self):
        self.client_id = os.environ.get("EBAY_CLIENT_ID", "")
        self.client_secret = os.environ.get("EBAY_CLIENT_SECRET", "")
        self._token = None
        self._token_exp = 0
        self.calls = 0

    def _get_token(self):
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        if not (self.client_id and self.client_secret):
            raise RuntimeError("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET are not set")
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        r = requests.post(
            self.TOKEN_URL,
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials",
                  "scope": "https://api.ebay.com/oauth/api_scope"},
            timeout=20,
        )
        r.raise_for_status()
        j = r.json()
        self._token = j["access_token"]
        self._token_exp = time.time() + int(j.get("expires_in", 7200))
        return self._token

    def search(self, q, marketplace="EBAY_US", currency="USD", ship_to="US", price_range=None,
               condition="ANY", location_jp=False, limit=100, exclude_sellers=None):
        filters = ["buyingOptions:{FIXED_PRICE}"]
        if price_range:
            filters.append(f"price:[{price_range[0]:.0f}..{price_range[1]:.0f}]")
            filters.append(f"priceCurrency:{currency}")
        if condition in ("NEW", "USED"):
            filters.append(f"conditions:{{{condition}}}")
        if location_jp:
            filters.append("itemLocationCountry:JP")
        if exclude_sellers:
            filters.append("excludeSellers:{" + "|".join(exclude_sellers) + "}")
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
            # shipping costs as seen by a buyer in the destination country
            "X-EBAY-C-ENDUSERCTX": f"contextualLocation=country%3D{ship_to}",
            **UA,
        }
        r = requests.get(self.SEARCH_URL, headers=headers,
                         params={"q": q, "limit": min(limit, 200), "filter": ",".join(filters)},
                         timeout=25)
        self.calls += 1
        r.raise_for_status()
        return [self._normalise(i) for i in r.json().get("itemSummaries", [])]

    @staticmethod
    def _normalise(i):
        p = i.get("price") or {}
        price = float(p.get("value") or 0)
        ship, max_delivery = None, None
        for opt in i.get("shippingOptions") or []:
            cost = (opt.get("shippingCost") or {}).get("value")
            if cost is not None and ship is None:
                ship = float(cost)
            max_delivery = max_delivery or opt.get("maxEstimatedDeliveryDate")
        seller = i.get("seller") or {}
        fp = seller.get("feedbackPercentage")
        return {
            "source": "ebay",
            "seller": seller.get("username"),
            "feedback_score": seller.get("feedbackScore"),
            "feedback_pct": float(fp) if fp not in (None, "") else None,
            "max_delivery": max_delivery,
            "title": i.get("title", ""),
            "price": price,
            "shipping": ship,
            "total": price + (ship or 0),
            "currency": p.get("currency"),
            "url": i.get("itemWebUrl"),
            "condition": i.get("condition"),
            "country": (i.get("itemLocation") or {}).get("country"),
            "image": (i.get("image") or {}).get("imageUrl"),
        }


class MockEbay:
    def __init__(self):
        self.data = json.loads((FIXTURES / "ebay.json").read_text(encoding="utf-8"))
        self.calls = 0

    def search(self, q, marketplace="EBAY_US", location_jp=False, **_):
        self.calls += 1
        items = [Ebay._normalise(i) for i in self.data.get(marketplace, {}).get(q, [])]
        return [i for i in items if i["country"] == "JP"] if location_jp else items


# ---------------------------------------------------------------- FX
def jpy_rates(fallback: dict, mock: bool = False):
    """Yen per 1 unit of each currency, e.g. {"USD": 152.3, "GBP": 198.1, ...}.
    Uses Frankfurter (European Central Bank reference rates); falls back to config.yaml."""
    if mock:
        return dict(fallback), "sample"
    curs = [c for c in fallback if c != "JPY"]
    for url in ("https://api.frankfurter.dev/v1/latest", "https://api.frankfurter.app/latest"):
        try:
            r = requests.get(url, params={"base": "JPY", "symbols": ",".join(curs)}, timeout=15, headers=UA)
            r.raise_for_status()
            j = r.json()
            rates = {c: round(1 / float(v), 4) for c, v in j["rates"].items()}
            if all(c in rates for c in curs):
                return rates, f"ECB via Frankfurter ({j.get('date')})"
        except Exception:
            continue
    return dict(fallback), "fallback (config.yaml)"
