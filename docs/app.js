/* Japan Resale Finder — front end. Reads data/results.json written by the daily scan. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const yen = (n) => (n == null ? "—" : (n < 0 ? "−¥" : "¥") + Math.abs(Math.round(n)).toLocaleString("ja-JP"));
  const usd = (n) => (n == null ? "—" : "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 }));
  const pct = (n) => (n == null ? "—" : Math.round(n * 100) + "%");
  const pct1 = (n) => (n == null ? "—" : +(n * 100).toFixed(2) + "%");
  const money = (n, cur) => (n == null ? "—" : new Intl.NumberFormat("en-GB", { style: "currency", currency: cur || "USD", maximumFractionDigits: 0 }).format(n));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
  const ICON = { knife: "🔪", pedal: "🎸", record: "💿", cd_dvd: "💿", game: "🎮", book: "📚", fishing: "🎣",
                 watch: "⌚", kitchenware: "🫖", kimono: "👘", cards: "🃏" };
  const LEVEL_ICON = { block: "🚫", caution: "⚠️", info: "ℹ️" };

  let DATA = null;
  const store = {
    get(k, d) { try { const v = localStorage.getItem("jrf:" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("jrf:" + k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  };

  // ------------------------------------------------------------- tabs
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + b.dataset.tab));
    window.scrollTo({ top: 0 });
  }));

  // ------------------------------------------------------------- load
  fetch("data/results.json", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((d) => { DATA = d; init(); })
    .catch((e) => { $("#status").textContent = "Couldn't load results (" + e.message + "). Has the first scan run?"; });

  function init() {
    const when = new Date(DATA.generated_at);
    $("#status").textContent = `Scanned ${when.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })} · $1 = ¥${DATA.fx.usd_jpy}`;
    $("#sampleBanner").hidden = DATA.mode !== "sample";
    if (DATA.sale_now) {
      const end = new Date(DATA.sale_now.end).toLocaleString("en-GB", { timeZone: "Asia/Tokyo", dateStyle: "medium", timeStyle: "short" });
      $("#saleBanner").textContent = `🛍 ${DATA.sale_now.name} is on until ${end} JST — scanning hourly 20:37–23:37.`;
      $("#saleBanner").hidden = false;
    }

    const cats = [...new Set(DATA.items.map((i) => i.category))];
    const labels = Object.fromEntries(DATA.items.map((i) => [i.category, i.label]));
    $("#fCat").insertAdjacentHTML("beforeend", cats.map((c) => `<option value="${esc(c)}">${esc(labels[c] || c)}</option>`).join(""));
    $("#fDest").insertAdjacentHTML("beforeend", Object.entries(DATA.destinations)
      .map(([k, d]) => `<option value="${esc(k)}">${esc(d.name)}</option>`).join(""));

    const saved = store.get("filters", {});
    for (const [id, v] of Object.entries(saved)) {
      const el = document.getElementById(id);
      if (!el) continue;
      if (el.type === "checkbox") el.checked = v; else el.value = v;
    }
    $("#filters").addEventListener("input", () => { saveFilters(); renderDeals(); });
    renderDeals(); renderIdeas(); renderWatch(); renderRules(); renderCosts();
  }

  function saveFilters() {
    const f = {};
    document.querySelectorAll("#filters select, #filters input").forEach((el) => { f[el.id] = el.type === "checkbox" ? el.checked : el.value; });
    store.set("filters", f);
  }

  // ------------------------------------------------------------- deals
  function figure(o, dest) {
    if (dest === "best") return o.best ? { ...o.best } : null;
    const r = o.per_dest[dest];
    return r && r.ok ? { country: dest, ...r } : null;
  }

  function renderDeals() {
    const cat = $("#fCat").value, dest = $("#fDest").value;
    const minP = Number($("#fProfit").value || 0), minM = Number($("#fMargin").value || 0) / 100;
    const text = $("#fText").value.trim().toLowerCase();
    const hideLoss = $("#fLoss").checked, hideBlock = $("#fBlock").checked;
    const sort = $("#fSort").value;
    const onlyGreat = $("#fGreat").checked;

    let rows = DATA.opportunities.map((o) => ({ o, f: figure(o, dest) })).filter(({ o, f }) => {
      if (!f) return false;
      if (cat && o.category !== cat) return false;
      if (f.blocked) return false;
      if (hideLoss && f.profit_jpy <= 0) return false;
      if (f.profit_jpy < minP || f.margin < minM) return false;
      if (hideBlock && o.warnings.some((w) => w.level === "block" && (!w.country || w.country === f.country))) return false;
      if (onlyGreat && !(o.deal && o.deal.great)) return false;
      if (text && !`${o.title_ja} ${o.title_en || ""} ${o.item_name}`.toLowerCase().includes(text)) return false;
      return true;
    });
    const key = { profit: (r) => r.f.profit_jpy, margin: (r) => r.f.margin, roi: (r) => r.f.roi, buy: (r) => -r.o.buy_jpy,
                  week: (r) => (r.f.profit_per_week != null ? r.f.profit_per_week : -1e9),
                  deal: (r) => (r.o.deal && r.o.deal.pct_below_typical != null ? r.o.deal.pct_below_typical : -9) }[sort];
    rows.sort((a, b) => key(b) - key(a));

    $("#count").textContent = `${rows.length} of ${DATA.opportunities.length} listings` +
      (dest === "best" ? " · profit shown for the best allowed destination" : ` · profit if shipped to ${DATA.destinations[dest].name}`);
    $("#deals").innerHTML = rows.length ? rows.map(({ o, f }) => card(o, f)).join("")
      : `<div class="empty">Nothing matches these filters.<br>Try lowering the minimum profit or turning off "Hide losses".</div>`;
  }

  function card(o, f) {
    const item = DATA.items.find((i) => i.id === o.item_id) || {};
    const dc = (item.comps_by_dest || {})[f.country] || item.comps || {};
    const soldUrl = f.price_source === "local" && dc.sold_url ? dc.sold_url : item.sold_url;
    const activeUrl = f.price_source === "local" && dc.active_url ? dc.active_url : item.active_url;
    const destName = (c) => (DATA.destinations[c] || {}).name || c;
    const relevant = o.warnings.filter((w) => !w.country || w.country === f.country);
    const top = dedupe(relevant.filter((w) => w.level !== "info"));
    const infos = dedupe(relevant.filter((w) => w.level === "info"));
    const thumb = o.image ? `<img class="thumb" src="${esc(safeUrl(o.image))}" alt="" loading="lazy">`
      : `<div class="thumb">${ICON[o.category] || "📦"}</div>`;
    const gt = "https://translate.google.com/?sl=ja&tl=en&op=translate&text=" + encodeURIComponent(o.title_ja);
    const destChips = Object.entries(o.per_dest).map(([c, r]) => {
      if (!r.ok) return `<span class="dest">${esc(c)} n/a</span>`;
      const cls = r.blocked ? "dest blocked" : (c === f.country ? "dest best" : "dest");
      return `<span class="${cls}" title="${esc(destName(c))}">${esc(c)} ${r.blocked ? "blocked" : yen(r.profit_jpy)}</span>`;
    }).join("");

    return `<article class="card">
      <div class="card-head">${thumb}
        <div class="titles">
          <p class="t-en">${esc(o.title_en || o.item_name)}</p>
          <p class="t-ja">${esc(o.title_ja)} ${o.title_en ? "" : `· <a href="${gt}" target="_blank" rel="noopener">translate</a>`}</p>
          <div class="chips"><span class="chip">${ICON[o.category] || ""} ${esc(o.item_name)}</span>
            <span class="chip">${esc(o.shop || "")}</span>${trustChip(o.trust)}</div>
          ${dealChips(o.deal)}
        </div>
      </div>
      <div class="nums">
        <div class="num"><b>${yen(o.buy_jpy)}</b><span>Buy${o.postage_included ? "" : " + postage"}${o.point_rate >= 2 ? ` · ${o.point_rate}x points` : ""}</span></div>
        <div class="num"><b>${yen(f.sale_jpy)}</b><span>Sell ${money(f.sale_local, f.currency)}</span></div>
        <div class="num"><b class="${f.profit_jpy > 0 ? "gain" : "loss"}">${yen(f.profit_jpy)}</b><span>Profit → ${esc(f.country)}</span></div>
        <div class="num"><b>${pct(f.margin)}</b><span>Margin (ROI ${pct(f.roi)})</span></div>
      </div>
      <div class="dests">${destChips}</div>
      ${o.sell_speed && o.sell_speed.days ? `<p class="hint">⏱ Sells in about ${Math.round(o.sell_speed.days)} days (${esc(o.sell_speed.source)}) · ≈ ${yen(f.profit_per_week)} profit per week of selling time</p>` : ""}
      ${top.length ? `<ul class="warns">${top.map(warn).join("")}</ul>` : ""}
      <details>
        <summary>Breakdown, comparisons &amp; notes</summary>
        <table>
          <tr><td>Sale price ${money(f.sale_local, f.currency)} on ${esc(siteFor(f))} → yen, after conversion cost</td><td>${yen(f.revenue_jpy)}</td></tr>
          <tr><td>eBay fees (${esc(f.fee_source)})</td><td>−${yen(f.ebay_fees_jpy)}</td></tr>
          <tr><td>Shipping to ${esc(destName(f.country))}: ${esc(svcName(f.shipping_service))} (${o.weight_g} g, ${esc(f.shipping_source)})</td><td>−${yen(f.shipping_jpy)}</td></tr>
          ${f.duty_jpy ? `<tr><td>Import duty you prepay (DDP)</td><td>−${yen(f.duty_jpy)}</td></tr>` : ""}
          <tr><td>Rakuten price</td><td>−${yen(f.buy_jpy)}</td></tr>
          ${f.points_jpy ? `<tr><td>楽天ポイント (Rakuten points): shop ${o.point_rate}x${DATA.assumptions.points.extra_rate_pct ? ` + your extra ${DATA.assumptions.points.extra_rate_pct}x` : ""}</td><td>+${yen(f.points_jpy)}</td></tr>` : ""}
          ${f.domestic_postage_jpy ? `<tr><td>Domestic postage (not included in listing)</td><td>−${yen(f.domestic_postage_jpy)}</td></tr>` : ""}
          <tr><td>Packaging</td><td>−${yen(f.packaging_jpy)}</td></tr>
          ${f.reserve_jpy ? `<tr><td>Reserve for returns / damage (${pct1(f.reserve_rate)})</td><td>−${yen(f.reserve_jpy)}</td></tr>` : ""}
          ${f.tax_refund_jpy ? `<tr><td>Consumption-tax refund (課税事業者 / taxable business)</td><td>+${yen(f.tax_refund_jpy)}</td></tr>` : ""}
          <tr class="total"><td>Estimated profit</td><td class="${f.profit_jpy > 0 ? "gain" : "loss"}">${yen(f.profit_jpy)}</td></tr>
        </table>
        <p class="hint">Sell price = median of ${f.comp_count || 0} current listings on ${esc(siteFor(f))} from ${esc(f.comp_basis || "—")},
          less ${Math.round((1 - DATA.assumptions.ebay.undercut) * 100)}% to undercut.${f.price_source !== "local" ? ` ${esc((DATA.destinations[f.country] || {}).site || "")} had too few listings, so the eBay.com price is used.` : ` ${(dc.jp_count ?? 0)} competing listings from Japan there.`}
          These are asking prices — check what actually sold before you buy.</p>
        ${f.fx ? `<p class="hint">💱 If the yen gets 5% stronger: <b class="${f.fx.yen_stronger_5 > 0 ? "gain" : "loss"}">${yen(f.fx.yen_stronger_5)}</b> · 5% weaker: <b class="gain">${yen(f.fx.yen_weaker_5)}</b></p>` : ""}
        ${chart(item, o)}
        ${trustList(o.trust)}
        ${infos.length ? `<ul class="warns">${infos.map(warn).join("")}</ul>` : ""}
      </details>
      <div class="links">
        <a class="btn hot" href="${esc(safeUrl(soldUrl))}" target="_blank" rel="noopener">Check sold prices (${esc(siteFor(f).replace("www.", ""))})</a>
        <a class="btn" href="${esc(safeUrl(o.url))}" target="_blank" rel="noopener">Rakuten listing</a>
        <a class="btn alt" href="${esc(safeUrl(activeUrl))}" target="_blank" rel="noopener">eBay listings</a>
      </div>
    </article>`;
  }

  function trustChip(t) {
    if (!t) return "";
    const rev = t.reviews ? ` ★${(t.rating || 0).toFixed(1)} (${t.reviews})` : "";
    if (t.score >= 2) return `<span class="chip trust-good">✓ Trusted shop${rev}</span>`;
    if (t.score <= -2) return `<span class="chip trust-bad">⚠ Low trust${rev}</span>`;
    if (!t.reviews) return `<span class="chip">No reviews yet</span>`;
    return rev ? `<span class="chip">${rev.trim()}</span>` : "";
  }
  function trustList(t) {
    if (!t || !t.reasons.length) return "";
    const cls = { good: "info", meh: "caution", bad: "caution" };
    return `<p class="hint"><b>Shop trust score ${t.score > 0 ? "+" : ""}${t.score}</b></p>
      <ul class="warns">${t.reasons.map((r) => `<li class="warn ${cls[r.kind]}">${r.kind === "good" ? "✓" : "⚠️"} ${esc(r.text)}</li>`).join("")}</ul>`;
  }
  function dealChips(d) {
    if (!d || !d.tags.length) return "";
    return `<div class="chips">${d.tags.map((t) => `<span class="chip deal-${esc(t.kind)}">${esc(t.text)}</span>`).join("")}</div>`;
  }
  function chart(item, o) {
    const h = (item.history || []).filter((r) => r[1] || r[2]);
    if (h.length < 2) return `<p class="hint">Price chart appears after a few days of scans.</p>`;
    const W = 320, H = 70, P = 4;
    const vals = h.flatMap((r) => [r[1], r[2]]).concat([o.buy_jpy]).filter(Boolean);
    const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
    const x = (i) => P + (i * (W - 2 * P)) / (h.length - 1);
    const y = (v) => H - P - ((v - lo) / span) * (H - 2 * P);
    const line = (k) => h.map((r, i) => (r[k] ? `${x(i).toFixed(1)},${y(r[k]).toFixed(1)}` : null)).filter(Boolean).join(" ");
    const d = o.deal || {};
    const trend = item.ebay_trend_us;
    return `<div class="chart">
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Rakuten price history">
        <polyline points="${line(2)}" class="l-med"/><polyline points="${line(1)}" class="l-min"/>
        <circle cx="${x(h.length - 1)}" cy="${y(o.buy_jpy)}" r="4" class="dot"/>
      </svg>
      <p class="hint">Rakuten, last ${h.length} days: <span class="k-min">— cheapest</span> · <span class="k-med">- - typical</span> · ● this listing.
        ${d.typical ? `Typical ${yen(d.typical)}, previous low ${yen(d.low)}.` : ""}
        ${trend != null ? ` eBay.com price ${trend >= 0 ? "up" : "down"} ${pct(Math.abs(trend))} over the period.` : ""}</p>
    </div>`;
  }

  function svcName(k) {
    return { EMS: "EMS", parcel_air: "国際小包 airmail parcel" }[k] || k || "—";
  }

  function siteFor(f) {
    return f.price_source === "local" ? (DATA.destinations[f.country] || {}).site || "ebay.com" : "www.ebay.com";
  }

  function dedupe(ws) {
    const seen = new Set();
    return ws.filter((w) => (seen.has(w.text) ? false : seen.add(w.text)));
  }
  function warn(w) {
    const src = w.source ? ` <a href="${esc(safeUrl(w.source))}" target="_blank" rel="noopener">source</a>` : "";
    return `<li class="warn ${esc(w.level)}">${LEVEL_ICON[w.level] || ""} ${esc(w.text)}${src}</li>`;
  }

  // ------------------------------------------------------------- ideas
  function renderIdeas() {
    const S = DATA.suggestions || { items: [] };
    if (!S.items.length) { $("#ideas").innerHTML = `<div class="empty">No ideas yet — they appear after the Monday morning scan.</div>`; return; }
    const when = S.generated_at ? new Date(S.generated_at).toLocaleDateString("en-GB", { dateStyle: "medium" }) : "";
    $("#ideas").innerHTML = `<p class="count">${S.items.length} ideas · ${esc(when)}</p>` + S.items.map((s, n) => `
      <article class="card">
        <div class="card-head"><div class="thumb">${ICON[s.category] || "💡"}</div>
          <div class="titles"><p class="t-en">${esc(s.ebay_query)}</p><p class="t-ja">${esc(s.title_ja)}</p>
            <div class="chips"><span class="chip">${esc(s.keyword)}</span><span class="chip">${s.reviews} reviews on Rakuten</span></div></div></div>
        <div class="nums">
          <div class="num"><b>${yen(s.buy_jpy)}</b><span>Buy</span></div>
          <div class="num"><b>${usd(s.sale_usd)}</b><span>Sell (eBay.com)</span></div>
          <div class="num"><b class="gain">${yen(s.best_profit_jpy)}</b><span>Profit → ${esc(s.best_country)}</span></div>
          <div class="num"><b>${s.comps}</b><span>Japan listings</span></div>
        </div>
        <details><summary>Watchlist entry</summary><pre class="yaml" id="yaml${n}">${esc(s.yaml)}</pre></details>
        <div class="links">
          <button class="btn hot" data-copy="yaml${n}">Copy watchlist entry</button>
          <a class="btn" href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">Rakuten</a>
          <a class="btn alt" href="${esc(safeUrl(s.sold_url))}" target="_blank" rel="noopener">eBay sold prices</a>
        </div>
      </article>`).join("");
    $("#ideas").querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", async () => {
      const text = document.getElementById(b.dataset.copy).textContent;
      try { await navigator.clipboard.writeText(text); b.textContent = "Copied ✓"; }
      catch { const r = document.createRange(); r.selectNodeContents(document.getElementById(b.dataset.copy));
              const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); b.textContent = "Selected — copy it"; }
    }));
  }

  // ------------------------------------------------------------- watchlist
  function renderWatch() {
    $("#watch").innerHTML = DATA.items.map((i) => {
      const c = i.comps || {};
      const ok = i.status === "ok";
      return `<article class="card">
        <div class="card-head"><div class="thumb">${ICON[i.category] || "📦"}</div>
          <div class="titles"><p class="t-en">${esc(i.name)}</p>
            <p class="t-ja">楽天 (Rakuten) search: ${esc(i.rakuten)} · eBay search: ${esc(i.ebay)}</p>
            <div class="chips"><span class="chip">${esc(i.label)}</span>
              <span class="chip" style="${ok ? "" : "color:var(--loss)"}">${esc(i.status)}</span></div></div></div>
        <div class="kv" style="margin-top:10px">
          ${Object.entries(i.comps_by_dest || {}).map(([code, m]) => `<span>${esc(m.site.replace("www.", ""))} — listings from Japan / all</span><span>${m.jp_count} / ${m.all_count} · ${money(m.local_price, m.currency)}</span>`).join("")}
          <span>Sell speed</span><span>${i.sell_speed && i.sell_speed.days ? `~${Math.round(i.sell_speed.days)} days (${esc(i.sell_speed.source)})` : "unknown — add days_to_sell from Terapeak"}</span>
          ${i.your_last_sale ? `<span>Your last sale</span><span>${yen(i.your_last_sale.sale_jpy)} → ${esc(i.your_last_sale.country)} (${esc(i.your_last_sale.date)})</span>` : ""}
          <span>Rakuten listings matched</span><span>${i.rakuten_matched ?? "—"} of ${i.rakuten_found ?? "—"}</span>
        </div>
        ${filteredInfo(i)}
        ${i.error ? `<ul class="warns"><li class="warn block">Error: ${esc(i.error)}</li></ul>` : ""}
        <div class="links">
          <a class="btn hot" href="${esc(safeUrl(i.sold_url))}" target="_blank" rel="noopener">eBay sold prices</a>
          <a class="btn alt" href="${esc(safeUrl(i.rakuten_search_url))}" target="_blank" rel="noopener">Rakuten search</a>
        </div></article>`;
    }).join("");
  }

  function filteredInfo(i) {
    const hid = i.rakuten_hidden || [];
    const f = ((i.comps_by_dest || {}).US || {}).filtered || {};
    const fTotal = Object.values(f).reduce((a, b) => a + b, 0);
    if (!hid.length && !fTotal) return "";
    return `<details><summary>Filtered out: ${hid.length} Rakuten listing${hid.length === 1 ? "" : "s"}, ${fTotal} eBay.com listing${fTotal === 1 ? "" : "s"}</summary>
      ${hid.length ? `<ul class="warns">${hid.map((h) => `<li class="warn caution">${esc(h.shop)}: ${esc(h.why)}</li>`).join("")}</ul>` : ""}
      ${fTotal ? `<div class="kv" style="margin-top:8px">${Object.entries(f).map(([k, v]) => `<span>${esc(k)}</span><span>${v}</span>`).join("")}</div>` : ""}
    </details>`;
  }

  // ------------------------------------------------------------- rules
  function renderRules() {
    const R = DATA.rules;
    const list = (ws) => (ws && ws.length ? `<ul class="warns">${ws.map(warn).join("")}</ul>` : "");
    let html = `<div class="section"><h3>General</h3>${list(DATA.global_notes)}</div>`;
    html += `<div class="section"><h3>By destination</h3>` + Object.entries(R.destinations || {})
      .map(([c, ws]) => `<p><b>${esc((DATA.destinations[c] || {}).name || c)}</b></p>${list(ws)}`).join("") + `</div>`;
    html += Object.entries(R.categories).map(([k, c]) => {
      const blocked = Object.entries(c.blocked_destinations || {}).map(([cc, t]) => ({ level: "block", text: `${cc}: ${t}` }));
      const id = c.id_check_any_price ? [{ level: "caution", text: "ID check and ledger entry required at any price when buying from individuals." }] : [];
      return `<div class="section"><h3>${ICON[k] || ""} ${esc(c.label)}</h3>
        <p class="hint">古物商 category (licence item category): ${esc(c.kobutsu || "—")}</p>
        ${list([...blocked, ...id, ...(c.warnings || [])])}</div>`;
    }).join("");
    html += `<div class="section"><h3>Words that trigger warnings</h3>` +
      R.keywords.map((k) => `<p class="hint"><b>${k.match.map(esc).join(", ")}</b></p>${list([k])}`).join("") + `</div>`;
    $("#rules").innerHTML = html;
  }

  // ------------------------------------------------------------- costs
  function renderCosts() {
    const a = DATA.assumptions, e = a.ebay;
    const rows = [
      ["Currency conversion cost", pct1(a.fx_conversion_cost)],
      ["eBay final value fee", pct1(e.final_value_fee) + " (watches / media higher)"],
      ["eBay international fee", pct1(e.international_fee) + " — check Seller Hub"],
      ["Tax on eBay fees", pct1(e.fee_tax) + " — check your invoice"],
      ["Per-order fee", "$" + e.per_order_fee_usd],
      ["List price vs. Japan competitors", pct1(e.undercut) + " of their median"],
      ["Packaging", yen(a.costs.packaging_jpy)],
      ["Domestic postage (when not included)", yen(a.costs.rakuten_domestic_postage_jpy)],
      ["Shipping", a.shipping_table_from >= "2027" ? `${esc(a.shipping_service)} rates from ${esc(a.shipping_table_from)}` : `${esc(a.shipping_service)}, current Japan Post rates`],
      ["Translation", esc(DATA.translation)],
    ];
    const dests = Object.entries(DATA.destinations).map(([k, d]) =>
      [`${esc(d.name)} — ${esc(d.site.replace("www.", ""))}, ${esc(d.currency)}, EMS zone ${d.zone}`, d.duty ? `you prepay ~${pct1(d.duty)} duty` : "buyer pays any import tax"]);
    const fxRows = Object.entries(DATA.fx.jpy_per || { USD: DATA.fx.usd_jpy }).map(([c, v]) => [`1 ${esc(c)}`, `¥${v}`]);
    const p = a.points || {}, al = a.alert_rules || {}, alertState = DATA.alerts || {};
    const ptsRows = [["Counted as discount", p.enabled ? "yes" : "no"], ["Shop rate", "from Rakuten, per listing"],
      ["Your extra rate (SPU / 買いまわり shop-hopping bonus)", (p.extra_rate_pct || 0) + "x"], ["Value per point", "¥" + (p.point_value_jpy ?? 1)]];
    const fmtJst = (iso) => new Date(iso).toLocaleString("en-GB", { timeZone: "Asia/Tokyo", dateStyle: "medium", timeStyle: "short" });
    const schedRows = [["Every day (JST)", DATA.schedule.daily_jst.join(" and ")],
      ["During Rakuten sales (JST)", DATA.schedule.sale_hourly_jst.join(", ")],
      ["Sale on now", DATA.sale_now ? esc(DATA.sale_now.name) : "no"],
      ["Next sale", DATA.next_sale ? `${esc(DATA.next_sale.name)} — ${fmtJst(DATA.next_sale.start)}` : "—"]];
    const alertRows = [["Status", alertState.enabled ? `on — ${alertState.sent} sent last scan` : `off (${esc(alertState.reason || "")})`],
      ["Alert when profit ≥", yen(al.min_profit_jpy)], ["…and margin ≥", pct1(al.min_margin)],
      ["Max alerts per scan", al.max_per_run], ["Re-alert same listing if profit rises", pct1(al.realert_if_profit_up)]];
    const tr = a.trust || {}, tre = tr.ebay || {}, trr = tr.rakuten || {}, hc = a.history || {};
    const trustRows = [["Rakuten: hide listings scoring below", trr.hide_below_score],
      ["Rakuten: drop-ship / back-order words", esc((trr.dropship_words || []).join(", "))],
      ["Rakuten: blocked / trusted shops", `${(trr.blocked_shops || []).length} / ${(trr.trusted_shops || []).length}`],
      ["eBay comps: min seller feedback", `${tre.min_feedback_score} ratings, ${tre.min_feedback_pct}% positive`],
      ["eBay comps: max estimated delivery", tre.max_delivery_days + " days"],
      ["eBay comps: one listing per seller", tre.one_listing_per_seller ? "yes" : "no"],
      ["eBay sellers excluded", (tre.exclude_sellers || []).length]];
    const histRows = [["History", DATA.history_mode === "sample" ? "sample (made-up)" : "built from your scans"],
      ["Compared against", `last ${hc.window_days} days`], ["Tags start after", `${hc.min_days} days of scans`],
      ["🔥 Great deal when", `${pct1(hc.great_deal_below_typical)} below typical price`],
      ["↓ Price-drop tag when", `listing falls ${pct1(hc.price_drop_min)}+`]];
    const C = DATA.calibration || {};
    const assumedFee = (e.final_value_fee + e.international_fee) * (1 + e.fee_tax);
    const calRows = [["Sales in the file", (C.sales || 0) + (C.sample ? " (sample)" : "")],
      ["eBay fees: real vs assumed", C.fee_rate != null ? `${pct1(C.fee_rate)} vs ${pct1(assumedFee)}` : `assumed ${pct1(assumedFee)} (needs 5 sales)`],
      ["Returns / damage rate", C.return_rate != null ? pct1(C.return_rate) : "category reserve (needs 10 sales)"],
      ["Items with real shipping & sell speed", C.items_with_sales || 0]];
    const rb = (a.risk || {}).reserve_by_category || {};
    rows.push(["Shipping services compared", (a.allowed_services || []).map(svcName).join(", ")]);
    rows.push(["Returns / damage reserve", Object.entries(rb).map(([k, v]) => `${k} ${pct1(v)}`).join(", ")]);
    rows.push(["Consumption-tax refund", (a.tax || {}).consumption_tax_refund ? "on (課税事業者 / taxable business)" : "off"]);
    const kv = (rs) => `<div class="kv">${rs.map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join("")}</div>`;
    $("#costs").innerHTML = `<div class="section"><h3>Scan schedule</h3>${kv(schedRows)}
      <p class="hint">Add お買い物マラソン (Shopping Marathon) and other sale dates under <code>sales: windows</code> in config.yaml when Rakuten announces them. 楽天スーパーSALE (Super Sale) is detected automatically.</p></div>
      <div class="section"><h3>Push alerts</h3>${kv(alertRows)}</div>
      <div class="section"><h3>Calibration from your sales</h3>${kv(calRows)}
        <p class="hint">Export the Google Sheet's "Calibration" tab as CSV and save it as <code>scanner/calibration/sales.csv</code> on GitHub.</p></div>
      <div class="section"><h3>Fees &amp; costs</h3>${kv(rows)}</div>
      <div class="section"><h3>楽天ポイント (Rakuten points)</h3>${kv(ptsRows)}</div>
      <div class="section"><h3>Seller trust filters</h3>${kv(trustRows)}</div>
      <div class="section"><h3>Price history &amp; deal tags</h3>${kv(histRows)}</div>
      <div class="section"><h3>Exchange rates</h3>${kv(fxRows)}<p class="hint">${esc(DATA.fx.source)}</p></div>
      <div class="section"><h3>Destinations</h3>${kv(dests)}
      <p class="hint">Japan Post raises international rates on 1 Feb 2027 (e.g. EMS to the US for 1 kg: ¥5,300 → ¥7,400). The app switches tables automatically on that date.</p></div>`;
  }

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
})();
