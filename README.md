# Japan Resale Finder

A personal research tool. It checks 楽天市場 (Rakuten Ichiba) prices for items on your watchlist, compares them with
each country's own eBay site (eBay.com, .ca, .co.uk, .com.au, .de) and converts everything to yen. It then estimates
your profit after fees, shipping, duty and 楽天ポイント (Rakuten points) for each country. It also flags licence, legal
and shipping problems, such as knives to the UK, and can send push alerts to your phone.

- **Scanner** (`scanner/`): Python. GitHub Actions runs it at 05:07 and 20:07 JST every day, and hourly from 20:37 to 23:37
  JST while a Rakuten sale is on.
- **App** (`docs/`): a phone-friendly web app on GitHub Pages. You can install it on Android from Chrome.

> **Until you add API keys, the app shows SAMPLE (made-up) data.** It says so in a yellow banner.

---

## One-time setup (about 30 minutes)

### 1. Put the code on GitHub
Create a new repository called `jp-resale-finder` and upload these files. On a free GitHub plan the repository has to
be **public** for Pages to work, which means your watchlist and results are publicly visible.

### 2. Get the API keys (all free)

| Service | Where | What to copy |
|---|---|---|
| Rakuten | https://webservice.rakuten.co.jp/ → アプリID発行 (issue an app ID) | アプリID (app ID) and アクセスキー (access key). In the app settings, set the allowed website to `https://davepomerlo.github.io` |
| eBay | https://developer.ebay.com/ → create an account → Application Keys → **Production** keyset | App ID (Client ID) and Cert ID (Client Secret) |
| DeepL *(optional, translates titles)* | https://www.deepl.com/pro-api → API Free | Auth key (ends in `:fx`) |

Without DeepL, titles stay in Japanese and each card has a "translate" link.

### 3. Add them as repository secrets
Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

```
RAKUTEN_APP_ID
RAKUTEN_ACCESS_KEY
RAKUTEN_ORIGIN        https://davepomerlo.github.io
EBAY_CLIENT_ID
EBAY_CLIENT_SECRET
DEEPL_API_KEY         (optional)
NTFY_TOPIC            (optional, for push alerts — see below)
```

### Push alerts (optional)
1. Install **ntfy** from the Google Play Store.
2. In the app, tap **+** and subscribe to a long random topic name, e.g. `dave-resale-7Kq2xP9w`.
   Anyone who knows the name can read the alerts, so don't use anything guessable.
3. Save the same name as the `NTFY_TOPIC` secret.

You'll get an alert when a listing goes over the thresholds in `config.yaml` (`alerts:`), which default to ¥5,000 profit
and a 15% margin. You get at most 5 alerts per scan, and the same listing won't alert again unless its profit rises
20% or more.

### 4. Turn on the website
Go to **Settings → Pages → Build and deployment → Deploy from a branch → `main` / `/docs`**.
The app will be at `https://davepomerlo.github.io/jp-resale-finder/`.

### 5. Run the first scan
Go to **Actions → Daily scan → Run workflow**. After that it runs every day on its own. It also runs whenever you
edit the watchlist, config or rules.

### 6. Install on your phone
Open the app URL in Chrome on Android, then **⋮ → Add to Home screen / Install app**.

---

## Everyday use

| To… | Edit |
|---|---|
| Add or remove items to track | `scanner/watchlist.yaml` (the GitHub mobile app works for this) |
| Match fees and shipping to your real invoices | `scanner/config.yaml` |
| Add or change legal and shipping warnings | `scanner/rules.yaml` |
| Add お買い物マラソン (Shopping Marathon) or other sale dates for hourly scans | `config.yaml` → `sales: windows` |
| Count your SPU (Super Point Up) or 買いまわり (shop-hopping) bonus | `config.yaml` → `points: extra_rate_pct` |

楽天スーパーSALE (Rakuten Super Sale) is detected automatically: the 4th to the 11th of March, June, September and
December. Rakuten Black Friday 2026 is pre-filled as a **prediction**, so correct it once the dates are announced.

