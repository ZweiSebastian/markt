/* Markt Terminal – Oberfläche
 * Daten: terminal.json (GitHub Actions, alle 30 Min.) + Live-Kurse (Yahoo) + Live-News (RSS).
 * In der Mac-App laufen Netzabrufe über die native Brücke (kein CORS); im Browser über fetch.
 */
'use strict';

const DATA_URL = new URLSearchParams(location.search).get('data') || 'https://raw.githubusercontent.com/ZweiSebastian/markt/terminal-data/terminal.json';
const DAY = 86400;

// ------------------------------------------------------------------ Native Brücke
const NATIVE = !!(window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.native);
async function nfetch(url, timeout = 25) {
  if (NATIVE) {
    const r = await window.webkit.messageHandlers.native.postMessage({ op: 'fetch', url, timeout });
    if (!r || !r.ok) throw new Error('HTTP ' + (r ? r.status : '?'));
    return r.text;
  }
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.text();
}
function openURL(u) {
  if (!u) return;
  if (NATIVE) window.webkit.messageHandlers.native.postMessage({ op: 'open', url: u });
  else window.open(u, '_blank');
}
function store(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* egal */ } }
// große Daten (Datenbasis) in der App als Datei, im Browser in localStorage
async function bigSave(k, v) { if (NATIVE) { try { await window.webkit.messageHandlers.native.postMessage({ op: 'save', key: k, text: v }); } catch (e) { /* */ } } else store(k, v); }
async function bigLoad(k) { if (NATIVE) { try { return await window.webkit.messageHandlers.native.postMessage({ op: 'load', key: k }); } catch (e) { return null; } } return load(k); }
function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

// ------------------------------------------------------------------ Konfiguration
const C = { s1: '#3987e5', s2: '#d95926', s3: '#199e70', s4: '#c98500', s5: '#d55181', s6: '#2e9e2e', s7: '#9085e9', s8: '#e66767',
  txt: '#e9ebf0', sec: '#a2a8b6', mut: '#697182', grid: '#1c2028', line: '#242934', up: '#3ddc84', down: '#ff6b6b',
  good: '#0ca30c', warn: '#fab219', serious: '#ec835a', crit: '#d03b3b', neg: '#e05252', pos: '#3987e5', mid: '#383835' };
const SER = [C.s1, C.s2, C.s3, C.s4, C.s5, C.s6, C.s7, C.s8];

const RANGES = [['1M', 31], ['3M', 92], ['6M', 183], ['1J', 365], ['3J', 1096], ['5J', 1826], ['10J', 3653], ['Max', 99999]];
let RANGE = +(load('range') || 365);

const SECTIONS = [
  ['einschaetzung', 'Einschätzung'], ['signale', 'Signale'], ['lage', 'Lage'], ['maerkte', 'Märkte'], ['bewertung', 'Bewertung'], ['zinsen', 'Zinsen'],
  ['risiko', 'Risiko & Breite'], ['rohstoffe', 'Rohstoffe'], ['fx', 'Währungen & Krypto'], ['konjunktur', 'Konjunktur'],
  ['zusammen', 'Zusammenhänge'], ['news', 'News'],
];
let SECTION = load('section') || 'einschaetzung';

const STRIP = ['msci', 'spx', 'ndx', 'dax', 'nikkei', 'vix', 'y10', 'y2', 'curve10_2', 'dxy', 'eurusd', 'gold', 'wti', 'btc'];

const GROUPS = [
  ['aktien', 'Aktien'], ['risiko', 'Volatilität'], ['zinsen', 'Zinsen'], ['anleihen', 'Anleihen-ETFs'], ['rohstoffe', 'Rohstoffe'],
  ['fx', 'Währungen'], ['krypto', 'Krypto'], ['verhaeltnis', 'Verhältnisse'], ['konjunktur', 'Konjunktur'],
  ['bewertung', 'Bewertung'], ['breite', 'Marktbreite'], ['sektoren', 'Sektoren'],
];

// Reihen für die Korrelationsmatrix (nur tägliche)
const MATRIX = ['spx', 'ndx', 'rut', 'dax', 'em', 'vix', 'y2', 'y10', 'real10', 'breakeven', 'curve10_2', 'hyg_ief',
  'tlt', 'dxy', 'eurusd', 'usdjpy', 'gold', 'copper', 'cu_au', 'wti', 'natgas', 'btc'];

// Klassische Zusammenhänge: erwartetes Vorzeichen + Erklärung
const CLASSICS = [
  ['y10', 'ndx', -1, 'Zinsen ↔ Tech-Aktien', 'Höhere Zinsen machen künftige Gewinne heute weniger wert – das trifft wachstumsstarke Tech-Aktien zuerst.'],
  ['real10', 'gold', -1, 'Realzins ↔ Gold', 'Gold wirft keine Zinsen ab. Steigt der Zins nach Inflation, wird es relativ unattraktiver.'],
  ['dxy', 'gold', -1, 'Dollar ↔ Gold', 'Gold wird in Dollar gehandelt; ein starker Dollar macht es für den Rest der Welt teurer.'],
  ['dxy', 'em', -1, 'Dollar ↔ Schwellenländer', 'Viele Schwellenländer sind in Dollar verschuldet – ein starker Dollar verteuert ihre Schulden.'],
  ['cu_au', 'y10', 1, 'Kupfer/Gold ↔ 10J-Zins', 'Kupfer steht für Wachstum, Gold für Vorsicht. Ihr Verhältnis gilt als Konjunkturbarometer und läuft oft mit den Zinsen.'],
  ['wti', 'breakeven', 1, 'Öl ↔ Inflationserwartung', 'Teureres Öl schlägt schnell auf Preise durch; der Anleihemarkt preist das in die Inflationserwartung ein.'],
  ['vix', 'spx', -1, 'VIX ↔ S&P 500', 'Der VIX misst die erwartete Schwankung. Fällt der Markt, steigt die Angst – fast immer gegenläufig.'],
  ['hyg_ief', 'spx', 1, 'Kreditappetit ↔ Aktien', 'Wenn Anleger Hochzinsanleihen gegenüber Staatsanleihen meiden, ist das oft ein Frühwarnzeichen für Aktien.'],
  ['btc', 'ndx', 1, 'Bitcoin ↔ Nasdaq', 'Bitcoin handelt meist wie eine besonders riskante Tech-Aktie – Liquidität treibt beide.'],
  ['us_eu10', 'eurusd', -1, 'Zinsabstand USA–Euro ↔ EUR/USD', 'Bringen US-Anleihen mehr Zins als europäische, fließt Geld in den Dollar – der Euro fällt.'],
  ['y10', 'usdjpy', 1, '10J-Zins ↔ Yen', 'Japan hat sehr niedrige Zinsen. Steigen US-Zinsen, lohnt es sich, Yen zu leihen und Dollar zu kaufen.'],
  ['spx', 'tlt', -1, 'Aktien ↔ Staatsanleihen', 'Lange Zeit Absicherung: Fielen Aktien, stiegen Anleihen. Bei hoher Inflation kann das kippen – dann fallen beide.'],
];

// News-Themen und zugehörige Reihen
const TAGS = [
  { id: 'fed', name: 'Notenbank & Zinsen', re: /\b(fed|fomc|powell|rate cuts?|rate hikes?|treasur|yields?|bonds?|anleihe|leitzins|zinsen|zins|ezb|ecb|lagarde|notenbank|central bank)/i, ids: ['y10', 'effr'] },
  { id: 'inflation', name: 'Inflation', re: /inflation|\bcpi\b|\bpce\b|teuerung|verbraucherpreise/i, ids: ['cpi', 'breakeven'] },
  { id: 'jobs', name: 'Arbeitsmarkt', re: /\bjobs?\b|payroll|unemploy|labor market|jobless|arbeitsmarkt|arbeitslos|beschäftig/i, ids: ['unemp', 'payrolls'] },
  { id: 'oel', name: 'Öl & Energie', re: /\boil\b|crude|opec|brent|\bwti\b|\böl|ölpreis|natural gas|erdgas|energy|energie|diesel|gasoline/i, ids: ['wti', 'natgas'] },
  { id: 'fx', name: 'Dollar & Währungen', re: /dollar|currenc|\byen\b|\beuro\b|yuan|devisen|währung/i, ids: ['dxy', 'eurusd'] },
  { id: 'gold', name: 'Gold & Metalle', re: /\bgold|silver|silber|copper|kupfer/i, ids: ['gold', 'copper'] },
  { id: 'krypto', name: 'Krypto', re: /bitcoin|crypto|krypto|ether|\bbtc\b/i, ids: ['btc', 'eth'] },
  { id: 'zoll', name: 'Zölle & Handel', re: /tariff|\bzoll|zölle|trade war|trade deal|handelsstreit|handelskrieg|exports?|imports?/i, ids: ['dxy', 'usdcny'] },
  { id: 'tech', name: 'Tech & KI', re: /\bai\b|\bki\b|nvidia|chip|semiconductor|halbleiter|openai|microsoft|apple|alphabet|meta\b|tesla/i, ids: ['ndx', 'xlk'] },
  { id: 'china', name: 'China', re: /china|chinese|beijing|peking|xi jinping/i, ids: ['usdcny', 'copper'] },
  { id: 'europa', name: 'Europa & DAX', re: /\bdax\b|europ|deutschland|germany|german|bund\b|bundesbank/i, ids: ['dax', 'eu10'] },
];

// ------------------------------------------------------------------ Daten
let DATA = null;          // Rohdaten
const S = {};             // id -> {name,g,u,k,f,src,t:Int32Array(Tage),v:Float64Array}
let LIVEON = false;
let liveAt = 0;

function decode(d) {
  for (const k of Object.keys(S)) delete S[k];
  for (const [id, s] of Object.entries(d.series)) {
    let t;
    if (s.t) t = Int32Array.from(s.t);
    else { t = new Int32Array(s.dt.length); let a = 0; for (let i = 0; i < s.dt.length; i++) { a += s.dt[i]; t[i] = a; } }
    S[id] = { id, name: s.name, g: s.g, u: s.u, k: s.k, f: s.f, src: s.src, t: Array.from(t), v: Array.from(s.v) };
  }
}

async function loadData(first) {
  if (first) {
    const c = await bigLoad('data');
    if (c) { try { DATA = JSON.parse(c); decode(DATA); } catch (e) { DATA = null; } }
  }
  try {
    const txt = await nfetch(DATA_URL + '?t=' + Date.now(), 40);
    const d = JSON.parse(txt);
    if (!DATA || d.updated !== DATA.updated) {
      DATA = d; decode(d); bigSave('data', txt);
      return true;
    }
  } catch (e) {
    if (!DATA) { document.getElementById('main').innerHTML = `<div class="empty">Daten konnten nicht geladen werden (${e.message}).<br>Internetverbindung prüfen – es wird automatisch erneut versucht.</div>`; }
  }
  return false;
}

// ------------------------------------------------------------------ Hilfen: Zeit & Format
const todayDay = () => Math.floor(Date.now() / 864e5);
const dDate = d => new Date(d * 864e5);
const fmtDate = (d, short) => { const x = dDate(d); return x.toLocaleDateString('de-DE', short ? { day: '2-digit', month: '2-digit', year: '2-digit', timeZone: 'UTC' } : { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' }); };
const nf = (v, dec) => v == null || !isFinite(v) ? '–' : v.toLocaleString('de-DE', { minimumFractionDigits: dec, maximumFractionDigits: dec });

function decFor(v, s) {
  if (s && s.k === 'rate') return s.u === 'Tsd.' ? 0 : 2;
  const a = Math.abs(v);
  return a >= 10000 ? 0 : a >= 1000 ? 1 : a >= 10 ? 2 : a >= 1 ? 3 : 4;
}
function axisDec(p, s) { const a = Math.abs(p); if (s && s.k === 'rate') return s.u === 'Tsd.' ? 0 : 2; return a >= 1000 ? 0 : a >= 100 ? 1 : a >= 10 ? 2 : a >= 1 ? 3 : 4; }
function fmtV(id, v) {
  const s = S[id]; if (v == null || !s) return '–';
  const unit = s.k === 'rate' ? (s.u === '%' ? ' %' : s.u === 'Pp.' ? ' Pp.' : s.u === 'Tsd.' ? ' Tsd.' : '') : '';
  return nf(v, decFor(v, s)) + unit;
}
// Veränderung: Preise in %, Zinsen in Basispunkten, Rest in Prozentpunkten
function chg(id, a, b) {
  const s = S[id]; if (a == null || b == null || !s) return null;
  if (s.k === 'rate') return { v: b - a, unit: (s.g === 'zinsen' && s.u !== 'Tsd.') ? 'bp' : s.u === 'Tsd.' ? 'tsd' : 'pp' };
  if (a <= 0) return null;
  return { v: (b / a - 1) * 100, unit: '%' };
}
function fmtC(c, withSign = true) {
  if (!c || c.v == null || !isFinite(c.v)) return '<span class="flat">–</span>';
  let txt;
  if (c.unit === 'bp') txt = nf(c.v * 100, 0) + ' Bp.';
  else if (c.unit === 'pp') txt = nf(c.v, 2) + ' Pp.';
  else if (c.unit === 'tsd') txt = nf(c.v, 0);
  else txt = nf(c.v, Math.abs(c.v) >= 100 ? 0 : Math.abs(c.v) >= 10 ? 1 : 2) + ' %';
  const sign = c.v > 0 && withSign ? '+' : '';
  const cls = Math.abs(c.v) < 1e-9 ? 'flat' : c.v > 0 ? 'up' : 'down';
  return `<span class="${cls}">${sign}${txt}</span>`;
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ------------------------------------------------------------------ Hilfen: Reihen
function lastIdx(s) { return s ? s.t.length - 1 : -1; }
function last(id) { const s = S[id]; return s && s.v.length ? s.v[s.v.length - 1] : null; }
function lastDay(id) { const s = S[id]; return s && s.t.length ? s.t[s.t.length - 1] : null; }
function idxAt(s, day) { // letzter Index mit t <= day
  let lo = 0, hi = s.t.length - 1, r = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (s.t[m] <= day) { r = m; lo = m + 1; } else hi = m - 1; }
  return r;
}
function valAt(id, day) { const s = S[id]; if (!s) return null; const i = idxAt(s, day); return i < 0 ? null : s.v[i]; }
function chgOver(id, days) { const s = S[id]; if (!s) return null; const ld = lastDay(id); return chg(id, valAt(id, ld - days), last(id)); }
function chg1d(id) { const s = S[id]; if (!s || s.v.length < 2) return null; return chg(id, s.v[s.v.length - 2], s.v[s.v.length - 1]); }
function ytd(id) { const ld = lastDay(id); if (ld == null) return null; const y = dDate(ld).getUTCFullYear(); const d0 = Math.floor(Date.UTC(y, 0, 1) / 864e5) - 1; return chg(id, valAt(id, d0), last(id)); }
function minRangeFor(s) { return s.f === 'm' ? 1096 : s.f === 'w' ? 365 : 0; }
function slice(id, days) {
  const s = S[id]; if (!s) return { t: [], v: [] };
  const span = Math.max(days, minRangeFor(s));
  const from = (lastDay(id) || 0) - span;
  let i = idxAt(s, from); if (i < 0) i = 0;
  return { t: s.t.slice(i), v: s.v.slice(i) };
}
function sma(arr, n) { const out = new Array(arr.length).fill(null); let sum = 0; for (let i = 0; i < arr.length; i++) { sum += arr[i]; if (i >= n) sum -= arr[i - n]; if (i >= n - 1) out[i] = sum / n; } return out; }

// Resampling & Veränderungen für Korrelationen
function keyOf(day, f) { if (f === 'd') return day; if (f === 'w') return Math.floor((day + 3) / 7); const x = dDate(day); return x.getUTCFullYear() * 12 + x.getUTCMonth(); }
function dayOfKey(k, f) { if (f === 'd') return k; if (f === 'w') return k * 7 + 1; return Math.floor(Date.UTC(Math.floor(k / 12), k % 12, 1) / 864e5); }
const _chgCache = new Map();
function changes(id, f) {
  const ck = id + '|' + f + '|' + (S[id] ? S[id].v.length + ':' + last(id) : '');
  if (_chgCache.has(ck)) return _chgCache.get(ck);
  const s = S[id]; const m = new Map(); if (!s) return m;
  const ks = [], vs = [];
  for (let i = 0; i < s.t.length; i++) { const k = keyOf(s.t[i], f); if (ks.length && ks[ks.length - 1] === k) vs[vs.length - 1] = s.v[i]; else { ks.push(k); vs.push(s.v[i]); } }
  for (let i = 1; i < ks.length; i++) {
    let c;
    if (s.k === 'rate') c = vs[i] - vs[i - 1];
    else c = (vs[i] > 0 && vs[i - 1] > 0) ? Math.log(vs[i] / vs[i - 1]) : NaN;
    if (isFinite(c)) m.set(ks[i], c);
  }
  _chgCache.set(ck, m);
  return m;
}
function freqOf(a, b) { const r = { d: 0, w: 1, m: 2 }; const fa = S[a] ? S[a].f : 'd', fb = S[b] ? S[b].f : 'd'; return r[fa] >= r[fb] ? fa : fb; }
function pearson(xs, ys) {
  const n = xs.length; if (n < 8) return null;
  let sx = 0, sy = 0; for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; }
  const mx = sx / n, my = sy / n; let a = 0, b = 0, c = 0;
  for (let i = 0; i < n; i++) { const dx = xs[i] - mx, dy = ys[i] - my; a += dx * dy; b += dx * dx; c += dy * dy; }
  return b > 0 && c > 0 ? a / Math.sqrt(b * c) : null;
}
function pairs(a, b, f, fromDay, lag = 0) {
  const A = changes(a, f), B = changes(b, f), xs = [], ys = [];
  const k0 = keyOf(fromDay, f);
  for (const [k, x] of A) { if (k < k0) continue; const y = B.get(k + lag); if (y !== undefined) { xs.push(x); ys.push(y); } }
  return [xs, ys];
}
function corr(a, b, f, fromDay, lag = 0) { const [x, y] = pairs(a, b, f, fromDay, lag); return pearson(x, y); }
function newestDay() { let m = 0; for (const s of Object.values(S)) if (s.f === 'd' && s.t.length) m = Math.max(m, s.t[s.t.length - 1]); return m; }

// ------------------------------------------------------------------ Diagramme
const charts = [];
function disposeCharts() { while (charts.length) { try { charts.pop().remove(); } catch (e) { /* */ } } }
function baseChart(el, opt = {}) {
  const ch = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { attributionLogo: false, background: { type: 'solid', color: 'transparent' }, textColor: C.mut, fontSize: 11, fontFamily: '-apple-system, system-ui, sans-serif' },
    grid: { vertLines: { visible: false }, horzLines: { color: C.grid } },
    rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 }, mode: opt.log ? 1 : 0 },
    timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true, lockVisibleTimeRangeOnResize: true, rightOffset: 0 },
    crosshair: { mode: 0, vertLine: { color: '#3a4150', labelBackgroundColor: '#2f3542', width: 1, style: 3 }, horzLine: { color: '#3a4150', labelBackgroundColor: '#2f3542', style: 3 } },
    handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: false, axisDoubleClickReset: true },
    localization: { locale: 'de-DE', dateFormat: 'dd.MM.yy', priceFormatter: opt.fmt || (p => nf(p, Math.abs(p) >= 1000 ? 0 : Math.abs(p) >= 10 ? 1 : 2)) },
  });
  charts.push(ch);
  addZoom(el, ch);
  return ch;
}
// Zoom: ⌘/⌥ + Scrollen oder Zwei-Finger-Zoom auf dem Trackpad, Knöpfe +/−/⟲; Ziehen verschiebt
function zoomChart(ch, f, x) {
  const ts = ch.timeScale(), r = ts.getVisibleLogicalRange(); if (!r) return;
  const c = x != null ? (ts.coordinateToLogical(x) ?? (r.from + r.to) / 2) : (r.from + r.to) / 2;
  let from = c - (c - r.from) * f, to = c + (r.to - c) * f;
  if (to - from < 10) return;
  ts.setVisibleLogicalRange({ from, to });
}
function addZoom(el, ch) {
  el.style.position = 'relative';
  el.addEventListener('wheel', e => {
    if (!(e.metaKey || e.altKey || e.ctrlKey)) return;          // normales Scrollen bleibt Seiten-Scrollen
    e.preventDefault();
    const rect = el.getBoundingClientRect();
    zoomChart(ch, Math.exp(Math.max(-0.5, Math.min(0.5, e.deltaY * 0.01))), e.clientX - rect.left);
  }, { passive: false });
  let g0 = 1;
  el.addEventListener('gesturestart', e => { e.preventDefault(); g0 = 1; });
  el.addEventListener('gesturechange', e => { e.preventDefault(); const rect = el.getBoundingClientRect();
    zoomChart(ch, g0 / e.scale, e.clientX - rect.left); g0 = e.scale; });
  const bar = document.createElement('div'); bar.className = 'zbar';
  bar.innerHTML = '<button title="Hineinzoomen">+</button><button title="Herauszoomen">−</button><button title="Alles anzeigen">⟲</button>';
  const [bi, bo, br] = bar.querySelectorAll('button');
  bi.onclick = e => { e.stopPropagation(); zoomChart(ch, 0.6); };
  bo.onclick = e => { e.stopPropagation(); zoomChart(ch, 1 / 0.6); };
  br.onclick = e => { e.stopPropagation(); if (ch._reset) ch._reset(); else ch.timeScale().fitContent(); };
  el.appendChild(bar);
}
// Zwei übereinanderliegende Diagramme koppeln: gleiche Achsenbreite, gleiche Zeitachse, gemeinsames Fadenkreuz
function linkCharts(a, sa, da, b, sb, db) {
  [a, b].forEach(x => x.applyOptions({ rightPriceScale: { minimumWidth: 72 } }));
  const ma = new Map(da.map(p => [p.time, p.value])), mb = new Map(db.map(p => [p.time, p.value]));
  const t0 = Math.min(da[0].time, db[0].time), t1 = Math.max(da[da.length - 1].time, db[db.length - 1].time);
  const fit = () => [a, b].forEach(x => { try { x.timeScale().setVisibleRange({ from: t0, to: t1 }); } catch (e) { /* */ } });
  fit(); requestAnimationFrame(fit); a._reset = b._reset = fit;
  let lock = false;
  const sync = (x, y) => x.timeScale().subscribeVisibleTimeRangeChange(r => { if (lock || !r) return; lock = true; try { y.timeScale().setVisibleRange(r); } catch (e) { /* */ } lock = false; });
  sync(a, b); sync(b, a);
  const near = (m, t) => { if (m.has(t)) return m.get(t); let best = null, bd = Infinity; for (const [k, v] of m) { const d = Math.abs(k - t); if (d < bd) { bd = d; best = v; } } return bd <= 8 * DAY ? best : null; };
  let clock = false;
  const cross = (y, sy, my) => p => { if (clock) return; clock = true;
    try { if (p && p.time != null) { const v = near(my, p.time); if (v != null) y.setCrosshairPosition(v, p.time, sy); else y.clearCrosshairPosition(); } else y.clearCrosshairPosition(); } catch (e) { /* */ }
    clock = false; };
  a.subscribeCrosshairMove(cross(b, sb, mb)); b.subscribeCrosshairMove(cross(a, sa, ma));
}
function pf(dec) { return { type: 'price', precision: dec, minMove: Math.pow(10, -dec) }; }

/* Karte mit Liniendiagramm.
   spec: {ids, title, sub, type:'line'|'baseline'|'hist', base, log, norm, height, note, colors} */
