/* ============================================================
   HGHMNDS MARKET INTELLIGENCE — DASHBOARD BRAIN (Power BI style)
   ============================================================ */

/* 0. Chart.js global defaults ------------------------------------------------ */
if (window.Chart) {
  Chart.defaults.color = '#8b949e';
  Chart.defaults.borderColor = '#30363d';
  Chart.defaults.font.family = 'Inter';
  Chart.defaults.font.size = 11;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.backgroundColor = '#1c2333';
  Chart.defaults.plugins.tooltip.borderColor = '#30363d';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.titleColor = '#e6edf3';
  Chart.defaults.plugins.tooltip.bodyColor = '#8b949e';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.maintainAspectRatio = false;
}

const C = {
  blue: '#388bfd', blueDim: '#1f4a8a', cyan: '#00d4ff', purple: '#7c3aed',
  green: '#3fb950', red: '#f85149', yellow: '#d29922', orange: '#db6d28',
  indigo: '#6e7fdd', grid: '#30363d', text: '#8b949e', chartBg: '#13192a',
};
const DOUGHNUT_COLORS = [C.blue, C.cyan, C.purple, C.green, C.yellow, C.orange, C.indigo, C.red];

const STOPWORDS = new Set(['the', 'a', 'is', 'it', 'and', 'in', 'of', 'to', 'i',
  'my', 'for', 'was', 'so', 'very', 'this', 'that', 'are', 'with', 'on']);

const DATA = {};
const CHARTS = {};
const JSON_FILES = ['summary', 'products', 'reviews', 'categories', 'price_ranges', 'weekly_diff'];
const BASE_CANDIDATES = ['../assets/data/', 'assets/data/', 'data/'];

/* 1. Data loading ------------------------------------------------------------ */
async function loadJSON(name) {
  for (const base of BASE_CANDIDATES) {
    try {
      const res = await fetch(base + name + '.json', { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (e) { /* next */ }
  }
  throw new Error('Could not load ' + name + '.json');
}

async function boot() {
  try {
    const results = await Promise.all(JSON_FILES.map(loadJSON));
    JSON_FILES.forEach((n, i) => { DATA[n] = results[i]; });
    initDashboard();
  } catch (err) {
    console.error(err);
    document.querySelector('.content').insertAdjacentHTML('afterbegin',
      `<div class="error-state">Failed to load dashboard data.<br>${err.message}<br><br>
       Serve the folder over HTTP — browsers block file:// fetches.</div>`);
  }
}
document.addEventListener('DOMContentLoaded', boot);

/* ---------------------------- utility functions ----------------------------- */
const formatPHP = (n) => (n == null || isNaN(n)) ? '—'
  : '₱' + Math.round(Number(n)).toLocaleString('en-US');
const formatK = (n) => {
  if (n == null || isNaN(n)) return '—';
  n = Number(n);
  return n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'K' : String(n);
};
const truncate = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n) + '…' : s; };
const round1 = (n) => (n == null || isNaN(n)) ? '—' : Number(n).toFixed(1);
const round2 = (n) => (n == null || isNaN(n)) ? '—' : Number(n).toFixed(2);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function starHTML(rating) {
  const r = Math.round(Number(rating) || 0);
  let out = '<span class="stars">';
  for (let i = 1; i <= 5; i++) out += i <= r ? '★' : '<span class="empty">★</span>';
  return out + '</span>';
}

function computeLinearRegression(xs, ys) {
  const n = xs.length;
  if (!n) return { slope: 0, intercept: 0 };
  let sx = 0, sy = 0, sxy = 0, sxx = 0;
  for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; sxy += xs[i] * ys[i]; sxx += xs[i] * xs[i]; }
  const denom = n * sxx - sx * sx;
  if (denom === 0) return { slope: 0, intercept: sy / n };
  const slope = (n * sxy - sx * sy) / denom;
  const intercept = (sy - slope * sx) / n;
  return { slope, intercept };
}

function pearson(xs, ys) {
  const n = xs.length;
  if (n < 2) return 0;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    dx += (xs[i] - mx) ** 2; dy += (ys[i] - my) ** 2;
  }
  const den = Math.sqrt(dx * dy);
  return den === 0 ? 0 : num / den;
}

function getWordFrequency(reviews, rating, topN) {
  const counter = new Map();
  reviews.filter((r) => Math.round(Number(r.rating)) === rating).forEach((r) => {
    (String(r.review_text || '').toLowerCase().match(/[a-z']+/g) || []).forEach((w) => {
      if (w.length > 1 && !STOPWORDS.has(w)) counter.set(w, (counter.get(w) || 0) + 1);
    });
  });
  return [...counter.entries()].sort((a, b) => b[1] - a[1]).slice(0, topN)
    .map(([word, count]) => ({ word, count }));
}

function getSentimentScore(reviews) {
  if (!reviews.length) return 0;
  const sum = reviews.reduce((a, r) => a + (Number(r.rating) || 0), 0);
  return (sum / (reviews.length * 5)) * 100;
}

/* per-platform aggregate from products.json (verified set) */
function platformAgg(platform) {
  const rows = DATA.products.filter((p) => p.platform === platform);
  const prices = rows.map((r) => r.price).filter((v) => v != null && !isNaN(v));
  const rated = rows.filter((r) => r.has_ratings && r.rating_avg != null);
  return {
    count: rows.length,
    avgPrice: prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : 0,
    avgRating: rated.length ? rated.reduce((a, b) => a + b.rating_avg, 0) / rated.length : 0,
    reviews: rows.reduce((a, b) => a + (Number(b.review_count) || 0), 0),
    sold: rows.reduce((a, b) => a + (Number(b.sold_final) || 0), 0),
  };
}

function getPlatformHealth(agg) {
  const ratingPart = (agg.avgRating / 5) * 40;
  const soldPart = (Math.min(agg.sold, 1000) / 1000) * 40;
  const reviewPart = (Math.min(agg.reviews, 500) / 500) * 20;
  return Math.round((ratingPart + soldPart + reviewPart) * 10) / 10;
}

/* category aggregates derived from products.json for internal consistency */
function categoryAgg() {
  const map = new Map();
  DATA.products.forEach((p) => {
    const k = p.category_derived || 'Other';
    if (!map.has(k)) map.set(k, { category: k, count: 0, sold: 0, priceSum: 0, ratingSum: 0, ratingN: 0 });
    const o = map.get(k);
    o.count++; o.sold += Number(p.sold_final) || 0; o.priceSum += Number(p.price) || 0;
    if (p.has_ratings && p.rating_avg != null) { o.ratingSum += p.rating_avg; o.ratingN++; }
  });
  return [...map.values()].map((o) => ({
    ...o, avgPrice: o.count ? o.priceSum / o.count : 0,
    avgRating: o.ratingN ? o.ratingSum / o.ratingN : null,
  }));
}

const PRICE_BUCKETS = [
  { label: 'Under ₱300', lo: 0, hi: 300 },
  { label: '₱300–₱500', lo: 300, hi: 500 },
  { label: '₱500–₱800', lo: 500, hi: 800 },
  { label: '₱800–₱1200', lo: 800, hi: 1200 },
  { label: 'Above ₱1200', lo: 1200, hi: Infinity },
];
function priceBucketStats() {
  return PRICE_BUCKETS.map((b) => {
    const rows = DATA.products.filter((p) => p.price >= b.lo && p.price < b.hi);
    return { label: b.label, count: rows.length,
      sold: rows.reduce((a, p) => a + (Number(p.sold_final) || 0), 0) };
  });
}

function badge(platform) {
  return platform === 'Shopee'
    ? '<span class="badge-shopee">Shopee</span>'
    : '<span class="badge-lazada">Lazada</span>';
}

/* ------------------------------ init dashboard ------------------------------ */
const TAB_TITLES = {
  overview: 'Overview — Command Center', sales: 'Sales Performance',
  pricing: 'Pricing Analytics', reviews: 'Customer Reviews',
  recommendations: 'Strategic Recommendations', products: 'Product Explorer',
  about: 'About',
};
const RENDERERS = {};
const rendered = new Set();

function initDashboard() {
  initTicker();
  initTopbar();
  initLastUpdated();
  initNav();
  renderTab('overview');
}

function renderTab(tab) {
  if (!rendered.has(tab)) {
    try { (RENDERERS[tab] || (() => {}))(); } catch (e) { console.error('render ' + tab, e); }
    rendered.add(tab);
  }
  Object.values(CHARTS).forEach((c) => { try { c.resize(); } catch (e) {} });
}

function initNav() {
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tab = item.dataset.tab;
      document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));
      item.classList.add('active');
      document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
      document.getElementById('tab-' + tab).classList.add('active');
      document.getElementById('topbar-title').textContent = TAB_TITLES[tab] || '';
      renderTab(tab);
    });
  });
}

