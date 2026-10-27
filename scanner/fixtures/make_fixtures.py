"""Generates SAMPLE (made-up) API responses so the app can be tested without keys.
None of these listings are real. Run: python scanner/fixtures/make_fixtures.py
"""
import json
import random
import zlib
from pathlib import Path

random.seed(7)
HERE = Path(__file__).parent

# (rakuten query, ebay query, [rakuten title templates], base jpy, ebay title, base usd, jp share)
SPEC = [
    ("ミソノ UX10 牛刀 24cm", "Misono UX10 gyuto 240mm",
     ["ミソノ UX10 牛刀 24cm No.713 スウェーデン鋼", "Misono UX10 牛刀 240mm 日本製 包丁",
      "ミソノ UX10シリーズ 牛刀 24cm 両刃", "【送料無料】ミソノ UX10 牛刀 24cm 箱付き"],
     31000, "Misono UX10 Gyuto 240mm Japanese Chef Knife Made in Japan", 335, 0.6),
    ("藤次郎 DP 牛刀 210mm", "Tojiro DP gyuto 210mm",
     ["藤次郎 DPコバルト合金鋼割込 牛刀 210mm F-808", "TOJIRO DP 牛刀 21cm 日本製", "藤次郎 DP 3層鋼 牛刀210mm"],
     9800, "Tojiro DP Gyuto 210mm F-808 Chef Knife Japan", 120, 0.5),
    ("BOSS SD-1W", "BOSS SD-1W Waza Craft",
     ["BOSS SD-1W 技 WAZA CRAFT Super OverDrive 日本製", "BOSS SD-1W スーパーオーバードライブ 技クラフト",
      "BOSS SD-1W 限定カラー エフェクター"],
     17800, "BOSS SD-1W Waza Craft Super Overdrive Guitar Effect Pedal", 139, 0.3),
    ("Maxon OD808", "Maxon OD808 overdrive",
     ["Maxon OD808 Overdrive 日本製 オーバードライブ", "MAXON OD808 オーバードライブ エフェクター 電池付"],
     14500, "Maxon OD808 Overdrive Pedal Made in Japan", 165, 0.7),
    ("シマノ ステラ C3000", "Shimano Stella C3000 JDM",
     ["シマノ 22 ステラ C3000XG スピニングリール", "シマノ 22ステラ C3000MHG", "SHIMANO ステラ C3000SDH"],
     74000, "Shimano 22 Stella C3000XG Spinning Reel JDM New", 640, 0.8),
    ("南部鉄器 鉄瓶 1.0L", "Nambu tekki tetsubin cast iron kettle Japan",
     ["南部鉄器 鉄瓶 アラレ 1.0L 日本製", "岩鋳 南部鉄器 鉄瓶 1.0L 新アラレ", "南部鉄器 鉄瓶 1.0L IH対応"],
     14800, "Iwachu Nambu Tekki Tetsubin Cast Iron Kettle 1.0L Arare", 165, 0.6),
]

