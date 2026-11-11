// Snipload – Zeitleiste (Canvas): Lineal, Kapitel, Filmstreifen, "Meist wiederholt"/Chat-Aktivitaet, Untertitel.
// Der gewaehlte Abschnitt wird wie im Logo als Schnittrahmen gezeichnet; die Abspielmarke traegt den Verlauf.
import { h, icon, clamp, clock, tc, span, t } from './core.js';

const PEARL = '#eef0fb';
const C = { tick: '#2a3046', label: '#6d7493', lane: '#0d1019', block: '#141826', text2: '#a1a8c4' };
const STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400];
const MINOR = { 0.2: 2, 2: 4, 15: 3, 30: 6, 120: 4, 900: 3, 1800: 6, 7200: 4, 14400: 4 };
const FONT = '"Geist", "Segoe UI", system-ui, sans-serif';
const MIN_LEN = 0.2;

function rr(ctx, x, y, w, hh, r) {
  r = Math.max(0, Math.min(r, w / 2, hh / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + hh, r);
  ctx.arcTo(x + w, y + hh, x, y + hh, r);
  ctx.arcTo(x, y + hh, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function fitText(ctx, text, max) {
  if (!text || max <= 8) return '';
  if (ctx.measureText(text).width <= max) return text;
  let lo = 0, hi = text.length;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (ctx.measureText(text.slice(0, mid) + '…').width <= max) lo = mid; else hi = mid - 1;
  }
  return lo ? text.slice(0, lo) + '…' : '';
}

export class Timeline {
  /** cb: {seek(t, live), range(a, b, edge), commit()} */
  constructor(cb) {
    this.cb = cb;
    this.canvas = h('canvas');
    this.tipCanvas = h('canvas', { width: 176, height: 99 });
    this.tipTime = h('span');
    this.tipEl = h('div.tl-tip', this.tipCanvas, this.tipTime);
    this.gutter = h('div.tl-gutter');
    this.wrap = h('div.tl-wrap', this.canvas, this.tipEl);
    this.el = h('div.tl', this.gutter, this.wrap);
    this.ctx = this.canvas.getContext('2d');
    this.dur = 0;
    this.view = { t0: 0, span: 1 };
    this.st = { t: 0, a: 0, b: 0, clips: [], pages: [], hype: null };
    this.sb = null; this.heat = null; this.chapters = [];
    this.sheets = new Map();
    this.w = 100; this.height = 90; this.dpr = 1;
    this.dirty = true;
    this.hoverX = null; this.hot = null; this.drag = null;
    this.lanesKey = '';
    this._bind();
    new ResizeObserver(() => this.resize()).observe(this.wrap);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { this.dirty = true; });
  }

  // ---------------------------------------------------------------- Daten
  setMeta(meta) {
    this.dur = Math.max(0.1, meta.duration || 0.1);
    this.sb = meta.storyboard && meta.storyboard.sheets && meta.storyboard.sheets.length ? meta.storyboard : null;
    this.heat = meta.heatmap && meta.heatmap.length > 3 ? meta.heatmap : null;
    this.chapters = (meta.chapters || []).filter(c => c.end > c.start);
    this.sheets.clear();
    this.view = { t0: 0, span: this.dur };
    this.layout();
    this.dirty = true;
  }
  set(patch) {
    Object.assign(this.st, patch);
    const key = [!!(this.st.pages && this.st.pages.length), !!this.st.hype].join();
    if (key !== this.lanesKey) { this.lanesKey = key; this.layout(); }
    this.dirty = true;
  }
  layout() {
    const L = {};
    let y = 0;
    L.ruler = { y, h: 22 }; y += 24;
    if (this.chapters.length) { L.chapters = { y, h: 18 }; y += 18 + 4; }
    L.video = { y: y + 5, h: 54 }; y += 54 + 10 + 4;
    if (this.heat || this.st.hype) { L.heat = { y, h: 24 }; y += 24 + 4; }
    if (this.st.pages && this.st.pages.length) { L.caps = { y, h: 20 }; y += 20 + 4; }
    this.L = L;
    this.height = y + 6;
    this.wrap.style.height = this.height + 'px';
    const tips = { chapters: ['list-video', t('Chapters')], video: ['film', t('Video')], heat: ['flame', t('Most replayed and chat activity')], caps: ['captions', t('Captions')] };
    this.gutter.replaceChildren();
    for (const k of ['chapters', 'video', 'heat', 'caps']) {
      if (!L[k]) continue;
      this.gutter.append(h('span.tl-ico', { style: { top: (L[k].y + L[k].h / 2 - 8) + 'px' }, tip: tips[k][1] }, icon(tips[k][0])));
    }
    this.resize();
  }
  resize() {
    const r = this.wrap.getBoundingClientRect();
    if (!r.width) return;
    this.dpr = Math.max(1, window.devicePixelRatio || 1);
    this.w = r.width;
    this.canvas.width = Math.round(r.width * this.dpr);
    this.canvas.height = Math.round(this.height * this.dpr);
    this.canvas.style.width = r.width + 'px';
    this.canvas.style.height = this.height + 'px';
    this.dirty = true;
  }

  // ---------------------------------------------------------------- Ansicht
  x(time) { return (time - this.view.t0) / this.view.span * this.w; }
  time(x) { return this.view.t0 + x / this.w * this.view.span; }
  get pps() { return this.w / this.view.span; }
  _span(sp) { return clamp(sp, Math.min(this.dur, Math.max(1.5, this.w / 400)), this.dur); }
  setView(t0, sp) {
    sp = this._span(sp);
    t0 = clamp(t0, 0, this.dur - sp);
    this.view = { t0, span: sp };
    this.dirty = true;
  }
  fit() { this.setView(0, this.dur); }
  zoomSel() {
    const { a, b } = this.st;
    const len = Math.max(MIN_LEN, b - a);
    this.setView(a - len * 0.35, len * 1.7);
  }
  zoom(factor, center) {
    if (center == null) center = this.view.t0 + this.view.span / 2;
    const k = (center - this.view.t0) / this.view.span;
    const sp = this._span(this.view.span * factor);
    this.setView(center - k * sp, sp);
  }
  get zoomed() { return this.view.span < this.dur - 1e-6; }
  /** Beim Abspielen mitlaufen: Marke bleibt im Bild. */
  follow(time) {
    if (!this.zoomed || this.drag) return;
    const x = this.x(time);
    if (x > this.w - 24 || x < 0) this.setView(time - this.view.span * 0.08, this.view.span);
  }

  // ---------------------------------------------------------------- Vorschaubilder (Storyboard)
  tile(time) {
    const sb = this.sb;
    if (!sb || !sb.interval) return null;
    const per = (sb.cols || 1) * (sb.rows || 1);
    let n = Math.floor(Math.max(0, time) / sb.interval);
    if (sb.count) n = Math.min(sb.count - 1, n);
    const si = Math.min(sb.sheets.length - 1, Math.floor(n / per));
    const idx = n - si * per;
    let rec = this.sheets.get(si);
    if (!rec) {
      const pic = new Image();
      rec = { pic, ok: false };
      pic.onload = () => { rec.ok = true; this.dirty = true; };
      pic.referrerPolicy = 'no-referrer';
      pic.src = sb.sheets[si];
      this.sheets.set(si, rec);
    }
    if (!rec.ok) return null;
    const sw = sb.width || rec.pic.naturalWidth / sb.cols, sh = sb.height || rec.pic.naturalHeight / sb.rows;
    const col = idx % sb.cols, row = Math.floor(idx / sb.cols);
    if ((row + 1) * sh > rec.pic.naturalHeight + 1 || (col + 1) * sw > rec.pic.naturalWidth + 1) return null;
    return { pic: rec.pic, sx: col * sw, sy: row * sh, sw, sh };
  }

  // ---------------------------------------------------------------- Zeichnen
  draw() {
    if (!this.dirty) return;
    this.dirty = false;
    const ctx = this.ctx, W = this.w, H = this.height;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.textBaseline = 'middle';
    this._ruler(ctx, W);
    if (this.L.chapters) this._chapters(ctx, W);
    this._video(ctx, W);
    if (this.L.heat) this._heat(ctx, W);
    if (this.L.caps) this._caps(ctx, W);
    this._clips(ctx);
    this._selection(ctx, W);
    this._hover(ctx, H);
    this._playhead(ctx, H);
    if (this.zoomed) this._scroll(ctx, W, H);
  }
  _ruler(ctx, W) {
    const L = this.L.ruler, pps = this.pps;
    const major = STEPS.find(s => s * pps >= 92) || STEPS[STEPS.length - 1];
    const minor = major / (MINOR[major] || 5);
    ctx.font = `500 11px ${FONT}`;
    ctx.fillStyle = C.label;
    ctx.strokeStyle = C.tick;
    ctx.lineWidth = 1;
    const end = Math.min(this.dur, this.view.t0 + this.view.span);
    let i = Math.ceil(this.view.t0 / minor - 1e-6);
    ctx.beginPath();
    for (; i * minor <= end + 1e-6; i++) {
      const tm = i * minor;
      const x = Math.round(this.x(tm)) + 0.5;
      const isMajor = Math.abs(tm / major - Math.round(tm / major)) < 1e-6;
      ctx.moveTo(x, L.y + L.h);
      ctx.lineTo(x, L.y + L.h - (isMajor ? 8 : 4));
      if (isMajor && x < W - 30) ctx.fillText(major < 1 ? tc(tm) : clock(tm), x + 5, L.y + 9);
    }
    ctx.stroke();
  }
  _chapters(ctx, W) {
    const L = this.L.chapters;
    ctx.font = `500 11px ${FONT}`;
    for (const c of this.chapters) {
      const x0 = this.x(c.start), x1 = this.x(Math.min(c.end, this.dur)) - 2;
      if (x1 < 0 || x0 > W) continue;
      rr(ctx, x0, L.y, Math.max(2, x1 - x0), L.h, 5);
      ctx.fillStyle = C.block;
      ctx.fill();
      const left = Math.max(x0, 0) + 7;
      const txt = fitText(ctx, c.title || '', x1 - left - 6);
      if (txt) { ctx.fillStyle = C.text2; ctx.fillText(txt, left, L.y + L.h / 2 + 0.5); }
    }
  }
  _video(ctx, W) {
    const L = this.L.video, pps = this.pps;
    const xs = Math.max(0, this.x(0)), xe = Math.min(W, this.x(this.dur));
    if (xe <= xs) return;
    ctx.save();
    rr(ctx, xs, L.y, xe - xs, L.h, 8);
    ctx.clip();
    ctx.fillStyle = C.lane;
    ctx.fillRect(xs, L.y, xe - xs, L.h);
    if (this.sb) {
      const ar = (this.sb.width && this.sb.height) ? this.sb.width / this.sb.height : 16 / 9;
      const tw = L.h * ar;
      const off = this.view.t0 * pps;
      for (let k = Math.floor(off / tw); k * tw - off < W; k++) {
        const tm = Math.min(this.dur - 0.01, (k + 0.5) * tw / pps);
        const tl = this.tile(tm);
        if (tl) ctx.drawImage(tl.pic, tl.sx, tl.sy, tl.sw, tl.sh, k * tw - off, L.y, tw + 0.6, L.h);
      }
    } else {
      // ohne Vorschaubilder: ruhige Flaeche mit feiner Teilung
      ctx.fillStyle = '#10131e';
      for (let x = xs; x < xe; x += 96) ctx.fillRect(x, L.y, 1, L.h);
    }
    // ausserhalb des Abschnitts abdunkeln
    const xa = this.x(this.st.a), xb = this.x(this.st.b);
    ctx.fillStyle = 'rgba(4, 6, 12, .6)';
    if (xa > xs) ctx.fillRect(xs, L.y, xa - xs, L.h);
    if (xb < xe) ctx.fillRect(xb, L.y, xe - xb, L.h);
    ctx.restore();
  }
  _heat(ctx, W) {
    const L = this.L.heat, base = L.y + L.h;
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, L.y - 2, W, L.h + 3);
    ctx.clip();
    if (this.heat) {
      const pts = this.heat.map(p => [this.x(((p.s || 0) + (p.e || 0)) / 2), base - 1 - clamp(p.v || 0, 0, 1) * (L.h - 4)]);
      ctx.beginPath();
      ctx.moveTo(this.x(0), base);
      ctx.lineTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) {
        const mx = (pts[i - 1][0] + pts[i][0]) / 2, my = (pts[i - 1][1] + pts[i][1]) / 2;
        ctx.quadraticCurveTo(pts[i - 1][0], pts[i - 1][1], mx, my);
      }
      ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
      ctx.lineTo(this.x(this.dur), base);
      ctx.closePath();
      const g = ctx.createLinearGradient(0, L.y, 0, base);
      g.addColorStop(0, 'rgba(238, 240, 251, .22)');
      g.addColorStop(1, 'rgba(238, 240, 251, .03)');
      ctx.fillStyle = g;
      ctx.fill();
      ctx.strokeStyle = 'rgba(238, 240, 251, .5)';
      ctx.lineWidth = 1.25;
      ctx.stroke();
    }
    const hy = this.st.hype;
    if (hy && hy.values) {
      const bw = Math.max(1, hy.bucket * this.pps - 1);
      ctx.fillStyle = 'rgba(140, 82, 251, .78)';
      for (let i = 0; i < hy.values.length; i++) {
        const x = this.x(i * hy.bucket);
        if (x + bw < 0 || x > W) continue;
        const hh = Math.max(1, hy.values[i] * (L.h - 3));
        ctx.fillRect(x, base - hh, bw, hh);
      }
    }
    ctx.restore();
  }
  _caps(ctx, W) {
    const L = this.L.caps;
    ctx.font = `500 10.5px ${FONT}`;
    for (const pg of this.st.pages) {
      const x0 = this.x(pg.t0), x1 = this.x(pg.t1) - 1;
      if (x1 < 0 || x0 > W) continue;
      rr(ctx, x0, L.y, Math.max(2, x1 - x0), L.h, 4);
      ctx.fillStyle = 'rgba(238, 240, 251, .11)';
      ctx.fill();
      if (x1 - x0 > 34) {
        const txt = fitText(ctx, pg.text, x1 - x0 - 10);
        if (txt) { ctx.fillStyle = '#c8cde6'; ctx.fillText(txt, x0 + 5, L.y + L.h / 2 + 0.5); }
      }
    }
  }
  _clips(ctx) {
    const L = this.L.video;
    ctx.font = `600 10.5px ${FONT}`;
    this.st.clips.forEach((c, i) => {
      const x0 = this.x(c.a), x1 = this.x(c.b);
      rr(ctx, x0, L.y - 2, Math.max(3, x1 - x0), L.h + 4, 7);
      ctx.strokeStyle = 'rgba(238, 240, 251, .42)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      if (x1 - x0 > 20) {
        rr(ctx, x0 + 5, L.y + L.h - 19, 16, 15, 4);
        ctx.fillStyle = 'rgba(4, 6, 12, .8)';
        ctx.fill();
        ctx.fillStyle = PEARL;
        ctx.textAlign = 'center';
        ctx.fillText(String(i + 1), x0 + 13, L.y + L.h - 11);
        ctx.textAlign = 'left';
      }
    });
  }
  /** Der Abschnitt als Schnittrahmen: zwei Winkel mit Ueberstand oben links und unten rechts (wie im Logo). */
  _selection(ctx, W) {
    const L = this.L.video;
    const xa = this.x(this.st.a), xb = this.x(this.st.b);
    if (xb < -20 || xa > W + 20) return;
    const y0 = L.y - 4, y1 = L.y + L.h + 4;
    const r = Math.min(9, Math.max(1, (xb - xa) / 2));
    const hot = this.drag ? this.drag.kind : this.hot;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = PEARL;
    ctx.lineWidth = hot === 'b' ? 4.5 : 3;
    ctx.beginPath();                       // oben + rechts
    ctx.moveTo(xa - 9, y0);
    ctx.lineTo(xb - r, y0);
    ctx.arcTo(xb, y0, xb, y0 + r, r);
    ctx.lineTo(xb, y1 + 7);
    ctx.stroke();
    ctx.lineWidth = hot === 'a' ? 4.5 : 3;
    ctx.beginPath();                       // links + unten
    ctx.moveTo(xa, y0 - 7);
    ctx.lineTo(xa, y1 - r);
    ctx.arcTo(xa, y1, xa + r, y1, r);
    ctx.lineTo(xb + 9, y1);
    ctx.stroke();
    // Laenge (anfassen = Abschnitt verschieben)
    ctx.font = `600 11px ${FONT}`;
    const label = span(this.st.b - this.st.a);
    const pw = ctx.measureText(label).width + 14;
    let px = xa + 8;
    if (xb - xa < pw + 16) px = xb + 16;
    px = clamp(px, 4, W - pw - 4);
    this.pill = { x: px, y: L.y + 6, w: pw, h: 19 };
    rr(ctx, px, this.pill.y, pw, 19, 6);
    ctx.fillStyle = hot === 'move' ? PEARL : 'rgba(4, 6, 12, .82)';
    ctx.fill();
    ctx.fillStyle = hot === 'move' ? '#080a12' : PEARL;
    ctx.fillText(label, px + 7, this.pill.y + 10);
  }
  _hover(ctx, H) {
    if (this.hoverX == null || this.drag) return;
    ctx.fillStyle = 'rgba(238, 240, 251, .28)';
    ctx.fillRect(Math.round(this.hoverX), this.L.ruler.y + this.L.ruler.h - 8, 1, H - this.L.ruler.h + 2);
  }
  _playhead(ctx, H) {
    const x = this.x(this.st.t);
    if (x < -8 || x > this.w + 8) return;
    const top = 3;
    const g = ctx.createLinearGradient(0, top, 0, H);
    g.addColorStop(0, '#d996fb'); g.addColorStop(0.45, '#8c52fb'); g.addColorStop(1, '#4764fc');
    ctx.fillStyle = g;
    ctx.fillRect(x - 1, top + 8, 2, H - top - 10);
    // Kopf: abgerundetes Dreieck nach unten (das Play-Dreieck aus dem Logo)
    ctx.beginPath();
    ctx.moveTo(x - 5, top + 1);
    ctx.lineTo(x + 5, top + 1);
    ctx.lineTo(x, top + 9);
    ctx.closePath();
    ctx.lineJoin = 'round';
    ctx.lineWidth = 3.5;
    const g2 = ctx.createLinearGradient(x - 6, top, x + 6, top + 10);
    g2.addColorStop(0, '#d996fb'); g2.addColorStop(1, '#6a5cfc');
    ctx.strokeStyle = g2;
    ctx.fillStyle = g2;
    ctx.stroke();
    ctx.fill();
  }
  _scroll(ctx, W, H) {
    const y = H - 3;
    rr(ctx, 0, y, W, 3, 1.5);
    ctx.fillStyle = '#1b2031';
    ctx.fill();
    const x0 = this.view.t0 / this.dur * W, w = Math.max(18, this.view.span / this.dur * W);
    rr(ctx, x0, y, w, 3, 1.5);
    ctx.fillStyle = this.hot === 'scroll' || (this.drag && this.drag.kind === 'scroll') ? PEARL : 'rgba(238, 240, 251, .45)';
    ctx.fill();
  }

  // ---------------------------------------------------------------- Bedienung
  _hit(x, y) {
    const L = this.L.video;
    if (this.zoomed && y >= this.height - 10) return 'scroll';
    const p = this.pill;
    if (p && x >= p.x && x <= p.x + p.w && y >= p.y && y <= p.y + p.h) return 'move';
    if (y >= L.y - 12 && y <= L.y + L.h + 12) {
      const xa = this.x(this.st.a), xb = this.x(this.st.b);
      const da = Math.abs(x - xa), db = Math.abs(x - xb);
      if (Math.min(da, db) <= 8) {
        if (Math.abs(xb - xa) < 16) return x < (xa + xb) / 2 ? 'a' : 'b';
        return da <= db ? 'a' : 'b';
      }
    }
    return 'seek';
  }
  _snap(time, e, skipPlayhead) {
    if (e && e.altKey) return time;
    const tol = 7 / this.pps;
    let best = time, bd = tol;
    const cands = [0, this.dur];
    if (!skipPlayhead) cands.push(this.st.t);
    for (const c of this.chapters) cands.push(c.start, c.end);
    for (const c of cands) { const d = Math.abs(c - time); if (d < bd) { bd = d; best = c; } }
    return best;
  }
  _bind() {
    const cv = this.canvas;
    const pos = e => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    cv.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      const [x, y] = pos(e);
      let kind = this._hit(x, y);
      if (e.shiftKey && kind !== 'scroll') kind = 'new';
      const tm = clamp(this.time(x), 0, this.dur);
      this.drag = { kind, x0: x, t0: tm, a0: this.st.a, b0: this.st.b, view0: this.view.t0 };
      cv.setPointerCapture(e.pointerId);
      if (kind === 'seek') this.cb.seek(tm, true);
      if (kind === 'new') this.cb.range(tm, Math.min(this.dur, tm + MIN_LEN), 'b');
      this._hideTip();
      this.dirty = true;
      e.preventDefault();
    });
    cv.addEventListener('pointermove', e => {
      const [x, y] = pos(e);
      if (!this.drag) {
        this.hoverX = x;
        const hot = this._hit(x, y);
        if (hot !== this.hot) { this.hot = hot; cv.style.cursor = hot === 'a' || hot === 'b' ? 'ew-resize' : hot === 'move' ? 'grab' : hot === 'scroll' ? 'pointer' : 'default'; }
        this._showTip(x, y);
        this.dirty = true;
        return;
      }
      const d = this.drag;
      const raw = clamp(this.time(x), 0, this.dur);
      if (d.kind === 'seek') this.cb.seek(raw, true);
      else if (d.kind === 'a') { const v = clamp(this._snap(raw, e), 0, this.st.b - MIN_LEN); this.cb.range(v, this.st.b, 'a'); }
      else if (d.kind === 'b') { const v = clamp(this._snap(raw, e), this.st.a + MIN_LEN, this.dur); this.cb.range(this.st.a, v, 'b'); }
      else if (d.kind === 'new') {
        const v = this._snap(raw, e, true);
        const a = Math.min(d.t0, v), b = Math.max(d.t0, v);
        this.cb.range(a, Math.max(a + MIN_LEN, b), v >= d.t0 ? 'b' : 'a');
      } else if (d.kind === 'move') {
        const len = d.b0 - d.a0;
        const a = clamp(d.a0 + (x - d.x0) / this.pps, 0, this.dur - len);
        this.cb.range(a, a + len, 'move');
      } else if (d.kind === 'scroll') {
        this.setView(d.view0 + (x - d.x0) / this.w * this.dur, this.view.span);
      }
      // am Rand mitschieben
      if (d.kind !== 'scroll' && this.zoomed) {
        if (x > this.w - 6) this.setView(this.view.t0 + this.view.span * 0.02, this.view.span);
        else if (x < 6) this.setView(this.view.t0 - this.view.span * 0.02, this.view.span);
      }
      this.dirty = true;
    });
    const end = e => {
      if (!this.drag) return;
      const kind = this.drag.kind;
      this.drag = null;
      try { cv.releasePointerCapture(e.pointerId); } catch (_) { /* egal */ }
      if (kind === 'seek') this.cb.seek(this.st.t, false);
      else if (kind !== 'scroll') this.cb.commit();
      this.dirty = true;
    };
    cv.addEventListener('pointerup', end);
    cv.addEventListener('pointercancel', end);
    cv.addEventListener('pointerleave', () => { this.hoverX = null; this.hot = null; this._hideTip(); this.dirty = true; });
    cv.addEventListener('dblclick', e => {
      const [x, y] = pos(e);
      const L = this.L.chapters;
      const tm = this.time(x);
      if (L && y >= L.y && y <= L.y + L.h) {
        const c = this.chapters.find(c2 => tm >= c2.start && tm < c2.end);
        if (c) { this.cb.range(c.start, Math.min(this.dur, c.end), 'b'); this.cb.commit(); }
      }
    });
    cv.addEventListener('wheel', e => {
      e.preventDefault();
      if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        const d = (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY);
        this.setView(this.view.t0 + d / this.w * this.view.span * 0.9, this.view.span);
      } else {
        const [x] = pos(e);
        this.zoom(Math.exp(clamp(e.deltaY, -240, 240) * 0.0022), this.time(x));
      }
      this.hoverX = null;
      this._hideTip();
    }, { passive: false });
  }
  _showTip(x, y) {
    if (y < this.L.ruler.y || this.hot === 'scroll') return this._hideTip();
    const tm = clamp(this.time(x), 0, this.dur);
    const tl = this.tile(tm);
    const c = this.tipCanvas;
    if (tl) {
      c.style.display = 'block';
      const g = c.getContext('2d');
      g.drawImage(tl.pic, tl.sx, tl.sy, tl.sw, tl.sh, 0, 0, c.width, c.height);
    } else c.style.display = 'none';
    const ch = this.chapters.find(c2 => tm >= c2.start && tm < c2.end);
    this.tipTime.textContent = tc(tm) + (ch && ch.title ? '  ' + ch.title : '');
    const el = this.tipEl;
    el.classList.add('on');
    const w = el.offsetWidth;
    el.style.left = clamp(x - w / 2, 0, this.w - w) + 'px';
  }
  _hideTip() { this.tipEl.classList.remove('on'); }
}