function initTicker() {
  const s = DATA.summary;
  const avgRating = (s.avg_rating_shopee + s.avg_rating_lazada) / 2;
  const parts = [
    `TOTAL PRODUCTS: ${s.total_products}`,
    `SHOPEE: ${s.shopee_count} PRODUCTS`,
    `LAZADA: ${s.lazada_count} PRODUCTS`,
    `AVG RATING: ${round1(avgRating)} ★`,
    `TOTAL SOLD: ${Number(s.total_sold).toLocaleString()} UNITS`,
    `TOTAL REVIEWS: ${Number(s.total_reviews).toLocaleString()}`,
    `TOP CATEGORY: ${s.top_category}`,
    `LAST UPDATED: ${s.scraped_at}`,
  ];
  const chunk = parts.map((p) => `<span>${esc(p)} ·</span>`).join('');
  document.getElementById('ticker').innerHTML = chunk + chunk;
}

function initTopbar() {
  const s = DATA.summary;
  document.getElementById('topbar-products').textContent = `${s.total_products} Products`;
  document.getElementById('topbar-updated').textContent = `Updated ${s.scraped_at}`;
}

function initLastUpdated() {
  document.getElementById('last-updated').textContent = DATA.summary.scraped_at || '—';
}

/* --------------------------------- KPI card --------------------------------- */
function kpiHTML({ label, value, delta, sub, small }) {
  let d = '';
  if (delta) {
    d = `<div class="kpi-delta ${delta.dir}">${delta.dir === 'up' ? '▲' : delta.dir === 'down' ? '▼' : '■'} ${esc(delta.text)}</div>`;
  }
  return `<div class="kpi-label">${esc(label)}</div>
    <div class="kpi-value ${small ? 'small' : ''}">${value}</div>
    ${d}${sub ? `<div class="kpi-sub">${esc(sub)}</div>` : ''}`;
}

function chartCard(cardId, title, badgeText, bodyClass) {
  const el = document.getElementById(cardId);
  el.innerHTML = `<div class="chart-card-header">
      <span class="chart-card-title">${esc(title)}</span>
      ${badgeText ? `<span class="chart-card-badge">${esc(badgeText)}</span>` : ''}
    </div><div class="${bodyClass || 'chart-wrap'}"></div>`;
  return el.querySelector('.' + (bodyClass || 'chart-wrap').split(' ')[0]);
}

function makeChart(container, type, data, options) {
  const canvas = document.createElement('canvas');
  container.appendChild(canvas);
  const key = container.closest('.chart-card').id;
  if (CHARTS[key]) CHARTS[key].destroy();
  CHARTS[key] = new Chart(canvas, { type, data, options });
  return CHARTS[key];
}

function gridScale(extra) {
  return {
    x: { grid: { color: C.grid }, ticks: { color: C.text, font: { size: 10 } }, border: { color: C.grid } },
    y: { grid: { color: C.grid }, ticks: { color: C.text, font: { size: 10 } }, border: { color: C.grid }, beginAtZero: true },
    ...extra,
  };
}

