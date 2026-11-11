// Snipload – Ergebnis-Vorschau: rechnet das 9:16-Bild genau wie der Export (facecam.py / finish.py)
// und zeigt Untertitel und Chat live darueber.
import { h, clamp } from './core.js';

export const OUT_W = 1080, OUT_H = 1920;

// ------------------------------------------------------------------ Geometrie (wie facecam.panel_plan)
export function panelPlan(src, aspect, W, H, zoom = 1, px = 0.5, py = 0.5) {
  const [sx, sy, sw, sh] = src;
  const SW = sw * aspect, SH = sh;
  const cover = Math.max(W / SW, H / SH), fit = Math.min(W / SW, H / SH);
  const zmin = fit / cover, zmax = 3;
  const z = clamp(Number(zoom) || 1, zmin, zmax);
  const s = cover * z;
  const winW = W / s, winH = H / s;
  const axis = (src0, length, win, out, p) => {
    if (win <= length + 1e-9) return [src0 + (length - win) * clamp(p, 0, 1), win, out, 0];
    let size = Math.round(length * s / 2) * 2;
    size = Math.max(2, Math.min(size, out));
    return [src0, length, size, Math.floor((out - size) / 2)];
  };
  const [x0, cw, ow, ox] = axis(sx * aspect, SW, winW, W, px);
  const [y0, ch, oh, oy] = axis(sy, SH, winH, H, py);
  return { crop: [x0 / aspect, y0, cw / aspect, ch], size: [ow, oh], pos: [ox, oy], bg: ow < W || oh < H, zoom: z, zmin, zmax };
}
const val = (o, k, d) => (o && o[k] != null && !isNaN(Number(o[k])) ? Number(o[k]) : d);
export function layoutGeometry(layout, aspect, outW = OUT_W, outH = OUT_H) {
  const split = clamp(val(layout, 'split', 0.4), 0.18, 0.65);
  const hf = Math.round(outH * split / 2) * 2, hg = outH - hf;
  const cam = panelPlan(layout.cam, aspect, outW, hf, val(layout, 'czoom', 1), val(layout, 'cx', 0.5), val(layout, 'cy', 0.5));
  const game = panelPlan([0, 0, 1, 1], aspect, outW, hg, val(layout, 'gzoom', 1), val(layout, 'gx', 0.5), val(layout, 'gy', 0.5));
  return { cam, game, hf, hg, w: outW, h: outH, camBottom: !!layout.cam_bottom };
}

function panel(ctx, pic, iw, ih, src, plan, X, Y, W, H, k) {
  const [cx, cy, cw, ch] = plan.crop;
  if (!plan.bg) {
    ctx.drawImage(pic, cx * iw, cy * ih, cw * iw, ch * ih, X * k, Y * k, W * k, H * k);
    return;
  }
  ctx.save();
  ctx.beginPath();
  ctx.rect(X * k, Y * k, W * k, H * k);
  ctx.clip();
  const [sx, sy, sw, sh] = src;
  const sc = Math.max(W / (sw * iw), H / (sh * ih));
  const dw = sw * iw * sc, dh = sh * ih * sc;
  ctx.filter = `blur(${Math.max(2, 20 * k)}px) brightness(.88)`;
  ctx.drawImage(pic, sx * iw, sy * ih, sw * iw, sh * ih, (X + (W - dw) / 2) * k, (Y + (H - dh) / 2) * k, dw * k, dh * k);
  ctx.filter = 'none';
  ctx.drawImage(pic, cx * iw, cy * ih, cw * iw, ch * ih, (X + plan.pos[0]) * k, (Y + plan.pos[1]) * k, plan.size[0] * k, plan.size[1] * k);
  ctx.restore();
}

/**
 * Zeichnet das Ergebnisbild. fmt: {aspect, crop_x, layout, cam}. pic: <video> oder <img>.
 * Rueckgabe false, wenn (noch) nichts gezeichnet werden kann.
 */
