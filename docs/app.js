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
    renderDeals(); renderWatch(); renderRules(); renderCosts();
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

    let rows = DATA.opportunities.map((o) => ({ o, f: figure(o, dest) })).filter(({ o, f }) => {
      if (!f) return false;
      if (cat && o.category !== cat) return false;
      if (f.blocked) return false;
      if (hideLoss && f.profit_jpy <= 0) return false;
      if (f.profit_jpy < minP || f.margin < minM) return false;
      if (hideBlock && o.warnings.some((w) => w.level === "block" && (!w.country || w.country === f.country))) return false;
      if (text && !`${o.title_ja} ${o.title_en || ""} ${o.item_name}`.toLowerCase().includes(text)) return false;
      return true;
    });
    const key = { profit: (r) => r.f.profit_jpy, margin: (r) => r.f.margin, roi: (r) => r.f.roi, buy: (r) => -r.o.buy_jpy }[sort];
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
            <span class="chip">${esc(o.shop || "")}</span></div>
        </div>
      </div>
      <div class="nums">
        <div class="num"><b>${yen(o.buy_jpy)}</b><span>Buy${o.postage_included ? "" : " + postage"}${o.points_jpy ? ` · ${o.point_rate}x pts −${yen(o.points_jpy)}` : ""}</span></div>
        <div class="num"><b>${yen(f.sale_jpy)}</b><span>Sell ${money(f.sale_local, f.currency)}</span></div>
        <div class="num"><b class="${f.profit_jpy > 0 ? "gain" : "loss"}">${yen(f.profit_jpy)}</b><span>Profit → ${esc(f.country)}</span></div>
        <div class="num"><b>${pct(f.margin)}</b><span>Margin (ROI ${pct(f.roi)})</span></div>
      </div>
      <div class="dests">${destChips}</div>
      ${top.length ? `<ul class="warns">${top.map(warn).join("")}</ul>` : ""}
      <details>
        <summary>Breakdown, comparisons &amp; notes</summary>
        <table>
          <tr><td>Sale price ${money(f.sale_local, f.currency)} on ${esc(siteFor(f))} → yen, after conversion cost</td><td>${yen(f.revenue_jpy)}</td></tr>
          <tr><td>eBay fees (incl. international fee &amp; tax on fees)</td><td>−${yen(f.ebay_fees_jpy)}</td></tr>
          <tr><td>EMS shipping to ${esc(destName(f.country))} (${o.weight_g} g packed)</td><td>−${yen(f.shipping_jpy)}</td></tr>
          ${f.duty_jpy ? `<tr><td>Import duty you prepay (DDP)</td><td>−${yen(f.duty_jpy)}</td></tr>` : ""}
          <tr><td>Rakuten price</td><td>−${yen(f.buy_jpy)}</td></tr>
          ${f.points_jpy ? `<tr><td>楽天ポイント (Rakuten points): shop ${o.point_rate}x${DATA.assumptions.points.extra_rate_pct ? ` + your extra ${DATA.assumptions.points.extra_rate_pct}x` : ""}</td><td>+${yen(f.points_jpy)}</td></tr>` : ""}
          ${f.domestic_postage_jpy ? `<tr><td>Domestic postage (not included in listing)</td><td>−${yen(f.domestic_postage_jpy)}</td></tr>` : ""}
          <tr><td>Packaging</td><td>−${yen(f.packaging_jpy)}</td></tr>
          <tr class="total"><td>Estimated profit</td><td class="${f.profit_jpy > 0 ? "gain" : "loss"}">${yen(f.profit_jpy)}</td></tr>
        </table>
        <p class="hint">Sell price = median of ${f.comp_count || 0} current listings on ${esc(siteFor(f))} from ${esc(f.comp_basis || "—")},
          less ${Math.round((1 - DATA.assumptions.ebay.undercut) * 100)}% to undercut${f.price_source !== "local" ? " (" + esc(f.price_source) + ")" : ""}.
          ${(dc.jp_count ?? 0)} competing listings from Japan there. These are asking prices — check what actually sold before you buy.</p>
        ${infos.length ? `<ul class="warns">${infos.map(warn).join("")}</ul>` : ""}
      </details>
      <div class="links">
        <a class="btn hot" href="${esc(safeUrl(soldUrl))}" target="_blank" rel="noopener">Check sold prices (${esc(siteFor(f).replace("www.", ""))})</a>
        <a class="btn" href="${esc(safeUrl(o.url))}" target="_blank" rel="noopener">Rakuten listing</a>
        <a class="btn alt" href="${esc(safeUrl(activeUrl))}" target="_blank" rel="noopener">eBay listings</a>
      </div>
    </article>`;
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
          <span>Rakuten listings matched</span><span>${i.rakuten_matched ?? "—"} of ${i.rakuten_found ?? "—"}</span>
        </div>
        ${i.error ? `<ul class="warns"><li class="warn block">Error: ${esc(i.error)}</li></ul>` : ""}
        <div class="links">
          <a class="btn hot" href="${esc(safeUrl(i.sold_url))}" target="_blank" rel="noopener">eBay sold prices</a>
          <a class="btn alt" href="${esc(safeUrl(i.rakuten_search_url))}" target="_blank" rel="noopener">Rakuten search</a>
        </div></article>`;
    }).join("");
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
    const kv = (rs) => `<div class="kv">${rs.map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join("")}</div>`;
    $("#costs").innerHTML = `<div class="section"><h3>Scan schedule</h3>${kv(schedRows)}
      <p class="hint">Add お買い物マラソン (Shopping Marathon) and other sale dates under <code>sales: windows</code> in config.yaml when Rakuten announces them. 楽天スーパーSALE (Super Sale) is detected automatically.</p></div>
      <div class="section"><h3>Push alerts</h3>${kv(alertRows)}</div>
      <div class="section"><h3>Fees &amp; costs</h3>${kv(rows)}</div>
      <div class="section"><h3>楽天ポイント (Rakuten points)</h3>${kv(ptsRows)}</div>
      <div class="section"><h3>Exchange rates</h3>${kv(fxRows)}<p class="hint">${esc(DATA.fx.source)}</p></div>
      <div class="section"><h3>Destinations</h3>${kv(dests)}
      <p class="hint">Japan Post raises international rates on 1 Feb 2027 (e.g. EMS to the US for 1 kg: ¥5,300 → ¥7,400). The app switches tables automatically on that date.</p></div>`;
  }

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
})();
