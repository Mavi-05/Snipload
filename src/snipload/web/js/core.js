// Snipload – Grundfunktionen der Oberflaeche: Verbindung zum Programm, Ereignisse, Sprache, Bausteine.
import { ICONS } from './icons.js';

export const K = new URLSearchParams(location.search).get('k') || '';

/** Gemeinsamer Zustand der ganzen Oberflaeche. */
export const S = {
  boot: null, cfg: {}, strings: {}, lang: 'en', jobs: [], editors: [], tools: null, update: null,
  whisper: null, upscale: null, page: 'home',
};

// ------------------------------------------------------------------ Aufrufe an das Programm
export async function api(name, args = {}) {
  let res;
  try {
    res = await fetch('/api/' + name, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Snip-Key': K }, body: JSON.stringify(args),
    });
  } catch (e) {
    throw new Error(t('Lost the connection to Snipload. Please restart the app.'));
  }
  const j = await res.json().catch(() => null);
  if (!j || !j.ok) {
    const err = new Error((j && j.error) || ('HTTP ' + res.status));
    err.code = j && j.code;
    throw err;
  }
  return j.result;
}

export function mediaUrl(path) { return '/media?k=' + encodeURIComponent(K) + '&p=' + encodeURIComponent(path); }
export function frameUrl(vid, time, width = 0) {
  return '/frame?k=' + encodeURIComponent(K) + '&v=' + encodeURIComponent(vid) + '&t=' + (Math.round(time * 10) / 10).toFixed(1) + '&w=' + width;
}

// ------------------------------------------------------------------ Ereignisse (vom Programm und innerhalb der Oberflaeche)
const listeners = {};
export function on(type, fn) {
  (listeners[type] || (listeners[type] = [])).push(fn);
  return () => { listeners[type] = (listeners[type] || []).filter(f => f !== fn); };
}
export function fire(type, data) {
  for (const fn of (listeners[type] || []).slice()) {
    try { fn(data); } catch (e) { console.error('[Snipload] handler', type, e); }
  }
}
export function connectEvents() {
  const es = new EventSource('/events?k=' + encodeURIComponent(K));
  es.onmessage = e => {
    let m;
    try { m = JSON.parse(e.data); } catch (_) { return; }
    fire(m.type, m.data);
  };
  return es;
}

// Lange Arbeiten (Tasks): api() liefert {task: id}; Fortschritt und Ergebnis kommen als Ereignis "task".
const taskWait = new Map();
const taskSeen = new Map();
on('task', d => {
  taskSeen.set(d.id, d);
  if (taskSeen.size > 60) taskSeen.delete(taskSeen.keys().next().value);
  settleTask(d);
});
function settleTask(d) {
  const w = taskWait.get(d.id);
  if (!w) return;
  if (w.onProgress) { try { w.onProgress(d); } catch (e) { console.error(e); } }
  if (d.status === 'done') { taskWait.delete(d.id); w.resolve(d.result); }
  else if (d.status === 'error' || d.status === 'cancelled') {
    taskWait.delete(d.id);
    const err = new Error(d.error || d.status);
    err.cancelled = d.status === 'cancelled';
    w.reject(err);
  }
}
/** Startet eine lange Arbeit und wartet auf ihr Ergebnis. handle.cancel() bricht ab. */
export async function runTask(name, args, onProgress, handle) {
  const { task } = await api(name, args);
  if (handle) { handle.id = task; handle.cancel = () => api('task_cancel', { id: task }).catch(() => {}); }
  return new Promise((resolve, reject) => {
    taskWait.set(task, { resolve, reject, onProgress });
    const seen = taskSeen.get(task);
    if (seen) settleTask(seen);
  });
}

// ------------------------------------------------------------------ Sprache
/** Uebersetzt einen englischen Text; {name} wird durch vars.name ersetzt. */
export function t(text, vars) {
  let out = S.strings[text] || text;
  if (vars) out = out.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  return out;
}