/* =============================== OVERVIEW ================================== */
RENDERERS.overview = function () {
  const s = DATA.summary;
  const diff = DATA.weekly_diff || {};
  const newN = (diff.new_products || []).length;
  const remN = (diff.disappeared_products || []).length;
  const priceN = (diff.price_changes || []).length;
  const rateN = (diff.rating_changes || []).length;
  const changeCount = newN + remN + priceN + rateN;

  const rated = DATA.products.filter((p) => p.has_ratings && p.rating_avg != null);
  const avgRating = rated.length ? rated.reduce((a, b) => a + b.rating_avg, 0) / rated.length : 0;
  const revenue = DATA.products.reduce((a, p) => a + (Number(p.price) || 0) * (Number(p.sold_final) || 0), 0);
  const revShopee = DATA.reviews.filter((r) => r.platform === 'Shopee').length;
  const revLazada = DATA.reviews.filter((r) => r.platform === 'Lazada').length;

  document.getElementById('kpi-products').innerHTML = kpiHTML({
    label: 'Authentic Products', value: s.total_products,
    delta: newN ? { dir: 'up', text: `+${newN} new` } : { dir: 'flat', text: 'no change' },
    sub: `Shopee ${s.shopee_count} · Lazada ${s.lazada_count}`,
  });
  document.getElementById('kpi-sold').className = 'kpi-card accent-green';
  document.getElementById('kpi-sold').innerHTML = kpiHTML({
    label: 'Total Units Sold', value: Number(s.total_sold).toLocaleString(),
    sub: 'Lazada lifetime + Shopee 30d',
  });
  document.getElementById('kpi-revenue-est').className = 'kpi-card accent-cyan';
  document.getElementById('kpi-revenue-est').innerHTML = kpiHTML({
    label: 'Est. GMV', value: formatPHP(revenue), small: true, sub: 'Price × units, verified set',
  });
  document.getElementById('kpi-rating').className = 'kpi-card accent-yellow';
  document.getElementById('kpi-rating').innerHTML = kpiHTML({
    label: 'Avg Rating', value: `${round1(avgRating)} ★`, sub: `from ${rated.length} rated products`,
  });
  document.getElementById('kpi-reviews').className = 'kpi-card accent-purple';
  document.getElementById('kpi-reviews').innerHTML = kpiHTML({
    label: 'Total Reviews', value: Number(s.total_reviews).toLocaleString(),
    sub: `Substantive: S ${revShopee} · L ${revLazada}`,
  });
  document.getElementById('kpi-weekly-change').className = 'kpi-card accent-orange';
  document.getElementById('kpi-weekly-change').innerHTML = kpiHTML({
    label: 'Weekly Changes', value: changeCount,
    sub: `${newN} new · ${remN} removed · ${priceN} price`,
  });

  // Platform comparison (pure HTML)
  const pcBody = chartCard('card-platform-compare', 'Platform Comparison', null, 'compare-wrap');
  ['Shopee', 'Lazada'].forEach((plat) => {
    const a = platformAgg(plat);
    const h = getPlatformHealth(a);
    pcBody.insertAdjacentHTML('beforeend', `
      <div class="compare-panel">
        <h4>${badge(plat)}</h4>
        <div class="compare-row"><span class="label">Products</span><span class="val">${a.count}</span></div>
        <div class="compare-row"><span class="label">Avg Price</span><span class="val">${formatPHP(a.avgPrice)}</span></div>
        <div class="compare-row"><span class="label">Avg Rating</span><span class="val">${round2(a.avgRating)} ★</span></div>
        <div class="compare-row"><span class="label">Total Sold</span><span class="val">${a.sold.toLocaleString()}</span></div>
        <div class="health-wrap">
          <div class="health-label"><span>Health Score /100</span><span class="score">${h}</span></div>
          <div class="progress-track"><div class="progress-fill" style="width:${h}%"></div></div>
        </div>
      </div>`);
  });

  // Top 10 bestsellers horizontal bar
  const topBody = chartCard('card-top-products', 'Top 10 Bestsellers', 'by units sold');
  const top10 = DATA.products.slice().sort((a, b) => b.sold_final - a.sold_final).slice(0, 10);
  makeChart(topBody, 'bar', {
    labels: top10.map((p) => truncate(p.product_name_clean, 25)),
    datasets: [{ data: top10.map((p) => p.sold_final), backgroundColor: C.blue, borderRadius: 3 }],
  }, { indexAxis: 'y', scales: gridScale(), plugins: { tooltip: { callbacks: {
    title: (i) => top10[i[0].dataIndex].product_name_clean } } } });

  // Category mix doughnut
  const cats = categoryAgg().sort((a, b) => b.count - a.count);
  const total = cats.reduce((a, c) => a + c.count, 0);
  const cmEl = document.getElementById('card-category-mix');
  cmEl.innerHTML = `<div class="chart-card-header"><span class="chart-card-title">Category Mix</span></div>
    <div class="chart-wrap" style="max-height:55%"></div>
    <div class="card-scroll" style="flex:0 0 auto;max-height:42%;margin-top:6px"></div>`;
  makeChart(cmEl.querySelector('.chart-wrap'), 'doughnut', {
    labels: cats.map((c) => c.category),
    datasets: [{ data: cats.map((c) => c.count), backgroundColor: DOUGHNUT_COLORS, borderColor: C.chartBg, borderWidth: 2 }],
  }, { cutout: '58%', plugins: { tooltip: { callbacks: {
    label: (ctx) => `${ctx.label}: ${ctx.raw} (${(ctx.raw / total * 100).toFixed(0)}%)` } } } });
  cmEl.querySelector('.card-scroll').innerHTML = cats.map((c, i) => `
    <div class="compare-row" style="padding:2px 0">
      <span class="label"><span style="color:${DOUGHNUT_COLORS[i % 8]}">●</span> ${esc(c.category)}</span>
      <span class="val">${c.count} · ${(c.count / total * 100).toFixed(0)}%</span></div>`).join('');

  // Change log
  const clBody = chartCard('card-change-log', 'Weekly Changes', null, 'change-list');
  renderChangeLog(clBody);
};

function renderChangeLog(container) {
  const diff = DATA.weekly_diff || {};
  const items = [];
  (diff.new_products || []).forEach((p) => items.push({ e: '🆕', t: 'New', n: p.product_name, pl: p.platform }));
  (diff.price_changes || []).forEach((p) => items.push({ e: p.pct_change > 0 ? '📈' : '📉',
    t: `Price ${p.pct_change > 0 ? 'up' : 'down'} ${Math.abs(p.pct_change)}%`, n: p.product_name, pl: p.platform }));
  (diff.rating_changes || []).forEach((p) => items.push({ e: '⭐',
    t: `Rating ${p.old_rating}→${p.new_rating}`, n: p.product_name, pl: p.platform }));
  (diff.disappeared_products || []).forEach((p) => items.push({ e: '🚨', t: 'Removed', n: p.product_name, pl: p.platform }));

  if (!items.length) {
    container.innerHTML = `<div class="change-empty">No changes detected this week.<br>
      The first weekly diff is generated on the next scheduled scrape.</div>`;
    return;
  }
  container.innerHTML = items.slice(0, 12).map((it) => `
    <div class="change-row"><span>${it.e}</span>
      <span><span class="c-text">${esc(it.t)} · ${esc(it.pl)} · </span><span class="c-name">${esc(truncate(it.n, 32))}</span></span>
    </div>`).join('');
}

/* ================================= SALES ================================== */
let bestSort = { key: 'sold_final', dir: -1 };