rak, eb = {}, {}
for rq, eq, titles, base_jpy, etitle, base_usd, jp_share in SPEC:
    items = []
    for i in range(10):
        t = random.choice(titles)
        price = int(base_jpy * random.uniform(0.85, 1.35) // 10 * 10)
        items.append({
            "itemName": t, "itemPrice": price,
            "itemUrl": f"https://item.rakuten.co.jp/sample-shop-{i}/sample-{zlib.crc32(t.encode()) % 99999}/",
            "shopName": f"サンプルショップ{i + 1} (sample shop)",
            "postageFlag": random.choice([0, 0, 1]),
            "mediumImageUrls": [],
            "itemCode": f"sample-shop-{i}:{rq[:4]}{i}",
            "pointRate": random.choice([1, 1, 1, 2, 5, 10]),
        })
    rak[rq] = items
    # (marketplace, currency, units per USD, local price multiplier, how many listings)
    markets = [("EBAY_US", "USD", 1.0, 1.0, 14), ("EBAY_GB", "GBP", 0.78, 1.08, 8),
               ("EBAY_AU", "AUD", 1.52, 1.12, 7), ("EBAY_DE", "EUR", 0.92, 1.0, 6),
               ("EBAY_CA", "CAD", 1.38, 1.05, random.choice([2, 6]))]
    for mk, cur, per_usd, mult, n in markets:
        listings = []
        for i in range(n):
            jp = random.random() < jp_share
            price = round(base_usd * per_usd * mult * random.uniform(0.85, 1.25), 2)
            listings.append({
                "title": etitle + (" (sample)" if i % 3 == 0 else ""),
                "price": {"value": str(price), "currency": cur},
                "shippingOptions": [{"shippingCost": {"value": "0.00" if jp else str(round(random.uniform(8, 20) * per_usd, 2)),
                                                      "currency": cur}}],
                "itemWebUrl": "https://www.ebay.com/sch/i.html?_nkw=" + eq.replace(" ", "+"),
                "condition": "New",
                "itemLocation": {"country": "JP" if jp else random.choice(["US", "US", "GB", "CN"])},
            })
        eb.setdefault(mk, {})[eq] = listings

(HERE / "rakuten.json").write_text(json.dumps(rak, ensure_ascii=False, indent=1), encoding="utf-8")
(HERE / "ebay.json").write_text(json.dumps(eb, ensure_ascii=False, indent=1), encoding="utf-8")

# sample "translations" so the UI shows English in sample mode
tr = {
    "ミソノ UX10 牛刀 24cm No.713 スウェーデン鋼": "Misono UX10 Gyuto 24cm No.713 Swedish steel",
    "Misono UX10 牛刀 240mm 日本製 包丁": "Misono UX10 Gyuto 240mm Made in Japan kitchen knife",
    "ミソノ UX10シリーズ 牛刀 24cm 両刃": "Misono UX10 series Gyuto 24cm double-bevel",
    "【送料無料】ミソノ UX10 牛刀 24cm 箱付き": "[Free shipping] Misono UX10 Gyuto 24cm with box",
    "藤次郎 DPコバルト合金鋼割込 牛刀 210mm F-808": "Tojiro DP cobalt alloy steel core Gyuto 210mm F-808",
    "TOJIRO DP 牛刀 21cm 日本製": "TOJIRO DP Gyuto 21cm Made in Japan",
    "藤次郎 DP 3層鋼 牛刀210mm": "Tojiro DP 3-layer steel Gyuto 210mm",
    "BOSS SD-1W 技 WAZA CRAFT Super OverDrive 日本製": "BOSS SD-1W Waza Craft Super OverDrive Made in Japan",
    "BOSS SD-1W スーパーオーバードライブ 技クラフト": "BOSS SD-1W Super Overdrive Waza Craft",
    "BOSS SD-1W 限定カラー エフェクター": "BOSS SD-1W limited colour effects pedal",
    "Maxon OD808 Overdrive 日本製 オーバードライブ": "Maxon OD808 Overdrive Made in Japan",
    "MAXON OD808 オーバードライブ エフェクター 電池付": "MAXON OD808 overdrive pedal, battery included",
    "シマノ 22 ステラ C3000XG スピニングリール": "Shimano 22 Stella C3000XG spinning reel",
    "シマノ 22ステラ C3000MHG": "Shimano 22 Stella C3000MHG",
    "SHIMANO ステラ C3000SDH": "SHIMANO Stella C3000SDH",
    "南部鉄器 鉄瓶 アラレ 1.0L 日本製": "Nambu ironware tetsubin kettle, Arare pattern, 1.0L, Made in Japan",
    "岩鋳 南部鉄器 鉄瓶 1.0L 新アラレ": "Iwachu Nambu ironware tetsubin 1.0L, new Arare pattern",
    "南部鉄器 鉄瓶 1.0L IH対応": "Nambu ironware tetsubin 1.0L, induction compatible",
}
(HERE / "translations_sample.json").write_text(json.dumps(tr, ensure_ascii=False, indent=1), encoding="utf-8")
print("fixtures written")