**Before you buy anything, tap "Check eBay sold prices" on the card.** The profit estimate is based on current
*asking* prices, because eBay limits its sold-price data to approved partners.

## Filtering out drop-shippers and weak sellers
**Rakuten listings** get a trust score (`scanner/trust.py`):

| Signal | Score |
|---|---|
| Shop is on your `trusted_shops` list | +3 |
| 楽天ショップ・オブ・ザ・イヤー (Rakuten Shop of the Year) | +2 |
| 10+ reviews averaging ★4.0+ | +1 |
| No reviews at all | −1 |
| Back-order or overseas words: お取り寄せ (made to order from supplier), 海外発送 (ships from overseas), 予約 (pre-order), 入荷待ち (awaiting stock), etc. | −2 |
| 5+ reviews averaging under ★3.5 | −2 |
| Shop is on your `blocked_shops` list | −5 |

Listings scoring below −2 are hidden. The Watchlist tab shows what was hidden and why.

**eBay comparison listings** are cleaned before the sell price is calculated. The scan drops:
- sellers with fewer than 50 feedback ratings or under 98% positive
- listings with an estimated delivery over 25 days, which usually means a drop-shipper or pre-order
- titles that say pre-order, made to order or backorder
- any sellers in your `exclude_sellers` list
- extra listings from the same seller, so one big drop-shipper can't push up the median

Change all of these under `trust:` in `config.yaml`.

## Price history and 🔥 great-deal tags
Each scan records the cheapest and typical Rakuten price for every watchlist item, plus each listing's price, in
`docs/data/history.json`. After 7 days of scans, cards get tags:
- **🔥 Great deal:** 15%+ below the item's typical price over the last 60 days.
- **📉 Lowest price in 60 days.**
- **↓ ¥X since <date>:** this listing has dropped 5% or more since it was last seen.
- **🆕 New listing.**

The card details show a 60-day price chart, and the Deals tab can filter to great deals only or sort by deal. Great deals
also get top priority in push alerts. Rakuten has no price-history API, so **history starts from your first scan**.

## How profit is estimated

```
sell price  = median of current listings on that country's eBay site from Japan-based sellers
              (or all sellers if fewer than 3) × 97%, converted to yen at the day's ECB rate.
              If the local site has fewer than 3 listings, the eBay.com price is used instead.
profit      = sell price in yen − currency conversion cost
              − eBay fees (final value fee + international fee + per-order fee, plus tax on fees)
              − EMS shipping (by weight and zone; switches to the new Japan Post rates on 1 Feb 2027)
              − US duty you prepay (12.5%, US only)
              − Rakuten price + 楽天ポイント (Rakuten points: shop rate + your extra rate, on the ex-tax price)
              − domestic postage (if not included) − packaging
```

The rates marked ASSUMPTION in `config.yaml`, such as the international fee and tax on fees, should be checked
against your first eBay invoice.

## Limits worth knowing
- Each scan makes about 10 eBay calls per watchlist item (5 sites × 2 searches). eBay's default Browse API allowance
  is several thousand calls a day, which covers dozens of items even with hourly sale scans.
- Points during 買いまわり (shop-hopping) only count if you actually buy from enough shops, so keep `extra_rate_pct`
  realistic.
- Matching relies on keywords, so tune `must_include` and `exclude` when you see wrong items.
- Rakuten mostly sells **new** items from shops. Even so, a lawyer's guide says new items bought at retail for resale can
  count as 古物 (secondhand goods). Treat the 古物商許可 (secondhand dealer licence) as needed.
- Rakuten's terms require the "Supported by Rakuten Developers" credit, which is in the app footer. eBay's API terms
  are written mainly for buying apps; read them when you sign up.
- Mercari and Yahoo! Auctions are not included because neither has an official open API.

## Run locally (optional)
```
pip install -r requirements.txt
python scanner/scan.py --mock          # sample data
python -m http.server -d docs 8000     # open http://localhost:8000
python -m pytest -q tests
```
