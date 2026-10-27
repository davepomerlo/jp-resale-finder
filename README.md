# Japan Resale Finder

A personal research tool. It checks 楽天市場 (Rakuten Ichiba) prices for items on your watchlist, compares them with
eBay, and estimates your profit after fees, shipping and duty for each country. It also flags licence, legal and
shipping problems, such as knives to the UK.

- **Scanner** (`scanner/`): Python. GitHub Actions runs it every day at about 05:00 JST.
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
```

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

**Before you buy anything, tap "Check eBay sold prices" on the card.** The profit estimate is based on current
*asking* prices, because eBay limits its sold-price data to approved partners.

## How profit is estimated

```
sell price  = median of current eBay listings from Japan-based sellers (or all sellers if fewer than 3) × 97%
profit      = sell price in yen − currency conversion cost
              − eBay fees (final value fee + international fee + per-order fee, plus tax on fees)
              − EMS shipping (by weight and zone; switches to the new Japan Post rates on 1 Feb 2027)
              − US duty you prepay (12.5%, US only)
              − Rakuten price − domestic postage (if not included) − packaging
```

The rates marked ASSUMPTION in `config.yaml`, such as the international fee and tax on fees, should be checked
against your first eBay invoice.

## Limits worth knowing
- Comparison prices come from eBay.com. Other countries are assumed to sell at the same price, with their own
  shipping and duty applied.
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