RENDERERS.sales = function () {
  const P = DATA.products;
  const totalSold = P.reduce((a, p) => a + (Number(p.sold_final) || 0), 0);
  const top = P.slice().sort((a, b) => b.sold_final - a.sold_final)[0] || {};
  const cats = categoryAgg().sort((a, b) => b.sold - a.sold);
  const shopeeSold = platformAgg('Shopee').sold;
  const lazadaSold = platformAgg('Lazada').sold;

  document.getElementById('kpi-total-sold').innerHTML = kpiHTML({
    label: 'Total Units Sold', value: totalSold.toLocaleString(), sub: 'Verified products' });
  document.getElementById('kpi-top-product').className = 'kpi-card accent-cyan';
  document.getElementById('kpi-top-product').innerHTML = kpiHTML({
    label: 'Best Seller', value: `<span style="font-size:0.9rem">${esc(truncate(top.product_name_clean, 22))}</span>`,
    small: true, sub: `${Number(top.sold_final || 0).toLocaleString()} units` });
  document.getElementById('kpi-top-category').className = 'kpi-card accent-purple';
  document.getElementById('kpi-top-category').innerHTML = kpiHTML({
    label: 'Top Category', value: `<span style="font-size:1.1rem">${esc(cats[0] ? cats[0].category : '—')}</span>`,
    small: true, sub: `${cats[0] ? cats[0].sold.toLocaleString() : 0} units sold` });
  document.getElementById('kpi-shopee-sold').className = 'kpi-card accent-orange';
  document.getElementById('kpi-shopee-sold').innerHTML = kpiHTML({
    label: 'Shopee Sold', value: shopeeSold.toLocaleString(), sub: 'sold_30d (API-limited)' });
  document.getElementById('kpi-lazada-sold').className = 'kpi-card accent-indigo';
  document.getElementById('kpi-lazada-sold').innerHTML = kpiHTML({
    label: 'Lazada Sold', value: lazadaSold.toLocaleString(), sub: 'lifetime units' });

  // Bestsellers table
  const bsEl = document.getElementById('card-bestsellers');
  bsEl.innerHTML = `<div class="chart-card-header"><span class="chart-card-title">Bestsellers — Top 15</span>
    <span class="chart-card-badge">click Sold / Price to sort</span></div>
    <div class="card-scroll" id="bestsellers-body"></div>`;
  renderBestsellers();

  // Sales by category vertical bar
  const scBody = chartCard('card-sales-category', 'Sales by Category', 'units');
  makeChart(scBody, 'bar', {
    labels: cats.map((c) => c.category),
    datasets: [{ data: cats.map((c) => c.sold),
      backgroundColor: cats.map((_, i) => i === 0 ? C.cyan : C.blue), borderRadius: 3 }],
  }, { scales: gridScale({ x: { grid: { display: false }, ticks: { color: C.text, font: { size: 9 },
    maxRotation: 40, minRotation: 40 } } }) });

  // Price vs sales scatter + regression
  const pvBody = chartCard('card-price-vs-sales', 'Price vs Sales — Correlation', 'trend line');
  const mk = (plat, color) => ({ label: plat, type: 'scatter',
    data: P.filter((p) => p.platform === plat).map((p) => ({ x: p.price, y: p.sold_final, name: p.product_name_clean })),
    backgroundColor: color, pointRadius: 4, pointHoverRadius: 6 });
  const xs = P.map((p) => p.price), ys = P.map((p) => p.sold_final);
  const { slope, intercept } = computeLinearRegression(xs, ys);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  makeChart(pvBody, 'scatter', {
    datasets: [mk('Shopee', C.orange), mk('Lazada', C.indigo), {
      label: 'Trend', type: 'line', borderColor: C.cyan, borderDash: [6, 4], borderWidth: 2,
      pointRadius: 0, data: [{ x: minX, y: slope * minX + intercept }, { x: maxX, y: slope * maxX + intercept }],
    }],
  }, { scales: {
    x: { grid: { color: C.grid }, ticks: { color: C.text, callback: (v) => '₱' + v }, title: { display: true, text: 'Price', color: C.text } },
    y: { grid: { color: C.grid }, ticks: { color: C.text }, beginAtZero: true, title: { display: true, text: 'Units Sold', color: C.text } },
  }, plugins: { tooltip: { callbacks: {
    label: (ctx) => ctx.raw.name ? `${ctx.raw.name}: ${formatPHP(ctx.raw.x)}, ${ctx.raw.y} sold` : '' } } } });

  // Sell-through analysis
  const buckets = priceBucketStats();
  const totBucketSold = buckets.reduce((a, b) => a + b.sold, 0) || 1;
  const topBucket = buckets.slice().sort((a, b) => b.sold - a.sold)[0];
  const stEl = document.getElementById('card-sellthrough');
  stEl.innerHTML = `<div class="chart-card-header"><span class="chart-card-title">Sell-Through Analysis</span></div>
    <div class="insight-box" style="margin-bottom:10px">Products priced <strong>${esc(topBucket.label)}</strong>
      account for <strong>${(topBucket.sold / totBucketSold * 100).toFixed(0)}%</strong> of all units sold —
      the strongest price-point demand.</div>
    <div class="chart-wrap"></div>`;
  makeChart(stEl.querySelector('.chart-wrap'), 'bar', {
    labels: buckets.map((b) => b.label),
    datasets: [{ data: buckets.map((b) => b.sold),
      backgroundColor: buckets.map((b) => b === topBucket ? C.green : C.blue), borderRadius: 3 }],
  }, { scales: gridScale({ x: { grid: { display: false }, ticks: { color: C.text, font: { size: 8 },
    maxRotation: 30, minRotation: 30 } } }) });
};

function renderBestsellers() {
  const rows = DATA.products.slice().sort((a, b) => b.sold_final - a.sold_final).slice(0, 15);
  rows.sort((a, b) => {
    let va = a[bestSort.key], vb = b[bestSort.key];
    if (typeof va === 'string') { va = va.toLowerCase(); vb = String(vb).toLowerCase(); }
    return va < vb ? -bestSort.dir : va > vb ? bestSort.dir : 0;
  });
  const arrow = (k) => bestSort.key === k ? `<span class="arrow">${bestSort.dir === -1 ? '▼' : '▲'}</span>` : '';
  const body = document.getElementById('bestsellers-body');
  body.innerHTML = `<table><thead><tr>
      <th>#</th><th>Product</th><th>Platform</th><th>Category</th>
      <th class="sortable" data-k="price">Price ${arrow('price')}</th>
      <th class="sortable" data-k="sold_final">Sold ${arrow('sold_final')}</th>
      <th>Rating</th></tr></thead><tbody>${rows.map((p, i) => `
      <tr class="${i < 3 ? 'rank-' + (i + 1) : ''}">
        <td>${i + 1}</td><td>${esc(truncate(p.product_name_clean, 30))}</td>
        <td>${badge(p.platform)}</td><td><span class="badge-category">${esc(p.category_derived)}</span></td>
        <td>${formatPHP(p.price)}</td><td>${Number(p.sold_final).toLocaleString()}</td>
        <td>${starHTML(p.rating_avg)}</td></tr>`).join('')}</tbody></table>`;
  body.querySelectorAll('th.sortable').forEach((th) => th.addEventListener('click', () => {
    const k = th.dataset.k;
    if (bestSort.key === k) bestSort.dir *= -1; else { bestSort.key = k; bestSort.dir = -1; }
    renderBestsellers();
  }));
}