// ------------------------------------------------------------------ DOM-Bausteine
const NS = 'http://www.w3.org/2000/svg';
function append(el, kids) {
  for (const k of kids) {
    if (k == null || k === false || k === true) continue;
    if (Array.isArray(k)) append(el, k);
    else el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
/** h('button.btn.primary', {onclick}, 'Text') – kleines Hilfsmittel zum Bauen von Elementen. */
export function h(spec, props, ...kids) {
  let tag = 'div';
  const cls = [];
  let id = null;
  for (const part of spec.split(/(?=[.#])/)) {
    if (part[0] === '.') cls.push(part.slice(1));
    else if (part[0] === '#') id = part.slice(1);
    else if (part) tag = part;
  }
  const el = document.createElement(tag);
  if (cls.length) el.className = cls.join(' ');
  if (id) el.id = id;
  if (props != null && (props instanceof Node || typeof props !== 'object' || Array.isArray(props))) { kids.unshift(props); props = null; }
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') { if (v) el.className = (el.className ? el.className + ' ' : '') + v; }
      else if (k === 'text') el.textContent = v;
      else if (k === 'html') el.innerHTML = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k === 'data') Object.assign(el.dataset, v);
      else if (k === 'tip') el.dataset.tip = v;
      else if (k === 'key') el.dataset.key = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k in el && k !== 'list' && k !== 'form') { try { el[k] = v; } catch (_) { el.setAttribute(k, v); } }
      else el.setAttribute(k, v === true ? '' : v);
    }
  }
  append(el, kids);
  return el;
}
export function clear(el, ...kids) { el.replaceChildren(); append(el, kids); return el; }

export function icon(name, cls = '') {
  const s = document.createElementNS(NS, 'svg');
  s.setAttribute('viewBox', '0 0 24 24');
  s.setAttribute('class', 'i ' + cls);
  s.setAttribute('aria-hidden', 'true');
  s.innerHTML = ICONS[name] || '';
  return s;
}
/** Das Logo-Zeichen (Schnittrahmen + Play). */
export function mark(cls = 'mark') {
  const s = document.createElementNS(NS, 'svg');
  s.setAttribute('viewBox', '0 0 1024 1024');
  s.setAttribute('class', cls);
  s.setAttribute('aria-hidden', 'true');
  const u = document.createElementNS(NS, 'use');
  u.setAttribute('href', '#mark');
  s.append(u);
  return s;
}
/** Bild, das weich einblendet und bei Fehlern unsichtbar bleibt. */
export function img(src, attrs = {}) {
  const el = h('img', Object.assign({ loading: 'lazy', decoding: 'async', referrerPolicy: 'no-referrer', alt: '' }, attrs));
  el.addEventListener('load', () => el.classList.add('ok'));
  if (src) el.src = src;
  return el;
}

// ------------------------------------------------------------------ Zahlen und Zeiten
const pad = n => String(n).padStart(2, '0');
/** 3:05 oder 1:02:03 */
export function clock(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
  return hh ? `${hh}:${pad(mm)}:${pad(ss)}` : `${mm}:${pad(ss)}`;
}
/** Zeitcode mit Zehnteln: 03:12.4 oder 1:03:12.4 */
export function tc(sec) {
  const tenths = Math.max(0, Math.round((sec || 0) * 10));
  const whole = Math.floor(tenths / 10), f = tenths % 10;
  const hh = Math.floor(whole / 3600), mm = Math.floor((whole % 3600) / 60), ss = whole % 60;
  return (hh ? `${hh}:${pad(mm)}` : pad(mm)) + `:${pad(ss)}.${f}`;
}
/** Laenge eines Clips: 28.5 s oder 2:05 min */
export function span(sec) {
  sec = Math.max(0, sec || 0);
  if (sec < 60) return sec.toFixed(1) + ' s';
  if (sec < 3600) return `${Math.floor(sec / 60)}:${pad(Math.floor(sec % 60))} min`;
  return clock(sec);
}
/** "1:02:03.5", "3:05", "90", "1m30s", "1h2m" -> Sekunden (oder null) */
export function parseTime(str) {
  str = String(str || '').trim().toLowerCase().replace(',', '.');
  if (!str) return null;
  let m = str.match(/^(?:(\d+(?:\.\d+)?)h)?\s*(?:(\d+(?:\.\d+)?)m(?:in)?)?\s*(?:(\d+(?:\.\d+)?)s?)?$/);
  if (m && /[hms]/.test(str)) return (parseFloat(m[1] || 0) * 3600) + (parseFloat(m[2] || 0) * 60) + parseFloat(m[3] || 0);
  const parts = str.split(':');
  if (parts.length > 3 || parts.some(p => p === '' || isNaN(Number(p)))) return null;
  return parts.reduce((acc, p) => acc * 60 + Number(p), 0);
}
export function compact(n) {
  if (n == null || isNaN(n)) return '';
  try { return new Intl.NumberFormat(S.lang, { notation: 'compact', maximumFractionDigits: 1 }).format(n); }
  catch (_) { return String(n); }
}
export function num(n, digits = 0) {
  try { return new Intl.NumberFormat(S.lang, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(n); }
  catch (_) { return String(n); }
}
export function ago(ts) {
  if (!ts) return '';
  const diff = ts - Date.now() / 1000;
  const abs = Math.abs(diff);
  const steps = [[60, 'second', 1], [3600, 'minute', 60], [86400, 'hour', 3600], [604800, 'day', 86400], [2629800, 'week', 604800], [31557600, 'month', 2629800], [Infinity, 'year', 31557600]];
  for (const [limit, unit, div] of steps) {
    if (abs < limit) {
      try { return new Intl.RelativeTimeFormat(S.lang, { numeric: 'auto' }).format(Math.round(diff / div), unit); }
      catch (_) { return ''; }
    }
  }
  return '';
}
export function bytes(n) {
  if (!n) return '';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return num(n, i > 1 && n < 100 ? 1 : 0) + ' ' + u[i];
}
export function dateLabel(ts) {
  try { return new Intl.DateTimeFormat(S.lang, { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(ts * 1000)); }
  catch (_) { return ''; }
}
export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
/** Pfad fuer Anzeigen, die das Ende zeigen sollen (rechtsbuendig gekuerzt): Zeichen bleiben in ihrer Reihenfolge. */
export const pathText = p => (p ? '\u200e' + p : '');
export function debounce(fn, ms) {
  let id = 0;
  const f = (...a) => { clearTimeout(id); id = setTimeout(() => fn(...a), ms); };
  f.flush = (...a) => { clearTimeout(id); fn(...a); };
  return f;
}
export function uid() { return Math.random().toString(36).slice(2, 10); }

// ------------------------------------------------------------------ Einstellungen (werden gesammelt gespeichert)
let pendingCfg = {};
const flushCfg = debounce(() => {
  const values = pendingCfg;
  pendingCfg = {};
  api('set_cfg_many', { values }).catch(e => console.warn('[Snipload] settings', e));
}, 350);
export function setCfg(key, value) {
  S.cfg[key] = value;
  pendingCfg[key] = value;
  flushCfg();
}

// ------------------------------------------------------------------ Bedienelemente
export function Btn(label, o = {}) {
  const cls = ['btn', o.kind, o.sm && 'sm', o.lg && 'lg', o.block && 'block', (!label && o.icon) && 'icon', o.class].filter(Boolean).join(' ');
  return h('button', { class: cls, type: 'button', onclick: o.onclick, tip: o.tip, key: o.key, disabled: o.disabled, 'aria-label': !label ? o.tip : null },
    o.icon ? icon(o.icon) : null, label ? h('span', label) : null, o.after ? icon(o.after) : null);
}
/** Knopf waehrend einer Arbeit sperren und einen Kreisel zeigen. */
export async function busy(btn, fn) {
  if (btn.classList.contains('disabled')) return;
  btn.classList.add('disabled');
  const first = btn.firstElementChild;
  const sp = h('span.spin');
  if (first && first.tagName.toLowerCase() === 'svg') first.replaceWith(sp); else btn.prepend(sp);
  try { return await fn(); }
  finally {
    btn.classList.remove('disabled');
    if (first && first.tagName.toLowerCase() === 'svg') sp.replaceWith(first); else sp.remove();
  }
}
export function Switch(value, onChange, attrs = {}) {
  const el = h('button.switch', Object.assign({ type: 'button', role: 'switch' }, attrs));
  const set = v => { el.classList.toggle('on', !!v); el.setAttribute('aria-checked', v ? 'true' : 'false'); };
  set(value);
  el.addEventListener('click', () => { const v = !el.classList.contains('on'); set(v); onChange(v); });
  el.set = set;
  return el;
}
/** Seg([[wert, text, icon?], ...], aktuellerWert, fn) */
export function Seg(options, value, onChange, o = {}) {
  const el = h('div.seg' + (o.block ? '.block' : ''), { role: 'radiogroup' });
  const set = v => { for (const b of el.children) { const on = b._v === v; b.classList.toggle('on', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); } };
  for (const [v, label, ic, tip] of options) {
    const b = h('button', { type: 'button', role: 'radio', tip, onclick: () => { set(v); onChange(v); } }, ic ? icon(ic) : null, label);
    b._v = v;
    el.append(b);
  }
  set(value);
  el.set = set;
  return el;
}
/** Select([[wert, text], ...] oder [{group, options}], wert, fn) */
export function Select(options, value, onChange, attrs = {}) {
  const el = h('select.field', attrs);
  const addOpt = (parent, [v, label, disabled]) => parent.append(h('option', { value: String(v), disabled: !!disabled }, label));
  for (const o of options) {
    if (o && o.group) { const g = h('optgroup', { label: o.group }); o.options.forEach(x => addOpt(g, x)); el.append(g); }
    else addOpt(el, o);
  }
  el.value = String(value);
  const flat = options.flatMap(o => (o && o.group ? o.options : [o]));
  el.addEventListener('change', () => { const hit = flat.find(o => String(o[0]) === el.value); onChange(hit ? hit[0] : el.value); });
  return el;
}
export function Swatch(value, onInput, tip) {
  const input = h('input', { type: 'color', value: value || '#ffffff' });
  const el = h('label.swatch', { tip, style: { background: value } }, input);
  input.addEventListener('input', () => { el.style.background = input.value; onInput(input.value); });
  el.set = v => { input.value = v; el.style.background = v; };
  return el;
}
/** Schieberegler-Zeile: Name, Regler, Wert (anklicken zum Eintippen). */
export function SliderRow(label, o) {
  const fmt = o.format || (v => String(v));
  const range = h('input.slider', { type: 'range', min: o.min, max: o.max, step: o.step || 1 });
  const val = h('span.slider-val', { tip: t('Click to type a value') });
  const paint = v => {
    range.style.setProperty('--p', ((v - o.min) / (o.max - o.min) * 100) + '%');
    val.textContent = fmt(v);
  };
  const set = v => { range.value = v; paint(Number(range.value)); };
  set(o.value);
  range.addEventListener('input', () => { const v = Number(range.value); paint(v); o.onInput && o.onInput(v); });
  range.addEventListener('change', () => o.onChange && o.onChange(Number(range.value)));
  if (o.reset != null) range.addEventListener('dblclick', () => { set(o.reset); o.onInput && o.onInput(o.reset); o.onChange && o.onChange(o.reset); });
  val.addEventListener('click', () => {
    const inp = h('input.field.sm', { value: String(Number(range.value)), style: { width: '100%', textAlign: 'right', padding: '0 5px' } });
    val.replaceWith(inp);
    inp.focus(); inp.select();
    const done = ok => {
      if (!inp.isConnected) return;
      inp.replaceWith(val);
      const v = parseFloat(inp.value.replace(',', '.'));
      if (ok && !isNaN(v)) { const c = clamp(v, o.min, o.max); set(c); o.onInput && o.onInput(c); o.onChange && o.onChange(c); }
    };
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') done(true); if (e.key === 'Escape') done(false); e.stopPropagation(); });
    inp.addEventListener('blur', () => done(true));
  });
  const el = h('div.slider-row', h('span.row-label.ellipsis', { tip: o.tip }, label), range, val);
  el.set = set;
  el.range = range;
  return el;
}
export function Row(label, ctl, o = {}) {
  return h('div.row' + (o.top ? '.top' : '') + (o.stack ? '.stack' : ''), { class: o.class },
    h('div.row-label', label, o.hint ? h('small', o.hint) : null), ctl ? h('div.row-ctl', ctl) : null);
}
export function Sec(title, ...kids) {
  return h('section.sec', title ? h('div.sec-title', title) : null, kids);
}
export function Note(kind, ...kids) {
  const ic = { ok: 'circle-check', warn: 'triangle-alert', bad: 'circle-x', info: 'info' }[kind] || 'info';
  return h('div.note.' + (kind || 'info'), icon(ic), h('div.grow', kids));
}
export function Empty(title, text, action) {
  return h('div.empty', mark(), h('div.empty-title', title), text ? h('div.empty-text', text) : null, action || null);
}

// ------------------------------------------------------------------ Meldungen, Dialoge, Menues, Tooltips
export function toast(text, kind = 'info', o = {}) {
  const box = document.getElementById('toasts');
  const ic = { info: 'info', success: 'circle-check', warn: 'triangle-alert', error: 'circle-x' }[kind] || 'info';
  const el = h('div.toast.' + kind, icon(ic), h('span', text));
  if (o.action) el.append(h('button.link-btn', { type: 'button', onclick: () => { o.action.fn(); close(); } }, o.action.label));
  const close = () => { if (!el.isConnected) return; el.classList.add('out'); setTimeout(() => el.remove(), 200); };
  box.append(el);
  while (box.children.length > 4) box.firstElementChild.remove();
  setTimeout(close, o.timeout || (kind === 'error' ? 8000 : 4500) + Math.min(4000, text.length * 25));
  return close;
}

const modalStack = [];
/** modal({title, body, foot, cls, sticky, onClose}) -> {el, body, close} */
export function modal(o) {
  const layer = document.getElementById('layer');
  const body = h('div.modal-body' + (o.pearl ? '.pearl' : ''), o.body);
  const box = h('div.modal' + (o.cls ? '.' + o.cls : ''), { role: 'dialog', 'aria-modal': 'true', tabIndex: -1 },
    h('div.modal-head', h('h2.modal-title', o.title || ''),
      o.sticky ? null : Btn('', { icon: 'x', kind: 'ghost', sm: true, tip: t('Close'), onclick: () => self.close() })),
    body,
    o.foot ? h('div.modal-foot', o.foot) : h('div', { style: { height: '14px' } }));
  const back = h('div.modal-back', box);
  const prevFocus = document.activeElement;
  const self = {
    el: box, body, closed: false,
    close(result) {
      if (self.closed) return;
      self.closed = true;
      back.remove();
      const i = modalStack.indexOf(self);
      if (i >= 0) modalStack.splice(i, 1);
      if (o.onClose) o.onClose(result);
      if (prevFocus && prevFocus.focus) { try { prevFocus.focus({ preventScroll: true }); } catch (_) { /* egal */ } }
    },
    sticky: !!o.sticky,
  };
  back.addEventListener('mousedown', e => { if (e.target === back && !o.sticky) self.close(); });
  layer.append(back);
  modalStack.push(self);
  const auto = box.querySelector('[autofocus]');
  (auto || box).focus({ preventScroll: true });
  return self;
}
export function topModal() { return modalStack[modalStack.length - 1] || null; }
/** Rueckfrage: liefert true/false. */
export function ask(o) {
  return new Promise(resolve => {
    const m = modal({
      title: o.title, body: o.text ? h('p', o.text) : null, onClose: r => resolve(!!r),
      foot: [Btn(o.cancel || t('Cancel'), { kind: 'ghost', onclick: () => m.close(false) }),
        Btn(o.ok || 'OK', { kind: o.danger ? 'danger' : 'primary', onclick: () => m.close(true) })],
    });
    m.el.querySelector('.modal-foot .btn:last-child').focus();
  });
}

let openMenuEl = null;
export function closeMenu() { if (openMenuEl) { openMenuEl.remove(); openMenuEl = null; } }
/** menu(anker, [{label, icon, hint, onClick, danger, checked} | '-' | {heading}], {right}) */
export function menu(anchor, items, o = {}) {
  closeMenu();
  const el = h('div.menu', { role: 'menu' });
  for (const it of items) {
    if (!it) continue;
    if (it === '-') { el.append(h('div.menu-sep')); continue; }
    if (it.heading) { el.append(h('div.menu-label', it.heading)); continue; }
    el.append(h('button', {
      type: 'button', role: 'menuitem', class: [it.danger && 'danger', it.checked && 'checked'].filter(Boolean).join(' '), disabled: it.disabled,
      onclick: () => { closeMenu(); it.onClick && it.onClick(); },
    }, it.icon ? icon(it.icon) : null, h('span.ellipsis', it.label), it.hint ? h('span.menu-hint', it.hint) : null));
  }
  document.getElementById('layer').append(el);
  const r = anchor instanceof Element ? anchor.getBoundingClientRect() : { left: anchor.x, right: anchor.x, top: anchor.y, bottom: anchor.y };
  const w = el.offsetWidth, hh = el.offsetHeight;
  let x = o.right ? r.right - w : r.left;
  let y = r.bottom + 6;
  if (y + hh > innerHeight - 8) y = Math.max(8, r.top - hh - 6);
  x = clamp(x, 8, innerWidth - w - 8);
  el.style.left = x + 'px';
  el.style.top = y + 'px';
  openMenuEl = el;
  const first = el.querySelector('button');
  if (first && o.focus) first.focus();
  return el;
}
document.addEventListener('mousedown', e => { if (openMenuEl && !openMenuEl.contains(e.target)) closeMenu(); }, true);
addEventListener('blur', closeMenu);
addEventListener('resize', closeMenu);

// Tooltips: data-tip="Text", optional data-key="Ctrl+E"
let tipTimer = 0, tipFor = null;
function hideTip() {
  clearTimeout(tipTimer);
  tipFor = null;
  const tip = document.getElementById('tip');
  if (tip) tip.classList.remove('on');
}
document.addEventListener('mouseover', e => {
  const el = e.target.closest && e.target.closest('[data-tip]');
  if (el === tipFor) return;
  hideTip();
  if (!el || !el.dataset.tip) return;
  tipFor = el;
  tipTimer = setTimeout(() => {
    if (!el.isConnected) return;
    const tip = document.getElementById('tip');
    clear(tip, el.dataset.tip, el.dataset.key ? h('span.kbd', el.dataset.key) : null);
    const r = el.getBoundingClientRect();
    const w = tip.offsetWidth, hh = tip.offsetHeight;
    let x, y;
    if (el.dataset.tipSide === 'right') { x = r.right + 10; y = r.top + r.height / 2 - hh / 2; }
    else { x = r.left + r.width / 2 - w / 2; y = r.bottom + 8; if (y + hh > innerHeight - 6) y = r.top - hh - 8; }
    tip.style.left = clamp(x, 6, innerWidth - w - 6) + 'px';
    tip.style.top = clamp(y, 6, innerHeight - hh - 6) + 'px';
    tip.classList.add('on');
  }, 380);
});
document.addEventListener('mousedown', hideTip, true);
document.addEventListener('keydown', hideTip, true);
document.addEventListener('scroll', hideTip, true);

// ------------------------------------------------------------------ Seiten
const pages = {};
export function definePage(id, def) { pages[id] = def; }
export function go(id, arg) {
  if (!pages[id]) return;
  const prev = S.page;
  if (prev !== id && pages[prev] && pages[prev].hide) pages[prev].hide();
  S.page = id;
  for (const el of document.querySelectorAll('.page')) el.classList.toggle('on', el.id === 'page-' + id);
  for (const b of document.querySelectorAll('.rail-btn[data-page]')) b.classList.toggle('on', b.dataset.page === id);
  if (pages[id].show) pages[id].show(arg);
  fire('page', id);
}

/** Tastenkuerzel nur, wenn gerade nicht getippt wird. */
export function typing(e) {
  const el = (e && e.target) || document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}