function chartCard(spec) {
  const card = document.createElement('div');
  card.className = 'card' + (spec.cls ? ' ' + spec.cls : '');
  const ids = spec.ids.filter(id => S[id]);
  if (!ids.length) { card.innerHTML = `<div class="ttl">${esc(spec.title)}</div><div class="note">Keine Daten.</div>`; return card; }
  const s0 = S[ids[0]];
  const span = Math.max(RANGE, spec.minDays || 0, ...ids.map(id => minRangeFor(S[id])));
  const ext = s0.f === 'm' ? '<small>(Monatswerte)</small>' : s0.f === 'w' ? '<small>(Wochenwerte)</small>' : '';
  card.innerHTML = `<div class="hd"><div><div class="ttl">${esc(spec.title)}${ext}</div>${spec.sub ? `<div class="sub">${spec.sub}</div>` : ''}</div>
    <button class="open" title="Im Vergleich öffnen">Vergleich ↗</button></div>
    <div class="legend"></div><div class="chart ${spec.height || ''}"></div>${spec.note ? `<div class="note">${spec.note}</div>` : ''}`;
  card.querySelector('.open').onclick = () => openCompare(ids[0], ids[1] || null);
  const legend = card.querySelector('.legend');
  queueMicrotask(() => {
    const el = card.querySelector('.chart');
    const ch = baseChart(el, { log: spec.log, fmt: spec.norm ? (p => nf(p, 0)) : (p => nf(p, axisDec(p, s0))) });
    const lines = [];
    ids.forEach((id, j) => {
      const sl = slice(id, span); if (!sl.t.length) return;
      const col = (spec.colors && spec.colors[j]) || SER[j];
      let base = 1; if (spec.norm) base = sl.v[0] / 100;
      const data = sl.t.map((d, i) => ({ time: d * DAY, value: spec.norm ? sl.v[i] / base : sl.v[i] }));
      let ser;
      if (spec.type === 'baseline') {
        ser = ch.addBaselineSeries({ baseValue: { type: 'price', price: spec.base || 0 }, lineWidth: 2, priceFormat: pf(2),
          topLineColor: C.s1, topFillColor1: 'rgba(57,135,229,.22)', topFillColor2: 'rgba(57,135,229,.02)',
          bottomLineColor: C.s8, bottomFillColor1: 'rgba(230,103,103,.02)', bottomFillColor2: 'rgba(230,103,103,.25)', priceLineVisible: false });
      } else if (spec.type === 'hist') {
        ser = ch.addHistogramSeries({ priceFormat: pf(0), priceLineVisible: false });
        data.forEach(p => { p.color = p.value >= 0 ? C.s1 : C.s8; });
      } else {
        ser = ch.addLineSeries({ color: col, lineWidth: 2, priceLineVisible: false, lastValueVisible: true, crosshairMarkerRadius: 4,
          priceFormat: pf(spec.norm ? 1 : decFor(sl.v[sl.v.length - 1], S[id])) });
      }
      ser.setData(data);
      if (spec.ref != null) ser.createPriceLine({ price: spec.ref, color: C.mut, lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: spec.refLabel || '' });
      lines.push({ id, ser, col, first: sl.v[0], firstd: sl.t[0], lastv: sl.v[sl.v.length - 1], lastd: sl.t[sl.t.length - 1] });
    });
    if (spec.sma) { // gleitender Durchschnitt zur ersten Reihe
      const s = S[ids[0]]; const m = sma(s.v, spec.sma); const from = (lastDay(ids[0]) || 0) - span; const d = [];
      for (let i = 0; i < s.t.length; i++) if (s.t[i] >= from && m[i] != null) d.push({ time: s.t[i] * DAY, value: m[i] });
      const ser = ch.addLineSeries({ color: C.mut, lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      ser.setData(d);
    }
    ch.timeScale().fitContent();
    const draw = (vals, day) => {
      legend.innerHTML = lines.map(l => {
        const v = vals ? vals.get(l.ser) : null;
        const val = v ? (v.value != null ? v.value : v.close) : l.lastv;
        const shown = spec.norm ? nf(val, 1) : fmtV(l.id, val);
        const c = spec.norm ? null : chg(l.id, l.first, val);
        return `<span><i style="border-color:${spec.type === 'baseline' || spec.type === 'hist' ? C.s1 : l.col}"></i>${esc(S[l.id].name)}<b>${shown}</b> ${c ? fmtC(c) : ''}</span>`;
      }).join('') + (spec.sma ? `<span><i style="border-color:${C.mut};border-top-style:dashed"></i>${spec.sma}-Tage-Linie</span>` : '') +
        `<span class="d">${day != null ? fmtDate(day) : 'seit ' + fmtDate(Math.min(...lines.map(l => l.firstd)))}</span>`;
    };
    draw(null, null);
    ch.subscribeCrosshairMove(p => { if (!p || p.time == null) draw(null, null); else draw(p.seriesData, p.time / DAY); });
  });
  return card;
}

// Mini-Linie in ein Canvas
function spark(cv, vals, color) {
  const dpr = window.devicePixelRatio || 1; const w = cv.clientWidth || 90, h = cv.clientHeight || 22;
  cv.width = w * dpr; cv.height = h * dpr; const g = cv.getContext('2d'); g.scale(dpr, dpr);
  const v = vals.filter(x => x != null && isFinite(x)); if (v.length < 2) return;
  let mn = Math.min(...v), mx = Math.max(...v); if (mx === mn) { mx += 1; mn -= 1; }
  g.strokeStyle = color || (v[v.length - 1] >= v[0] ? C.up : C.down); g.lineWidth = 1.5; g.lineJoin = 'round'; g.beginPath();
  v.forEach((x, i) => { const px = i / (v.length - 1) * (w - 2) + 1, py = h - 2 - (x - mn) / (mx - mn) * (h - 4); i ? g.lineTo(px, py) : g.moveTo(px, py); });
  g.stroke();
}
function sparkVals(id, days) { const sl = slice(id, days); const step = Math.max(1, Math.floor(sl.v.length / 120)); return sl.v.filter((_, i) => i % step === 0 || i === sl.v.length - 1); }

// ------------------------------------------------------------------ Tooltip
const tip = document.getElementById('tip');
function showTip(e, html) { tip.innerHTML = html; tip.hidden = false; const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8); const y = Math.min(e.clientY + 14, innerHeight - tip.offsetHeight - 8); tip.style.left = x + 'px'; tip.style.top = y + 'px'; }
function hideTip() { tip.hidden = true; }

// ------------------------------------------------------------------ Kopf, Leiste, Navigation
function renderRanges() {
  const el = document.getElementById('ranges');
  el.innerHTML = RANGES.map(([n, d]) => `<button data-d="${d}" class="${d === RANGE ? 'on' : ''}">${n}</button>`).join('');
  el.onclick = e => { const b = e.target.closest('button'); if (!b) return; RANGE = +b.dataset.d; store('range', RANGE); renderRanges(); renderSection(); };
}
function renderNav() {
  const el = document.getElementById('nav');
  el.innerHTML = SECTIONS.map(([id, n], i) => `<button data-s="${id}" class="${id === SECTION ? 'on' : ''}"><span>${n}</span><kbd>⌘${i + 1}</kbd></button>`).join('') +
    `<div class="navfoot" id="navfoot"></div>`;
  el.onclick = e => { const b = e.target.closest('button'); if (b) go(b.dataset.s); };
  renderFoot();
}
document.addEventListener('click', e => { if (e.target && e.target.id === 'tvlink') { e.preventDefault(); openURL('https://www.tradingview.com/lightweight-charts/'); } });
function renderFoot() {
  const f = document.getElementById('navfoot'); if (!f || !DATA) return;
  const bad = (DATA.diag || []).filter(d => !d.ok && !/vorheriger Lauf/.test(d.src));
  f.innerHTML = `Quellen: Yahoo Finance, Fed H.15, US Treasury, NY Fed, EZB, BLS, Freddie Mac, EIA, Shiller.<br>Diagramme: <a href="#" id="tvlink" style="color:inherit">TradingView Lightweight Charts</a>` +
    (bad.length ? `<br><span style="color:var(--warn)">${bad.length} Quelle(n) mit Fehler beim letzten Lauf:</span> ${bad.map(d => esc(d.src)).join(', ')}` : '');
}
function go(id) { SECTION = id; store('section', id); renderNav(); renderSection(); document.getElementById('main').scrollTop = 0; }

function renderStrip() {
  const el = document.getElementById('strip');
  el.innerHTML = STRIP.filter(id => S[id]).map(id => {
    const c = chg1d(id);
    return `<div class="tk" data-id="${id}"><div class="n">${esc(short(id))}</div><div class="v">${fmtV(id, last(id))}</div><div class="c">${fmtC(c)}</div><canvas></canvas>${S[id].live ? '<span class="lv" title="live"></span>' : ''}</div>`;
  }).join('');
  el.querySelectorAll('.tk').forEach(tk => { spark(tk.querySelector('canvas'), sparkVals(tk.dataset.id, 31)); tk.onclick = () => openCompare(tk.dataset.id); });
}
const SHORT = { msci: 'MSCI World', spx: 'S&P 500', ndx: 'Nasdaq 100', rut: 'Russell 2000', dax: 'DAX', nikkei: 'Nikkei', vix: 'VIX', y10: 'US 10J', y2: 'US 2J', curve10_2: 'Kurve 10J−2J', dxy: 'Dollar-Index', eurusd: 'EUR/USD', gold: 'Gold', wti: 'Öl WTI', btc: 'Bitcoin' };
const short = id => SHORT[id] || S[id].name;

function renderStatus() {
  const el = document.getElementById('status'); if (!DATA) return;
  const up = new Date(DATA.updated); const mins = Math.round((Date.now() - up) / 6e4);
  const age = mins < 60 ? `vor ${mins} Min.` : mins < 1440 ? `vor ${Math.round(mins / 60)} Std.` : up.toLocaleDateString('de-DE');
  el.innerHTML = `<span>${marketState()}</span><span>Daten ${age}</span><span class="live ${LIVEON ? 'on' : ''}" title="Live-Kurse alle 60 s"><i></i>${LIVEON ? 'Live' : 'Live aus'}</span>`;
}
function marketState() {
  const ny = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const d = ny.getDay(), m = ny.getHours() * 60 + ny.getMinutes();
  const open = d >= 1 && d <= 5 && m >= 570 && m < 960;
  return open ? '<span style="color:var(--good)">● US-Börse offen</span>' : '<span>○ US-Börse geschlossen</span>';
}

// ------------------------------------------------------------------ Abschnitte
function renderSection() {
  disposeCharts(); hideTip();
  const m = document.getElementById('main'); m.innerHTML = '';
  if (!DATA) return;
  ({ einschaetzung: secEinschaetzung, signale: secSignale, lage: secLage, maerkte: secMaerkte, bewertung: secBewertung, zinsen: secZinsen, risiko: secRisiko,
    rohstoffe: secRohstoffe, fx: secFx, konjunktur: secKonjunktur, zusammen: secZusammen, news: secNews }[SECTION] || secEinschaetzung)(m);
}
function head(m, title, lead) { m.insertAdjacentHTML('beforeend', `<h1>${title}</h1>${lead ? `<p class="lead">${lead}</p>` : ''}`); }
function grid(m, cls = '') { const g = document.createElement('div'); g.className = 'grid ' + cls; m.appendChild(g); return g; }
function sect(m, t) { m.insertAdjacentHTML('beforeend', `<h2 class="sect">${t}</h2>`); }

// ---------- Lage
function status(cls, label) { const ic = { good: '✓', warn: '!', serious: '!', crit: '!!', neutral: '–' }[cls]; return `<span class="badge ${cls}">${label}</span>`; }
function tileDefs() {
  const T = [];
  const MT = DATA.model && DATA.model.targets;
  if (MT && MT.world) { const n = MT.world.now; T.push({ id: '__model', l: 'Einschätzung MSCI World', v: `${n.score} / 100`, s: n.action,
    b: status(n.cls === 'crit' ? 'crit' : n.cls, n.label), spark: MT.world.hist.score.slice(-60) }); }
  const spx = S.spx;
  if (spx) {
    const m200 = sma(spx.v, 200); const r = (last('spx') / m200[m200.length - 1] - 1) * 100;
    T.push({ id: 'spx', l: 'Trend S&P 500', v: (r > 0 ? '+' : '') + nf(r, 1) + ' %', s: 'Abstand zur 200-Tage-Linie',
      b: r > 0 ? status('good', 'Aufwärtstrend') : r > -10 ? status('warn', 'unter 200-Tage') : status('crit', 'Abwärtstrend') });
  }
  const mk = DATA.markt || {};
  if (mk.cape) {
    const z = mk.z20;
    T.push({ id: 'cape', l: 'Bewertung (CAPE)', v: nf(mk.cape, 1), s: `20-J.-Ø ${nf(mk.mean20, 1)} · ${nf(z, 1)} σ`,
      b: z > 2 ? status('crit', 'sehr teuer') : z > 1 ? status('serious', 'überbewertet') : z > -1 ? status('neutral', 'fair') : status('good', 'günstig') });
  }
  if (S.vix) { const v = last('vix'); T.push({ id: 'vix', l: 'Angst (VIX)', v: nf(v, 1), s: 'erwartete Schwankung S&P 500',
    b: v < 15 ? status('good', 'ruhig') : v < 20 ? status('neutral', 'normal') : v < 30 ? status('warn', 'nervös') : status('crit', 'Panik') }); }
  if (S.curve10_3m) {
    const v = last('curve10_3m'); const ld = lastDay('curve10_3m'); const sl = slice('curve10_3m', 730); const wasInv = sl.v.some(x => x < 0);
    T.push({ id: 'curve10_3m', l: 'Zinskurve 10J − 3M', v: (v > 0 ? '+' : '') + nf(v, 2) + ' Pp.', s: wasInv && v > 0 ? 'war in den letzten 2 J. invertiert' : '10-jährige minus 3-monatige Zinsen',
      b: v < 0 ? status('warn', 'invertiert') : wasInv ? status('serious', 'wieder steil') : v < 0.5 ? status('neutral', 'flach') : status('good', 'normal') });
  }
  if (S.hyg_ief) { const s = S.hyg_ief; const m = sma(s.v, 200); const r = (last('hyg_ief') / m[m.length - 1] - 1) * 100;
    T.push({ id: 'hyg_ief', l: 'Kredit (HYG/IEF)', v: (r > 0 ? '+' : '') + nf(r, 1) + ' %', s: 'Hochzins ggü. Staatsanleihen vs. 200-T.-Linie',
      b: r > 0 ? status('good', 'Risikoappetit') : r > -2 ? status('warn', 'Vorsicht') : status('crit', 'Flucht aus Risiko') }); }
  if (S.dxy) { const c = chgOver('dxy', 92).v; T.push({ id: 'dxy', l: 'Dollar (3 M.)', v: (c > 0 ? '+' : '') + nf(c, 1) + ' %', s: `Dollar-Index ${nf(last('dxy'), 1)}`,
    b: c > 3 ? status('warn', 'stark') : c < -3 ? status('neutral', 'schwach') : status('neutral', 'stabil') }); }
  if (S.breadth) { const c = chgOver('breadth', 92).v; T.push({ id: 'breadth', l: 'Marktbreite (3 M.)', v: (c > 0 ? '+' : '') + nf(c, 1) + ' %', s: 'gleichgewichtet vs. normaler S&P 500',
    b: c < -3 ? status('warn', 'wenige Gewinner') : c > 2 ? status('good', 'breit') : status('neutral', 'ausgeglichen') }); }
  if (S.cpi) { const v = last('cpi'); T.push({ id: 'cpi', l: 'US-Inflation', v: nf(v, 1) + ' %', s: `Kern ${nf(last('core'), 1)} % · ${dDate(lastDay('cpi')).toLocaleDateString('de-DE', { month: 'short', year: '2-digit', timeZone: 'UTC' })}`,
    b: v < 2.5 ? status('good', 'nahe Ziel') : v < 3.5 ? status('neutral', 'erhöht') : v < 5 ? status('warn', 'hoch') : status('crit', 'sehr hoch') }); }
  if (S.sahm) { const v = last('sahm'); T.push({ id: 'sahm', l: 'Arbeitsmarkt (Sahm)', v: nf(v, 2), s: `Arbeitslosenquote ${nf(last('unemp'), 1)} %`,
    b: v < 0.3 ? status('good', 'stabil') : v < 0.5 ? status('warn', 'kühlt ab') : status('crit', 'Rezessionssignal') }); }
  if (S.real10) { const v = last('real10'); T.push({ id: 'real10', l: 'Realzins 10J', v: nf(v, 2) + ' %', s: `Inflationserwartung ${nf(last('breakeven'), 2)} %`,
    b: v > 2 ? status('warn', 'restriktiv') : v > 0.5 ? status('neutral', 'neutral') : status('good', 'locker') }); }
  if (S.wti) { const c = chgOver('wti', 365).v; T.push({ id: 'wti', l: 'Öl WTI (1 J.)', v: (c > 0 ? '+' : '') + nf(c, 0) + ' %', s: `${nf(last('wti'), 2)} $ je Barrel`,
    b: c > 40 ? status('warn', 'Preisschock') : c < -30 ? status('neutral', 'Einbruch') : status('neutral', 'normal') }); }
  if (S.fedbs) { const c = chgOver('fedbs', 365).v; T.push({ id: 'fedbs', l: 'Liquidität (Fed-Bilanz)', v: (c > 0 ? '+' : '') + nf(c, 1) + ' %', s: `${nf(last('fedbs'), 2)} Bio. $ · ggü. Vorjahr`,
    b: c < -3 ? status('warn', 'wird entzogen') : c > 3 ? status('good', 'wird zugeführt') : status('neutral', 'stabil') }); }
  return T;
}
function secLage(m) {
  head(m, 'Lage', 'Die wichtigsten Signale auf einen Blick. Ein Klick öffnet die Reihe im Vergleich.');
  const g = grid(m, 'tiles');
  for (const t of tileDefs()) {
    const d = document.createElement('div'); d.className = 'tile';
    d.innerHTML = `<div class="th"><div class="tl">${t.l}</div>${t.b}</div><div class="tv">${t.v}</div><div class="ts">${t.s}</div><canvas></canvas>`;
    d.onclick = () => t.id === '__model' ? go('einschaetzung') : openCompare(t.id); g.appendChild(d);
    requestAnimationFrame(() => spark(d.querySelector('canvas'), t.spark || sparkVals(t.id, 365), C.s1));
  }

  const g2 = grid(m, 'wide'); g2.style.marginTop = '12px';
  g2.appendChild(moversCard());
  g2.appendChild(unusualCard(5));
  g2.appendChild(stressCard());
  g2.appendChild(capeCard());
  g2.appendChild(chartCard({ ids: ['spx'], title: 'S&P 500', log: RANGE > 1100, sma: 200 }));
  g2.appendChild(chartCard({ ids: ['y10', 'y2'], title: 'US-Zinsen 10 und 2 Jahre' }));
}

function moversCard() {
  const c = document.createElement('div'); c.className = 'card';
  const nd = newestDay(); const rows = [];
  for (const s of Object.values(S)) {
    if (s.f !== 'd' || s.g === 'intern' || s.id === 'cape' || s.v.length < 260 || nd - s.t[s.t.length - 1] > 4) continue;
    const ch = changes(s.id, 'd'); const vals = [...ch.values()].slice(-252);
    const lastK = s.t[s.t.length - 1]; const x = ch.get(lastK); if (x === undefined) continue;
    const sd = Math.sqrt(vals.reduce((a, b) => a + b * b, 0) / vals.length); if (!sd) continue;
    rows.push({ id: s.id, z: x / sd, c: chg1d(s.id) });
  }
  rows.sort((a, b) => Math.abs(b.z) - Math.abs(a.z));
  c.innerHTML = `<div class="hd"><div><div class="ttl">Ungewöhnlich starke Bewegungen</div><div class="sub">Letzte Tagesveränderung im Verhältnis zur üblichen Schwankung (1 J.)</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th>Reihe</th><th>Letzter</th><th>Veränd.</th><th>× üblich</th></tr>
    ${rows.slice(0, 8).map(r => `<tr class="row" data-id="${r.id}"><td>${esc(S[r.id].name)}</td><td>${fmtV(r.id, last(r.id))}</td><td>${fmtC(r.c)}</td><td>${nf(Math.abs(r.z), 1)}×</td></tr>`).join('')}</table>
    <div class="note">Ab etwa 2× ist eine Bewegung auffällig, ab 3× selten.</div>`;
  c.querySelectorAll('tr.row').forEach(r => r.onclick = () => openCompare(r.dataset.id));
  return c;
}

function stressCard() {
  const c = document.createElement('div'); c.className = 'card';
  const st = DATA.stress; if (!st) { c.innerHTML = '<div class="ttl">Stress-Zähler</div><div class="note">Keine Daten.</div>'; return c; }
  const F = [
    ['oel', 'Ölschock', `WTI ggü. Vorjahr ${st.inputs.wti_yoy != null ? nf(st.inputs.wti_yoy, 0) + ' %' : '–'} (Signal ab +50 % & 3-J.-Hoch)`],
    ['fed', 'Fed erhöht', `Fed Funds in 3 M. ${st.inputs.ff_3m != null ? (st.inputs.ff_3m > 0 ? '+' : '') + nf(st.inputs.ff_3m, 2) : '–'} Pp.`],
    ['zins10', '10J-Zins auf 10-J.-Hoch', `${nf(st.inputs.gs10, 2)} % vs. bisheriges Hoch ${nf(st.inputs.gs10_max10y, 2)} %`],
    ['bewertung', 'Bewertung hoch', `TR-CAPE ${nf(st.inputs.trz, 1)} σ über 20-J.-Ø`],
    ['hypo', 'Hypothekenzins +1 Pp.', `in 24 M. ${st.inputs.mort_24m != null ? (st.inputs.mort_24m > 0 ? '+' : '') + nf(st.inputs.mort_24m, 2) : '–'} Pp.`],
    ['haus_real', 'Hauspreise real fallend', 'Case-Shiller abzüglich Inflation'],
    ['midterm', 'Midterm-Jahr', 'Jan.–Okt. vor US-Zwischenwahlen'],
  ];
  c.innerHTML = `<div class="hd"><div><div class="ttl">Stress-Zähler <small>aus deiner Makro-Forschung</small></div>
    <div class="sub">Wie viele der 7 Warnsignale gerade aktiv sind (monatlich, seit 1976).</div></div><div class="big">${st.now.n}<span class="mut" style="font-size:16px"> / 7</span></div></div>
    <div class="flags">${F.map(([k, n, d]) => `<div class="flag ${st.now[k] ? 'on' : 'off'}"><span class="fi">${st.now[k] ? '!' : '✓'}</span><div>${n}<div class="fd">${d}</div></div></div>`).join('')}</div>
    <div class="legend"></div><div class="chart short"></div><div class="chart short" style="height:90px"></div>
    <div class="note">Ergebnis der Forschung: Mehr aktive Signale haben die Renditen der Folgejahre historisch kaum verschlechtert (Rangkorrelation ≈ 0). Monate mit ≥ 5 Signalen: 1980–82 und 2022–23 – danach lag der S&P 500 nach 1 Jahr im Median bei +12,5 %, der größte Rückgang in 3 J. im Median bei −23 %.</div>`;
  queueMicrotask(() => {
    const els = c.querySelectorAll('.chart');
    const ms = st.months.map(p => Math.floor(Date.UTC(+p.slice(0, 4), +p.slice(5, 7) - 1, 1) / 864e5));
    const from = 0; // ganze Historie seit 1976
    const a = baseChart(els[0], { log: true }); const sx = a.addLineSeries({ color: C.s1, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, priceFormat: pf(0) });
    const dS = ms.map((d, i) => ({ time: d * DAY, value: st.spx[i] })).filter(p => p.value != null && p.time / DAY >= from);
    sx.setData(dS);
    const b = baseChart(els[1]); const h = b.addHistogramSeries({ priceFormat: pf(0), priceLineVisible: false, lastValueVisible: false });
    const dN = ms.map((d, i) => ({ time: d * DAY, value: st.n[i], color: st.n[i] >= 5 ? C.serious : st.n[i] >= 3 ? C.warn : C.mut })).filter(p => p.value != null && p.time / DAY >= from);
    h.setData(dN);
    const lg = c.querySelector('.legend');
    const draw = t => {
      const i = t == null ? ms.length - 1 : ms.indexOf(t);
      lg.innerHTML = `<span><i style="border-color:${C.s1}"></i>S&P 500 (log)<b>${nf(st.spx[i], 0)}</b></span><span><i style="border-color:${C.warn}"></i>Aktive Signale<b>${st.n[i]}</b></span><span class="d">${st.months[i]}</span>`;
    };
    draw(null);
    linkCharts(a, sx, dS, b, h, dN);
    const ch = p => draw(p && p.time ? p.time / DAY : null);
    a.subscribeCrosshairMove(ch); b.subscribeCrosshairMove(ch);
  });
  return c;
}

function capeCard() {
  const mk = DATA.markt || {};
  const c = chartCard({ ids: ['cape'], title: 'Shiller-KGV (CAPE)', sub: mk.cape ? `${nf(mk.cape, 1)} – ${mk.pct20 != null ? 'höher als an ' + nf(mk.pct20, 0) + ' % der Tage der letzten 20 J.' : ''} · Einstiegssignal ${mk.score != null ? mk.score + '/100' : '–'} · S&P ${mk.vs200w != null ? nf(mk.vs200w, 0) + ' % über 200-Wochen-Linie' : ''}` : '',
    ref: mk.mean20, refLabel: '20-J.-Ø', note: 'Details mit Einstiegsregel in der Markt-App. Dein Einstieg: S&P an/unter 200-Wochen-Linie, dann Kauf, sobald das CAPE wieder steigt.' });
  return c;
}

// ---------- Märkte
function overviewTable(groups, title) {
  const c = document.createElement('div'); c.className = 'card full';
  let rows = '';
  for (const [g, gn] of GROUPS.filter(x => groups.includes(x[0]))) {
    const ids = Object.values(S).filter(s => s.g === g).map(s => s.id); if (!ids.length) continue;
    rows += `<tr class="grp"><td colspan="9">${gn}</td></tr>`;
    for (const id of ids) {
      const s = S[id]; const sl = slice(id, 365);
      const lo = Math.min(...sl.v), hi = Math.max(...sl.v), pos = hi > lo ? (last(id) - lo) / (hi - lo) * 100 : 50;
      rows += `<tr class="row" data-id="${id}"><td>${esc(s.name)}${s.live ? ' <span style="color:var(--good)" title="live">●</span>' : ''}</td><td>${fmtV(id, last(id))}</td>
        <td>${fmtC(s.f === 'd' ? chg1d(id) : null)}</td><td>${fmtC(chgOver(id, 7))}</td><td>${fmtC(chgOver(id, 30))}</td><td>${fmtC(ytd(id))}</td><td>${fmtC(chgOver(id, 365))}</td>
        <td><span class="rng" title="Tief ${fmtV(id, lo)} · Hoch ${fmtV(id, hi)}"><i style="left:calc(${pos.toFixed(1)}% - 1px)"></i></span></td><td><canvas class="sp"></canvas></td></tr>`;
    }
  }
  c.innerHTML = `<div class="hd"><div class="ttl">${title}</div></div><table class="t"><tr><th>Name</th><th>Letzter</th><th>1 T.</th><th>1 W.</th><th>1 M.</th><th>lfd. J.</th><th>1 J.</th><th>52-W.-Spanne</th><th>3 M.</th></tr>${rows}</table>
    <div class="note">Zinsen in Basispunkten (Bp.), sonst in %. ● = live aktualisiert.</div>`;
  requestAnimationFrame(() => c.querySelectorAll('tr.row').forEach(r => { spark(r.querySelector('canvas'), sparkVals(r.dataset.id, 92)); r.onclick = () => openCompare(r.dataset.id); }));
  return c;
}
function heatColor(v, scale) { // divergierend blau (+) / rot (−), grau in der Mitte
  const x = Math.max(-1, Math.min(1, v / scale)); const a = Math.abs(x);
  const mid = [56, 56, 53], pos = [57, 135, 229], neg = [224, 82, 82]; const t = x >= 0 ? pos : neg;
  const c = mid.map((m, i) => Math.round(m + (t[i] - m) * Math.pow(a, 0.8)));
  return `rgb(${c.join(',')})`;
}
function sectorCard() {
  const c = document.createElement('div'); c.className = 'card';
  const ids = Object.values(S).filter(s => s.g === 'sektoren').map(s => s.id);
  const P = [['1 W.', 7], ['1 M.', 30], ['3 M.', 92], ['1 J.', 365]];
  const rel = {}; for (const id of ids) rel[id] = P.map(([, d]) => { const a = chgOver(id, d), b = chgOver('spx', d); return a && b ? a.v - b.v : null; });
  ids.sort((a, b) => (rel[b][2] || 0) - (rel[a][2] || 0));
  c.innerHTML = `<div class="hd"><div><div class="ttl">Sektoren gegenüber S&P 500</div><div class="sub">Mehr- oder Minderrendite in Prozentpunkten – zeigt, wohin das Geld rotiert.</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th>Sektor</th>${P.map(p => `<th>${p[0]}</th>`).join('')}</tr>
    ${ids.map(id => `<tr class="row" data-id="${id}"><td>${esc(S[id].name)}</td>${rel[id].map((v, j) => `<td class="heat" style="background:${v == null ? 'transparent' : heatColor(v, [3, 6, 10, 20][j])}">${v == null ? '–' : (v > 0 ? '+' : '') + nf(v, 1)}</td>`).join('')}</tr>`).join('')}</table>`;
  c.querySelectorAll('tr.row').forEach(r => r.onclick = () => openCompare(r.dataset.id, 'spx'));
  return c;
}
function secMaerkte(m) {
  head(m, 'Märkte', 'Alle Reihen mit Veränderungen. Klick auf eine Zeile öffnet sie im Vergleich.');
  const g = grid(m, 'wide');
  g.appendChild(chartCard({ ids: ['msci', 'spx', 'ndx', 'dax', 'nikkei', 'em'], title: 'Aktienindizes im Vergleich', sub: 'Start des Zeitraums = 100', norm: true, height: 'tall' }));
  g.appendChild(sectorCard());
  const g2 = grid(m); g2.style.marginTop = '12px';
  g2.appendChild(overviewTable(['aktien', 'risiko', 'zinsen', 'anleihen', 'rohstoffe', 'fx', 'krypto', 'verhaeltnis', 'bewertung', 'konjunktur'], 'Alle Werte'));
}

// ---------- Zinsen
function curveCard() {
  const c = document.createElement('div'); c.className = 'card';
  const mats = [['3M', 'y3m', 0.25], ['2J', 'y2', 2], ['10J', 'y10', 10], ['30J', 'y30', 30]];
  const ld = lastDay('y10'); const snaps = [['heute', 0, C.s1], ['vor 1 M.', 30, C.s2], ['vor 1 J.', 365, C.s3], ['vor 3 J.', 1096, C.s7]];
  const vals = snaps.map(([n, d]) => mats.map(([, id]) => valAt(id, ld - d)));
  const all = vals.flat().filter(v => v != null); const lo = Math.floor(Math.min(...all) - 0.3), hi = Math.ceil(Math.max(...all) + 0.3);
  const W = 520, H = 210, L = 40, R = 14, T = 12, B = 26;
  const xs = mats.map(([, , y]) => L + Math.log(y / 0.25) / Math.log(30 / 0.25) * (W - L - R));
  const ys = v => T + (hi - v) / (hi - lo) * (H - T - B);
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;margin-top:6px">`;
  for (let v = lo; v <= hi; v += (hi - lo > 4 ? 1 : 0.5)) svg += `<line x1="${L}" x2="${W - R}" y1="${ys(v)}" y2="${ys(v)}" stroke="${C.grid}"/><text x="${L - 6}" y="${ys(v) + 4}" fill="${C.mut}" font-size="10" text-anchor="end">${nf(v, 1)}</text>`;
  mats.forEach(([n], i) => svg += `<text x="${xs[i]}" y="${H - 8}" fill="${C.mut}" font-size="11" text-anchor="middle">${n}</text>`);
  snaps.forEach(([n, , col], j) => {
    const pts = vals[j].map((v, i) => v == null ? null : [xs[i], ys(v)]).filter(Boolean);
    svg += `<polyline fill="none" stroke="${col}" stroke-width="${j ? 1.5 : 2.5}" ${j ? 'stroke-dasharray="' + (j === 1 ? '4 3' : j === 2 ? '2 3' : '6 3 2 3') + '"' : ''} points="${pts.map(p => p.join(',')).join(' ')}"/>`;
    pts.forEach((p, i) => svg += `<circle cx="${p[0]}" cy="${p[1]}" r="${j ? 3 : 4}" fill="${col}" stroke="var(--panel)" stroke-width="2" data-j="${j}" data-i="${i}"/>`);
  });
  svg += '</svg>';
  c.innerHTML = `<div class="hd"><div><div class="ttl">US-Zinskurve</div><div class="sub">Rendite nach Laufzeit. Normal steigt die Kurve – fallend (invertiert) ging oft Rezessionen voraus.</div></div></div>
    <div class="legend">${snaps.map(([n, , col], j) => `<span><i style="border-color:${col};${j ? 'border-top-style:dashed' : ''}"></i>${n}</span>`).join('')}</div>${svg}`;
  c.querySelectorAll('circle').forEach(ci => { ci.onmousemove = e => { const j = +ci.dataset.j, i = +ci.dataset.i; showTip(e, `${snaps[j][0]} · ${mats[i][0]}: <b>${nf(vals[j][i], 2)} %</b>`); }; ci.onmouseleave = hideTip; });
  return c;
}
function secZinsen(m) {
  head(m, 'Zinsen', 'Zinsen sind der Preis des Geldes – sie beeinflussen Bewertungen, Währungen und Konjunktur.');
  const g = grid(m);
  g.appendChild(curveCard());
  g.appendChild(chartCard({ ids: ['y3m', 'y2', 'y10', 'y30'], title: 'US-Staatsanleihen' }));
  g.appendChild(chartCard({ ids: ['curve10_2'], title: 'Zinskurve 10J − 2J', type: 'baseline', sub: 'Rot = invertiert' }));
  g.appendChild(chartCard({ ids: ['curve10_3m'], title: 'Zinskurve 10J − 3M', type: 'baseline', sub: 'Lieblingsindikator der Fed-Forscher für Rezessionen' }));
  g.appendChild(chartCard({ ids: ['effr', 'ecb'], title: 'Leitzinsen: Fed und EZB' }));
  g.appendChild(chartCard({ ids: ['real10', 'breakeven'], title: 'Realzins und Inflationserwartung (10J)', sub: 'Nominalzins = Realzins + Inflationserwartung' }));
  g.appendChild(chartCard({ ids: ['y10', 'eu10'], title: 'USA vs. Euroraum 10J' }));
  g.appendChild(chartCard({ ids: ['us_eu10'], title: 'Zinsabstand USA − Euro 10J', type: 'baseline', sub: 'Größerer Abstand stützt meist den Dollar' }));
  g.appendChild(chartCard({ ids: ['mort30'], title: 'US-Hypothekenzins 30J' }));
}
function secRisiko(m) {
  head(m, 'Risiko & Breite', 'Wie viel Risiko Anleger gerade eingehen wollen und wie breit der Markt steigt – Angstbarometer, Kreditmarkt und Marktbreite.');
  const g = grid(m);
  g.appendChild(chartCard({ ids: ['vix'], title: 'VIX – Angst am Aktienmarkt', ref: 20, refLabel: '20' }));
  g.appendChild(chartCard({ ids: ['vix_term'], title: 'VIX-Kurve (1 Monat / 3 Monate)', ref: 1, refLabel: '1,0', sub: 'Über 1 = kurzfristige Angst größer als längerfristige – typisch für akuten Stress' }));
  g.appendChild(chartCard({ ids: ['move'], title: 'MOVE – Angst am Anleihemarkt' }));
  g.appendChild(chartCard({ ids: ['nfci', 'anfci'], title: 'Finanzbedingungen (Chicago Fed)', ref: 0, refLabel: '0', sub: 'Über 0 = straffer als im Durchschnitt seit 1971, unter 0 = locker' }));
  g.appendChild(chartCard({ ids: ['aaii'], title: 'Anlegerstimmung (AAII)', ref: 0, refLabel: '0', sub: 'Bullen minus Bären in Prozentpunkten – Extreme gelten als Kontraindikator' }));
  g.appendChild(chartCard({ ids: ['skew'], title: 'SKEW – Nachfrage nach Crash-Absicherung' }));
  g.appendChild(chartCard({ ids: ['kre', 'xlf'], title: 'Regionalbanken vs. Finanzsektor', norm: true, sub: 'Start = 100 · Regionalbanken reagieren früh auf Kreditstress' }));
  g.appendChild(chartCard({ ids: ['hyg_ief'], title: 'Kreditappetit (HYG/IEF)', sma: 200, sub: 'Steigt, wenn Anleger riskante Unternehmensanleihen Staatsanleihen vorziehen' }));
  g.appendChild(chartCard({ ids: ['vwehx'], title: 'Hochzinsanleihen (Fonds seit 1978)', sma: 200, sub: 'Fallen riskante Unternehmensanleihen unter ihren Trend, zogen sich Anleger oft schon vor Aktiencrashs aus Risiken zurück' }));
  if (S.baa_spread) g.appendChild(chartCard({ ids: ['baa_spread'], title: 'Kreditaufschlag Baa − 10J (seit 1953)', sub: 'Was mittelgute Unternehmen mehr zahlen müssen als der Staat. Steigt vor und in Krisen.', minDays: 3653 }));
  g.appendChild(chartCard({ ids: ['breadth'], title: 'Marktbreite (RSP/SPY)', sub: 'Fällt, wenn nur wenige große Aktien den Index tragen' }));
  g.appendChild(chartCard({ ids: ['ew_lag'], title: 'Rückstand der vielen (6 Monate)', ref: 0, refLabel: '0', sub: 'Gleichgewichteter S&P 500 minus normaler, Kursentwicklung über 6 Monate in Prozentpunkten – stark negativ heißt: wenige Schwergewichte tragen den Index' }));
  g.appendChild(chartCard({ ids: ['sect_part'], title: 'US-Sektoren im Aufwärtstrend', ref: 50, refLabel: '50 %', sub: 'Anteil der 11 Sektoren über ihrer 200-Tage-Linie – steigt der Index, während dieser Anteil fällt, tragen immer weniger den Markt' }));
  g.appendChild(chartCard({ ids: ['world_part'], title: 'Weltbörsen im Aufwärtstrend', ref: 50, refLabel: '50 %', sub: 'Anteil von 9 großen Indizes (USA, Europa, Japan, Hongkong, Schwellenländer) über ihrer 200-Tage-Linie' }));
  g.appendChild(chartCard({ ids: ['ndx_spx'], title: 'Tech-Dominanz (Nasdaq 100 / S&P 500)' }));
  g.appendChild(chartCard({ ids: ['small_large'], title: 'Nebenwerte gegenüber Standardwerten', sub: 'Small Caps hängen stärker an Konjunktur und Zinsen' }));
  g.appendChild(chartCard({ ids: ['disc_stap'], title: 'Zyklischer Konsum vs. Basiskonsum', sub: 'Steigt in Phasen von Konsumlaune, fällt bei Vorsicht' }));
  g.appendChild(chartCard({ ids: ['tlt', 'ief', 'lqd', 'hyg', 'tip'], title: 'Anleihe-ETFs im Vergleich', norm: true, sub: 'Start = 100' }));
}
function secRohstoffe(m) {
  head(m, 'Rohstoffe', 'Energie, Edelmetalle und Kupfer – Inflation, Konjunktur und Geopolitik in Preisen.');
  const g = grid(m);
  g.appendChild(chartCard({ ids: ['wti', 'brent'], title: 'Rohöl' }));
  g.appendChild(chartCard({ ids: ['natgas'], title: 'Erdgas (Henry Hub)' }));
  g.appendChild(chartCard({ ids: ['heatoil', 'diesel'], title: 'Diesel: Future und Tankstelle (US)', sub: 'Gleiche Einheit ($ je Gallone)' }));
  g.appendChild(chartCard({ ids: ['gold'], title: 'Gold' }));
  g.appendChild(chartCard({ ids: ['silver'], title: 'Silber' }));
  g.appendChild(chartCard({ ids: ['copper'], title: 'Kupfer', sub: '„Dr. Copper“ – reagiert früh auf die Weltkonjunktur' }));
  g.appendChild(chartCard({ ids: ['cu_au'], title: 'Kupfer/Gold-Verhältnis', sub: 'Wachstum gegen Vorsicht' }));
  g.appendChild(chartCard({ ids: ['gold_spx'], title: 'Gold gegenüber S&P 500' }));
}
function secFx(m) {
  head(m, 'Währungen & Krypto', 'Der Dollar ist die Weltleitwährung – seine Stärke wirkt auf Rohstoffe, Schwellenländer und Gewinne.');
  const g = grid(m);
  g.appendChild(chartCard({ ids: ['dxy'], title: 'Dollar-Index', sma: 200 }));
  g.appendChild(chartCard({ ids: ['eurusd'], title: 'EUR/USD' }));
  g.appendChild(chartCard({ ids: ['usdjpy'], title: 'USD/JPY' }));
  g.appendChild(chartCard({ ids: ['usdcny'], title: 'USD/CNY' }));
  g.appendChild(chartCard({ ids: ['btc'], title: 'Bitcoin', log: RANGE > 400, sma: 200 }));
  g.appendChild(chartCard({ ids: ['eth'], title: 'Ethereum', log: RANGE > 400 }));
  g.appendChild(chartCard({ ids: ['btc_ndx'], title: 'Bitcoin gegenüber Nasdaq 100' }));
}
function secKonjunktur(m) {
  head(m, 'Konjunktur', 'Monats- und Wochendaten zur US-Wirtschaft. Kurze Zeiträume werden automatisch auf mindestens 1–3 Jahre erweitert.');
  const g = grid(m);
  g.appendChild(chartCard({ ids: ['cpi', 'core', 'hicp'], title: 'Inflation USA und Euroraum', ref: 2, refLabel: 'Ziel 2 %' }));
  g.appendChild(chartCard({ ids: ['cli_us', 'cli_g7'], title: 'OECD-Frühindikator', ref: 100, refLabel: '100', sub: 'Über 100 und steigend = Wachstum über Trend; läuft der Konjunktur einige Monate voraus' }));
  g.appendChild(chartCard({ ids: ['claims'], title: 'Erstanträge auf Arbeitslosenhilfe (Tsd., 4-W.-Ø)', sub: 'Wöchentlich und schnell – steigt früh, wenn Firmen entlassen (nicht saisonbereinigt)' }));
  g.appendChild(chartCard({ ids: ['unemp'], title: 'US-Arbeitslosenquote' }));
  g.appendChild(chartCard({ ids: ['sahm'], title: 'Sahm-Regel', ref: 0.5, refLabel: 'Schwelle 0,5', sub: 'Steigt der Wert über 0,5, begann bisher fast immer eine Rezession' }));
  if (S.u6) g.appendChild(chartCard({ ids: ['u6', 'unemp'], title: 'Unterbeschäftigung U-6 vs. Arbeitslosenquote', sub: 'U-6 zählt auch unfreiwillige Teilzeit und Entmutigte mit – wer nur ein paar Stunden Gig-Arbeit findet, gilt in der normalen Quote als beschäftigt', minDays: 3653 }));
  if (S.pt_econ) g.appendChild(chartCard({ ids: ['pt_econ'], title: 'Unfreiwillige Teilzeit', sub: 'Anteil der Beschäftigten, die gern Vollzeit arbeiten würden, aber nur Teilzeit finden', minDays: 3653 }));
  if (S.multi_jobs) g.appendChild(chartCard({ ids: ['multi_jobs'], title: 'Mehrfachbeschäftigte', sub: 'Anteil mit zwei oder mehr Jobs. Wichtig: Die Stellenstatistik zählt Jobs, nicht Menschen – wer drei Jobs hat, zählt dort dreifach', minDays: 3653 }));
  g.appendChild(chartCard({ ids: ['payrolls'], title: 'Neue Stellen pro Monat (Tsd.)', type: 'hist' }));
  g.appendChild(chartCard({ ids: ['fedbs'], title: 'Fed-Bilanzsumme', sub: 'Steigt bei Anleihekäufen (QE), fällt beim Abbau (QT)' }));
  g.appendChild(chartCard({ ids: ['ecbbs'], title: 'EZB-Bilanzsumme' }));
  g.appendChild(chartCard({ ids: ['mort30'], title: 'US-Hypothekenzins 30J' }));
  g.appendChild(chartCard({ ids: ['diesel'], title: 'US-Diesel (Tankstelle)' }));
}
function secBewertung(m) {
  head(m, 'Bewertung', 'Wie teuer Aktien gemessen an Gewinnen, Zinsen und Wirtschaftsleistung sind. Bewertung sagt wenig über die nächsten Monate, aber viel über die nächsten 10 Jahre.');
  const g = grid(m);
  g.appendChild(capeCard());
  g.appendChild(chartCard({ ids: ['cape_long'], title: 'Shiller-KGV seit 1881', sub: 'Monatswerte · Langfristiger Schnitt rund 17', ref: 17, refLabel: 'Ø ~17', minDays: 99999 }));
  g.appendChild(chartCard({ ids: ['ecy'], title: 'Aktien-Risikoprämie (Excess CAPE Yield)', type: 'baseline', sub: 'Gewinnrendite (1/CAPE) minus realer 10J-Zins. Niedrig = Aktien bieten wenig Mehrertrag gegenüber Anleihen', minDays: 99999 }));
  g.appendChild(chartCard({ ids: ['buffett'], title: 'Buffett-Indikator', sub: 'US-Börsenwert (Wilshire 5000) im Verhältnis zum BIP – Näherung', minDays: 3653 }));
  g.appendChild(chartCard({ ids: ['spx_real'], title: 'S&P 500 seit 1871 – real, mit Dividenden', log: true, sub: 'Logarithmisch · inflationsbereinigt, heute = 100', minDays: 99999 }));
  g.appendChild(chartCard({ ids: ['world_us'], title: 'MSCI World gegenüber S&P 500', sub: 'Fällt, wenn die USA den Rest der Welt schlagen', minDays: 3653 }));
}

// ---------- Einschätzung (Modell)
let TGT = load('tgt') || 'world';
const BANDC = [[0, 35, C.crit], [35, 45, C.warn], [45, 65, '#5b6170'], [65, 100, C.good]];
function monthDay(p) { return Math.floor(Date.UTC(+p.slice(0, 4), +p.slice(5, 7) - 1, p.length > 7 ? +p.slice(8, 10) : 1) / 864e5); }
function gaugeHTML(score) {
  const segs = BANDC.map(([a, b, c]) => `<div style="left:${a}%;width:${b - a}%;background:${c}"></div>`).join('');
  return `<div class="gauge">${segs}<i style="left:calc(${Math.max(0, Math.min(100, score))}% - 2px)"></i></div>
    <div class="gscale">${[0, 35, 45, 65, 100].map(v => `<span style="left:${v}%">${v}</span>`).join('')}</div>`;
}
function pillarBar(v) { // 0..100, Mitte 50
  if (v == null) return '<span class="mut">–</span>';
  const x = Math.max(0, Math.min(100, v)); const l = Math.min(50, x), w = Math.abs(x - 50);
  return `<span class="pbar"><b style="left:${l}%;width:${w}%;background:${x >= 50 ? C.s1 : C.s8}"></b><i></i></span>`;
}
function compBar(v) { // -1..+1
  if (v == null) return '<span class="mut">–</span>';
  return pillarBar(50 + 50 * v);
}
function secEinschaetzung(m) {
  const M = DATA.model;
  head(m, 'Einschätzung', 'Alle Daten zusammen gelesen, täglich neu berechnet: ein Regelmodell aus acht Säulen, eine vorwärts getestete Crash-Wahrscheinlichkeit, die ähnlichsten Momente der Vergangenheit und was danach kam. Kursabhängige Teile rechnet die App mit jedem Live-Kurs nach.');
  if (M && M.targets && !M.targets[TGT]) TGT = 'world';
  if (!M || !M.targets || !M.targets[TGT]) { m.insertAdjacentHTML('beforeend', '<div class="card"><div class="note">Das Modell ist noch nicht berechnet – die nächste Datenaktualisierung liefert es.</div></div>'); return; }
  const T = M.targets[TGT], N = T.now;
  // Übersicht aller Indizes – zugleich Auswahl
  const ov = document.createElement('div'); ov.className = 'card full';
  const yrs = t => { const a = +t.since.slice(0, 4), b = +t.now.month.slice(0, 4); return b - a; };
  ov.innerHTML = `<div class="hd"><div><div class="ttl">Alle Indizes im Überblick</div><div class="sub">Klick auf eine Zeile zeigt die Einschätzung im Detail. Stand ${fmtDate(monthDay(N.day))} (Tagesmodell); Score und Wahrscheinlichkeit live mit den aktuellen Kursen.</div></div></div>
    <table class="t ov" style="margin-top:6px"><tr><th rowspan="2">Index</th><th rowspan="2">Region</th><th rowspan="2">Score</th><th rowspan="2">Lage</th><th colspan="4" class="grp">Risiko: Rückgang um 15 % oder mehr in den nächsten 12 Monaten</th><th rowspan="2">Trend</th><th rowspan="2">Daten</th></tr>
    <tr><th title="Vorwärts getestete Modellprognose für heute">Prognose</th><th title="Wie oft es früher passierte, wenn der Score ähnlich war">früher bei<br>gleichem Score</th><th title="Wie oft es nach den 8 ähnlichsten Momenten der Geschichte passierte">früher in<br>ähnlichen Lagen</th><th title="Wie oft es im Durchschnitt aller Monate passierte">im<br>Durchschnitt</th></tr>
    ${Object.entries(M.targets).map(([k, t]) => { const tr = (t.now.pillars.find(p => p.id === 'trend') || {}).score; const y = yrs(t);
      return `<tr class="row ${k === TGT ? 'hl' : ''}" data-t="${k}"><td>${esc(t.name)}</td><td style="font-family:inherit" class="mut">${esc(t.region || '')}</td><td><b id="ov-s-${k}">${t.now.score}</b></td>
      <td style="font-family:inherit" id="ov-l-${k}"><span class="badge ${t.now.cls === 'crit' ? 'crit' : t.now.cls}">${esc(t.now.label)}</span></td>
      <td id="ov-p-${k}">${riskCell(t.now.risk ? t.now.risk.prob : null)}${t.prob && t.prob.pooled ? '<span class="mut" title="kurze Historie – Modell vom S&P 500 übernommen">¹</span>' : ''}</td>
      <td>${riskCell(t.now.risk ? t.now.risk.band : null)}</td><td>${riskCell(t.now.risk ? t.now.risk.analog : null)}</td><td class="mut">${t.now.risk ? t.now.risk.base + ' %' : '–'}</td>
      <td>${pillarBar(tr)}</td><td style="font-family:inherit" class="${y < 25 ? '' : 'mut'}">seit ${t.since.slice(0, 4)}${y < 25 ? ' <span style="color:var(--warn)" title="Kurzer Rückblick – Prozentwerte beruhen auf wenigen Fällen">⚠</span>' : ''}</td></tr>`; }).join('')}</table>
    <div class="note">Lesebeispiel: „Prognose 23 % · im Durchschnitt 20 %“ heißt, ein Rückgang um 15 % oder mehr ist gerade etwas wahrscheinlicher als üblich. Die mittleren beiden Spalten zeigen, wie oft er früher in vergleichbaren Lagen tatsächlich kam. ¹ kurze Historie, Prognose am S&P 500 gelernt. ⚠ weniger als 25 Jahre Daten. MSCI World in Euro mit Dividenden (wie ein thesaurierender ETF). Für DAX, Euro Stoxx, Nikkei und Schwellenländer gibt es kein frei verfügbares KGV, die Bewertung ist dort eine Näherung.</div>`;
  ov.querySelectorAll('tr.row').forEach(r => r.onclick = () => { TGT = r.dataset.t; store('tgt', TGT); renderSection(); setTimeout(() => { const h = document.getElementById('hero'); if (h) h.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 30); });
  m.appendChild(ov);
  planCard(m, M);
  sect(m, esc(T.name) + ' im Detail');

  // Kopf: Score, Ampel, Handlung, Säulen, Klartext
  const hero = document.createElement('div'); hero.className = 'card hero'; hero.id = 'hero';
  hero.innerHTML = `<div class="hgrid">
    <div>
      <div class="lbl">Gesamtscore ${esc(T.name)}</div>
      <div class="hscore"><span class="big" id="hs-score">${N.score}</span><span class="mut"> / 100</span> <span id="hs-badge"><span class="badge ${N.cls === 'crit' ? 'crit' : N.cls}">${esc(N.label)}</span></span><span class="livetag" id="hs-live"></span></div>
      ${gaugeHTML(N.score)}
      <div class="action"><span class="mut">Modell sagt:</span> <b id="hs-action">${esc(N.action)}</b></div>
      ${N.risk ? `<div class="probbox"><div class="lbl">Wahrscheinlichkeit für einen Rückgang von mindestens ${Math.round(T.crash * 100)} % in den nächsten 12 Monaten</div>
        <div><span class="big" id="hs-prob" style="font-size:30px">${N.risk.prob ?? '–'} %</span> <span class="mut">normal: ${N.risk.base} %</span>${T.prob && T.prob.pooled ? ' <span class="mut">· am S&P 500 gelernt (kurze Historie)</span>' : ''}</div>
        <div class="rk"><span>So oft kam es tatsächlich vor: <b>${N.risk.band ?? '–'} %</b> bei ähnlichem Score</span><span><b>${N.risk.analog ?? '–'} %</b> in den ähnlichsten Momenten</span></div></div>` : ''}
    </div>
    <div>
      <div class="lbl">Säulen <span class="mut">(50 = neutral)</span></div>
      <table class="t pil">${N.pillars.map(p => `<tr><td>${esc(p.name)} <span class="mut">${Math.round(p.weight * 100)} %</span></td><td>${pillarBar(p.score)}</td><td>${p.score == null ? '–' : p.score}</td></tr>`).join('')}</table>
    </div></div>
    <div class="interp">${N.text.map(esc).join(' ')}</div>`;
  m.appendChild(hero);

  // Säulen im Detail
  sect(m, 'Säulen im Detail');
  const g = grid(m);
  N.pillars.forEach(p => {
    const c = document.createElement('div'); c.className = 'card';
    c.innerHTML = `<div class="hd"><div class="ttl">${esc(p.name)} <small>${Math.round(p.weight * 100)} % Gewicht</small></div><div class="big" style="font-size:20px">${p.score == null ? '–' : p.score}</div></div>
      <table class="t comp">${p.comps.map(k => `<tr style="${k.stale ? 'opacity:.55' : ''}"><td>${esc(k.name)}<div class="mut" style="font-size:11px">${esc(k.text || '')}${k.asof && Math.abs(monthDay(k.asof) - monthDay(N.day)) > 10 ? ' · Stand ' + fmtDate(monthDay(k.asof)) : ''}${k.stale ? ' · zu alt, nicht eingerechnet' : ''}</div></td><td>${compBar(k.score)}</td></tr>`).join('')}</table>`;
    g.appendChild(c);
  });
  g.appendChild(ruleCard(M));
  if (DATA.konz && (T.region === 'USA' || T.region === 'Welt')) konzSection(m, DATA.konz);
  if (M.quality && (T.region === 'USA' || T.region === 'Welt')) qualitySection(m, M.quality);

  // Verlauf
  sect(m, 'Verlauf');
  const vh = document.createElement('div'); vh.className = 'card full';
  vh.innerHTML = `<div class="hd"><div><div class="ttl">${esc(T.name)}, Score und Wahrscheinlichkeit seit ${T.since.slice(0, 4)}</div><div class="sub">Oben der Index (logarithmisch), unten Score (Fläche) und Crash-Wahrscheinlichkeit in % (orange, ab ${T.prob && T.prob.oos_from ? T.prob.oos_from.slice(0, 4) : '–'} vorwärts getestet). Wochenwerte, gestrichelt 35 / 45 / 55 / 65.</div></div></div>
    <div class="legend" id="vlg"></div><div class="chart" style="height:260px"></div><div class="chart" style="height:170px"></div>`;
  m.appendChild(vh);
  queueMicrotask(() => {
    const els = vh.querySelectorAll('.chart'); const H = T.hist; const ds = H.days.map(monthDay);
    const a = baseChart(els[0], { log: true, fmt: p => nf(p, 0) });
    const ps = a.addLineSeries({ color: C.s1, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, priceFormat: pf(0) });
    const dPrice = ds.map((d, i) => ({ time: d * DAY, value: H.price[i] })).filter(x => x.value != null);
    ps.setData(dPrice);
    const b = baseChart(els[1], { fmt: p => nf(p, 0) });
    const sc = b.addBaselineSeries({ baseValue: { type: 'price', price: 50 }, lineWidth: 2, priceLineVisible: false, priceFormat: pf(0),
      topLineColor: C.s3, topFillColor1: 'rgba(25,158,112,.25)', topFillColor2: 'rgba(25,158,112,.03)',
      bottomLineColor: C.s8, bottomFillColor1: 'rgba(230,103,103,.03)', bottomFillColor2: 'rgba(230,103,103,.25)',
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 15, maxValue: 85 } }) });
    const dScore = ds.map((d, i) => ({ time: d * DAY, value: H.score[i] })).filter(x => x.value != null);
    sc.setData(dScore);
    [35, 45, 55, 65].forEach(v => sc.createPriceLine({ price: v, color: C.mut, lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
    const pr = b.addLineSeries({ color: C.s4, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, priceFormat: pf(0) });
    pr.setData(ds.map((d, i) => ({ time: d * DAY, value: H.prob[i] })).filter(x => x.value != null));
    linkCharts(a, ps, dPrice, b, sc, dScore);
    const lg = vh.querySelector('#vlg');
    const draw = t => { const i = t == null ? ds.length - 1 : ds.indexOf(t); if (i < 0) return;
      lg.innerHTML = `<span><i style="border-color:${C.s1}"></i>${esc(T.name)}<b>${nf(H.price[i], 0)}</b></span><span><i style="border-color:${C.s3}"></i>Score<b>${nf(H.score[i], 0)}</b></span><span><i style="border-color:${C.s4}"></i>Wahrscheinlichkeit<b>${H.prob[i] == null ? '–' : nf(H.prob[i], 0) + ' %'}</b></span><span class="d">${fmtDate(ds[i])}</span>`; };
    draw(null);
    const ch = p => draw(p && p.time ? p.time / DAY : null); a.subscribeCrosshairMove(ch); b.subscribeCrosshairMove(ch);
  });

  // Was danach kam
  analogSection(m, T);
  episodeSection(m, T);
  probSection(m, T);
  sect(m, 'Was historisch danach kam');
  const g2 = grid(m, 'wide');
  const bt = document.createElement('div'); bt.className = 'card';
  const cur = T.bands.find(b => N.score >= b.lo && N.score < b.hi);
  bt.innerHTML = `<div class="hd"><div><div class="ttl">Renditen nach Score-Bereich</div><div class="sub">${esc(T.name)}, Monate seit ${T.since.slice(0, 4)}. Kursrendite ohne Dividenden, Median.</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th>Score</th><th>Monate</th><th>Rückgang ≥ ${Math.round(T.crash * 100)} % im 1. J.</th><th>tiefster Stand im 1. J.</th><th>1 J.</th><th>im Plus</th><th>schlechtester 1 J.</th><th>3 J. p.a.</th><th>5 J. p.a.</th></tr>
    ${T.bands.map(b => `<tr class="${b === cur ? 'hl' : ''}"><td>${b.band}${b === cur ? ' ◀' : ''}</td><td>${b.n}</td><td>${riskCell(b.crash12)}</td><td>${fmtPct(b.dd12)}</td><td>${fmtPct(b.f12)}</td><td>${b.pos12 == null ? '–' : nf(b.pos12, 0) + ' %'}</td><td>${fmtPct(b.worst12, 0)}</td><td>${fmtPct(b.f36)}</td><td>${fmtPct(b.f60)}</td></tr>`).join('')}
    <tr><td class="mut">alle Monate</td><td class="mut"></td><td>${T.base.crash12} %</td><td>${fmtPct(T.base.dd12)}</td><td>${fmtPct(T.base.f12)}</td><td>${nf(T.base.pos12, 0)} %</td><td></td><td>${fmtPct(T.base.f36)}</td><td></td></tr></table>
    <div class="note">Lesart: Die Spalte „Rückgang“ zeigt, wie oft es nach einem Monat in diesem Bereich innerhalb eines Jahres mindestens ${Math.round(T.crash * 100)} % nach unten ging (Monatsschlusskurse). „Tiefster Stand“ = wie weit es im Median zwischenzeitlich fiel.</div>`;
  g2.appendChild(bt);
  const rk = document.createElement('div'); rk.className = 'card';
  const R = T.rank;
  rk.innerHTML = `<div class="hd"><div><div class="ttl">Welche Säule hat bisher geholfen?</div><div class="sub">Rangkorrelation mit dem, was danach kam. 0 = kein Zusammenhang, positiv = höherer Wert, besserer Verlauf.</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th></th><th>Rückgang im 1. J.</th><th>Rendite 12 M.</th><th>Rendite 3 J.</th></tr>
    <tr class="hl"><td>Gesamtscore</td><td>${fmtR(R.score_dd)}</td><td>${fmtR(R.score_f12)}</td><td>${fmtR(R.score_f36)}</td></tr>
    ${Object.entries(R.pillars).map(([k, v]) => `<tr><td>${esc((N.pillars.find(p => p.id === k) || {}).name || k)}</td><td>${fmtR(v.dd)}</td><td>${fmtR(v.f12)}</td><td>${fmtR(v.f36)}</td></tr>`).join('')}</table>
    <div class="note">Werte um ±0,1 sind Rauschen, ab etwa 0,2 ein echter, aber schwacher Zusammenhang. Bewertung wirkt typischerweise erst über Jahre, Trend und Stimmung eher kurzfristig. „Rückgang“: positiv = höherer Score, kleinere Rückgänge danach.</div>`;
  g2.appendChild(rk);

  // Strategien – Startzeitpunkt frei wählbar
  sect(m, 'Regeln im Test');
  const st = document.createElement('div'); st.className = 'card full';
  const S3 = T.strategies; const SM = T.strat_months;
  const y0 = +SM[0].slice(0, 4), y1 = +SM[SM.length - 1].slice(0, 4);
  const presets = [1990, 2000, 2008, 2010, 2020].filter(y => y > y0 && y < y1);
  st.innerHTML = `<div class="hd"><div><div class="ttl">Was wäre aus 100 geworden?</div><div class="sub">${esc(T.name)}, wöchentlich angepasst (Entscheidung am Freitag, gilt ab Montag), nicht investiertes Geld im Geldmarkt. Ohne Dividenden, Steuern und Kosten. Logarithmisch. Startpunkt wählen oder ins Diagramm klicken.</div></div></div>
    <div class="sstart"><span class="mut">Start:</span><button data-y="${SM[0]}">${y0}</button>${presets.map(y => `<button data-y="${y}">${y}</button>`).join('')}<input type="month" id="ss-in" min="${SM[0].slice(0, 7)}" max="${SM[SM.length - 13].slice(0, 7)}"><span class="mut" id="ss-lbl"></span></div>
    <div class="legend" id="slg"></div><div class="chart tall"></div>
    <table class="t" style="margin-top:8px"><tr><th>Regel</th><th>Rendite p.a.</th><th>größter Verlust</th><th>Schwankung</th><th>Ø investiert</th></tr>
    ${S3.map((x, j) => `<tr><td><i style="display:inline-block;width:12px;border-top:2px solid ${SER[j]};vertical-align:middle;margin-right:6px"></i>${esc(x.name)}<div class="mut" style="font-size:11px">${esc(x.desc)}</div></td><td id="sr-c${j}"></td><td id="sr-d${j}"></td><td id="sr-v${j}"></td><td id="sr-e${j}"></td></tr>`).join('')}</table>
    <div class="note">So arbeiten auch viele systematische Fonds: feste Regeln statt Bauchgefühl. Ihr Vorteil liegt meist weniger in höherer Rendite als in kleineren Verlusten – wer weniger investiert ist, verpasst dafür auch Teile der Aufschwünge. Ab frei gewähltem Start rechnet die App mit Monatswerten; der größte Verlust berücksichtigt den tiefsten Tageskurs je Monat.</div>`;
  m.appendChild(st);
  queueMicrotask(() => {
    const ch = baseChart(st.querySelector('.chart'), { log: true, fmt: p => nf(p, 0) });
    const ds = SM.map(monthDay); const lines = S3.map((x, j) => ch.addLineSeries({ color: SER[j], lineWidth: 2, priceLineVisible: false, priceFormat: pf(0) }));
    let i0 = 0;
    const stats = (x, i) => { const e = x.eq, n = e.length - 1 - i; if (n < 12) return null;
      const cagr = (Math.pow(e[e.length - 1] / e[i], 12 / n) - 1) * 100;
      let pk = e[i], mdd = 0; for (let k = i + 1; k < e.length; k++) { const lo = x.lo ? x.lo[k] : e[k]; mdd = Math.min(mdd, lo / pk - 1); pk = Math.max(pk, e[k]); }
      const rs = []; for (let k = i + 1; k < e.length; k++) rs.push(e[k] / e[k - 1] - 1); const mu = rs.reduce((a, b) => a + b, 0) / rs.length;
      const vol = Math.sqrt(rs.reduce((a, b) => a + (b - mu) ** 2, 0) / (rs.length - 1) * 12) * 100;
      const ex = x.ex ? x.ex.slice(i + 1).reduce((a, b) => a + b, 0) / (e.length - 1 - i) * 100 : x.expo;
      return { cagr, mdd: mdd * 100, vol, ex }; };
    const lg = st.querySelector('#slg');
    const draw = t => { let i = t == null ? ds.length - 1 : ds.indexOf(t); if (i < i0) i = i0; if (i < 0) return;
      lg.innerHTML = S3.map((x, j) => `<span><i style="border-color:${SER[j]}"></i>${esc(x.name)}<b>${nf(x.eq[i] / x.eq[i0] * 100, 0)}</b></span>`).join('') + `<span class="d">${SM[i]}</span>`; };
    const setStart = i => { i0 = Math.max(0, Math.min(ds.length - 13, i));
      S3.forEach((x, j) => { lines[j].setData(x.eq.slice(i0).map((v, k) => ({ time: ds[i0 + k] * DAY, value: v / x.eq[i0] * 100 })));
        const r = stats(x, i0); const set = (id, h) => { const el = st.querySelector('#' + id); if (el) el.innerHTML = h; };
        set('sr-c' + j, r ? fmtPct(r.cagr) : '–'); set('sr-d' + j, r ? `<span style="color:${C.down}">${nf(r.mdd, 0)} %</span>` : '–');
        set('sr-v' + j, r ? nf(r.vol, 1) + ' %' : '–'); set('sr-e' + j, r ? nf(r.ex, 0) + ' %' : '–'); });
      ch.timeScale().fitContent();
      st.querySelector('#ss-lbl').textContent = `ab ${fmtDate(ds[i0])} · ${nf((ds.length - 1 - i0) / 12, 1)} Jahre`;
      st.querySelector('#ss-in').value = SM[i0].slice(0, 7);
      st.querySelectorAll('.sstart button').forEach(b => b.classList.toggle('on', SM.findIndex(d => d >= b.dataset.y) === i0));
      draw(null); };
    const idxOf = ymOrY => { const k = SM.findIndex(d => d >= String(ymOrY)); return k < 0 ? 0 : k; };
    st.querySelectorAll('.sstart button').forEach(b => b.onclick = () => setStart(idxOf(b.dataset.y)));
    st.querySelector('#ss-in').onchange = e => { if (e.target.value) setStart(idxOf(e.target.value)); };
    ch.subscribeClick(p => { if (p && p.time) setStart(ds.indexOf(p.time / DAY)); });
    ch.subscribeCrosshairMove(p => draw(p && p.time ? p.time / DAY : null));
    setStart(0);
  });
  m.insertAdjacentHTML('beforeend', `<div class="note" style="margin-top:14px;max-width:900px">${esc(M.note)} Das Modell fasst Daten nach festen Regeln zusammen, es kennt deine persönliche Lage nicht und garantiert nichts. Rückblicke zeigen, was war – nicht, was kommt.</div>`);
}
function konzSection(m, K) {
  const P = K.pe || {}, L = K.lag || {}, Hs = K.hist || {}, st = (Hs.stats || {})['1963'], sa = (Hs.stats || {}).all;
  if (!P.idx && !L.v && !st) return;
  sect(m, 'Konzentration: breites Risiko oder nur die Schwergewichte?');
  const c = document.createElement('div'); c.className = 'card full';
  const pe = v => v == null ? '–' : nf(v, 1);
  const qName = ['stärkster Rückstand', 'leichter Rückstand', 'gleichauf', 'leicht vorn', 'deutlich vorn'];
  const rows = st ? st.rows : [];
  const tile = (lbl, v, sub, col) => `<div><div class="lbl">${lbl}</div><div class="big" style="font-size:22px;${col ? 'color:' + col : ''}">${v}</div><div class="mut" style="font-size:11px">${sub}</div></div>`;
  const ratio = P.top && P.rest ? P.top / P.rest : null;
  c.innerHTML = `<div class="hd"><div><div class="ttl">KGV aufgeteilt und Rückstand der „vielen“</div>
    <div class="sub">Ein einziges Index-KGV vermischt zwei Lagen: Der ganze Markt ist teuer – oder nur die zehn größten Werte. Ebenso bei der Kursentwicklung: Tragen wenige Schwergewichte den Index, während die meisten Aktien zurückbleiben? KGV der letzten 12 Monate über Yahoo Finance (Stand ${esc(K.pe_at || '–')}), Top 10 = die zehn größten Positionen des S&P 500, Rest = der Index ohne sie, errechnet aus Gewicht und Gewinnen.</div></div></div>
    <div class="anasum" style="grid-template-columns:repeat(5,1fr)">
      ${tile('KGV S&P 500', pe(P.idx), 'alle 500')}
      ${tile('KGV Top 10', pe(P.top), `${P.w_top != null ? nf(P.w_top, 0) + ' % des Index' : ''}${P.top_f ? ' · erwartet ' + pe(P.top_f) : ''}`, ratio && ratio >= 1.5 ? C.serious : null)}
      ${tile('KGV Rest', pe(P.rest), 'ohne Top 10')}
      ${tile('KGV gleichgewichtet', pe(P.eq), 'RSP, jede Aktie gleich')}
      ${tile('Rückstand der vielen', L.v == null ? '–' : (L.v > 0 ? '+' : '') + nf(L.v * 100, 1) + ' %', 'gleichgewichtet ggü. normal, 6 Mon.', L.q === 0 ? C.serious : null)}
    </div>
    ${(K.flags || []).length ? `<div class="interp"><b>Hinweis:</b> ${K.flags.map(esc).join(' ')}</div>` : `<div class="interp">Keine auffällige Konzentration: Die vielen halten mit, und die Bewertung der Top 10 weicht nicht extrem vom Rest ab.</div>`}
    ${st ? `<div class="lbl" style="margin-top:10px">Was früher folgte – Index nahe am Hoch, eingeteilt nach Rückstand der vielen (USA seit ${st.from.slice(0, 4)}, Monatsdaten)</div>
    <table class="t" style="margin-top:4px"><tr><th>Lage der vielen (6 Mon.)</th><th>Monate</th><th>Verlust ≥ 15 % binnen 12 Mon.</th><th>Index nach 12 Mon. (Median)</th><th>Lücke wurde noch größer</th></tr>
    ${rows.map((r, i) => `<tr style="${L.q === i ? 'background:rgba(255,170,0,.10);font-weight:600' : ''}"><td>${qName[i]}${L.q === i ? ' ← heute' : ''}</td><td>${r.n}</td><td>${riskCell(r.dd15)}</td><td>${fmtPct(r.fw, 0)}</td><td>${r.widen == null ? '–' : nf(r.widen, 0) + ' %'}</td></tr>`).join('')}
    <tr class="mut"><td>alle Monate nahe Hoch</td><td>${st.n}</td><td>${st.base} %</td><td></td><td></td></tr></table>` : ''}
    <div class="g2" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px">
      <div><div class="lbl">Rückstand der vielen, täglich (RSP ggü. SPY, 6 Monate, in %)</div><div class="chart kz1" style="height:170px"></div></div>
      <div><div class="lbl">KGV mitgeschrieben (ab ${esc(((K.track || [])[0] || {}).d || '–')})</div><div class="chart kz2" style="height:170px"></div></div>
    </div>
    <div class="note">So liest du das: Hinken die vielen stark hinterher, während der Index nahe am Hoch steht, kam es seit 1963 etwa dreimal so oft zu einem Rückschlag von 15 % oder mehr – die Rendite über 12 Monate war im Mittel aber trotzdem gut, und meist liefen die Schwergewichte sogar weiter vorneweg. Es ist deshalb ein Hinweis auf <b>erhöhtes Rückschlagrisiko</b>, kein Verkaufssignal. Im Test machte es die Crash-Prognose sogar schlechter (trainiert bis 1989, geprüft ab 1990) und fließt deshalb <b>nicht</b> in den Score ein. Historie: Kenneth-French-Datenbibliothek, größere Hälfte der US-Aktien gleich gewichtet (verläuft zu 94 % wie RSP)${sa ? `; seit 1927: ${sa.rows[0].dd15} % gegenüber ${sa.base} % im Schnitt` : ''}. Ein historisches KGV ohne Top 10 gibt es nicht frei – deshalb wird es ab jetzt täglich mitgeschrieben. Die Top 10 sind die größten Positionen des SPY${P.holdings ? ' (' + P.holdings.map(h => esc(h.t)).join(', ') + ')' : ''} – Alphabet ist mit zwei Aktiengattungen doppelt vertreten. „erwartet“ = KGV auf die geschätzten Gewinne der nächsten 12 Monate (für den Gesamtindex nicht frei verfügbar).</div>`;
  m.appendChild(c);
  queueMicrotask(() => {
    const e1 = c.querySelector('.kz1'), e2 = c.querySelector('.kz2');
    const s = S.ew_lag;
    if (s && e1) { const ch = baseChart(e1, { fmt: v => nf(v, 1) + ' %' }); const ser = ch.addAreaSeries({ lineColor: C.s1, topColor: 'rgba(57,135,229,.25)', bottomColor: 'rgba(57,135,229,0)', lineWidth: 1.5, priceLineVisible: false });
      const from = Math.max(0, s.t.length - 1260); const d = []; for (let i = from; i < s.t.length; i++) d.push({ time: s.t[i] * DAY, value: s.v[i] });
      ser.setData(d); ser.createPriceLine({ price: 0, color: C.mut, lineStyle: 2, lineWidth: 1, axisLabelVisible: false }); ch.timeScale().fitContent(); }
    const tr = (K.track || []).filter(x => x.top || x.rest || x.eq);
    if (e2) { if (tr.length < 2) { e2.innerHTML = '<div class="mut" style="padding:60px 0;text-align:center">Wird ab heute täglich gesammelt – nach ein paar Tagen erscheint hier der Verlauf.</div>'; }
      else { const ch = baseChart(e2, { fmt: v => nf(v, 1) });
        [['top', C.serious, 'Top 10'], ['rest', C.s3, 'Rest'], ['eq', C.sec, 'gleichgewichtet'], ['idx', C.s1, 'S&P 500']].forEach(([k, col, t]) => {
          const d = tr.filter(x => x[k] != null).map(x => ({ time: monthDay(x.d) * DAY, value: x[k] })); if (d.length) ch.addLineSeries({ color: col, lineWidth: 1.5, title: t, priceLineVisible: false }).setData(d); });
        ch.timeScale().fitContent(); } }
  });
}
function qualitySection(m, Q) {
  sect(m, 'Gewinnqualität der Schwergewichte');
  const c = document.createElement('div'); c.className = 'card full';
  const pc = v => v == null ? '–' : fmtPct(v * 100, 0);
  const cell = (v, bad, good, f) => { if (v == null) return '–'; const col = bad(v) ? C.serious : good(v) ? C.up : C.txt; return `<span style="color:${col}">${f(v)}</span>`; };
  const P = Q.parts || {};
  c.innerHTML = `<div class="hd"><div><div class="ttl">Sind die Gewinne der Tech-Riesen echt?</div>
    <div class="sub">Kreisgeschäfte – A investiert in B, B kauft bei A, beide melden Wachstum – hinterlassen Spuren in der Bilanz: Gewinne ohne Geldzufluss, Buchgewinne auf Beteiligungen statt Geschäftsgewinn, Forderungen, die schneller wachsen als der Umsatz, Investitionen, die den Cashflow auffressen, und frisches Geld über neue Schulden und Aktien. Gerechnet wird mit dem operativen Gewinn, weil Wertsteigerungen von Beteiligungen den ausgewiesenen Gewinn aufblähen. Genau das wird hier gemessen (letzte 12 Monate, Quartalsberichte über Yahoo Finance, Stand ${esc(Q.at || '')}).</div></div>
    <div class="big" style="font-size:20px">${Math.round(50 + 50 * Q.score)}</div></div>
    <div class="anasum" style="grid-template-columns:repeat(3,1fr)">
      ${[['cc', 'Gewinn durch Cashflow gedeckt'], ['rec', 'Forderungen vs. Umsatz'], ['capex', 'Investitionen vs. Cashflow'], ['inv', 'Beteiligungen'], ['fin', 'Fremdfinanzierung'], ['nonop', 'Buchgewinne']].filter(([k]) => P[k] != null).map(([k, n]) => `<div><div class="lbl">${n}</div><div>${compBar(P[k] ?? null)}</div></div>`).join('')}
    </div>
    <table class="t qt" style="margin-top:8px"><tr><th>Firma</th><th>Börsen&shy;wert</th><th>Cashflow<br>÷ op. Gewinn</th><th>freier Cashflow<br>÷ op. Gewinn</th><th>Investitionen<br>÷ Cashflow</th><th>Gewinn nicht<br>aus Geschäft</th><th>neue Schulden<br>+ Aktien</th><th>Schulden<br>ggü. Vorjahr</th><th>Umsatz<br>ggü. Vorjahr</th><th>Forderungen<br>ggü. Vorjahr</th><th>Quartal</th></tr>
    ${(Q.companies || []).map(x => `<tr><td>${esc(x.t)}</td><td>${x.mc ? nf(x.mc / 1e12, 2) + ' Bio.' : '–'}</td>
      <td>${x.cash_op != null ? cell(x.cash_op, v => v < 0.85, v => v >= 1.1, v => nf(v * 100, 0) + ' %') : cell(x.cash_conv, v => v < 0.8, v => v >= 1.0, v => nf(v * 100, 0) + ' %')}</td>
      <td>${cell(x.fcf_op ?? x.fcf_ni, v => v < 0.3, v => v >= 0.8, v => nf(v * 100, 0) + ' %')}</td>
      <td>${cell(x.capex_ocf, v => v > 0.8, v => v < 0.4, v => nf(v * 100, 0) + ' %')}</td>
      <td>${cell(x.nonop, v => v > 0.25, v => v < 0.05, v => nf(v * 100, 0) + ' %')}</td>
      <td>${x.fin_ocf == null ? '–' : cell(x.fin_ocf, v => v > 0.4, v => v < 0.1, v => nf((x.debt_iss || 0) + (x.eq_iss || 0), 0) + ' Mrd.')}</td>
      <td>${cell(x.debt_g, v => v > 0.5, () => false, v => (v > 0 ? '+' : '') + nf(v * 100, 0) + ' %')}</td>
      <td>${x.rev_g == null ? '–' : (x.rev_g > 0 ? '+' : '') + nf(x.rev_g * 100, 0) + ' %'}</td>
      <td>${cell(x.rec_g, v => x.rev_g != null && v - x.rev_g > 0.15, () => false, v => (v > 0 ? '+' : '') + nf(v * 100, 0) + ' %')}</td><td class="mut">${x.asof ? fmtDate(monthDay(x.asof)) : '–'}</td></tr>`).join('')}</table>
    ${Q.flags && Q.flags.length ? `<div class="interp"><b>Auffällig:</b> ${Q.flags.map(esc).join(' · ')}</div>` : ''}
    <div class="note">Das ist ein Warnsignal, kein Beweis: Hohe Investitionen können sich auszahlen, und Forderungen steigen auch bei echtem Wachstum. Konkrete Gegengeschäfte (wer wem was zusagt) stehen nur im Fließtext der Berichte und lassen sich nicht automatisch auslesen. Die Werte fließen mit dem Gewinnwachstum in die Säule „Gewinne“ ein – nur für den aktuellen Stand, denn diese Daten gibt es nicht für frühere Jahrzehnte.</div>`;
  m.appendChild(c);
}
function probSection(m, T) {
  const Pq = T.prob; if (!Pq || !Pq.calib || !Pq.calib.length) return;
  sect(m, 'Wie verlässlich ist die Wahrscheinlichkeit?');
  const c = document.createElement('div'); c.className = 'card full';
  c.innerHTML = `<div class="hd"><div><div class="ttl">Vorwärts getestet seit ${Pq.oos_from ? Pq.oos_from.slice(0, 4) : '–'}</div>
    <div class="sub">Für jedes Jahr wurde das Modell nur mit Daten trainiert, deren Ausgang damals schon bekannt war, und dann auf das neue Jahr angewendet${Pq.pooled ? ' – wegen der kurzen Historie mit dem am S&P 500 gelernten Zusammenhang' : ''}. Die Tabelle vergleicht, was es vorhergesagt hat, mit dem, was passierte (Monatsenden).</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th>vorhergesagt</th><th>Fälle</th><th>Ø vorhergesagt</th><th>tatsächlich eingetreten</th></tr>
    ${Pq.calib.filter(x => x.n).map(x => `<tr><td>${x.lo}–${x.hi} %</td><td>${x.n}</td><td>${x.pred} %</td><td>${riskCell(x.real)}</td></tr>`).join('')}</table>
    <div class="interp">${Pq.skill == null ? 'Zu wenig Fälle für eine Bewertung.' : Pq.skill > 5 ? `Das Modell war treffsicherer als der bloße Durchschnitt (Brier-Skill <b>${fmtPct(Pq.skill, 0)}</b>). Die Werte sind eher vorsichtig: Was es als niedrig einstufte, trat etwas häufiger ein. Der Wert ist eine grobe Orientierung, keine Präzisionsangabe.` : Pq.skill > 0 ? `Das Modell war nur knapp besser als der bloße Durchschnitt (Brier-Skill <b>${fmtPct(Pq.skill, 0)}</b>). Lies den Wert als grobe Richtung.` : `Das Modell war hier <b>nicht besser</b> als der bloße Durchschnitt (Brier-Skill ${fmtPct(Pq.skill, 0)}) – für diesen Index taugt die Zahl nur als Hinweis.`}</div>`;
  m.appendChild(c);
}
// ---------- Live-Score: kursabhängige Komponenten mit dem aktuellen Kurs neu rechnen (spiegelt terminal/model.py)
function ip(v, xs, ys) { if (v == null || !isFinite(v)) return null; if (v <= xs[0]) return ys[0]; if (v >= xs[xs.length - 1]) return ys[ys.length - 1];
  for (let i = 1; i < xs.length; i++) if (v <= xs[i]) { const f = (v - xs[i - 1]) / (xs[i] - xs[i - 1]); return ys[i - 1] + f * (ys[i] - ys[i - 1]); } return null; }
const cl1 = v => v == null || !isFinite(v) ? null : Math.max(-1, Math.min(1, v));
function liveModel(T) {
  const L = T.live; if (!L || !L.closes || !S[T.sid]) return null;
  const s = S[T.sid]; const pNow = s.v[s.v.length - 1], dNow = s.t[s.t.length - 1];
  const lastD = monthDay(L.last);
  let series = L.closes.slice();
  if (dNow === lastD) series[series.length - 1] = pNow; else if (dNow > lastD) series.push(pNow); else return null;
  const n = series.length, p = series[n - 1];
  const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
  const comps = {};
  if (n >= 210) comps.sma10 = ['trend', cl1((p / mean(series.slice(n - 210)) - 1) / 0.05)];
  if (n >= 253) comps.mom12 = ['trend', cl1((p / series[n - 1 - 252] - 1 - (L.tbill || 0) / 100) / 0.15)];
  if (n >= 1000) comps.w200 = ['trend', ip(p / mean(series.slice(n - 1000)) - 1, [-0.05, 0.10, 0.30, 0.50], [1.0, 0.3, 0.0, -0.4])];
  comps.dd = ['stimmung', ip(p / Math.max(...series.slice(Math.max(0, n - 252))) - 1, [-0.25, -0.10, 0.0], [1.0, 0.4, 0.0])];
  if (n >= 22 && L.rv_med) { const r = []; for (let i = n - 21; i < n; i++) r.push(Math.log(series[i] / series[i - 1]));
    const m_ = mean(r); const sd = Math.sqrt(r.reduce((x, y) => x + (y - m_) ** 2, 0) / (r.length - 1)) * Math.sqrt(252);
    comps.rv = ['schwankung', ip(sd / L.rv_med, [0.8, 1.25, 2.0], [0.3, 0.0, -1.0])]; }
  const all = Object.assign({}, L.fixed, comps);
  const pil = {}; L.pillars.forEach(k => pil[k] = []);
  Object.values(all).forEach(([k, v]) => { if (v != null && isFinite(v) && pil[k]) pil[k].push(v); });
  let num = 0, den = 0; const pv = {};
  L.pillars.forEach(k => { if (pil[k].length) { pv[k] = mean(pil[k]); num += L.weights[k] * pv[k]; den += L.weights[k]; } });
  if (!den) return null;
  const tot = num / den; const t = tot / L.sd;
  const score = Math.max(0, Math.min(100, 50 + 15 * t));
  const prob = L.coef ? 100 / (1 + Math.exp(-(L.coef[0] + L.coef[1] * t))) : null;
  return { score, prob, day: dNow };
}
function labelOf(sc) { return sc >= 65 ? ['Rückenwind', 'good', 'Kaufen – auch größere Beträge'] : sc >= 45 ? ['Neutral', 'neutral', 'Normal investieren (Sparplan oder in Raten)'] : sc >= 35 ? ['Gegenwind', 'warn', 'Nur in Raten investieren, keine großen Einmalbeträge'] : ['Gefahrenzone', 'crit', 'Abwarten – historisch folgten hier meist Verluste']; }
function updateLive() {
  const M = DATA && DATA.model; if (!M || !M.targets || SECTION !== 'einschaetzung') return;
  for (const [k, T] of Object.entries(M.targets)) {
    const r = liveModel(T); if (!r) continue;
    const sc = Math.round(r.score), lb = labelOf(sc);
    const e1 = document.getElementById('ov-s-' + k); if (e1) e1.textContent = sc;
    const e2 = document.getElementById('ov-l-' + k); if (e2) e2.innerHTML = `<span class="badge ${lb[1]}">${lb[0]}</span>`;
    const e3 = document.getElementById('ov-p-' + k); if (e3 && r.prob != null) e3.innerHTML = riskCell(Math.round(r.prob)) + (T.prob && T.prob.pooled ? '<span class="mut">¹</span>' : '');
    if (k === TGT) {
      const h = document.getElementById('hs-score'); if (h) h.textContent = sc;
      const hb = document.getElementById('hs-badge'); if (hb) hb.innerHTML = `<span class="badge ${lb[1]}">${lb[0]}</span>`;
      const ha = document.getElementById('hs-action'); if (ha) ha.textContent = lb[2];
      const hp = document.getElementById('hs-prob'); if (hp && r.prob != null) hp.textContent = Math.round(r.prob) + ' %';
      const hl = document.getElementById('hs-live'); if (hl) hl.innerHTML = LIVEON ? `● live ${new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}` : '';
    }
  }
  refreshPlanLive();
}
// ---------- Einstiegsplan: einen größeren Betrag regelbasiert anlegen (Score + Ausstiegssignal)
let PLAN; // undefined = noch nicht geladen, null = keiner angelegt
const PLAN_DEF = { amount: 460000, reserve: 0, target: 'world_eur', start: null, base: 12, max: 24, linePct: 0, lineMax: 36, lineBand: 5, buys: [] };
const eur = v => nf(Math.round(v), 0) + ' €';
const ymd = d => d.toISOString().slice(0, 10);
function monthsBetween(a, b) { return (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth(); }
async function planLoad() { if (PLAN !== undefined) return; try { const t = await bigLoad('einstiegsplan'); PLAN = t ? JSON.parse(t) : null; } catch (e) { PLAN = null; } }
function planSave() { bigSave('einstiegsplan', JSON.stringify(PLAN)); }
// Monate seit Start, in denen das Ausstiegssignal am Monatsende auf „draußen“ stand (verlängern die Frist)
function monthsOut(S, start, today) {
  if (!S || !S.trades) return 0;
  const tr = S.trades.slice().sort((a, b) => a.d < b.d ? -1 : 1); let n = 0;
  for (let d = new Date(start.getFullYear(), start.getMonth() + 1, 0); d < today; d = new Date(d.getFullYear(), d.getMonth() + 2, 0)) {
    const last = tr.filter(x => x.d <= ymd(d)).pop(); if (last && last.k === 'aus') n++;
  }
  return n;
}
function planState(P, M, liveScore) {
  const T = M.targets[P.target] || M.targets.world; const today = new Date();
  const start = P.start ? new Date(P.start + 'T12:00:00') : today;
  const invAll = Math.max(0, P.amount - (P.reserve || 0)), invLine = Math.round(invAll * (P.linePct || 0) / 100), inv = invAll - invLine;
  const nb = (P.buys || []).filter(b => b.t !== 'l'), done = nb.reduce((x, b) => x + b.a, 0), rest = Math.max(0, inv - done);
  const curM = ymd(today).slice(0, 7), boughtM = nb.filter(b => b.d.slice(0, 7) === curM).reduce((x, b) => x + b.a, 0);
  const sig = T.signals && !T.signals.error ? T.signals.state : 1;
  const mOut = monthsOut(T.signals, start, today);
  const elapsed = Math.max(0, monthsBetween(start, today));
  const left = Math.max(1, (P.max || 24) + mOut - elapsed);          // Monate inkl. laufendem bis zur Frist
  const sc = T.now.score; const base = inv / (P.base || 12);
  const r = { T, inv, done, rest, boughtM, sig, mOut, elapsed, left, sc, base, due: 0, kind: '', head: '', why: '' };
  if (rest <= 1) { r.kind = 'done'; r.head = 'Plan erfüllt – alles angelegt'; r.why = 'Ab jetzt entscheidet nur noch der Signale-Reiter, ob du draußen bleibst oder wieder einsteigst.'; return r; }
  if (sig === 0) { r.kind = 'pause'; r.head = 'Pause: Ausstiegssignal aktiv'; r.why = `Der Signale-Reiter steht für ${esc(T.name)} auf „draußen“. Solange das so ist, wird nichts angelegt – die Frist verlängert sich um jeden solchen Monat.`; return r; }
  if (sc >= 55) { r.kind = 'all'; r.due = rest; r.head = 'Rest jetzt anlegen'; r.why = `Score ${sc} liegt bei 55 oder darüber: Das Crash-Risiko ist unterdurchschnittlich – historisch war es dann am besten, den Rest auf einmal anzulegen.`; return r; }
  if (left <= 1) { r.kind = 'all'; r.due = rest; r.head = 'Frist erreicht – Rest anlegen'; r.why = `Die ${P.max || 24}-Monats-Frist ist erreicht. Länger zu warten hat historisch mehr gekostet als genützt.`; return r; }
  if (sc < 45) { r.kind = 'pause'; r.head = 'Pause: Score unter 45'; r.why = `Score ${sc}: erhöhtes Crash-Risiko. Diesen Monat nichts anlegen – noch ${left} Monate bis zur Frist, danach wird der Rest in jedem Fall angelegt.`; return r; }
  const target = Math.max(base, rest / left);
  r.due = Math.max(0, Math.min(rest, target - boughtM)); r.kind = r.due > 1 ? 'rate' : 'wait';
  r.head = r.kind === 'rate' ? 'Monatsrate anlegen' : 'Rate für diesen Monat erledigt';
  r.why = `Score ${sc} (45–55): normales Umfeld – in Raten. Ziel diesen Monat ${eur(target)}${target > base + 1 ? ' (etwas mehr als ein Zwölftel, damit die Frist reicht)' : ' (ein Zwölftel)'}, davon schon ${eur(boughtM)} angelegt.`;
  return r;
}
// Linien-Anteil: wartet auf die 200-Wochen-Linie (≈ 1000 Börsentage), höchstens lineMax Monate, danach in Raten
function lineState(P, M) {
  const T = M.targets[P.target] || M.targets.world; const today = new Date();
  const invAll = Math.max(0, P.amount - (P.reserve || 0)), inv = Math.round(invAll * (P.linePct || 0) / 100);
  if (!inv) return null;
  const lb = (P.buys || []).filter(b => b.t === 'l'), done = lb.reduce((x, b) => x + b.a, 0), rest = Math.max(0, inv - done);
  const s = S[T.sid]; let px = null, line = null;
  if (s && s.v.length >= 1000) { px = s.v[s.v.length - 1]; let sum = 0; for (let i = s.v.length - 1000; i < s.v.length; i++) sum += s.v[i]; line = sum / 1000; }
  const dist = px && line ? px / line - 1 : null;
  const start = P.start ? new Date(P.start + 'T12:00:00') : today; const elapsed = Math.max(0, monthsBetween(start, today));
  const maxM = P.lineMax || 36, band = (P.lineBand ?? 5) / 100;
  const r = { inv, done, rest, dist, line, px, elapsed, maxM, due: 0, kind: '', head: '', why: '' };
  if (rest <= 1) { r.kind = 'done'; r.head = 'Linien-Anteil vollständig angelegt'; return r; }
  if (dist != null && dist <= band) { r.kind = 'all'; r.due = rest; r.head = 'Linie erreicht – Linien-Anteil anlegen';
    r.why = `${esc(T.name)} liegt nur ${nf(dist * 100, 1)} % über seiner 200-Wochen-Linie. Darauf hat dieser Teil gewartet.`; return r; }
  if (elapsed >= maxM) { const left = Math.max(1, maxM + 12 - elapsed), curM = ymd(today).slice(0, 7);
    const boughtM = lb.filter(b => b.d.slice(0, 7) === curM).reduce((x, b) => x + b.a, 0);
    r.due = Math.max(0, Math.min(rest, Math.max(inv / 12, rest / left) - boughtM)); r.kind = r.due > 1 ? 'rate' : 'wait';
    r.head = 'Wartezeit abgelaufen – in Raten anlegen'; r.why = `Die Linie kam in ${maxM} Monaten nicht. Damit der Teil nicht ewig draußen bleibt, geht er jetzt über 12 Monate in Raten rein.`; return r; }
  r.kind = 'pause'; r.head = 'Wartet auf die 200-Wochen-Linie';
  r.why = dist == null ? 'Zu wenig Kursdaten für die 200-Wochen-Linie.' : `${esc(T.name)} liegt ${nf(dist * 100, 0)} % über der Linie (${nf(line, 0)}). Angelegt wird, sobald der Abstand unter ${nf(band * 100, 0)} % fällt – spätestens nach ${maxM} Monaten (noch ${Math.max(0, maxM - elapsed)}).`;
  return r;
}
function planLiveHint(P, M, liveScore, st) {
  if (liveScore == null || st.kind === 'done' || st.sig === 0) return '';
  const zone = s => s >= 55 ? 'all' : s < 45 ? 'pause' : 'rate'; const a = zone(st.sc), b = zone(Math.round(liveScore));
  if (a === b) return `<span class="mut">Live-Score ${Math.round(liveScore)} – keine Änderung absehbar.</span>`;
  const txt = { all: 'dann wäre morgen der Rest dran', pause: 'dann wäre morgen Pause', rate: 'dann gälte morgen wieder die Monatsrate' }[b];
  return `<span style="color:var(--warn)">Live-Score ${Math.round(liveScore)}: Hält das bis Börsenschluss, ${txt}. Entschieden wird mit dem Schlusswert.</span>`;
}
function planCard(m, M) {
  sect(m, 'Dein Einstiegsplan');
  const c = document.createElement('div'); c.className = 'card full'; c.id = 'plancard'; m.appendChild(c);
  if (PLAN === undefined) { c.innerHTML = '<div class="note">Lade Plan …</div>'; planLoad().then(() => drawPlan(c, M)); }
  else drawPlan(c, M);
}
function drawPlan(c, M) {
  const opts = Object.entries(M.targets).map(([k, t]) => `<option value="${k}">${esc(t.name)}</option>`).join('');
  if (!PLAN || c.dataset.edit === '1') {
    const P = PLAN || Object.assign({}, PLAN_DEF, { start: ymd(new Date()) });
    c.innerHTML = `<div class="hd"><div><div class="ttl">${PLAN ? 'Plan bearbeiten' : 'Einstiegsplan anlegen'}</div>
      <div class="sub">Für einen größeren Betrag, der nach und nach in den Markt soll. Die Regel kommt aus dem Test seit 1953: Score ab 55 → Rest sofort, 45–55 → Monatsraten, unter 45 → Pause, Ausstiegssignal aktiv → Pause; spätestens nach der Frist ist alles angelegt.</div></div></div>
      <div class="pform">
        <label>Gesamtbetrag (€)<input id="pf-a" type="number" step="1000" value="${P.amount}"></label>
        <label>davon Reserve, wird nicht angelegt (€)<input id="pf-r" type="number" step="1000" value="${P.reserve || 0}"></label>
        <label>Richtwert (Score und Signal von)<select id="pf-t">${opts}</select></label>
        <label>Start<input id="pf-s" type="date" value="${P.start || ymd(new Date())}"></label>
        <label>Raten (Monate)<input id="pf-b" type="number" min="1" max="60" value="${P.base || 12}"></label>
        <label>spätestens alles nach (Monaten)<input id="pf-m" type="number" min="1" max="60" value="${P.max || 24}"></label>
        <label>Linien-Anteil: wartet auf die 200-Wochen-Linie (%)<input id="pf-lp" type="number" min="0" max="100" step="5" value="${P.linePct || 0}"></label>
        <label>Linien-Anteil: höchstens warten (Monate)<input id="pf-lm" type="number" min="1" max="120" value="${P.lineMax || 36}"></label>
        <label>Linie gilt als erreicht bei Abstand unter (%)<input id="pf-lb" type="number" min="0" max="20" step="1" value="${P.lineBand ?? 5}"></label>
      </div>
      <div class="pbtn"><button id="pf-save" class="pri">Speichern</button>${PLAN ? '<button id="pf-cancel">Abbrechen</button><button id="pf-del" class="danger">Plan löschen</button>' : ''}</div>
      <div class="note">Die Reserve ist das, was du in den nächsten Jahren für den Haushalt brauchen könntest – sie gehört aufs Tagesgeld oder in einen Geldmarktfonds, nicht in Aktien. Der Plan wird nur auf diesem Mac gespeichert.</div>`;
    c.querySelector('#pf-t').value = P.target in M.targets ? P.target : 'world';
    c.querySelector('#pf-save').onclick = () => {
      const v = id => c.querySelector(id).value;
      PLAN = Object.assign({}, P, { amount: +v('#pf-a') || 0, reserve: +v('#pf-r') || 0, target: v('#pf-t'), start: v('#pf-s'), base: Math.max(1, +v('#pf-b') || 12), max: Math.max(1, +v('#pf-m') || 24), linePct: Math.max(0, Math.min(100, +v('#pf-lp') || 0)), lineMax: Math.max(1, +v('#pf-lm') || 36), lineBand: Math.max(0, +v('#pf-lb')), buys: P.buys || [] });
      planSave(); c.dataset.edit = '0'; drawPlan(c, M);
    };
    if (PLAN) { c.querySelector('#pf-cancel').onclick = () => { c.dataset.edit = '0'; drawPlan(c, M); };
      c.querySelector('#pf-del').onclick = () => { if (c.dataset.del !== '1') { c.dataset.del = '1'; c.querySelector('#pf-del').textContent = 'Wirklich löschen?'; return; } PLAN = null; planSave(); c.dataset.edit = '0'; c.dataset.del = '0'; drawPlan(c, M); }; }
    return;
  }
  const P = PLAN; const live = liveModel(M.targets[P.target] || M.targets.world); const st = planState(P, M, live && live.score);
  const ls = lineState(P, M);
  const totInv = st.inv + (ls ? ls.inv : 0), totDone = st.done + (ls ? ls.done : 0);
  const pct = totInv ? totDone / totInv * 100 : 0;
  const colOf = k => ({ all: C.up, rate: C.s1, wait: C.sec, pause: C.warn, done: C.up }[k]);
  const col = colOf(st.kind);
  c.innerHTML = `<div class="hd"><div><div class="ttl">Einstiegsplan · ${eur(P.amount)}${P.reserve ? ` <small>(${eur(P.reserve)} Reserve)</small>` : ''}</div>
      <div class="sub">Richtwert ${esc(st.T.name)} · Start ${fmtDate(monthDay(P.start))} · Monat ${st.elapsed + 1} · noch ${st.left} Monat(e) bis zur Frist${st.mOut ? ` (um ${st.mOut} verlängert wegen Ausstiegssignal)` : ''}</div></div>
      <button id="pl-edit" class="ghost">Bearbeiten</button></div>
    <div class="plan">
      <div class="pnow" style="border-color:${col}">
        <div class="lbl">Heute${ls ? ` · Hauptteil ${eur(st.inv)}` : ''}</div>
        <div class="phead" style="color:${col}">${st.head}</div>
        ${st.due > 1 ? `<div class="big" style="font-size:30px">${eur(st.due)}</div>` : ''}
        <div class="pwhy">${st.why}</div>
        <div class="plive" id="pl-live">${planLiveHint(P, M, live && live.score, st)}</div>
        ${ls ? `<div class="pline" style="border-color:${colOf(ls.kind)}"><div class="lbl">Linien-Anteil · ${eur(ls.inv)} · angelegt ${eur(ls.done)}</div>
          <div class="phead" style="color:${colOf(ls.kind)};font-size:15px">${ls.head}</div>${ls.due > 1 ? `<div class="big" style="font-size:22px">${eur(ls.due)}</div>` : ''}<div class="pwhy">${ls.why}</div></div>` : ''}
      </div>
      <div>
        <div class="lbl">Fortschritt</div>
        <div class="pprog"><i style="width:${Math.min(100, pct).toFixed(1)}%"></i></div>
        <div class="pnums"><span>angelegt <b>${eur(totDone)}</b></span><span>offen <b>${eur(totInv - totDone)}</b></span><span>${nf(pct, 0)} %</span></div>
        <div class="paddr"><input id="pl-amt" type="number" step="100" value="${Math.round(st.due || (ls && ls.due) || 0) || ''}" placeholder="Betrag"><input id="pl-d" type="date" value="${ymd(new Date())}">${ls ? `<select id="pl-t"><option value="n">Hauptteil</option><option value="l"${!(st.due > 1) && ls.due > 1 ? ' selected' : ''}>Linien-Anteil</option></select>` : ''}<button id="pl-add" class="pri">Als gekauft eintragen</button></div>
        ${(P.buys || []).length ? `<table class="t" style="margin-top:8px"><tr><th>Datum</th><th>Betrag</th>${ls ? '<th>Teil</th>' : ''}<th></th></tr>${P.buys.slice().reverse().map((b, i) => `<tr><td>${fmtDate(monthDay(b.d))}</td><td>${eur(b.a)}</td>${ls ? `<td class="mut">${b.t === 'l' ? 'Linie' : 'Haupt'}</td>` : ''}<td><button class="x" data-i="${P.buys.length - 1 - i}" title="Eintrag entfernen">×</button></td></tr>`).join('')}</table>` : '<div class="note">Noch nichts eingetragen. Trag jede Ausführung ein – daraus rechnet der Plan, was noch offen ist.</div>'}
      </div>
    </div>
    <div class="note">Regel (getestet für jeden Startmonat seit 1953, 10 Jahre Horizont): Endwert im Median wie „sofort alles“ oder leicht besser, aber nur halb so oft mehr als 20 % Buchverlust in den ersten drei Jahren. Vor einem Crash <i>nach</i> dem Einstieg schützt keine Einstiegsregel – dafür ist der Ausstieg im Signale-Reiter da. Entschieden wird mit dem Schluss-Score; der Live-Score zeigt nur, was sich anbahnt. ${ls ? 'Linien-Anteil: Bei hohem CAPE (über +1,5 σ) kam der Kurs seit 1900 in 8 von 9 Phasen nach 16–43 Monaten an die 200-Wochen-Linie zurück; die Ausnahme (1989–2001) dauerte 11 Jahre – deshalb die Höchstwartezeit. ' : ''}Kein Anlagerat.</div>`;
  c.querySelector('#pl-edit').onclick = () => { c.dataset.edit = '1'; drawPlan(c, M); };
  c.querySelector('#pl-add').onclick = () => { const a = +c.querySelector('#pl-amt').value, d = c.querySelector('#pl-d').value; if (!(a > 0) || !d) return;
    const tSel = c.querySelector('#pl-t'); const t = tSel ? tSel.value : 'n';
    P.buys = (P.buys || []).concat([{ d, a, t }]).sort((x, y) => x.d < y.d ? -1 : 1); planSave(); drawPlan(c, M); };
  c.querySelectorAll('button.x').forEach(b => b.onclick = () => { P.buys.splice(+b.dataset.i, 1); planSave(); drawPlan(c, M); });
}
function refreshPlanLive() {
  const el = document.getElementById('pl-live'); const M = DATA && DATA.model; if (!el || !PLAN || !M) return;
  const live = liveModel(M.targets[PLAN.target] || M.targets.world); const st = planState(PLAN, M, live && live.score);
  el.innerHTML = planLiveHint(PLAN, M, live && live.score, st);
}
function riskCell(v) {
  if (v == null) return '–';
  const c = v >= 40 ? C.crit : v >= 25 ? C.serious : v >= 15 ? C.warn : C.sec;
  return `<span style="color:${c};font-weight:600">${nf(v, 0)} %</span>`;
}
function analogSection(m, T) {
  const A = T.analogs; if (!A || !A.items || !A.items.length) return;
  sect(m, 'Ähnliche Momente in der Vergangenheit');
  const c = document.createElement('div'); c.className = 'card full';
  const PN = { bewertung: 'Bew.', gewinne: 'Gew.', trend: 'Trend', schwankung: 'Schw.', breite: 'Breite', konjunktur: 'Konj.', finanzen: 'Fin.', stimmung: 'Stimm.' };
  const NOWP = Object.fromEntries(T.now.pillars.map(p => [p.id, p.score]));
  c.innerHTML = `<div class="hd"><div><div class="ttl">Die ${A.n} ähnlichsten Monate seit ${T.since.slice(0, 4)}</div>
    <div class="sub">Gesucht wird über alle Komponenten der acht Säulen gleichzeitig – nicht nur über den Score. Zwischen zwei Treffern liegen mindestens 18 Monate, damit es verschiedene Episoden sind. Darunter der Verlauf des ${esc(T.name)} in den 36 Monaten danach (Start = 100).</div></div></div>
    <div class="anasum">
      <div><div class="lbl">nach 12 Monaten (Median)</div><div class="big" style="font-size:22px">${fmtPct(A.f12)}</div></div>
      <div><div class="lbl">nach 24 Monaten (Median)</div><div class="big" style="font-size:22px">${fmtPct(A.f24)}</div></div>
      <div><div class="lbl">im Plus nach 12 M.</div><div class="big" style="font-size:22px">${A.pos12 ?? '–'} %</div></div>
      <div><div class="lbl">Rückgang ≥ ${Math.round(T.crash * 100)} % im 1. Jahr</div><div class="big" style="font-size:22px">${riskCell(A.crash12)}</div><div class="mut" style="font-size:11px">normal: ${A.crash_base} %</div></div>
    </div>
    <div class="legend" id="alg"></div><div class="chart tall" id="ach"></div>
    <table class="t ana" style="margin-top:10px"><tr><th>Monat</th><th>Ähnlichkeit</th><th>Score</th>${Object.keys(PN).map(k => `<th>${PN[k]}</th>`).join('')}<th>6 M.</th><th>12 M.</th><th>24 M.</th><th>tiefster Stand 12 M.</th><th>24 M.</th></tr>
    <tr class="hl"><td>heute</td><td></td><td>${T.now.score}</td>${Object.keys(PN).map(k => `<td>${NOWP[k] ?? '–'}</td>`).join('')}<td colspan="5" class="mut" style="font-family:inherit">?</td></tr>
    ${A.items.map((a, i) => `<tr class="row" data-i="${i}"><td><i class="sw" style="background:${SER[i % 8]}"></i>${esc(a.name)}</td><td>${a.sim} %</td><td>${a.score}</td>${Object.keys(PN).map(k => `<td>${a.pillars[k] ?? '–'}</td>`).join('')}<td>${fmtPct(a.f6)}</td><td>${fmtPct(a.f12)}</td><td>${fmtPct(a.f24)}</td><td>${fmtPct(a.dd12)}</td><td>${fmtPct(a.dd24)}</td></tr>`).join('')}</table>
    <div class="note">Säulenwerte 0–100, 50 = neutral. Eine Analogie ist kein Fahrplan: Ähnliche Ausgangslagen entwickelten sich oft sehr unterschiedlich – entscheidend ist die Streuung, nicht der Durchschnitt. Klick auf eine Zeile hebt ihren Verlauf hervor.</div>`;
  m.appendChild(c);
  queueMicrotask(() => {
    const el = c.querySelector('#ach');
    const base = 0; // Zeitachse: Monate nach dem Analog-Monat als künstliche Tage
    const ch = baseChart(el, { fmt: p => nf(p, 0) });
    ch.applyOptions({ timeScale: { tickMarkFormatter: t => `${Math.round(t / DAY / 30.44)} M.` }, localization: { timeFormatter: t => `Monat ${Math.round(t / DAY / 30.44)}`, priceFormatter: p => nf(p, 0) } });
    const T0 = 0, step = 30.44 * DAY;
    const lines = A.items.map((a, i) => {
      const l = ch.addLineSeries({ color: SER[i % 8], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerRadius: 3, priceFormat: pf(0) });
      l.setData(a.path.map((v, h) => v == null ? null : { time: Math.round(T0 + h * step), value: v }).filter(Boolean));
      return l;
    });
    const md = ch.addLineSeries({ color: C.txt, lineWidth: 3, priceLineVisible: false, lastValueVisible: true, priceFormat: pf(0) });
    md.setData(A.median_path.map((v, h) => v == null ? null : { time: Math.round(T0 + h * step), value: v }).filter(Boolean));
    md.createPriceLine({ price: 100, color: C.mut, lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    md.createPriceLine({ price: 100 * (1 - T.crash), color: C.serious, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `−${Math.round(T.crash * 100)} %` });
    ch.timeScale().fitContent();
    const lg = c.querySelector('#alg');
    const draw = h => {
      lg.innerHTML = `<span><i style="border-color:${C.txt};border-top-width:3px"></i>Median<b>${h == null ? '' : nf(A.median_path[h], 0)}</b></span>` +
        A.items.map((a, i) => `<span><i style="border-color:${SER[i % 8]}"></i>${esc(a.name)}${h == null || a.path[h] == null ? '' : `<b>${nf(a.path[h], 0)}</b>`}</span>`).join('') +
        `<span class="d">${h == null ? '36 Monate danach' : 'Monat ' + h}</span>`;
    };
    draw(null);
    ch.subscribeCrosshairMove(p => draw(p && p.time != null ? Math.round(p.time / step) : null));
    let sel = null;
    c.querySelectorAll('tr.row').forEach(r => r.onclick = () => {
      const i = +r.dataset.i; sel = sel === i ? null : i;
      lines.forEach((l, j) => l.applyOptions({ lineWidth: sel === null ? 1 : j === sel ? 3 : 1, color: sel === null || j === sel ? SER[j % 8] : 'rgba(120,126,140,.25)' }));
      c.querySelectorAll('tr.row').forEach(x => x.classList.toggle('hl', sel !== null && +x.dataset.i === sel));
    });
  });
}
function episodeSection(m, T) {
  const E = T.episodes; if (!E || !E.length) return;
  sect(m, 'Große Einbrüche – hat das Modell gewarnt?');
  const c = document.createElement('div'); c.className = 'card full';
  const mn = p => fmtDate(monthDay(p));
  c.innerHTML = `<div class="hd"><div><div class="ttl">Alle Rückgänge des ${esc(T.name)} von mindestens ${Math.round(T.episode * 100)} % seit ${T.since.slice(0, 4)}</div>
    <div class="sub">Tagesschlusskurse. „Warnung“ = erster Tag ab 6 Monate vor dem Hoch bis zum Tief, an dem der Score unter 45 fiel. Rechts: größter Verlust im selben Zeitraum, wenn man der jeweiligen Regel gefolgt wäre.</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th>Hoch</th><th>Tief</th><th>Verlust</th><th>Dauer</th><th>Score am Hoch</th><th>Wahrsch. am Hoch</th><th>Warnung</th><th>da schon verloren</th><th>Modell-Quote</th><th>Trendregel</th><th>Schutzregel</th></tr>
    ${E.map(e => `<tr><td>${mn(e.peak)}</td><td>${mn(e.trough)}</td><td>${fmtPct(e.depth, 0)}</td><td>${e.months} M.</td><td>${e.s_peak ?? '–'}</td><td>${e.p_peak == null ? '–' : e.p_peak + ' %'}</td>
      <td style="font-family:inherit">${e.warn ? mn(e.warn) : '<span style="color:var(--serious)">keine</span>'}</td><td>${e.lost_at_warn == null ? '–' : fmtPct(e.lost_at_warn, 0)}</td>
      <td>${fmtPct(e.dd_score, 0)}</td><td>${fmtPct(e.dd_trend, 0)}</td><td>${fmtPct(e.dd_schutz, 0)}</td></tr>`).join('')}</table>
    <div class="note">Schnelle Schocks wie 1987 oder 2020 kündigen sich in Monatsdaten kaum an – das Modell hilft vor allem bei langen Abwärtsphasen wie 1973/74, 2000–2002 und 2007–2009, die den größten Schaden anrichten.</div>`;
  m.appendChild(c);
}
function fmtPct(v, d = 1) { if (v == null) return '–'; const c = v > 0 ? 'up' : v < 0 ? 'down' : 'flat'; return `<span class="${c}">${v > 0 ? '+' : ''}${nf(v, d)} %</span>`; }
function fmtR(v) { if (v == null) return '–'; return `<span style="color:${Math.abs(v) < 0.1 ? C.mut : v > 0 ? C.up : C.down}">${v > 0 ? '+' : ''}${nf(v, 2)}</span>`; }
function ruleCard(M) {
  const c = document.createElement('div'); c.className = 'card';
  const r = M.rule || {}; const rows = [['world', 'MSCI World'], ['spx', 'S&P 500']].filter(([k]) => r[k]);
  c.innerHTML = `<div class="hd"><div><div class="ttl">Deine Einstiegsregel</div><div class="sub">Kurs an oder unter der 200-Wochen-Linie, dann kaufen, sobald das CAPE wieder steigt.</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th>Index</th><th>Abstand zur 200-W.-Linie</th><th>zuletzt berührt</th></tr>
    ${rows.map(([k, n]) => `<tr><td>${n}</td><td>${fmtPct(r[k].dist)}</td><td>${r[k].lastTouch ? fmtDate(Math.floor(new Date(r[k].lastTouch) / 864e5)) : '–'}</td></tr>`).join('')}</table>
    <div class="flag ${r.signalScore >= 70 ? 'off' : 'on'}" style="margin-top:10px"><span class="fi">${r.signalScore >= 70 ? '✓' : '…'}</span><div>Einstiegssignal der Markt-App: <b>${r.signalScore != null ? r.signalScore + ' / 100' : '–'}</b><div class="fd">ab 70 Kaufzone, 100 = bestätigte Wende</div></div></div>
    <div class="note">Deine Regel ist bewusst streng: Sie wartet auf echte Schwächephasen. Das Modell oben bewertet dagegen jede Lage und sagt, wie günstig oder ungünstig sie im Vergleich zur Geschichte war.</div>`;
  return c;
}


// ---------- Signale (Ein-/Ausstieg, eigener Reiter zum Vergleich mit der Einschätzung)
function secSignale(m) {
  const M = DATA.model;
  head(m, 'Signale', 'Klare Ein- und Ausstiegssignale statt Score. Sicherheit hat Vorrang: raus erst bei Bestätigung, wieder rein bewusst spät. Die Regel wird jedes Jahr neu festgelegt – nur mit den jeweils letzten 35 Jahren S&P 500 – und gilt dann unverändert für dieses Jahr. Alles ab 1990 ist damit ein echter Vorwärtstest.');
  if (!M || !M.signal_params || !M.targets) { m.insertAdjacentHTML('beforeend', '<div class="card"><div class="note">Signale werden mit der nächsten Datenaktualisierung berechnet.</div></div>'); return; }
  if (!M.targets[TGT] || !M.targets[TGT].signals || M.targets[TGT].signals.error) TGT = 'world';
  const Pp = M.signal_params, Cal = M.signal_cal || {};
  const rule = `<b>Aussteigen</b>, wenn der Score an ${Pp.exit_n} Börsentagen in Folge unter ${Pp.exit_s} liegt${Pp.exit_trend ? ' und der Kurs unter seiner 10-Monats-Linie' : ''}. <b>Wieder einsteigen</b>, wenn der Score an ${Pp.entry_n} Börsentagen in Folge mindestens ${Pp.entry_s} erreicht und der Kurs über seiner 10-Monats-Linie liegt. Nach jedem Wechsel mindestens 20 Börsentage Pause.`;
  const rc = document.createElement('div'); rc.className = 'card full';
  rc.innerHTML = `<div class="hd"><div><div class="ttl">Die Regel</div><div class="sub">${rule}</div></div></div>
    <div class="note">Aktuelle Regel, ausgewählt aus ${Cal.n_tested || '–'} Varianten mit dem S&P 500 ${Cal.from ? Cal.from.slice(0, 4) : ''}–${Cal.to ? Cal.to.slice(0, 4) : ''}: kleinster größter Verlust bei höchstens 2,5 Ausstiegen pro Jahrzehnt und höchstens 1 Prozentpunkt weniger Rendite als Kaufen und Halten.</div>
    ${M.signal_roll ? `<details class="roll"><summary>Wie sich die Regel über die Jahre verändert hat</summary><table class="t" style="margin-top:6px"><tr><th>gültig</th><th>gelernt aus</th><th>Ausstieg</th><th>Wiedereinstieg</th></tr>${(() => {
      const ks = Object.keys(M.signal_roll).sort(); const rows = []; let cur = null;
      ks.forEach(k => { const p = M.signal_roll[k].p; const sig_ = JSON.stringify(p); if (!cur || cur.sig !== sig_) { cur = { sig: sig_, a: k, b: k, p, from: M.signal_roll[k].from }; rows.push(cur); } else cur.b = k; });
      return rows.map(r => `<tr><td>${r.a}${r.b !== r.a ? '–' + r.b : ''}</td><td class="mut">35 Jahre davor</td><td>Score &lt; ${r.p.exit_s}, ${r.p.exit_n} Tage${r.p.exit_trend ? ' + unter Linie' : ''}</td><td>Score ≥ ${r.p.entry_s}, ${r.p.entry_n} Tage + über Linie</td></tr>`).join(''); })()}</table></details>` : ''}</div>`;
  m.appendChild(rc);

  const ov = document.createElement('div'); ov.className = 'card full';
  const condTxt = (S) => S.state === 1
    ? `Ausstieg erst nach ${S.need} Tagen Score &lt; ${Pp.exit_s}${Pp.exit_trend ? ' + Kurs unter Linie' : ''} – erfüllt seit ${S.run} Tagen`
    : `Wiedereinstieg erst nach ${S.need} Tagen Score ≥ ${Pp.entry_s} + Kurs über Linie – erfüllt seit ${S.run} Tagen`;
  ov.innerHTML = `<div class="hd"><div><div class="ttl">Alle Indizes</div><div class="sub">Stand nach dem letzten Tagesschluss. Kennzahlen ab 1990 – jedes Jahr mit der Regel, die damals aus den 35 Jahren davor festgelegt worden wäre. Klick auf eine Zeile zeigt Details.</div></div></div>
    <table class="t ov" style="margin-top:6px"><tr><th>Index</th><th>Signal</th><th>seit</th><th>Score</th><th>Bedingung</th><th>Rendite p.a.<br>Signal / Halten</th><th>größter Verlust<br>Signal / Halten</th><th>Ausstiege<br>pro Jahrzehnt</th><th>davon<br>teurer zurück</th></tr>
    ${Object.entries(M.targets).filter(([k, t]) => t.signals && !t.signals.error).map(([k, t]) => { const S = t.signals, O = S.oos || S.all;
      return `<tr class="row ${k === TGT ? 'hl' : ''}" data-t="${k}"><td>${esc(t.name)}</td>
      <td style="font-family:inherit">${S.state === 1 ? '<span class="badge good">Investiert</span>' : '<span class="badge crit">Draußen</span>'}</td>
      <td>${fmtDate(monthDay(S.since))}</td><td>${S.score}</td><td style="font-family:inherit;white-space:normal;font-size:11.5px;color:var(--sec);max-width:260px">${condTxt(S)}</td>
      <td>${fmtPct(O.cagr)} / ${fmtPct(O.bh_cagr)}</td><td>${fmtPct(O.mdd, 0)} / ${fmtPct(O.bh_mdd, 0)}</td><td>${nf(O.per_decade ?? 0, 1)}</td>
      <td>${S.false} von ${S.false + S.useful}</td></tr>`; }).join('')}</table>
    <div class="note">„Teurer zurück“ = Ausstieg, nach dem der Wiedereinstieg teurer war als der Ausstieg – echte Fehlalarme, aber auch richtige Ausstiege mit spätem Wiedereinstieg (z. B. 2020). Das Signal wird mit den Tagesdaten der Pipeline berechnet (alle 30 Minuten während der US-Handelszeit), nicht mit jedem Live-Kurs – ein Wechsel braucht ohnehin mehrere Tage Bestätigung.</div>`;
  ov.querySelectorAll('tr.row').forEach(r => r.onclick = () => { TGT = r.dataset.t; store('tgt', TGT); renderSection(); });
  m.appendChild(ov);

  const T = M.targets[TGT], S = T.signals;
  if (!S || S.error) return;
  sect(m, esc(T.name) + ' im Detail');
  // Chart mit Wechseln
  const ch = document.createElement('div'); ch.className = 'card full';
  ch.innerHTML = `<div class="hd"><div><div class="ttl">${esc(T.name)} mit allen Ein- und Ausstiegen seit ${S.all.from.slice(0, 4)}</div><div class="sub">Rot ▼ = Ausstieg, grün ▲ = Wiedereinstieg. Logarithmisch, Wochenwerte. Darunter: was aus 100 geworden wäre.</div></div></div>
    <div class="legend" id="sglg"></div><div class="chart tall"></div><div class="chart" style="height:220px"></div>
    <table class="t" style="margin-top:8px"><tr><th>Zeitraum</th><th>Rendite p.a. Signal</th><th>Halten</th><th>größter Verlust Signal</th><th>Halten</th><th>Ausstiege</th><th>Ø investiert</th></tr>
    ${[['vor 1990 (Regel von 1990)', S.is], ['Vorwärtstest (ab 1990)', S.oos], ['gesamt', Object.assign({ exits: S.n_trades ? Math.ceil(S.n_trades / 2) : 0 }, S.all)]].filter(x => x[1]).map(([n, O]) =>
      `<tr class="${n.startsWith('Vorwärts') ? 'hl' : ''}"><td>${n} <span class="mut">${O.from ? O.from.slice(0, 4) : ''}${O.to ? '–' + O.to.slice(0, 4) : ''}</span></td><td>${fmtPct(O.cagr)}</td><td>${fmtPct(O.bh_cagr)}</td><td>${fmtPct(O.mdd, 0)}</td><td>${fmtPct(O.bh_mdd, 0)}</td><td>${O.exits ?? '–'}</td><td>${O.invested} %</td></tr>`).join('')}</table>
    <div class="note">Kursrenditen ohne Dividenden, nicht investiertes Geld im Geldmarkt, ohne Steuern und Kosten. Wichtig: Jeder Ausstieg ist in Deutschland ein steuerpflichtiger Verkauf – bei wenigen Wechseln pro Jahrzehnt fällt das weniger ins Gewicht, verschwindet aber nicht.</div>`;
  m.appendChild(ch);
  queueMicrotask(() => {
    const els = ch.querySelectorAll('.chart'); const H = T.hist; const ds = H.days.map(monthDay);
    const a = baseChart(els[0], { log: true, fmt: p => nf(p, 0) });
    const ps = a.addLineSeries({ color: C.s1, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, priceFormat: pf(0) });
    const data = ds.map((d, i) => ({ time: d * DAY, value: H.price[i] })).filter(x => x.value != null);
    ps.setData(data);
    const times = data.map(x => x.time);
    const snap = t => { let lo = 0, hi = times.length - 1; while (lo < hi) { const mid = (lo + hi) >> 1; if (times[mid] < t) lo = mid + 1; else hi = mid; } return times[lo]; };
    ps.setMarkers(S.trades.map(x => ({ time: snap(monthDay(x.d) * DAY), position: x.k === 'aus' ? 'aboveBar' : 'belowBar', color: x.k === 'aus' ? C.crit : C.good, shape: x.k === 'aus' ? 'arrowDown' : 'arrowUp', size: 1 }))
      .filter((v, i, arr) => arr.findIndex(y => y.time === v.time) === i).sort((x, y) => x.time - y.time));
    a.timeScale().fitContent();
    const b = baseChart(els[1], { log: true, fmt: p => nf(p, 0) });
    const qd = S.eq.days.map(monthDay);
    const l1 = b.addLineSeries({ color: C.s3, lineWidth: 2, priceLineVisible: false, priceFormat: pf(0) });
    l1.setData(qd.map((d, i) => ({ time: d * DAY, value: S.eq.sig[i] * 100 })));
    const l2 = b.addLineSeries({ color: C.s2, lineWidth: 1.5, priceLineVisible: false, priceFormat: pf(0) });
    l2.setData(qd.map((d, i) => ({ time: d * DAY, value: S.eq.bh[i] * 100 })));
    b.timeScale().fitContent();
    const lg = ch.querySelector('#sglg');
    lg.innerHTML = `<span><i style="border-color:${C.s1}"></i>${esc(T.name)}</span><span style="color:${C.crit}">▼ Ausstieg</span><span style="color:${C.good}">▲ Wiedereinstieg</span><span><i style="border-color:${C.s3}"></i>Signal (unten)</span><span><i style="border-color:${C.s2}"></i>Kaufen und halten (unten)</span>`;
  });
  // Bilanz je Crash
  const ep = document.createElement('div'); ep.className = 'card full';
  ep.innerHTML = `<div class="hd"><div><div class="ttl">Bilanz je großem Einbruch (≥ 20 %)</div><div class="sub">Wie weit unter dem Hoch kam der Ausstieg, wie weit über dem Tief der Wiedereinstieg? Hellere Zeilen: Zeitraum, mit dem die Regel festgelegt wurde.</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th>Hoch</th><th>Tief</th><th>Verlust Index</th><th>Ausstieg</th><th>unter Hoch</th><th>Wiedereinstieg</th><th>über Tief</th><th>Verlust mit Signal</th></tr>
    ${S.episodes.map(e => `<tr style="${e.oos ? '' : 'opacity:.6'}"><td>${fmtDate(monthDay(e.peak))}</td><td>${fmtDate(monthDay(e.trough))}</td><td>${fmtPct(e.depth, 0)}</td>
      <td style="font-family:inherit">${e.exit ? fmtDate(monthDay(e.exit)) + (e.already_out ? ' <span class="mut">(schon vorher)</span>' : '') : '<span style="color:var(--serious)">keiner</span>'}</td>
      <td>${e.exit_vs_peak == null ? '–' : e.already_out ? '<span class="up">vorher raus</span>' : fmtPct(e.exit_vs_peak)}</td>
      <td style="font-family:inherit">${e.entry ? fmtDate(monthDay(e.entry)) : e.exit ? '<span class="mut">noch draußen</span>' : '–'}</td><td>${e.entry_vs_trough == null ? '–' : fmtPct(e.entry_vs_trough)}</td>
      <td>${fmtPct(e.strat_dd, 0)}</td></tr>`).join('')}</table>
    <div class="note">„Keiner“ heißt: Der Einbruch war zu schnell oder zu flach für die Bestätigungsregel – der volle Verlust wurde mitgenommen. Der Wiedereinstieg liegt oft deutlich über dem Tief: Das ist der Preis dafür, nicht in Zwischenerholungen einzusteigen.</div>`;
  m.appendChild(ep);
  // alle Wechsel
  const tr = document.createElement('div'); tr.className = 'card full';
  tr.innerHTML = `<div class="hd"><div><div class="ttl">Alle Ausstiege – hat es sich gelohnt?</div><div class="sub">${S.useful} lohnten sich (im Median ${S.useful_gain == null ? '–' : nf(S.useful_gain, 1) + ' %'} günstiger wieder eingestiegen), ${S.false} kosteten Geld (im Median ${S.false_cost == null ? '–' : nf(S.false_cost, 1) + ' %'} teurer wieder eingestiegen). Die Ausstiege, die sich lohnten, waren die großen Crashs – sie gleichen viele kleine Kosten aus. Das ist die Versicherungsprämie.</div></div></div>
    <table class="t" style="margin-top:6px"><tr><th>Ausstieg</th><th>Wiedereinstieg</th><th>Kurs bei Wiedereinstieg ggü. Ausstieg</th><th>tiefster Stand dazwischen</th><th>Ergebnis</th></tr>
    ${S.pairs.slice().reverse().map(x => `<tr><td>${fmtDate(monthDay(x.aus))}</td><td>${x.ein ? fmtDate(monthDay(x.ein)) : '<span class="mut">noch draußen</span>'}</td>
      <td>${x.chg == null ? '–' : `<span class="${x.chg < 0 ? 'up' : 'down'}">${x.chg > 0 ? '+' : ''}${nf(x.chg, 1)} %</span>`}</td>
      <td>${fmtPct(x.low)}</td><td style="font-family:inherit">${x.chg == null ? '–' : x.chg < 0 ? '<span class="badge good">lohnte sich</span>' : '<span class="badge warn">kostete</span>'}</td></tr>`).join('')}</table>`;
  m.appendChild(tr);
  m.insertAdjacentHTML('beforeend', `<div class="note" style="margin-top:14px;max-width:900px">Vergleich zur Einschätzung: Dort gibt es eine stufenlose Lagebewertung und eine Wahrscheinlichkeit, hier eine Ja/Nein-Entscheidung mit Bestätigungsregeln. Beide nutzen denselben Score. Kein Anlagerat – ein Regelwerk, getestet an der Vergangenheit.</div>`);
}
// ---------- Zusammenhänge
let MX = { f: load('mx_f') || 'w', d: +(load('mx_d') || 730) };
let CMP = { a: load('cmp_a') || 'y10', b: load('cmp_b') || 'ndx', mode: load('cmp_mode') || 'auto', win: +(load('cmp_win') || 0) };

function matrixCard() {
  const c = document.createElement('div'); c.className = 'card full';
  const ids = MATRIX.filter(id => S[id]); const nd = newestDay(); const from = nd - MX.d;
  const M = ids.map(a => ids.map(b => a === b ? 1 : corr(a, b, MX.f, from)));
  const WIN = [['3 M.', 92], ['6 M.', 183], ['1 J.', 365], ['2 J.', 730], ['5 J.', 1826], ['10 J.', 3653]];
  c.innerHTML = `<div class="hd"><div><div class="ttl">Korrelationsmatrix</div><div class="sub">Wie stark sich die Veränderungen zweier Reihen gemeinsam bewegen: +1 gleichläufig, −1 gegenläufig, 0 kein Zusammenhang. Zinsen über ihre Veränderung, Preise über Renditen.</div></div></div>
    <div class="ctl"><label>Zeitraum <span class="seg" id="mxd">${WIN.map(([n, d]) => `<button data-d="${d}" class="${d === MX.d ? 'on' : ''}">${n}</button>`).join('')}</span></label>
    <label>Basis <span class="seg" id="mxf"><button data-f="d" class="${MX.f === 'd' ? 'on' : ''}">Tage</button><button data-f="w" class="${MX.f === 'w' ? 'on' : ''}">Wochen</button></span></label></div>
    <div class="mx"><table><tr><th></th>${ids.map(id => `<th class="c"><div class="vh"><span>${esc(short2(id))}</span></div></th>`).join('')}</tr>
    ${ids.map((a, i) => `<tr><th class="r">${esc(short2(a))}</th>${ids.map((b, j) => i === j ? '<td class="self"></td>' : `<td data-i="${i}" data-j="${j}" style="background:${M[i][j] == null ? 'transparent' : heatColor(M[i][j], 1)}">${M[i][j] == null ? '' : nf(M[i][j] * 10, 0)}</td>`).join('')}</tr>`).join('')}</table></div>
    <div class="scale">−1 <span class="bar" style="background:linear-gradient(90deg,${heatColor(-1, 1)},${heatColor(0, 1)},${heatColor(1, 1)})"></span> +1 · Zahlen = Korrelation × 10 · Klick öffnet das Paar im Vergleich${MX.f === 'd' ? ' · Achtung: Börsen in Asien/Europa schließen vor den USA – Wochenbasis ist bei Tageswerten fairer.' : ''}</div>`;
  c.querySelector('#mxd').onclick = e => { const b = e.target.closest('button'); if (!b) return; MX.d = +b.dataset.d; store('mx_d', MX.d); c.replaceWith(matrixCard()); };
  c.querySelector('#mxf').onclick = e => { const b = e.target.closest('button'); if (!b) return; MX.f = b.dataset.f; store('mx_f', MX.f); c.replaceWith(matrixCard()); };
  c.querySelectorAll('td[data-i]').forEach(td => {
    const a = ids[+td.dataset.i], b = ids[+td.dataset.j], v = M[+td.dataset.i][+td.dataset.j];
    td.onmousemove = e => showTip(e, `${esc(S[a].name)} ↔ ${esc(S[b].name)}<br>Korrelation <b>${v == null ? '–' : nf(v, 2)}</b>`);
    td.onmouseleave = hideTip; td.onclick = () => { hideTip(); openCompare(a, b); };
  });
  return c;
}
const SHORT2 = { real10: 'Realzins 10J', breakeven: 'Inflationserw.', curve10_2: 'Kurve 10−2', hyg_ief: 'Kredit HYG/IEF', tlt: 'Anleihen 20J+', cu_au: 'Kupfer/Gold', em: 'Schwellenl.', y2: 'US 2J', y10: 'US 10J', natgas: 'Erdgas' };
const short2 = id => SHORT2[id] || SHORT[id] || S[id].name;

function unusualList(n) {
  const ids = MATRIX.filter(id => S[id]); const nd = newestDay(); const out = [];
  for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
    const a = ids[i], b = ids[j];
    const now = corr(a, b, 'w', nd - 365), long = corr(a, b, 'w', nd - 3653);
    if (now == null || long == null) continue;
    const d = now - long;
    if (Math.abs(d) >= 0.35 && (Math.abs(long) >= 0.25 || Math.abs(now) >= 0.35)) out.push({ a, b, now, long, d });
  }
  out.sort((x, y) => Math.abs(y.d) - Math.abs(x.d));
  const cnt = {}, res = []; // jede Reihe höchstens zweimal, sonst dominiert eine einzelne
  for (const r of out) { if ((cnt[r.a] || 0) >= 2 || (cnt[r.b] || 0) >= 2) continue; cnt[r.a] = (cnt[r.a] || 0) + 1; cnt[r.b] = (cnt[r.b] || 0) + 1; res.push(r); if (res.length >= n) break; }
  return res;
}
function relWord(r) { const a = Math.abs(r); const s = r >= 0 ? 'gleichläufig' : 'gegenläufig'; return a < 0.15 ? 'kaum verbunden' : a < 0.35 ? 'leicht ' + s : a < 0.6 ? s : 'stark ' + s; }
function unusualCard(n) {
  const c = document.createElement('div'); c.className = 'card';
  const L = unusualList(n);
  c.innerHTML = `<div class="hd"><div><div class="ttl">Zusammenhänge, die gerade anders laufen</div><div class="sub">Korrelation der letzten 12 Monate gegenüber 10 Jahren (Wochenbasis). Solche Brüche zeigen oft einen Regimewechsel.</div></div>
    ${SECTION !== 'zusammen' ? '<button class="open">Alle ↗</button>' : ''}</div>
    <table class="t" style="margin-top:6px"><tr><th>Paar</th><th>10 J.</th><th>12 M.</th><th>jetzt</th></tr>
    ${L.map(r => `<tr class="row" data-a="${r.a}" data-b="${r.b}"><td>${esc(short2(r.a))} ↔ ${esc(short2(r.b))}</td><td>${nf(r.long, 2)}</td><td style="background:${heatColor(r.d, 1)}">${nf(r.now, 2)}</td><td style="font-family:inherit;color:var(--sec)">${relWord(r.now)}</td></tr>`).join('') || '<tr><td colspan="4" class="mut">Nichts Auffälliges.</td></tr>'}</table>`;
  const o = c.querySelector('.open'); if (o) o.onclick = () => go('zusammen');
  c.querySelectorAll('tr.row').forEach(r => r.onclick = () => openCompare(r.dataset.a, r.dataset.b));
  return c;
}
function classicsCard() {
  const c = document.createElement('div'); c.className = 'card full'; const nd = newestDay();
  c.innerHTML = `<div class="hd"><div><div class="ttl">Klassische Zusammenhänge – gelten sie noch?</div><div class="sub">Lehrbuch-Beziehungen, geprüft an den Daten: 10 Jahre gegenüber den letzten 12 Monaten (Wochenbasis).</div></div></div>
    <div class="pairs" style="margin-top:8px">${CLASSICS.filter(([a, b]) => S[a] && S[b]).map(([a, b, sign, t, d]) => {
      const now = corr(a, b, 'w', nd - 365), long = corr(a, b, 'w', nd - 3653);
      let st = status('neutral', 'unklar');
      if (now != null) { const s = now * sign; st = s >= 0.3 ? status('good', 'gilt') : s >= 0.1 ? status('neutral', 'schwach') : s > -0.1 ? status('warn', 'ausgesetzt') : status('serious', 'umgekehrt'); }
      return `<div class="pair" data-a="${a}" data-b="${b}"><div class="pt"><span>${t}</span>${st}</div><div class="pd">${d}</div>
        <div class="pv"><span>erwartet <b>${sign > 0 ? 'gleichläufig' : 'gegenläufig'}</b></span><span>10 J. <b>${nf(long, 2)}</b></span><span>12 M. <b>${nf(now, 2)}</b></span></div></div>`;
    }).join('')}</div>`;
  c.querySelectorAll('.pair').forEach(p => p.onclick = () => openCompare(p.dataset.a, p.dataset.b));
  return c;
}
function seriesOptions(sel) {
  return GROUPS.map(([g, gn]) => { const ids = Object.values(S).filter(s => s.g === g); if (!ids.length) return '';
    return `<optgroup label="${gn}">${ids.map(s => `<option value="${s.id}" ${s.id === sel ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</optgroup>`; }).join('');
}
function compareCard() {
  const c = document.createElement('div'); c.className = 'card full'; c.id = 'compare';
  if (!S[CMP.a]) CMP.a = 'y10'; if (!S[CMP.b]) CMP.b = 'ndx';
  const a = CMP.a, b = CMP.b;
  let f = freqOf(a, b); if (f === 'd' && RANGE > 3000) f = 'w'; // vor 11 J. liegen nur Wochenwerte vor
  const unitF = { d: 'Tage', w: 'Wochen', m: 'Monate' }[f];
  const wins = f === 'd' ? [[60, '60 T.'], [120, '120 T.'], [250, '1 J.']] : f === 'w' ? [[26, '26 W.'], [52, '52 W.'], [104, '2 J.']] : [[12, '12 M.'], [24, '24 M.'], [36, '36 M.']];
  const win = wins.some(w => w[0] === CMP.win) ? CMP.win : wins[f === 'd' ? 1 : 1][0];
  const bothPrice = S[a].k !== 'rate' && S[b].k !== 'rate';
  const mode = CMP.mode === 'auto' ? (bothPrice ? 'idx' : 'z') : CMP.mode;
  const span = Math.max(RANGE, minRangeFor(S[a]), minRangeFor(S[b]), f === 'w' ? 365 : f === 'm' ? 1096 : 0);
  const nd = Math.min(lastDay(a), lastDay(b)); const from = nd - span;
  const r = corr(a, b, f, from), rl = corr(a, b, f, nd - 3653);
  const maxLag = f === 'd' ? 20 : f === 'w' ? 12 : 12;
  const lagFrom = nd - Math.max(span, f === 'd' ? 730 : 1826);
  const lags = []; for (let L = -maxLag; L <= maxLag; L++) lags.push([L, corr(a, b, f, lagFrom, L)]);
  const best = lags.filter(x => x[1] != null).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]))[0];
  const r0 = (lags.find(x => x[0] === 0) || [0, null])[1];
  // beta & Interpretation
  const [xs, ys] = pairs(a, b, f, from);
  let interp = `Im gewählten Zeitraum (${RANGES.find(x => x[1] === RANGE) ? RANGES.find(x => x[1] === RANGE)[0] : ''}${span > RANGE ? ', erweitert' : ''}) bewegten sich <b>${esc(S[a].name)}</b> und <b>${esc(S[b].name)}</b> ${r == null ? 'ohne genug gemeinsame Daten' : `<b>${relWord(r)}</b> (r = ${nf(r, 2)}, ${xs.length} ${unitF})`}.`;
  if (rl != null && r != null) interp += ` Über 10 Jahre: ${relWord(rl)} (r = ${nf(rl, 2)})${Math.abs(r - rl) > 0.3 ? ' – <b>der Zusammenhang hat sich deutlich verändert</b>' : ''}.`;
  if (best && best[0] !== 0 && r0 != null && Math.abs(best[1]) > Math.abs(r0) + 0.1 && Math.abs(best[1]) > 0.2) {
    const lead = best[0] > 0 ? a : b, lagN = Math.abs(best[0]);
    interp += ` Mit Verschiebung ist der Zusammenhang stärker: <b>${esc(S[lead].name)}</b> läuft etwa <b>${lagN} ${unitF}</b> voraus (r = ${nf(best[1], 2)}).`;
  } else interp += ' Ein zeitlicher Vorlauf ist nicht erkennbar – beide reagieren eher gleichzeitig.';
  if (r != null && xs.length > 10) {
    const mx = xs.reduce((s, x) => s + x, 0) / xs.length, my = ys.reduce((s, y) => s + y, 0) / ys.length;
    let cov = 0, vx = 0; for (let i = 0; i < xs.length; i++) { cov += (xs[i] - mx) * (ys[i] - my); vx += (xs[i] - mx) ** 2; }
    const beta = cov / vx; const ua = S[a].k === 'rate' ? (S[a].g === 'zinsen' ? 10 : 1) : 1; // pro 10 Bp. bzw. 1 %
    const ex = S[a].k === 'rate' ? (S[a].g === 'zinsen' ? '+0,10 Pp.' : '+1 Pp.') : '+1 %';
    const delta = S[a].k === 'rate' ? beta * (S[a].g === 'zinsen' ? 0.1 : 1) : beta * Math.log(1.01);
    const eff = S[b].k === 'rate' ? `${delta > 0 ? '+' : ''}${nf(delta * (S[b].g === 'zinsen' ? 100 : 1), S[b].g === 'zinsen' ? 1 : 2)} ${S[b].g === 'zinsen' ? 'Bp.' : 'Pp.'}` : `${delta > 0 ? '+' : ''}${nf((Math.exp(delta) - 1) * 100, 2)} %`;
    interp += ` Faustregel aus diesem Zeitraum: Bewegt sich ${esc(S[a].name)} um ${ex}, bewegte sich ${esc(S[b].name)} im Schnitt um <b>${eff}</b>.`;
  }
  interp += ' <span class="mut">Korrelation zeigt gemeinsame Bewegung, nicht Ursache und Wirkung.</span>';

  c.innerHTML = `<div class="hd"><div><div class="ttl">Vergleich</div><div class="sub">Zwei Reihen gegenüberstellen: Verlauf, rollierende Korrelation und Vorlauf/Nachlauf.</div></div></div>
    <div class="ctl"><label>A <select id="ca">${seriesOptions(a)}</select></label><button class="iconbtn small" id="cswap" title="Tauschen">⇄</button>
    <label>B <select id="cb">${seriesOptions(b)}</select></label>
    <label>Darstellung <span class="seg" id="cmode"><button data-m="idx" class="${mode === 'idx' ? 'on' : ''}">Start = 100</button><button data-m="z" class="${mode === 'z' ? 'on' : ''}">Standardisiert</button><button data-m="raw" class="${mode === 'raw' ? 'on' : ''}">Einzeln</button></span></label>
    <label>Fenster <span class="seg" id="cwin">${wins.map(([w, n]) => `<button data-w="${w}" class="${w === win ? 'on' : ''}">${n}</button>`).join('')}</span></label></div>
    <div class="legend" id="clg"></div>
    <div style="display:grid;grid-template-columns:${mode === 'raw' ? '1fr 1fr' : '1fr'};gap:12px"><div class="chart tall" id="cc1"></div>${mode === 'raw' ? '<div class="chart tall" id="cc1b"></div>' : ''}</div>
    <div style="display:grid;grid-template-columns:1.4fr 1fr;gap:16px;margin-top:8px">
      <div><div class="ttl" style="font-size:12px;color:var(--sec)">Rollierende Korrelation (${wins.find(w => w[0] === win)[1]})</div><div class="chart short" id="cc2"></div></div>
      <div><div class="ttl" style="font-size:12px;color:var(--sec)">Vorlauf/Nachlauf (${unitF}, ${f === 'd' ? '2' : '5'} J.)</div><div id="cc3"></div></div>
    </div>
    <div class="interp">${interp}</div>`;
  const rerender = () => { store('cmp_a', CMP.a); store('cmp_b', CMP.b); store('cmp_mode', CMP.mode); store('cmp_win', CMP.win); disposeIn(c); c.replaceWith(compareCard()); };
  c.querySelector('#ca').onchange = e => { CMP.a = e.target.value; rerender(); };
  c.querySelector('#cb').onchange = e => { CMP.b = e.target.value; rerender(); };
  c.querySelector('#cswap').onclick = () => { [CMP.a, CMP.b] = [CMP.b, CMP.a]; rerender(); };
  c.querySelector('#cmode').onclick = e => { const bt = e.target.closest('button'); if (!bt) return; CMP.mode = bt.dataset.m; rerender(); };
  c.querySelector('#cwin').onclick = e => { const bt = e.target.closest('button'); if (!bt) return; CMP.win = +bt.dataset.w; rerender(); };

  queueMicrotask(() => {
    // 1) Verlauf
    const sa = slice(a, span), sb = slice(b, span);
    const tf = (sl, kind) => {
      if (mode === 'idx') { const b0 = sl.v[0]; return sl.v.map(v => v / b0 * 100); }
      if (mode === 'z') { const n = sl.v.length, m = sl.v.reduce((s, v) => s + v, 0) / n, sd = Math.sqrt(sl.v.reduce((s, v) => s + (v - m) ** 2, 0) / n) || 1; return sl.v.map(v => (v - m) / sd); }
      return sl.v;
    };
    const va = tf(sa), vb = tf(sb);
    const lg = c.querySelector('#clg');
    const ch1 = baseChart(c.querySelector('#cc1'), { fmt: p => nf(p, mode === 'z' ? 1 : mode === 'idx' ? 0 : decFor(p, S[a])) });
    const l1 = ch1.addLineSeries({ color: C.s1, lineWidth: 2, priceLineVisible: false, priceFormat: pf(mode === 'raw' ? decFor(last(a), S[a]) : 2) });
    l1.setData(sa.t.map((d, i) => ({ time: d * DAY, value: va[i] })));
    let ch1b = ch1, l2;
    if (mode === 'raw') { ch1b = baseChart(c.querySelector('#cc1b'), { fmt: p => nf(p, decFor(p, S[b])) }); }
    l2 = ch1b.addLineSeries({ color: C.s2, lineWidth: 2, priceLineVisible: false, priceFormat: pf(mode === 'raw' ? decFor(last(b), S[b]) : 2) });
    l2.setData(sb.t.map((d, i) => ({ time: d * DAY, value: vb[i] })));
    if (mode === 'z') l1.createPriceLine({ price: 0, color: C.mut, lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    ch1.timeScale().fitContent(); if (ch1b !== ch1) ch1b.timeScale().fitContent();
    const drawLg = day => {
      const dd = day == null ? null : day;
      const v1 = dd == null ? last(a) : valAt(a, dd), v2 = dd == null ? last(b) : valAt(b, dd);
      lg.innerHTML = `<span><i style="border-color:${C.s1}"></i>A · ${esc(S[a].name)}<b>${fmtV(a, v1)}</b> ${fmtC(chg(a, sa.v[0], v1))}</span>
        <span><i style="border-color:${C.s2}"></i>B · ${esc(S[b].name)}<b>${fmtV(b, v2)}</b> ${fmtC(chg(b, sb.v[0], v2))}</span>
        <span class="d">${dd != null ? fmtDate(dd) : 'seit ' + fmtDate(from, true)}${mode === 'z' ? ' · standardisiert: Abstand vom Durchschnitt in Standardabweichungen' : ''}</span>`;
    };
    drawLg(null);
    ch1.subscribeCrosshairMove(p => drawLg(p && p.time ? p.time / DAY : null));
    if (ch1b !== ch1) ch1b.subscribeCrosshairMove(p => drawLg(p && p.time ? p.time / DAY : null));

    // 2) rollierende Korrelation
    const A = changes(a, f), B = changes(b, f); const keys = [...A.keys()].filter(k => B.has(k)).sort((x, y) => x - y);
    const rc = []; const k0 = keyOf(from, f);
    for (let i = win; i <= keys.length; i++) {
      if (keys[i - 1] < k0) continue;
      const ks = keys.slice(i - win, i); const r_ = pearson(ks.map(k => A.get(k)), ks.map(k => B.get(k)));
      if (r_ != null) rc.push({ time: dayOfKey(keys[i - 1], f) * DAY, value: r_ });
    }
    const ch2 = baseChart(c.querySelector('#cc2'), { fmt: p => nf(p, 1) });
    const bs = ch2.addBaselineSeries({ baseValue: { type: 'price', price: 0 }, lineWidth: 2, priceLineVisible: false, priceFormat: pf(2),
      topLineColor: C.s1, topFillColor1: 'rgba(57,135,229,.25)', topFillColor2: 'rgba(57,135,229,.03)',
      bottomLineColor: C.s8, bottomFillColor1: 'rgba(230,103,103,.03)', bottomFillColor2: 'rgba(230,103,103,.25)',
      autoscaleInfoProvider: () => ({ priceRange: { minValue: -1, maxValue: 1 } }) });
    bs.setData(rc);
    if (rl != null) bs.createPriceLine({ price: rl, color: C.mut, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '10 J.' });
    ch2.timeScale().fitContent();

    // 3) Vorlauf/Nachlauf als Balken (SVG)
    const W = 360, H = 150, L0 = 30, T0 = 8, B0 = 30; const bw = (W - L0 - 6) / lags.length;
    const y = v => T0 + (1 - v) / 2 * (H - T0 - B0);
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block">`;
    [-1, -0.5, 0, 0.5, 1].forEach(v => svg += `<line x1="${L0}" x2="${W - 6}" y1="${y(v)}" y2="${y(v)}" stroke="${v === 0 ? C.line : C.grid}"/><text x="${L0 - 5}" y="${y(v) + 3}" fill="${C.mut}" font-size="9" text-anchor="end">${nf(v, 1)}</text>`);
    lags.forEach(([L, v], i) => {
      if (v == null) return; const x = L0 + i * bw + 1; const top = Math.min(y(0), y(v)), h = Math.max(1, Math.abs(y(v) - y(0)));
      const isBest = best && L === best[0];
      svg += `<rect x="${x}" y="${top}" width="${Math.max(1, bw - 2)}" height="${h}" rx="1.5" fill="${v >= 0 ? C.s1 : C.s8}" opacity="${isBest ? 1 : 0.55}" data-l="${L}" data-v="${v}"/>`;
    });
    svg += `<text x="${L0}" y="${H - 14}" fill="${C.mut}" font-size="9.5">← B läuft voraus</text><text x="${W - 6}" y="${H - 14}" fill="${C.mut}" font-size="9.5" text-anchor="end">A läuft voraus →</text>`;
    svg += `<text x="${L0 + (lags.length / 2) * bw}" y="${H - 2}" fill="${C.mut}" font-size="9.5" text-anchor="middle">0</text></svg>`;
    const box = c.querySelector('#cc3'); box.innerHTML = svg;
    box.querySelectorAll('rect').forEach(rr => { rr.onmousemove = e => { const L = +rr.dataset.l; showTip(e, `${L === 0 ? 'gleichzeitig' : L > 0 ? `A ${L} ${unitF} vor B` : `B ${-L} ${unitF} vor A`}: r = <b>${nf(+rr.dataset.v, 2)}</b>`); }; rr.onmouseleave = hideTip; });
  });
  return c;
}
function disposeIn(el) { /* Diagramme bleiben in charts[]; werden beim Abschnittswechsel entsorgt */ }
function openCompare(a, b) {
  CMP.a = a; if (b) CMP.b = b; else if (CMP.b === a) CMP.b = a === 'spx' ? 'y10' : 'spx';
  CMP.mode = 'auto';
  if (SECTION !== 'zusammen') { go('zusammen'); }
  else renderSection();
  setTimeout(() => { const el = document.getElementById('compare'); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 30);
}
function secZusammen(m) {
  head(m, 'Zusammenhänge', 'Wie die Märkte einander beeinflussen: Korrelationen, Brüche in alten Mustern und ein Werkzeug, um beliebige Reihen gegenüberzustellen.');
  const g = grid(m, 'wide');
  g.appendChild(compareCard());
  g.appendChild(unusualCard(10));
  g.appendChild(moversCard());
  g.appendChild(classicsCard());
  g.appendChild(matrixCard());
}

// ------------------------------------------------------------------ News
let NEWS = [], NEWSF = load('newsf') || 'all', NEWSTAG = null, seenNews = new Set(JSON.parse(load('seen') || '[]'));
function tagsOf(t) { return TAGS.filter(x => x.re.test(t)).map(x => x.id); }
function parseFeed(xml, src, cat) {
  const doc = new DOMParser().parseFromString(xml, 'text/xml'); const out = [];
  doc.querySelectorAll('item').forEach(it => {
    const t = (it.querySelector('title') || {}).textContent || '';
    const l = (it.querySelector('link') || {}).textContent || '';
    const dn = it.querySelector('pubDate') || it.getElementsByTagNameNS('http://purl.org/dc/elements/1.1/', 'date')[0];
    const d = dn ? new Date(dn.textContent.trim()) : null;
    if (t.trim()) out.push({ t: t.trim(), l: l.trim(), d: d && !isNaN(d) ? d.toISOString() : null, s: src, c: cat });
  });
  return out.slice(0, 30);
}
async function loadNews() {
  const feeds = (DATA && DATA.feeds) || [];
  let items = [];
  if (feeds.length) {
    const res = await Promise.allSettled(feeds.map(f => nfetch(f.u, 20).then(x => parseFeed(x, f.s, f.c))));
    // je Quelle begrenzen, damit kein Ticker-Dienst die Liste flutet
    res.forEach((r, i) => { if (r.status === 'fulfilled') items = items.concat(r.value.slice(0, /investing/i.test(feeds[i].s) ? 8 : 20)); });
  }
  if (!items.length && DATA && DATA.news) { const per = {}; items = DATA.news.filter(n => (per[n.s] = (per[n.s] || 0) + 1) <= (/investing/i.test(n.s) ? 8 : 20)); }
  const seen = new Set(); items = items.filter(n => { const k = n.t.toLowerCase().slice(0, 80); if (seen.has(k)) return false; seen.add(k); return true; });
  items.sort((x, y) => (y.d || '').localeCompare(x.d || ''));
  items.forEach(n => n.tags = tagsOf(n.t));
  NEWS = items.slice(0, 200);
  renderNewsCol(); if (SECTION === 'news') renderSection();
}
function rel(iso) {
  if (!iso) return ''; const m = Math.round((Date.now() - new Date(iso)) / 6e4);
  if (m < 1) return 'gerade'; if (m < 60) return `vor ${m} Min.`; if (m < 1440) return `vor ${Math.round(m / 60)} Std.`;
  return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
}
function newsFiltered() { return NEWS.filter(n => (NEWSF === 'all' || n.c === NEWSF) && (!NEWSTAG || n.tags.includes(NEWSTAG))); }
function newsItems(list) {
  return list.map((n, i) => `<div class="ni ${seenNews.has(n.l) ? '' : 'new'}" data-i="${i}"><div class="nm"><span class="src">${esc(n.s)}</span><span>${rel(n.d)}</span>${n.tags.slice(0, 2).map(t => `<span class="ntag">${esc(TAGS.find(x => x.id === t).name)}</span>`).join('')}</div><div class="nt">${esc(n.t)}</div></div>`).join('') || '<div class="empty">Keine Meldungen für diesen Filter.</div>';
}
function bindNews(el, list) {
  el.querySelectorAll('.ni').forEach(d => d.onclick = () => { const n = list[+d.dataset.i]; seenNews.add(n.l); store('seen', JSON.stringify([...seenNews].slice(-600))); d.classList.remove('new'); openURL(n.l); });
}
function renderNewsCol() {
  const seg = document.getElementById('newsSeg');
  seg.innerHTML = [['all', 'Alle'], ['us', 'US'], ['de', 'DE'], ['fed', 'Fed']].map(([k, n]) => `<button data-f="${k}" class="${NEWSF === k ? 'on' : ''}">${n}</button>`).join('');
  seg.onclick = e => { const b = e.target.closest('button'); if (!b) return; NEWSF = b.dataset.f; store('newsf', NEWSF); renderNewsCol(); if (SECTION === 'news') renderSection(); };
  const counts = {}; NEWS.forEach(n => n.tags.forEach(t => counts[t] = (counts[t] || 0) + 1));
  const tg = document.getElementById('newsTags');
  tg.innerHTML = TAGS.filter(t => counts[t.id]).sort((a, b) => counts[b.id] - counts[a.id]).map(t => `<button class="tag ${NEWSTAG === t.id ? 'on' : ''}" data-t="${t.id}">${t.name} ${counts[t.id]}</button>`).join('');
  tg.onclick = e => { const b = e.target.closest('button'); if (!b) return; NEWSTAG = NEWSTAG === b.dataset.t ? null : b.dataset.t; renderNewsCol(); if (SECTION === 'news') renderSection(); };
  const list = newsFiltered(); const el = document.getElementById('newsList');
  el.innerHTML = newsItems(list); bindNews(el, list);
}
function secNews(m) {
  const tag = NEWSTAG ? TAGS.find(t => t.id === NEWSTAG) : null;
  head(m, 'News', tag ? `Thema: <b>${tag.name}</b> – mit den passenden Reihen. Thema in der rechten Spalte wählen oder abwählen.` : 'Live aus CNBC, MarketWatch, Yahoo Finance, FT, Investing.com, Fed, Handelsblatt und tagesschau. Wähle rechts ein Thema, um die passenden Reihen zu sehen.');
  if (tag) { const g = grid(m); tag.ids.filter(id => S[id]).forEach(id => g.appendChild(chartCard({ ids: [id], title: S[id].name }))); }
  const c = document.createElement('div'); c.className = 'card newsbig'; c.style.marginTop = '12px'; c.style.padding = '0';
  const list = newsFiltered(); c.innerHTML = newsItems(list); bindNews(c, list); m.appendChild(c);
}

// ------------------------------------------------------------------ Live-Kurse (Yahoo)
async function liveQuote(id) {
  const tk = DATA.live[id]; if (!tk) return false;
  const txt = await nfetch(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(tk)}?range=5d&interval=1d`, 12);
  const j = JSON.parse(txt).chart.result[0]; const meta = j.meta;
  const p = meta.regularMarketPrice; const t = meta.regularMarketTime; if (!p || !t) return false;
  const s = S[id]; const day = Math.floor(t / 86400);
  // US-Handelstag: Datum in New York
  const ny = new Date(new Date(t * 1000).toLocaleString('en-US', { timeZone: meta.exchangeTimezoneName || 'America/New_York' }));
  const d2 = Math.floor(Date.UTC(ny.getFullYear(), ny.getMonth(), ny.getDate()) / 864e5);
  const lastD = s.t[s.t.length - 1];
  if (d2 === lastD) s.v[s.v.length - 1] = p; else if (d2 > lastD) { s.t.push(d2); s.v.push(p); }
  s.live = true; return true;
}
async function liveTick(all) {
  if (!DATA || !DATA.live) return;
  const ids = all ? Object.keys(DATA.live).filter(id => S[id]) : STRIP.filter(id => DATA.live[id] && S[id]);
  let ok = 0;
  for (let i = 0; i < ids.length; i += 6) {
    const r = await Promise.allSettled(ids.slice(i, i + 6).map(liveQuote));
    ok += r.filter(x => x.status === 'fulfilled' && x.value).length;
  }
  LIVEON = ok > 0; liveAt = Date.now(); _chgCache.clear();
  renderStrip(); renderStatus(); updateLive();
}

// ------------------------------------------------------------------ Suche (⌘K)
let pItems = [], pSel = 0;
function openPalette() {
  const p = document.getElementById('palette'); p.hidden = false; const i = document.getElementById('pin'); i.value = ''; i.focus(); fillPalette('');
}
function closePalette() { document.getElementById('palette').hidden = true; }
function fillPalette(q) {
  const norm = s => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const qq = norm(q.trim());
  const sec = SECTIONS.map(([id, n]) => ({ type: 'sec', id, n, g: 'Bereich' }));
  const ser = Object.values(S).filter(s => s.g !== 'intern').map(s => ({ type: 'ser', id: s.id, n: s.name, g: (GROUPS.find(g => g[0] === s.g) || [0, ''])[1] }));
  pItems = [...sec, ...ser].filter(x => !qq || norm(x.n + ' ' + x.g + ' ' + x.id).includes(qq)).slice(0, 40);
  pSel = 0; drawPalette();
}
function drawPalette() {
  const el = document.getElementById('plist');
  el.innerHTML = pItems.map((x, i) => `<div class="pi ${i === pSel ? 'on' : ''}" data-i="${i}"><span>${esc(x.n)}</span><span class="pg">${x.g}${x.type === 'ser' && last(x.id) != null ? ' · ' + fmtV(x.id, last(x.id)) : ''}</span></div>`).join('') || '<div class="empty">Nichts gefunden.</div>';
  el.querySelectorAll('.pi').forEach(d => { d.onclick = () => choose(+d.dataset.i); });
  const on = el.querySelector('.on'); if (on) on.scrollIntoView({ block: 'nearest' });
}
function choose(i) { const x = pItems[i]; if (!x) return; closePalette(); if (x.type === 'sec') go(x.id); else openCompare(x.id); }

// ------------------------------------------------------------------ Start
function bindKeys() {
  document.getElementById('cmdBtn').onclick = openPalette;
  document.getElementById('palette').onclick = e => { if (e.target.id === 'palette') closePalette(); };
  document.getElementById('pin').oninput = e => fillPalette(e.target.value);
  document.getElementById('newsReload').onclick = () => loadNews();
  const body = document.getElementById('body'); const nt = document.getElementById('newsToggle');
  const setNews = on => { body.classList.toggle('nonews', !on); nt.classList.toggle('on', on); store('news', on ? '1' : '0'); };
  setNews(load('news') !== '0');
  nt.onclick = () => setNews(body.classList.contains('nonews'));
  document.addEventListener('keydown', e => {
    const pal = !document.getElementById('palette').hidden;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); pal ? closePalette() : openPalette(); return; }
    if (pal) {
      if (e.key === 'Escape') closePalette();
      else if (e.key === 'ArrowDown') { pSel = Math.min(pItems.length - 1, pSel + 1); drawPalette(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { pSel = Math.max(0, pSel - 1); drawPalette(); e.preventDefault(); }
      else if (e.key === 'Enter') choose(pSel);
      return;
    }
    if ((e.metaKey || e.ctrlKey) && /^[1-9]$/.test(e.key)) { e.preventDefault(); const s = SECTIONS[+e.key - 1]; if (s) go(s[0]); }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); nt.click(); }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'r') { e.preventDefault(); refresh(true); }
    if (!e.metaKey && !e.ctrlKey && !e.altKey && e.target.tagName !== 'SELECT' && e.target.tagName !== 'INPUT') {
      const r = { '1': 31, '3': 92, '6': 183, 'j': 365, 'y': 365 }[e.key.toLowerCase()];
      if (e.key === '/') { e.preventDefault(); openPalette(); }
    }
  });
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (['lage', 'maerkte'].includes(SECTION)) document.querySelectorAll('canvas').forEach(() => {}); }, 200); });
}
async function refresh(force) {
  const changed = await loadData(false);
  if (changed || force) { renderStrip(); renderSection(); renderFoot(); }
  renderStatus();
}
async function start() {
  renderRanges(); bindKeys();
  await loadData(true);
  renderNav(); renderStrip(); renderSection(); renderStatus();
  loadNews();
  liveTick(true).then(() => { if (['lage', 'maerkte'].includes(SECTION)) renderSection(); });
  setInterval(() => liveTick(false), 60e3);                 // Leiste jede Minute
  setInterval(() => liveTick(true), 5 * 60e3);              // alles alle 5 Min.
  setInterval(() => refresh(false), 10 * 60e3);             // neue Datenbasis alle 10 Min. prüfen
  setInterval(loadNews, 5 * 60e3);
  setInterval(renderStatus, 30e3);
}
start();