/* ================================ PRICING ================================= */
RENDERERS.pricing = function () {
  const P = DATA.products;
  const prices = P.map((p) => p.price).filter((v) => v != null && !isNaN(v));
  const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
  const sorted = prices.slice().sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const minP = Math.min(...prices), maxP = Math.max(...prices);
  const discs = P.map((p) => Number(p.discount_pct) || 0);
  const avgDisc = discs.reduce((a, b) => a + b, 0) / discs.length;
  const onSale = P.filter((p) => Number(p.discount_pct) > 0).length;
  const elasticity = pearson(P.map((p) => p.price), P.map((p) => p.sold_final));

  document.getElementById('kpi-avg-price').innerHTML = kpiHTML({
    label: 'Avg Price', value: formatPHP(avg), sub: `median ${formatPHP(median)}` });
  document.getElementById('kpi-price-range').className = 'kpi-card accent-cyan';
  document.getElementById('kpi-price-range').innerHTML = kpiHTML({
    label: 'Price Range', value: `<span style="font-size:1.1rem">${formatPHP(minP)} – ${formatPHP(maxP)}</span>`, small: true });
  document.getElementById('kpi-avg-discount').className = 'kpi-card accent-green';
  document.getElementById('kpi-avg-discount').innerHTML = kpiHTML({
    label: 'Avg Discount', value: round1(avgDisc) + '%', sub: 'verified, non-suspicious' });
  document.getElementById('kpi-price-elasticity').className = 'kpi-card accent-purple';
  document.getElementById('kpi-price-elasticity').innerHTML = kpiHTML({
    label: 'Price Elasticity', value: round2(elasticity),
    sub: 'neg = lower price → more sales' });
  document.getElementById('kpi-on-sale').className = 'kpi-card accent-orange';
  document.getElementById('kpi-on-sale').innerHTML = kpiHTML({
    label: 'On Sale Now', value: onSale, sub: `${(onSale / P.length * 100).toFixed(0)}% of catalog` });

  // Price distribution histogram (8 buckets)
  const nB = 8, w = (maxP - minP) / nB || 1;
  const counts = new Array(nB).fill(0);
  prices.forEach((p) => { let i = Math.floor((p - minP) / w); if (i >= nB) i = nB - 1; if (i < 0) i = 0; counts[i]++; });
  const maxCount = Math.max(...counts);
  const pdBody = chartCard('card-price-dist', 'Price Distribution', 'product count');
  makeChart(pdBody, 'bar', {
    labels: counts.map((_, i) => '₱' + Math.round(minP + i * w)),
    datasets: [{ data: counts, backgroundColor: counts.map((c) => c === maxCount ? C.cyan : C.blue), borderRadius: 3 }],
  }, { scales: gridScale({ x: { grid: { display: false }, ticks: { color: C.text, font: { size: 9 } } } }) });

  // Avg price by category horizontal bar
  const cats = categoryAgg().sort((a, b) => b.avgPrice - a.avgPrice);
  const pcBody = chartCard('card-price-category', 'Avg Price by Category', '₱');
  makeChart(pcBody, 'bar', {
    labels: cats.map((c) => c.category),
    datasets: [{ data: cats.map((c) => Math.round(c.avgPrice)), backgroundColor: C.purple, borderRadius: 3 }],
  }, { indexAxis: 'y', scales: gridScale({ x: { grid: { color: C.grid }, ticks: { color: C.text, callback: (v) => '₱' + v } } }) });

  // Discount analysis grouped bar (Shopee vs Lazada)
  const daBody = chartCard('card-discount-analysis', 'Discount Analysis', 'S vs L');
  const dstat = (plat) => {
    const r = P.filter((p) => p.platform === plat);
    const onS = r.filter((p) => Number(p.discount_pct) > 0);
    const ds = onS.map((p) => Number(p.discount_pct));
    return { onSale: onS.length, avg: ds.length ? ds.reduce((a, b) => a + b, 0) / ds.length : 0, max: ds.length ? Math.max(...ds) : 0 };
  };
  const sS = dstat('Shopee'), sL = dstat('Lazada');
  makeChart(daBody, 'bar', {
    labels: ['On Sale (#)', 'Avg Disc %', 'Max Disc %'],
    datasets: [
      { label: 'Shopee', data: [sS.onSale, +sS.avg.toFixed(1), sS.max], backgroundColor: C.orange, borderRadius: 3 },
      { label: 'Lazada', data: [sL.onSale, +sL.avg.toFixed(1), sL.max], backgroundColor: C.indigo, borderRadius: 3 },
    ],
  }, { scales: gridScale({ x: { grid: { display: false }, ticks: { color: C.text, font: { size: 9 } } } }),
    plugins: { legend: { display: true, labels: { color: C.text, boxWidth: 8, font: { size: 9 } } } } });

  // Platform price comparison per category (grouped)
  const ppBody = chartCard('card-platform-price', 'Price by Platform / Category', '₱ avg');
  const catNames = [...new Set(P.map((p) => p.category_derived))];
  const avgFor = (plat, cat) => {
    const r = P.filter((p) => p.platform === plat && p.category_derived === cat);
    return r.length ? Math.round(r.reduce((a, p) => a + p.price, 0) / r.length) : 0;
  };
  makeChart(ppBody, 'bar', {
    labels: catNames,
    datasets: [
      { label: 'Shopee', data: catNames.map((c) => avgFor('Shopee', c)), backgroundColor: C.orange, borderRadius: 3 },
      { label: 'Lazada', data: catNames.map((c) => avgFor('Lazada', c)), backgroundColor: C.indigo, borderRadius: 3 },
    ],
  }, { scales: gridScale({ x: { grid: { display: false }, ticks: { color: C.text, font: { size: 8 }, maxRotation: 40, minRotation: 40 } } }),
    plugins: { legend: { display: true, labels: { color: C.text, boxWidth: 8, font: { size: 9 } } } } });

  // Data quality (HTML)
  const s = DATA.summary;
  const total = s.total_products + s.suspicious_count; // verified + flagged
  const dqEl = document.getElementById('card-data-quality');
  dqEl.innerHTML = `<div class="chart-card-header"><span class="chart-card-title">Data Quality</span></div>
    <div class="dq-grid">
      <div class="dq-item"><div class="dq-num">${total}</div><div class="dq-lbl">Total Scraped</div></div>
      <div class="dq-item"><div class="dq-num">${s.total_products}</div><div class="dq-lbl">Authentic</div></div>
      <div class="dq-item"><div class="dq-num">${P.length}</div><div class="dq-lbl">Verified Shown</div></div>
      <div class="dq-item"><div class="dq-num">${s.suspicious_count}</div><div class="dq-lbl">Suspicious Flagged</div></div>
    </div>
    <div class="insight-box warn"><strong>${(s.suspicious_count / total * 100).toFixed(0)}%</strong>
      of listings filtered as suspicious/knockoff. All metrics reflect verified HGHMNDS products only.</div>`;
};

/* ================================ REVIEWS ================================= */
let reviewTimer = null, reviewIdx = 0;