export function drawResult(ctx, cw, ch, pic, size, fmt) {
  if (!pic || !size || !size.w) return false;
  const iw = size.w, ih = size.h;
  const aspect = iw / ih;
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, cw, ch);
  const a = fmt.aspect;
  if (a === 'crop916') {
    const s = Math.max(OUT_W / iw, OUT_H / ih);
    const vw = OUT_W / s, vh = OUT_H / s;
    ctx.drawImage(pic, (iw - vw) * clamp(fmt.crop_x == null ? 0.5 : fmt.crop_x, 0, 1), 0, vw, vh, 0, 0, cw, ch);
  } else if (a === 'blur916') {
    const k = ch / OUT_H;
    const s = Math.max(OUT_W / iw, OUT_H / ih);
    const vw = OUT_W / s, vh = OUT_H / s;
    ctx.filter = `blur(${Math.max(2, 40 * k)}px) brightness(.94) saturate(1.15)`;
    ctx.drawImage(pic, (iw - vw) / 2, (ih - vh) / 2, vw, vh, -cw * 0.04, -ch * 0.04, cw * 1.08, ch * 1.08);
    ctx.filter = 'none';
    const f = Math.min(OUT_W / iw, OUT_H / ih);
    const fw = iw * f * k, fh = ih * f * k;
    ctx.drawImage(pic, 0, 0, iw, ih, (cw - fw) / 2, (ch - fh) / 2, fw, fh);
  } else if (a === 'facecam' && fmt.layout && fmt.layout.cam) {
    const g = layoutGeometry(fmt.layout, aspect);
    const k = ch / OUT_H;
    const yCam = g.camBottom ? g.hg : 0, yGame = g.camBottom ? 0 : g.hf;
    panel(ctx, pic, iw, ih, fmt.layout.cam, g.cam, 0, yCam, g.w, g.hf, k);
    panel(ctx, pic, iw, ih, [0, 0, 1, 1], g.game, 0, yGame, g.w, g.hg, k);
  } else if (a === 'facecam_raw' && fmt.cam) {
    const [x, y, w, hh] = fmt.cam;
    ctx.drawImage(pic, x * iw, y * ih, w * iw, hh * ih, 0, 0, cw, ch);
  } else {
    const f = Math.min(cw / iw, ch / ih);
    ctx.drawImage(pic, 0, 0, iw, ih, (cw - iw * f) / 2, (ch - ih * f) / 2, iw * f, ih * f);
  }
  return true;
}

/** Ausgabegroesse eines Formats (fuer Untertitel-Skalierung und Beschriftung). */
export function outputSize(fmt, meta, upscale) {
  const sw = (meta && meta.width) || 1920, sh = (meta && meta.height) || 1080;
  const a = fmt.aspect;
  if (a === 'crop916' || a === 'blur916' || a === 'facecam') {
    const w = { 1440: 1440, 2160: 2160 }[upscale] || 1080;
    return { w, h: w * 16 / 9 };
  }
  if (a === 'facecam_raw' && fmt.cam) {
    let w = Math.round(fmt.cam[2] * sw / 2) * 2, hh = Math.round(fmt.cam[3] * sh / 2) * 2;
    if (upscale && upscale > hh) { w = Math.round(w * upscale / hh / 2) * 2; hh = upscale; }
    return { w: Math.max(2, w), h: Math.max(2, hh) };
  }
  if (upscale && upscale > sh) return { w: Math.round(sw * upscale / sh / 2) * 2, h: upscale };
  return { w: sw, h: sh };
}

// ------------------------------------------------------------------ Untertitel
const fontLoads = new Map();
/** Sorgt dafuer, dass die gewaehlte Schrift im Fenster geladen ist (eigene/System-Schriften ueber ihre Datei). */
export function ensureFont(style) {
  const name = style && style.font;
  if (!name) return Promise.resolve();
  const key = name + '|' + (style.font_url || '');
  if (fontLoads.has(key)) return fontLoads.get(key);
  let p;
  if (style.font_url) {
    p = new FontFace(name, `url("${style.font_url}")`).load().then(f => { document.fonts.add(f); });
  } else {
    p = document.fonts.load(`24px "${name}"`);
  }
  p = p.catch(() => {});
  fontLoads.set(key, p);
  return p;
}