RENDERERS.reviews = function () {
  const R = DATA.reviews;
  const s = DATA.summary;
  const rated = DATA.products.filter((p) => p.has_ratings && p.rating_avg != null);
  const avgRating = rated.length ? rated.reduce((a, b) => a + b.rating_avg, 0) / rated.length : 0;
  const sentiment = getSentimentScore(R);
  const fiveStar = R.filter((r) => Math.round(Number(r.rating)) === 5).length;
  const substantive = R.length;
  const avgLen = R.reduce((a, r) => a + (Number(r.review_length) || 0), 0) / (R.length || 1);

  document.getElementById('kpi-total-reviews').innerHTML = kpiHTML({
    label: 'Total Reviews', value: Number(s.total_reviews).toLocaleString(), sub: `${substantive} substantive` });
  document.getElementById('kpi-avg-rating').className = 'kpi-card accent-yellow';
  document.getElementById('kpi-avg-rating').innerHTML = kpiHTML({
    label: 'Avg Rating', value: `${round1(avgRating)} ★`, sub: 'rated products' });
  document.getElementById('kpi-sentiment').className = 'kpi-card accent-green';
  document.getElementById('kpi-sentiment').innerHTML = kpiHTML({
    label: 'Sentiment Score', value: Math.round(sentiment) + '/100', sub: 'weighted from ratings' });
  document.getElementById('kpi-5star-pct').className = 'kpi-card accent-cyan';
  document.getElementById('kpi-5star-pct').innerHTML = kpiHTML({
    label: '5★ Share', value: (fiveStar / R.length * 100).toFixed(0) + '%', sub: `${fiveStar} reviews` });
  document.getElementById('kpi-substantive').className = 'kpi-card accent-purple';
  document.getElementById('kpi-substantive').innerHTML = kpiHTML({
    label: 'Substantive', value: substantive, sub: `avg ${Math.round(avgLen)} chars` });

  // Rating breakdown grouped bar
  const starBy = (plat) => {
    const c = [0, 0, 0, 0, 0];
    R.filter((r) => r.platform === plat).forEach((r) => { const s = Math.round(Number(r.rating)); if (s >= 1 && s <= 5) c[s - 1]++; });
    return c;
  };
  const sh = starBy('Shopee'), la = starBy('Lazada');
  const rbBody = chartCard('card-rating-breakdown', 'Rating Breakdown by Platform', 'S vs L');
  makeChart(rbBody, 'bar', {
    labels: ['5★', '4★', '3★', '2★', '1★'],
    datasets: [
      { label: 'Shopee', data: [sh[4], sh[3], sh[2], sh[1], sh[0]], backgroundColor: C.orange, borderRadius: 3 },
      { label: 'Lazada', data: [la[4], la[3], la[2], la[1], la[0]], backgroundColor: C.indigo, borderRadius: 3 },
    ],
  }, { scales: gridScale({ x: { grid: { display: false } } }),
    plugins: { legend: { display: true, labels: { color: C.text, boxWidth: 8, font: { size: 9 } } } } });

  // Keyword bars
  renderKeywords('card-keywords-positive', '5★ Review Keywords', getWordFrequency(R, 5, 10), 'pos');
  renderKeywords('card-keywords-negative', '1★ Review Keywords', getWordFrequency(R, 1, 10), 'neg');

  // Review samples (rotating)
  const rsEl = document.getElementById('card-review-samples');
  rsEl.innerHTML = `<div class="chart-card-header"><span class="chart-card-title">Customer Voice</span>
    <span class="chart-card-badge">auto-rotating</span></div>
    <div class="review-samples-wrap"><div class="review-cards" id="review-cards"></div>
    <div class="dots" id="review-dots"></div></div>`;
  startReviewRotation();
};

function renderKeywords(cardId, title, pairs, cls) {
  const body = chartCard(cardId, title, cls === 'pos' ? 'positive' : 'negative', 'kw-list');
  const max = pairs.length ? pairs[0].count : 1;
  body.innerHTML = pairs.map((p) => `
    <div class="kw-row"><span class="kw-word">${esc(p.word)}</span>
      <span class="kw-track"><span class="kw-fill ${cls}" style="width:${p.count / max * 100}%"></span></span>
      <span class="kw-count">${p.count}</span></div>`).join('') ||
    '<div class="change-empty">No reviews at this rating.</div>';
}

function startReviewRotation() {
  const pool = DATA.reviews.filter((r) => (r.review_text || '').length >= 20);
  const cardsEl = document.getElementById('review-cards');
  const dotsEl = document.getElementById('review-dots');
  if (!pool.length) { cardsEl.innerHTML = '<div class="change-empty">No reviews available.</div>'; return; }
  const groups = Math.ceil(pool.length / 3);
  const dotN = Math.min(groups, 12);
  // Crossfade the whole container (it persists) rather than fading then
  // hard-swapping innerHTML — that left new cards popping in at full opacity.
  cardsEl.style.transition = 'opacity 0.45s ease';

  const paint = () => {
    const cards = [];
    for (let i = 0; i < 3; i++) {
      const r = pool[(reviewIdx * 3 + i) % pool.length];
      const initial = (r.buyer_name || 'A').trim().charAt(0).toUpperCase() || 'A';
      cards.push(`<div class="review-card">
        <div class="rc-head"><span class="avatar">${esc(initial)}</span>${starHTML(r.rating)}${badge(r.platform)}</div>
        <div class="rc-body">${esc(truncate(r.review_text, 140))}</div>
        <div class="rc-foot"><span>${esc(r.buyer_name || 'Anonymous')}</span><span>${esc(r.date || '')}</span></div>
      </div>`);
    }
    cardsEl.innerHTML = cards.join('');
    dotsEl.innerHTML = Array.from({ length: dotN }, (_, i) =>
      `<span class="dot ${i === reviewIdx % dotN ? 'active' : ''}"></span>`).join('');
  };

  reviewIdx = 0;
  paint();
  cardsEl.style.opacity = '1';
  if (reviewTimer) clearInterval(reviewTimer);
  reviewTimer = setInterval(() => {
    cardsEl.style.opacity = '0';                 // fade out
    setTimeout(() => {                            // swap while invisible
      reviewIdx = (reviewIdx + 1) % groups;
      paint();
      cardsEl.style.opacity = '1';               // fade back in
    }, 460);
  }, 6000);
}

/* =========================== RECOMMENDATIONS ============================== */
RENDERERS.recommendations = function () {
  const P = DATA.products;
  const s = DATA.summary;
  const buckets = priceBucketStats();
  const totSold = buckets.reduce((a, b) => a + b.sold, 0) || 1;
  const topBucket = buckets.slice().sort((a, b) => b.sold - a.sold)[0];
  const cats = categoryAgg();
  const topCatSold = cats.slice().sort((a, b) => b.sold - a.sold)[0];
  const bestValueCat = cats.filter((c) => c.avgRating).sort((a, b) => (b.avgRating / b.avgPrice) - (a.avgRating / a.avgPrice))[0];
  const shopee = platformAgg('Shopee'), lazada = platformAgg('Lazada');
  const suspPct = s.suspicious_count / (s.total_products + s.suspicious_count) * 100;
  const lowRated = P.filter((p) => p.has_ratings && p.rating_avg != null && p.rating_avg < 4.5)
    .sort((a, b) => a.rating_avg - b.rating_avg).slice(0, 3);

  // Score cards
  const pricingScore = Math.round(topBucket.sold / totSold * 100);
  document.getElementById('card-rec-score1').className = 'kpi-card accent-green';
  document.getElementById('card-rec-score1').innerHTML = `<div class="rec-score">
    <div class="kpi-label">Pricing Sweet Spot</div>
    <div class="big">${esc(topBucket.label.replace('₱', '₱'))}</div>
    <div class="kpi-sub">${pricingScore}% of units sold in this band</div></div>`;

  const focusPlatform = lazada.sold > shopee.sold ? 'Lazada' : 'Shopee';
  document.getElementById('card-rec-score2').className = 'kpi-card accent-indigo';
  document.getElementById('card-rec-score2').innerHTML = `<div class="rec-score">
    <div class="kpi-label">Platform to Prioritize</div>
    <div class="big">${focusPlatform}</div>
    <div class="kpi-sub">${focusPlatform === 'Lazada' ? lazada.sold.toLocaleString() + ' units · verified sales data' : 'higher ratings & review volume'}</div></div>`;

  document.getElementById('card-rec-score3').className = 'kpi-card accent-red';
  document.getElementById('card-rec-score3').innerHTML = `<div class="rec-score">
    <div class="kpi-label">Quality Risk</div>
    <div class="big">${suspPct.toFixed(0)}%</div>
    <div class="kpi-sub">${s.suspicious_count} suspicious / knockoff listings flagged</div></div>`;

  // Recommendation list
  const recs = [
    { cls: 'good', html: `<strong>Anchor pricing at ${esc(topBucket.label)}.</strong> This band drives
      ${pricingScore}% of all units sold — the clearest demand signal. Position hero products here.` },
    { cls: '', html: `<strong>Double down on ${esc(topCatSold.category)}.</strong> It leads all categories with
      ${topCatSold.sold.toLocaleString()} units sold across ${topCatSold.count} listings
      (avg ${formatPHP(topCatSold.avgPrice)}).` },
    { cls: '', html: `<strong>Prioritize ${focusPlatform} for volume.</strong> Lazada shows
      ${lazada.sold.toLocaleString()} verified lifetime units vs Shopee's API-limited sold data;
      Shopee still wins on rating (${round2(shopee.avgRating)}★) and review depth.` },
    { cls: 'alert', html: `<strong>${s.suspicious_count} knockoff/suspicious listings detected.</strong>
      File takedowns — these fake-discount listings (₱7,777→₱199 style) erode brand pricing power
      and mislead ${suspPct.toFixed(0)}% of the search surface.` },
    { cls: bestValueCat ? 'good' : '', html: bestValueCat
      ? `<strong>Best value-for-rating: ${esc(bestValueCat.category)}.</strong> Highest rating-per-peso
         (${round2(bestValueCat.avgRating)}★ at ${formatPHP(bestValueCat.avgPrice)}) — a strong upsell anchor.`
      : 'Rating data insufficient for value analysis.' },
    { cls: lowRated.length ? 'warn' : 'good', html: lowRated.length
      ? `<strong>Watch ${lowRated.length} under-performing products.</strong> Lowest rated:
         ${lowRated.map((p) => `${esc(truncate(p.product_name_clean, 24))} (${round1(p.rating_avg)}★)`).join(', ')}.
         Review quality complaints before restocking.`
      : 'No products rated below 4.5★ — quality is consistently strong.' },
  ];
  const listEl = document.getElementById('card-rec-list');
  listEl.innerHTML = `<div class="chart-card-header"><span class="chart-card-title">Strategic Recommendations</span>
    <span class="chart-card-badge">derived from ${P.length} verified products · ${DATA.reviews.length} reviews</span></div>
    <div class="rec-grid">${recs.map((r) => `<div class="insight-box ${r.cls}">${r.html}</div>`).join('')}</div>`;
};

/* ================================ PRODUCTS ================================ */
const filterState = { platform: 'all', category: 'all', price: 'all', rating: 0, sale: false, search: '' };
let prodSort = { key: 'sold_final', dir: -1 };

RENDERERS.products = function () {
  const cats = [...new Set(DATA.products.map((p) => p.category_derived))].sort();
  document.getElementById('filter-bar').innerHTML = `
    <input type="text" id="f-search" placeholder="Search products..." />
    <select id="f-platform"><option value="all">All Platforms</option><option>Shopee</option><option>Lazada</option></select>
    <select id="f-category"><option value="all">All Categories</option>${cats.map((c) => `<option>${esc(c)}</option>`).join('')}</select>
    <select id="f-price"><option value="all">All Prices</option>
      <option value="0-300">Under ₱300</option><option value="300-500">₱300–₱500</option>
      <option value="500-800">₱500–₱800</option><option value="800-1200">₱800–₱1200</option>
      <option value="1200-999999">Above ₱1200</option></select>
    <select id="f-rating"><option value="0">All Ratings</option><option value="4">4★ & up</option><option value="3">3★ & up</option></select>
    <div class="filter-toggle" id="f-sale">On Sale Only</div>
    <span class="filter-count" id="f-count"></span>`;

  document.getElementById('card-products-table').innerHTML = `<div class="table-wrap" id="products-table"></div>`;

  const bind = (id, ev, fn) => document.getElementById(id).addEventListener(ev, fn);
  bind('f-search', 'input', (e) => { filterState.search = e.target.value.toLowerCase(); renderProducts(); });
  bind('f-platform', 'change', (e) => { filterState.platform = e.target.value; renderProducts(); });
  bind('f-category', 'change', (e) => { filterState.category = e.target.value; renderProducts(); });
  bind('f-price', 'change', (e) => { filterState.price = e.target.value; renderProducts(); });
  bind('f-rating', 'change', (e) => { filterState.rating = Number(e.target.value); renderProducts(); });
  bind('f-sale', 'click', (e) => { filterState.sale = !filterState.sale; e.target.classList.toggle('active', filterState.sale); renderProducts(); });

  document.getElementById('drawer-close').addEventListener('click', closeDrawer);
  document.getElementById('drawer-overlay').addEventListener('click', closeDrawer);
  renderProducts();
};

function filteredProducts() {
  return DATA.products.filter((p) => {
    if (filterState.platform !== 'all' && p.platform !== filterState.platform) return false;
    if (filterState.category !== 'all' && p.category_derived !== filterState.category) return false;
    if (filterState.rating && !(p.rating_avg >= filterState.rating)) return false;
    if (filterState.sale && !(Number(p.discount_pct) > 0)) return false;
    if (filterState.search && !String(p.product_name_clean || '').toLowerCase().includes(filterState.search)) return false;
    if (filterState.price !== 'all') {
      const [lo, hi] = filterState.price.split('-').map(Number);
      if (!(p.price >= lo && p.price < hi)) return false;
    }
    return true;
  });
}