const mctx = document.createElement('canvas').getContext('2d');
export function emPx(style, W, H) {
  const ref = Math.min(H, W * 16 / 9);
  return Math.max(6, ref * (Number(style.size) || 7) / 100);
}
export function textWidth(text, style, em) {
  mctx.font = `${em}px "${style.font}", "Montserrat Black"`;
  return mctx.measureText(text).width + (Number(style.spacing) || 0) * em / 100 * Math.max(0, text.length - 1);
}
function groupLines(words, perLine, fits, gap = 0.7) {
  const lines = [];
  let cur = [];
  for (const w of words) {
    if (cur.length) {
      const last = cur[cur.length - 1];
      const pause = w.t0 - last.t1;
      const endOfSentence = /[.!?…]$/.test(last.w);
      const tooWide = !fits(cur.map(x => x.w).concat(w.w).join(' '));
      if (cur.length >= perLine || pause > gap || tooWide || (endOfSentence && cur.length >= 2)) { lines.push(cur); cur = []; }
    }
    cur.push(w);
  }
  if (cur.length) lines.push(cur);
  return lines;
}
/** Woerter -> Seiten (wie captions.pages): [{t0, t1, lines: [[wort,...]], flat, text}] */
export function pages(words, style, W, H) {
  if (!words || !words.length) return [];
  const em = emPx(style, W, H);
  const up = !!style.uppercase;
  const maxw = W * 0.88;
  const fits = text => textWidth(up ? text.toUpperCase() : text, style, em) <= maxw;
  const lines = groupLines(words, Math.max(1, parseInt(style.words, 10) || 3), fits);
  const n = Math.max(1, parseInt(style.lines, 10) || 1);
  const out = [];
  for (let i = 0; i < lines.length; i += n) {
    const grp = lines.slice(i, i + n);
    const flat = grp.flat();
    out.push({ t0: grp[0][0].t0, t1: flat[flat.length - 1].t1, lines: grp, flat, text: flat.map(w => w.w).join(' ') });
  }
  for (let i = 0; i + 1 < out.length; i++) {
    const d = out[i + 1].t0 - out[i].t1;
    if (d > 0 && d < 0.5) out[i].t1 = out[i + 1].t0;
  }
  return out;
}

function rgba(hex, alpha) {
  let s = String(hex || '#ffffff').replace('#', '');
  if (s.length === 3) s = s.split('').map(c => c + c).join('');
  const n = parseInt(s, 16) || 0;
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

export class CaptionOverlay {
  constructor() {
    this.block = h('div.cap-block');
    this.el = h('div.cap-layer', this.block);
    this.pages = [];
    this.pg = null;
    this.act = -2;
    this.idx = 0;
    this.style = null;
    this.spans = [];
  }
  set(words, style, outW, outH) {
    this.style = style;
    this.outW = outW;
    this.outH = outH;
    this.pages = words && words.length ? pages(words, style, outW, outH) : [];
    this.pg = null;
    this.act = -2;
    this.idx = 0;
    this.block.replaceChildren();
    this.css();
  }
  /** Groessen an die aktuelle Anzeigehoehe anpassen (nach set und bei Groessenaenderung aufrufen). */
  css() {
    const st = this.style;
    if (!st) return;
    const k = (this.el.clientHeight || 1) / this.outH;
    const em = emPx(st, this.outW, this.outH) * k;
    const bord = em * (Number(st.outline) || 0) / 100;
    const shad = em * (Number(st.shadow) || 0) / 100;
    const box = !!st.box;
    const s = this.el.style;
    s.fontFamily = `"${st.font}", "Montserrat Black", sans-serif`;
    s.fontSize = em + 'px';
    s.color = st.color || '#fff';
    s.letterSpacing = ((Number(st.spacing) || 0) * em / 100) + 'px';
    s.textTransform = st.uppercase ? 'uppercase' : 'none';
    s.setProperty('--cap-stroke', box ? '0px' : (2 * bord) + 'px');
    s.setProperty('--cap-stroke-color', st.outline_color || '#000');
    s.setProperty('--cap-shadow', !box && shad > 0.2 ? `drop-shadow(${shad}px ${shad}px 0 ${rgba(st.shadow_color, 0.65)})` : 'none');
    s.setProperty('--cap-hl', st.hl_color || '#ffd400');
    s.setProperty('--cap-hl-stroke', (2 * Math.max(bord, em * 0.2)) + 'px');
    s.setProperty('--cap-dim', rgba(st.color, 0.55));
    s.setProperty('--cap-box', box ? rgba(st.box_color, Number(st.box_opacity) || 0.6) : 'transparent');
    s.setProperty('--cap-pad', box ? Math.max(bord, em * 0.18) + 'px' : '0px');
    s.setProperty('--cap-slide', (em * 0.6) + 'px');
    this.block.style.top = (Number(st.pos) || 72) + '%';
    this.el.dataset.hl = st.hl_mode || 'color';
    this.el.classList.toggle('pop', !!st.word_pop && st.hl_mode !== 'none');
    this.el.classList.toggle('dim', !!st.dim_upcoming);
  }
  render(time) {
    const pgs = this.pages;
    if (!pgs.length) { if (this.pg) { this.pg = null; this.block.replaceChildren(); } return; }
    let i = this.idx;
    if (i >= pgs.length || time < pgs[i].t0) i = 0;
    while (i < pgs.length && pgs[i].t1 <= time) i++;
    this.idx = Math.min(i, pgs.length - 1);
    const pg = i < pgs.length && pgs[i].t0 <= time ? pgs[i] : null;
    if (pg !== this.pg) {
      this.pg = pg;
      this.act = -2;
      this.spans = [];
      this.block.replaceChildren();
      if (pg) {
        const page = h('div.cap-page.' + ({ pop: 'in-pop', fade: 'in-fade', slide: 'in-slide' }[this.style.anim] || 'in-none'));
        for (const line of pg.lines) {
          const row = h('div.cap-line');
          line.forEach((w, n) => {
            if (n) row.append(' ');
            const sp = h('span.cap-word', w.w);
            this.spans.push(sp);
            row.append(sp);
          });
          page.append(h('div.cap-row', row));
        }
        this.block.append(page);
      }
    }
    if (!pg) return;
    let a = 0;
    for (let j = 1; j < pg.flat.length; j++) { if (pg.flat[j].t0 <= time) a = j; else break; }
    if (this.style.hl_mode === 'none') a = -1;
    if (a !== this.act) {
      this.act = a;
      this.spans.forEach((sp, j) => { sp.classList.toggle('act', j === a); sp.classList.toggle('up', a >= 0 && j > a); });
    }
  }
}

// ------------------------------------------------------------------ Chat
export class ChatOverlay {
  constructor() {
    this.list = h('div.chat-list');
    this.el = h('div.chat-ov', this.list);
    this.msgs = [];
    this.sig = '';
    this.style = {};
    this.badges = {};
  }
  set(messages, style, box, badgeUrls) {
    this.msgs = messages || [];
    this.style = style || {};
    this.badges = badgeUrls || {};
    if (box) {
      const s = this.el.style;
      s.left = (box.x * 100) + '%'; s.top = (box.y * 100) + '%'; s.width = (box.w * 100) + '%'; s.height = (box.h * 100) + '%';
    }
    this.sig = '';
    this.el.classList.toggle('msg-bg', this.style.msg_bg !== false);
    this.el.classList.toggle('panel-bg', this.style.bg === 'solid');
    this.el.classList.toggle('no-shadow', this.style.shadow === false);
    this.el.style.setProperty('--chat-bg', `rgba(14, 14, 22, ${Number(this.style.bg_opacity == null ? 0.55 : this.style.bg_opacity)})`);
    this.el.style.setProperty('--chat-text', this.style.text_color || '#fff');
    this.css();
  }
  css() {
    const u = (this.el.clientWidth || 1) / (Number(this.style.width) || 420);
    this.el.style.fontSize = ((Number(this.style.font_size) || 22) * u) + 'px';
  }
  render(time) {
    const m = this.msgs;
    if (!m.length) { if (this.sig) { this.sig = ''; this.list.replaceChildren(); } return; }
    // letzte Nachricht mit t <= time
    let lo = 0, hi = m.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (m[mid].t <= time) lo = mid + 1; else hi = mid; }
    const end = lo;
    const age = Number(this.style.max_age) || 0;
    let start = Math.max(0, end - 24);
    if (age) while (start < end && time - m[start].t >= age) start++;
    const sig = start + ':' + end;
    if (sig === this.sig) return;
    this.sig = sig;
    const st = this.style;
    const nodes = [];
    for (let i = start; i < end; i++) {
      const msg = m[i];
      const row = h('div.chat-msg' + (msg.kind === 'super' ? '.super' : ''));
      if (st.badges !== false) {
        for (const b of msg.badges || []) {
          const url = this.badges[b] || (String(b).startsWith('http') ? b : null);
          if (url) row.append(h('img.chat-badge', { src: url, alt: '', referrerPolicy: 'no-referrer' }));
        }
      }
      row.append(h('b', { style: { color: st.name_colors === false ? 'inherit' : (msg.color || '#b9a3ff') } }, msg.user + (msg.kind === 'super' ? '' : ':')), ' ');
      for (const p of msg.parts || []) {
        if (p.e && st.emotes !== false) row.append(h('img.chat-emote', { src: p.e, alt: p.n || '', referrerPolicy: 'no-referrer' }));
        else row.append(p.t || p.n || '');
      }
      nodes.push(row);
    }
    this.list.replaceChildren(...nodes);
  }
}