function renderProducts() {
  let rows = filteredProducts();
  rows.sort((a, b) => {
    let va = a[prodSort.key], vb = b[prodSort.key];
    if (typeof va === 'string') { va = va.toLowerCase(); vb = String(vb).toLowerCase(); }
    return va < vb ? -prodSort.dir : va > vb ? prodSort.dir : 0;
  });
  document.getElementById('f-count').textContent = `Showing ${rows.length} of ${DATA.products.length} products`;

  const arrow = (k) => prodSort.key === k ? `<span class="arrow">${prodSort.dir === -1 ? '▼' : '▲'}</span>` : '';
  const wrap = document.getElementById('products-table');
  wrap.innerHTML = `<table><thead><tr>
      <th>#</th><th>Product</th><th>Platform</th><th>Category</th>
      <th class="sortable" data-k="price">Price ${arrow('price')}</th>
      <th>Orig</th><th>Disc</th>
      <th class="sortable" data-k="sold_final">Sold ${arrow('sold_final')}</th>
      <th class="sortable" data-k="rating_avg">Rating ${arrow('rating_avg')}</th>
      <th class="sortable" data-k="review_count">Reviews ${arrow('review_count')}</th>
      <th>Link</th></tr></thead><tbody>${rows.map((p, i) => {
        const disc = Number(p.discount_pct) > 0 ? `<span class="disc-tag">-${round1(p.discount_pct)}%</span>` : '—';
        const orig = (p.original_price && p.original_price > p.price) ? `<span class="strike">${formatPHP(p.original_price)}</span>` : '—';
        const initial = String(p.product_name_clean || 'H').trim().charAt(0).toUpperCase();
        const img = p.image_url
          ? `<img class="thumb" src="${esc(p.image_url)}" loading="lazy" onerror="this.outerHTML='<span class=&quot;thumb-ph&quot;>${initial}</span>'"/>`
          : `<span class="thumb-ph">${initial}</span>`;
        return `<tr data-idx="${i}">
          <td>${img}</td>
          <td>${esc(truncate(p.product_name_clean, 34))}</td>
          <td>${badge(p.platform)}</td>
          <td><span class="badge-category">${esc(p.category_derived)}</span></td>
          <td>${formatPHP(p.price)}</td><td>${orig}</td><td>${disc}</td>
          <td>${Number(p.sold_final).toLocaleString()}</td>
          <td>${starHTML(p.rating_avg)} <span style="color:var(--text-muted);font-size:0.7rem">${round1(p.rating_avg)}</span></td>
          <td>${Number(p.review_count).toLocaleString()}</td>
          <td><a class="link-btn" href="${esc(p.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">↗</a></td>
        </tr>`;
      }).join('')}</tbody></table>`;

  wrap.querySelectorAll('th.sortable').forEach((th) => th.addEventListener('click', () => {
    const k = th.dataset.k;
    if (prodSort.key === k) prodSort.dir *= -1; else { prodSort.key = k; prodSort.dir = -1; }
    renderProducts();
  }));
  wrap.querySelectorAll('tbody tr').forEach((tr) => tr.addEventListener('click', () => openDrawer(rows[Number(tr.dataset.idx)])));
}

function openDrawer(p) {
  const initial = String(p.product_name_clean || 'H').trim().charAt(0).toUpperCase();
  const disc = Number(p.discount_pct) > 0 ? `<span class="disc-tag">-${round1(p.discount_pct)}%</span>` : '';
  const orig = (p.original_price && p.original_price > p.price) ? `<span class="strike">${formatPHP(p.original_price)}</span>` : '';
  const img = p.image_url
    ? `<img class="drawer-img" src="${esc(p.image_url)}" onerror="this.style.display='none'"/>` : '';
  document.getElementById('drawer-content').innerHTML = `
    ${img}
    <div>${badge(p.platform)} <span class="badge-category">${esc(p.category_derived)}</span></div>
    <div class="drawer-name">${esc(p.product_name_clean)}</div>
    <div class="drawer-price"><span class="cur">${formatPHP(p.price)}</span> ${orig} ${disc}</div>
    <div class="drawer-stats">
      <div class="drawer-stat"><div class="n">${Number(p.sold_final).toLocaleString()}</div><div class="l">Sold</div></div>
      <div class="drawer-stat"><div class="n">${round1(p.rating_avg)}★</div><div class="l">Rating</div></div>
      <div class="drawer-stat"><div class="n">${Number(p.review_count).toLocaleString()}</div><div class="l">Reviews</div></div>
    </div>
    <div class="drawer-desc">Sold via ${esc(p.sold_source || '—')}. ${p.has_ratings ? 'Rated by verified buyers.' : 'No ratings yet.'}</div>
    <a class="drawer-cta" href="${esc(p.url)}" target="_blank" rel="noopener">View on ${esc(p.platform)} ↗</a>`;
  document.getElementById('product-drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
}
function closeDrawer() {
  document.getElementById('product-drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
}

/* ================================= ABOUT ================================== */
RENDERERS.about = function () {
  document.getElementById('card-about-left').innerHTML = `<div class="about-body">
    <h2>HGHMNDS Market Intelligence</h2>
    <p>An automated market-intelligence platform tracking HGHMNDS Clothing across the Philippines'
       two largest e-commerce marketplaces. It scrapes listings, pricing, ratings, and reviews weekly,
       flags knockoffs, and surfaces the analytics and strategy you see here.</p>
    <h3>Data Sources</h3>
    <div class="pills" style="margin-top:4px">${badge('Shopee')} ${badge('Lazada')}</div>
    <p style="margin-top:8px">Shopee via internal JSON APIs; Lazada via headless browser scraping of search
       and product pages. Deduplicated, cleaned, and authenticity-checked with Pandas.</p>
    <h3>Business Metrics Analyzed</h3>
    <ul>
      <li>Pricing distribution, elasticity & discount strategy</li>
      <li>Sales volume, sell-through & bestseller ranking</li>
      <li>Review sentiment, rating breakdown & keyword mining</li>
      <li>Platform health scoring & knockoff risk detection</li>
    </ul>
    <h3>Pipeline</h3>
    <div class="pipeline">
      <div class="pipe-step"><span class="pi">🕷️</span><span class="pl">Scrape</span></div><span class="pipe-arrow">→</span>
      <div class="pipe-step"><span class="pi">🧹</span><span class="pl">Clean</span></div><span class="pipe-arrow">→</span>
      <div class="pipe-step"><span class="pi">📊</span><span class="pl">Analyze</span></div><span class="pipe-arrow">→</span>
      <div class="pipe-step"><span class="pi">📦</span><span class="pl">Export</span></div><span class="pipe-arrow">→</span>
      <div class="pipe-step"><span class="pi">🚀</span><span class="pl">Deploy</span></div>
    </div></div>`;

  document.getElementById('card-about-right').innerHTML = `<div class="about-body">
    <div class="about-avatar">GA</div>
    <div class="about-name">Gabriel Alegre Caña</div>
    <div class="about-role">Data Analyst · Dashboard Developer</div>
    <div class="about-affil">BS Economics · Cavite State University</div>
    <div class="pills">
      <a class="pill" href="https://www.linkedin.com/" target="_blank" rel="noopener">LinkedIn</a>
      <a class="pill" href="https://github.com/hashtro9-rgb" target="_blank" rel="noopener">GitHub</a>
    </div>
    <h3>Tech Stack</h3>
    <div class="tech-tags">
      <span class="tech-tag">Python</span><span class="tech-tag">Playwright</span>
      <span class="tech-tag">Pandas</span><span class="tech-tag">Chart.js</span>
      <span class="tech-tag">GitHub Actions</span><span class="tech-tag">GitHub Pages</span>
    </div>
    <h3>Automation</h3>
    <p>Dashboard data auto-updates every Sunday via a scheduled GitHub Actions pipeline —
       scrape, clean, analyze, export, and redeploy with zero manual steps.</p>
    <div class="insight-box" style="margin-top:12px">Every metric here is computed from the latest
       verified scrape. Suspicious and knockoff listings are excluded from all analytics.</div>
    </div>`;
};
