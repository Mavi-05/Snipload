// Snipload – Editor: Video ansehen, Abschnitt waehlen, Ergebnis live pruefen, exportieren.
import { S, api, on, runTask, t, h, icon, img, clear, go, definePage, toast, Btn, Empty, mark, clamp, clock, tc, span, parseTime, setCfg, debounce } from './core.js';
import { createPlayer, FrameFeed } from './player.js';
import { Timeline } from './timeline.js';
import { drawResult, outputSize, CaptionOverlay, ChatOverlay, ensureFont, panelPlan } from './preview.js';
import { buildInspector } from './inspector.js';

/** Alles, was zum gerade geoeffneten Video gehoert. */
export const E = {
  meta: null, dur: 0, player: null, feed: null, t: 0, playing: false, loop: false, muted: false,
  a: 0, b: 0, clips: [],
  fmt: { aspect: 'original', crop_x: 0.5, cam: null, camPx: null, layout: null, also_full: false, remember: false, detect: null },
  cap: { on: false, words: [], range: null, style: {}, burn: true, srt: false, source: 'ai', model: 'balanced', lang: 'auto', translate: false },
  chat: { messages: [], badges: {}, range: null, burn: false, alpha: '', style: {}, corner: 'bl', w: 0.42, h: 0.36, hype: null },
  fx: { speed: 1, brightness: 0, contrast: 0, saturation: 0, sharpen: 0, volume_db: 0, normalize: false, mute: false, fade_in: 0, fade_out: 0, fps: 0, up_target: 0, up_engine: 'lanczos' },
  out: { kind: 'video', quality: 'best', audio_fmt: 'mp3', exact: true, gif_fps: 15, gif_width: 480, size_mb: 0, hevc: false, name: '' },
};

let root, stateEl, edEl, titleEl, byEl, srcMon, srcFrame, srcHost, srcPoster, srcShield, srcOv, srcWait, outMon, outFrame, outCanvas, outHit, outNote;
let playBtn, timeNow, timeDur, inField, outField, lenEl, loopBtn, muteBtn, momentsEl, tl, ins, capOv, chatOv;
let loadReq = 0, raf = 0, lastDraw = '', seekHold = 0, seekTimer = 0, seekWant = null, lastSeekAt = 0, lastUrl = '';
let fmtRev = 0;

export function initEditor() {
  root = document.getElementById('page-editor');
  stateEl = h('div.ed-state');
  edEl = h('div.ed.hidden');
  clear(root, edEl, stateEl);
  showEmpty();
  definePage('editor', { hide: () => { if (E.player && E.playing) E.player.pause(); } });
  on('key', onKey);
  on('tools-changed', () => { if (ins && E.meta) ins.refresh(); });
}

function showEmpty() {
  stateEl.classList.remove('hidden');
  clear(stateEl, Empty(t('No video open'), t('Find a video or paste a link, then cut your clip here.'), Btn(t('Find a video'), { kind: 'primary', icon: 'search', onclick: () => go('home') })));
}
function showLoading(url) {
  stateEl.classList.remove('hidden');
  let host = '';
  try { host = new URL(url).hostname.replace(/^www\./, ''); } catch (_) { /* egal */ }
  clear(stateEl, h('div.ed-load-box', mark('ed-load-mark'), h('div.ed-load-title', t('Opening the video…')), h('div', host)));
}
function showError(url, message) {
  stateEl.classList.remove('hidden');
  clear(stateEl, Empty(t('Couldn’t open this video'), message,
    h('div.hstack', Btn(t('Back'), { kind: 'ghost', onclick: () => go('home') }), Btn(t('Try again'), { kind: 'primary', icon: 'refresh-cw', onclick: () => openVideo(url) }))));
}

// ------------------------------------------------------------------ Video oeffnen
export async function openVideo(url) {
  go('editor');
  const req = ++loadReq;
  lastUrl = url;
  teardown();
  showLoading(url);
  let meta;
  try { meta = await api('load', { url }); } catch (e) { if (req === loadReq) showError(url, e.message); return; }
  if (req !== loadReq) return;
  if (!meta.duration) {
    showError(url, meta.live ? t('This stream is still live. Open its recording (VOD) to clip it, or wait until the stream has ended.') : t('This video has no length information, so it can’t be cut.'));
    return;
  }
  S.cfg.recent = [{ id: meta.id, url: meta.url, title: meta.title, thumb: meta.thumb, channel: meta.channel, duration: meta.duration, platform: meta.platform, ts: Date.now() / 1000 }]
    .concat((S.cfg.recent || []).filter(r => r.id !== meta.id)).slice(0, 30);
  setup(meta);
}

function teardown() {
  cancelAnimationFrame(raf);
  raf = 0;
  if (E.player) { try { E.player.destroy(); } catch (_) { /* egal */ } }
  if (E.feed) E.feed.destroy();
  E.player = null; E.feed = null; E.meta = null; E.playing = false;
  edEl.classList.add('hidden');
  clear(edEl);
}

function setup(meta) {
  const d = S.boot;
  Object.assign(E, { meta, dur: meta.duration, t: 0, playing: false, clips: [] });
  const sizes = S.cfg.fc_sizes || null;
  E.fmt = { aspect: ['original', 'crop916', 'blur916', 'facecam', 'facecam_raw'].includes(S.cfg.aspect) ? S.cfg.aspect : 'original', crop_x: 0.5, cam: null, camPx: null, layout: null,
    also_full: !!S.cfg.also_full, remember: !!sizes, detect: null };
  E.cap = { on: false, words: [], range: null, style: Object.assign({}, d.caption_default, S.cfg.caption_style || {}), burn: true, srt: false,
    source: 'ai', model: S.cfg.caption_model || 'balanced', lang: S.cfg.caption_lang || 'auto', translate: false };
  E.chat = { messages: [], badges: {}, range: null, burn: false, alpha: '', style: Object.assign({}, d.chat_default, S.cfg.chat_style || {}), corner: 'bl', w: 0.42, h: 0.36, hype: null };
  E.fx = { speed: 1, brightness: 0, contrast: 0, saturation: 0, sharpen: 0, volume_db: 0, normalize: false, mute: false, fade_in: 0, fade_out: 0, fps: 0, up_target: 0,
    up_engine: S.cfg.upscale_engine || 'lanczos' };
  E.out = { kind: S.cfg.kind === 'audio' ? 'audio' : 'video', quality: S.cfg.quality || 'best', audio_fmt: S.cfg.audio_fmt || 'mp3', exact: S.cfg.exact !== false,
    gif_fps: 15, gif_width: 480, size_mb: 0, hevc: false, name: '' };
  const start = clamp(meta.start_hint || 0, 0, Math.max(0, meta.duration - 1));
  E.a = start;
  E.b = meta.duration <= 90 && !meta.start_hint ? meta.duration : Math.min(meta.duration, start + 30);
  E.t = start;
  build();
  stateEl.classList.add('hidden');
  edEl.classList.remove('hidden');
  tl.setMeta(meta);
  tl.set({ t: E.t, a: E.a, b: E.b, clips: [], pages: [], hype: null });
  if (E.b - E.a < meta.duration * 0.2 && meta.duration > 600) tl.zoomSel();
  paintRange();
  paintMoments();
  applyFormat();
  startPlayer(start);
  raf = requestAnimationFrame(tick);
}

async function startPlayer(start) {
  const meta = E.meta;
  srcWait.classList.add('on');
  let p;
  try { p = await createPlayer(srcHost, meta, start); } catch (e) { p = null; }
  if (E.meta !== meta) { if (p) p.destroy(); return; }
  srcWait.classList.remove('on');
  if (!p) return;
  E.player = p;
  p.onState = playing => { E.playing = playing; paintPlay(); };
  p.setMuted(E.muted);
  if (E.fx.speed !== 1) p.setRate(E.fx.speed);
  setTimeout(() => srcPoster.classList.add('gone'), p.kind === 'youtube' || p.kind === 'twitch' ? 1200 : 0);
  if (!p.sound) toast(t('Preview without sound: this video can only be shown as still frames here. The export has sound.'), 'info');
  ensureFeed();
}
function ensureFeed() {
  if (E.feed || !E.player || !wantOut()) return;
  const feed = new FrameFeed(E.meta, E.player);
  E.feed = feed;
  feed.init().then(() => { lastDraw = ''; });
}

// ------------------------------------------------------------------ Aufbau
function build() {
  const meta = E.meta;
  titleEl = h('div.ed-title.ellipsis', meta.title || '');
  byEl = h('span.ed-by.ellipsis', meta.channel || '');
  const bar = h('div.ed-bar', titleEl, meta.channel ? byEl : null, h('div.grow'),
    Btn('', { icon: 'external-link', kind: 'ghost', sm: true, tip: t('Open the original page'), onclick: () => api('open_url', { url: meta.url }) }),
    Btn('', { icon: 'x', kind: 'ghost', sm: true, tip: t('Close this video'), onclick: () => { loadReq++; teardown(); showEmpty(); go('home', { fresh: true }); } }));

  srcHost = h('div.mon-host.mon-fx');
  srcPoster = img(meta.thumb, { class: 'mon-poster', loading: 'eager' });
  srcShield = h('div.mon-shield');
  srcOv = h('div.mon-ov');
  srcWait = h('div.mon-wait', h('span.spin', { style: { width: '22px', height: '22px' } }));
  srcFrame = h('div.mon-frame', srcHost, srcPoster, srcShield, srcOv, srcWait);
  const ar = meta.width && meta.height ? meta.width / meta.height : 16 / 9;
  srcFrame.style.setProperty('--ar', ar.toFixed(5));
  srcMon = h('div.mon.mon-src', srcFrame);
  outCanvas = h('canvas.mon-fx');
  outHit = h('div.mon-hit');
  outNote = h('div.mon-note.hidden');
  outFrame = h('div.mon-frame', outCanvas, outHit, outNote);
  outMon = h('div.mon.mon-out', outFrame);
  capOv = new CaptionOverlay();
  chatOv = new ChatOverlay();
  wireShield();
  wireOutHit();
  new ResizeObserver(() => { capOv.css(); chatOv.css(); lastDraw = ''; }).observe(outFrame);
  new ResizeObserver(() => { capOv.css(); chatOv.css(); }).observe(srcFrame);

  // Transport
  playBtn = h('button.play-btn', { type: 'button', tip: t('Play or pause'), key: 'Space', onclick: togglePlay }, icon('play', 'nudge'));
  timeNow = document.createTextNode(tc(E.t));
  timeDur = h('span', ' / ' + clock(E.dur));
  inField = h('input.tc-field', { spellcheck: false, tip: t('Start of the clip'), 'aria-label': t('Start of the clip') });
  outField = h('input.tc-field', { spellcheck: false, tip: t('End of the clip'), 'aria-label': t('End of the clip') });
  for (const [f, edge] of [[inField, 'a'], [outField, 'b']]) {
    const apply = () => {
      const v = parseTime(f.value);
      if (v == null) return paintRange();
      if (edge === 'a') setRange(clamp(v, 0, E.dur - 0.2), Math.max(E.b, Math.min(E.dur, v + 0.2)), 'a', true);
      else setRange(Math.min(E.a, Math.max(0, v - 0.2)), clamp(v, 0.2, E.dur), 'b', true);
    };
    f.addEventListener('keydown', e => { if (e.key === 'Enter') { apply(); f.blur(); } if (e.key === 'Escape') { paintRange(); f.blur(); } e.stopPropagation(); });
    f.addEventListener('blur', apply);
    f.addEventListener('focus', () => f.select());
  }
  lenEl = h('span.ed-len');
  loopBtn = Btn('', { icon: 'repeat', kind: 'ghost', tip: t('Repeat the clip while playing'), onclick: () => { E.loop = !E.loop; loopBtn.classList.toggle('on', E.loop); } });
  muteBtn = Btn('', { icon: 'volume-2', kind: 'ghost', tip: t('Mute'), key: 'M', onclick: toggleMute });
  const transport = h('div.ed-transport',
    Btn('', { icon: 'skip-back', kind: 'ghost', tip: t('Jump to the start of the clip'), key: 'Q', onclick: () => seek(E.a) }),
    playBtn,
    Btn('', { icon: 'skip-forward', kind: 'ghost', tip: t('Jump to the end of the clip'), key: 'W', onclick: () => seek(E.b) }),
    h('div.ed-time', timeNow, timeDur),
    h('div.ed-range',
      Btn('', { icon: 'arrow-left-to-line', kind: 'ghost', sm: true, tip: t('Start the clip here'), key: 'I', onclick: () => markEdge('a') }),
      inField, h('span.dash'), outField,
      Btn('', { icon: 'arrow-right-to-line', kind: 'ghost', sm: true, tip: t('End the clip here'), key: 'O', onclick: () => markEdge('b') }),
      lenEl),
    h('div.ed-tools', loopBtn, muteBtn,
      Btn('', { icon: 'camera', kind: 'ghost', tip: t('Save this frame as an image'), key: 'S', onclick: snapshot })));

  // Zeitleiste
  tl = new Timeline({
    seek: (time, live) => seek(time, live),
    range: (a, b, edge) => setRange(a, b, edge, false),
    commit: () => commitRange(),
  });
  momentsEl = h('div.tl-moments');
  const tlBar = h('div.tl-bar', momentsEl,
    Btn('', { icon: 'zoom-out', kind: 'ghost', sm: true, tip: t('Zoom out'), key: '−', onclick: () => tl.zoom(1.6, E.t) }),
    Btn('', { icon: 'zoom-in', kind: 'ghost', sm: true, tip: t('Zoom in'), key: '+', onclick: () => tl.zoom(1 / 1.6, E.t) }),
    Btn('', { icon: 'scan', kind: 'ghost', sm: true, tip: t('Zoom to the clip'), onclick: () => tl.zoomSel() }),
    Btn('', { icon: 'move-horizontal', kind: 'ghost', sm: true, tip: t('Show the whole video'), onclick: () => tl.fit() }));

  ins = buildInspector(E, { changed, seek, setRange: (a, b) => setRange(a, b, 'a', true), detectFacecam, exportNow, addClip, removeClip, capPages: () => capOv.pages, loadChat, findHype, setCam, rememberSizes });
  clear(edEl,
    h('div.ed-main', bar, h('div.ed-stage', srcMon, outMon), transport, h('div.ed-tl', tlBar, tl.el)),
    ins.el);
}

// ------------------------------------------------------------------ Format und Ueberlagerungen
const wantOut = () => E.out.kind !== 'audio' && E.fmt.aspect !== 'original';
function outAr() {
  if (E.fmt.aspect === 'facecam_raw') {
    const c = E.fmt.cam;
    const sar = (E.meta.width && E.meta.height) ? E.meta.width / E.meta.height : 16 / 9;
    return c ? clamp(c[2] * sar / c[3], 0.3, 3) : 1;
  }
  return 9 / 16;
}
function chatBox() {
  const c = E.chat, m = 0.03;
  const w = clamp(c.w, 0.15, 0.94), hh = clamp(c.h, 0.1, 0.94);
  return { x: c.corner.endsWith('r') ? 1 - m - w : m, y: c.corner.startsWith('t') ? m : 1 - m - hh, w, h: hh };
}
/** Nach jeder Aenderung an Format, Untertiteln, Chat oder Effekten: Monitore und Vorschau anpassen. */
function applyFormat() {
  const show = wantOut();
  outMon.classList.toggle('hidden', !show);
  outMon.style.setProperty('--ar', outAr().toFixed(5));
  outFrame.style.setProperty('--ar', outAr().toFixed(5));
  const target = show ? outFrame : srcFrame;
  const before = show ? outHit : srcShield;
  if (capOv.el.parentNode !== target) target.insertBefore(capOv.el, before);
  if (chatOv.el.parentNode !== target) target.insertBefore(chatOv.el, capOv.el);
  const audio = E.out.kind === 'audio';
  capOv.el.classList.toggle('hidden', audio || !E.cap.on || !E.cap.burn);
  chatOv.el.classList.toggle('hidden', audio || !(E.chat.burn && E.chat.messages.length));
  const size = outputSize({ aspect: E.fmt.aspect, cam: E.fmt.cam }, E.meta, E.fx.up_target);
  ensureFont(E.cap.style).then(() => { capOv.set(E.cap.on ? E.cap.words : [], E.cap.style, size.w, size.h); tl.set({ pages: E.cap.on ? capOv.pages : [] }); if (ins) ins.capsChanged(); });
  capOv.set(E.cap.on ? E.cap.words : [], E.cap.style, size.w, size.h);
  chatOv.set(E.chat.messages, E.chat.style, chatBox(), E.chat.badges);
  tl.set({ pages: E.cap.on ? capOv.pages : [], hype: E.chat.hype, clips: E.clips });
  const f = E.fx;
  const fx = (f.brightness || f.contrast || f.saturation) ? `brightness(${(1 + f.brightness * 0.3).toFixed(3)}) contrast(${(1 + f.contrast * 0.5).toFixed(3)}) saturate(${(1 + f.saturation).toFixed(3)})` : 'none';
  srcHost.style.setProperty('--fx', fx);
  outCanvas.style.setProperty('--fx', fx);
  outHit.className = 'mon-hit' + (E.fmt.aspect === 'facecam' && E.fmt.cam ? ' pan' : E.fmt.aspect === 'crop916' ? ' pan' : '');
  const needCam = (E.fmt.aspect === 'facecam' || E.fmt.aspect === 'facecam_raw') && !E.fmt.cam;
  outNote.classList.toggle('hidden', !needCam);
  if (needCam) outNote.textContent = t('Find the facecam first, or draw its frame in the picture on the left.');
  paintSrcOverlay();
  fmtRev++;
  lastDraw = '';
  if (show) ensureFeed();
  if (ins) ins.foot();
}
/** what: 'format' | 'caps' | 'chat' | 'fx' | 'out' | 'draw' (nur neu zeichnen) */
function changed(what) {
  if (what === 'draw') { fmtRev++; lastDraw = ''; paintSrcOverlay(true); if (ins) ins.foot(); return; }
  if (what === 'fx' && E.player) E.player.setRate(E.fx.speed);
  if (what === 'caps') setCfg('caption_style', stripStyle(E.cap.style));
  if (what === 'chat') setCfg('chat_style', E.chat.style);
  applyFormat();
}
function stripStyle(st) { const o = Object.assign({}, st); delete o.font_url; return o; }

function paintSrcOverlay(keep) {
  const a = E.fmt.aspect;
  const sar = (E.meta.width && E.meta.height) ? E.meta.width / E.meta.height : 16 / 9;
  if (keep && srcOv.firstChild && srcOv.firstChild._kind === a) return placeBox();
  clear(srcOv);
  if (E.out.kind === 'audio') return;
  if (a === 'crop916') {
    const box = h('div.crop-box.x-only');
    box._kind = a;
    srcOv.append(box);
    dragBox(box, 'move', (dx) => {
      const wf = Math.min(1, (9 / 16) / sar);
      if (wf < 1) E.fmt.crop_x = clamp(E.fmt.crop_x + dx / (1 - wf), 0, 1);
      changed('draw');
    });
  } else if ((a === 'facecam' || a === 'facecam_raw') && E.fmt.cam) {
    const box = h('div.crop-box.cam', h('span.crop-label', t('Facecam')));
    box._kind = a;
    for (const c of ['nw', 'ne', 'sw', 'se']) {
      const hd = h('span.crop-handle.' + c);
      box.append(hd);
      dragBox(hd, c, (dx, dy) => resizeCam(c, dx, dy));
    }
    srcOv.append(box);
    dragBox(box, 'move', (dx, dy) => {
      const c = E.fmt.cam;
      setCam([clamp(c[0] + dx, 0, 1 - c[2]), clamp(c[1] + dy, 0, 1 - c[3]), c[2], c[3]]);
    });
  }
  placeBox();
}
function placeBox() {
  const box = srcOv.firstChild;
  if (!box) return;
  const sar = (E.meta.width && E.meta.height) ? E.meta.width / E.meta.height : 16 / 9;
  let r;
  if (box._kind === 'crop916') { const wf = Math.min(1, (9 / 16) / sar); r = [E.fmt.crop_x * (1 - wf), 0, wf, 1]; }
  else r = E.fmt.cam;
  if (!r) return;
  Object.assign(box.style, { left: (r[0] * 100) + '%', top: (r[1] * 100) + '%', width: (r[2] * 100) + '%', height: (r[3] * 100) + '%' });
}
function dragBox(el, kind, onMove) {
  el.addEventListener('pointerdown', e => {
    if (e.button !== 0 || (kind === 'move' && e.target !== el && !e.target.classList.contains('crop-label'))) return;
    e.preventDefault();
    e.stopPropagation();
    el.setPointerCapture(e.pointerId);
    const r = srcFrame.getBoundingClientRect();
    let px = e.clientX, py = e.clientY;
    const move = ev => { onMove((ev.clientX - px) / r.width, (ev.clientY - py) / r.height); px = ev.clientX; py = ev.clientY; };
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up); if (ins) ins.refresh(); };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  });
}
function resizeCam(corner, dx, dy) {
  let [x, y, w, hh] = E.fmt.cam;
  const min = 0.06;
  if (corner.includes('w')) { const nx = clamp(x + dx, 0, x + w - min); w += x - nx; x = nx; } else w = clamp(w + dx, min, 1 - x);
  if (corner.includes('n')) { const ny = clamp(y + dy, 0, y + hh - min); hh += y - ny; y = ny; } else hh = clamp(hh + dy, min, 1 - y);
  setCam([x, y, w, hh]);
}
/** Facecam-Rahmen setzen (von Hand oder aus der Erkennung). */
export function setCam(cam, px) {
  E.fmt.cam = cam;
  E.fmt.camPx = px || null;
  const sizes = E.fmt.remember ? (S.cfg.fc_sizes || {}) : {};
  if (!E.fmt.layout) {
    const split = sizes.split || autoSplit(cam), gzoom = sizes.gzoom || 1;
    E.fmt.layout = { cam, split, gzoom, czoom: sizes.czoom || 1, gx: suggestGx(cam, split, gzoom), gy: 0.5, cx: 0.5, cy: 0.5, cam_bottom: !!sizes.cam_bottom };
  } else E.fmt.layout.cam = cam;
  outMon.style.setProperty('--ar', outAr().toFixed(5));
  outFrame.style.setProperty('--ar', outAr().toFixed(5));
  outNote.classList.add('hidden');
  changed('draw');
}
/** Gameplay-Ausschnitt so legen, dass die Facecam darin moeglichst nicht noch einmal auftaucht (wie facecam.suggest_gx). */
function suggestGx(cam, split, gzoom) {
  const sar = (E.meta.width && E.meta.height) ? E.meta.width / E.meta.height : 16 / 9;
  const hg = 1920 - Math.round(1920 * clamp(split, 0.18, 0.65) / 2) * 2;
  const gw = panelPlan([0, 0, 1, 1], sar, 1080, hg, gzoom, 0.5, 0.5).crop[2];
  if (gw >= 0.999) return 0.5;
  const x0 = cam[0], x1 = cam[0] + cam[2];
  let x = (x0 + x1) / 2 > 0.5 ? x0 - gw - 0.02 : x1 + 0.02;
  x = clamp(x, 0, 1 - gw);
  return Math.round(clamp(x / (1 - gw), 0.2, 0.8) * 1000) / 1000;
}
function autoSplit(cam) {
  const sar = (E.meta.width && E.meta.height) ? E.meta.width / E.meta.height : 16 / 9;
  const ca = cam[2] * sar / Math.max(1e-6, cam[3]);
  return Math.round(clamp((1080 / ca) / 1920, 0.22, 0.5) * 1000) / 1000;
}

// Klick ins Quellbild: abspielen/anhalten. Untertitel lassen sich mit der Maus in der Hoehe verschieben.
function capDrag(e, frame) {
  if (!E.cap.on || !E.cap.burn || capOv.el.parentNode !== frame || !capOv.block.firstChild) return false;
  const r = capOv.block.getBoundingClientRect();
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top - 6 || e.clientY > r.bottom + 6) return false;
  const fr = frame.getBoundingClientRect();
  const el = e.currentTarget;
  el.setPointerCapture(e.pointerId);
  const move = ev => { E.cap.style.pos = Math.round(clamp((ev.clientY - fr.top) / fr.height * 100, 6, 94) * 10) / 10; capOv.css(); };
  const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); changed('caps'); if (ins) ins.refresh(); };
  el.addEventListener('pointermove', move);
  el.addEventListener('pointerup', up);
  return true;
}
function wireShield() {
  let dragged = false;
  srcShield.addEventListener('pointerdown', e => { dragged = e.button === 0 && capDrag(e, srcFrame); });
  srcShield.addEventListener('click', () => { if (!dragged) togglePlay(); dragged = false; });
}
function wireOutHit() {
  outHit.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    e.preventDefault();
    if (capDrag(e, outFrame)) return;
    const r = outFrame.getBoundingClientRect();
    const a = E.fmt.aspect;
    const sar = (E.meta.width && E.meta.height) ? E.meta.width / E.meta.height : 16 / 9;
    let move = null;
    if (a === 'crop916') {
      const scaled = r.height * sar;
      move = (dx) => { if (scaled > r.width) E.fmt.crop_x = clamp(E.fmt.crop_x - dx / (scaled - r.width), 0, 1); };
    } else if (a === 'facecam' && E.fmt.cam) {
      const L = E.fmt.layout;
      const split = clamp(L.split, 0.18, 0.65);
      const edge = (L.cam_bottom ? 1 - split : split) * r.height;
      const y = e.clientY - r.top;
      if (Math.abs(y - edge) < 9) {
        move = (dx, dy, ev) => { const f = clamp((ev.clientY - r.top) / r.height, 0, 1); L.split = Math.round(clamp(L.cam_bottom ? 1 - f : f, 0.18, 0.65) * 1000) / 1000; };
      } else {
        const inCam = L.cam_bottom ? y > edge : y < edge;
        const k = 1920 / r.height;
        move = (dx, dy) => {
          const H = inCam ? Math.round(1920 * split / 2) * 2 : 1920 - Math.round(1920 * split / 2) * 2;
          const src = inCam ? L.cam : [0, 0, 1, 1];
          const SW = src[2] * sar, SH = src[3];
          const cover = Math.max(1080 / SW, H / SH);
          const plan = panelPlan(src, sar, 1080, H, inCam ? L.czoom : L.gzoom, 0.5, 0.5);
          const s = cover * plan.zoom;
          const freeX = SW - 1080 / s, freeY = SH - H / s;
          const kx = inCam ? 'cx' : 'gx', ky = inCam ? 'cy' : 'gy';
          if (freeX > 1e-6) L[kx] = clamp((L[kx] == null ? 0.5 : L[kx]) - dx * k / s / freeX, 0, 1);
          if (freeY > 1e-6) L[ky] = clamp((L[ky] == null ? 0.5 : L[ky]) - dy * k / s / freeY, 0, 1);
        };
      }
    }
    if (!move) return;
    outHit.setPointerCapture(e.pointerId);
    let px = e.clientX, py = e.clientY;
    const onMove = ev => { move(ev.clientX - px, ev.clientY - py, ev); px = ev.clientX; py = ev.clientY; changed('draw'); };
    const up = () => { outHit.removeEventListener('pointermove', onMove); outHit.removeEventListener('pointerup', up); outHit.removeEventListener('pointercancel', up); rememberSizes(); if (ins) ins.refresh(); };
    outHit.addEventListener('pointermove', onMove);
    outHit.addEventListener('pointerup', up);
    outHit.addEventListener('pointercancel', up);
  });
  outHit.addEventListener('pointermove', e => {
    if (E.fmt.aspect !== 'facecam' || !E.fmt.cam || e.buttons) return;
    const r = outFrame.getBoundingClientRect();
    const L = E.fmt.layout;
    const edge = (L.cam_bottom ? 1 - L.split : L.split) * r.height;
    outHit.classList.toggle('split', Math.abs(e.clientY - r.top - edge) < 9);
  });
  outHit.addEventListener('wheel', e => {
    if (E.fmt.aspect !== 'facecam' || !E.fmt.cam) return;
    e.preventDefault();
    const r = outFrame.getBoundingClientRect();
    const L = E.fmt.layout;
    const edge = (L.cam_bottom ? 1 - L.split : L.split) * r.height;
    const y = e.clientY - r.top;
    const key = (L.cam_bottom ? y > edge : y < edge) ? 'czoom' : 'gzoom';
    L[key] = Math.round(clamp((L[key] || 1) * Math.exp(-clamp(e.deltaY, -200, 200) * 0.0016), 0.3, 3) * 1000) / 1000;
    changed('draw');
    rememberSizes();
    if (ins) ins.refreshSoon();
  }, { passive: false });
}
export function rememberSizes() {
  const L = E.fmt.layout;
  if (E.fmt.remember && L) setCfg('fc_sizes', { split: L.split, gzoom: L.gzoom, czoom: L.czoom, cam_bottom: !!L.cam_bottom });
}

// ------------------------------------------------------------------ Wiedergabe
function paintPlay() { clear(playBtn, icon(E.playing ? 'pause' : 'play', E.playing ? '' : 'nudge')); }
function togglePlay() {
  const p = E.player;
  if (!p) return;
  if (E.playing) { p.pause(); E.playing = false; }
  else {
    if (E.loop && (E.t < E.a - 0.05 || E.t >= E.b - 0.05)) seek(E.a);
    else if (E.t >= E.dur - 0.1) seek(0);
    p.play();
    E.playing = true;
  }
  paintPlay();
}
function toggleMute() {
  E.muted = !E.muted;
  if (E.player) E.player.setMuted(E.muted);
  clear(muteBtn, icon(E.muted ? 'volume-x' : 'volume-2'));
  muteBtn.classList.toggle('on', E.muted);
}
/** Springt zu einer Stelle. live = waehrend des Ziehens (wird gedrosselt). */
export function seek(time, live) {
  time = clamp(time, 0, E.dur);
  E.t = time;
  seekHold = performance.now();
  tl.set({ t: time });
  if (!E.player) return;
  const now = performance.now();
  const slow = E.player.kind === 'youtube' || E.player.kind === 'twitch' || E.player.kind === 'stills';
  if (live && slow && now - lastSeekAt < 140) {
    seekWant = time;
    if (!seekTimer) seekTimer = setTimeout(() => { seekTimer = 0; if (seekWant != null && E.player) { lastSeekAt = performance.now(); E.player.seek(seekWant); seekWant = null; } }, 150);
    return;
  }
  seekWant = null;
  lastSeekAt = now;
  E.player.seek(time);
}
function tick() {
  raf = requestAnimationFrame(tick);
  if (!E.meta) return;
  const p = E.player;
  if (p) {
    const pt = p.time;
    const held = performance.now() - seekHold < 900 && Math.abs(pt - E.t) > 0.35;
    if (!held) E.t = clamp(pt, 0, E.dur);
    if (E.playing !== p.playing && performance.now() - seekHold > 400) { E.playing = p.playing; paintPlay(); }
    if (E.playing && E.loop && E.t >= E.b - 0.02) seek(E.a);
    if (E.playing && E.t >= E.dur - 0.05) { p.pause(); E.playing = false; paintPlay(); }
  }
  const txt = tc(E.t);
  if (timeNow.data !== txt) timeNow.data = txt;
  tl.set({ t: E.t });
  if (E.playing) tl.follow(E.t);
  tl.draw();
  capOv.render(E.t);
  chatOv.render(E.t);
  if (ins) ins.tick(E.t);
  if (E.feed && wantOut()) {
    E.feed.sync(E.t, E.playing, p ? p.rate : 1);
    const d = E.feed.drawable;
    if (d) {
      const key = (E.feed.video && d === E.feed.video ? d.currentTime.toFixed(3) : 's' + E.feed.version) + '|' + fmtRev;
      if (key !== lastDraw) {
        const dpr = Math.min(2, window.devicePixelRatio || 1);
        const w = Math.max(2, Math.round(outFrame.clientWidth * dpr)), hh = Math.max(2, Math.round(outFrame.clientHeight * dpr));
        if (outCanvas.width !== w || outCanvas.height !== hh) { outCanvas.width = w; outCanvas.height = hh; }
        try {
          if (drawResult(outCanvas.getContext('2d'), w, hh, d, E.feed.size, { aspect: E.fmt.aspect, crop_x: E.fmt.crop_x, layout: E.fmt.layout, cam: E.fmt.cam })) lastDraw = key;
        } catch (_) { lastDraw = key; }
      }
    }
  }
}

// ------------------------------------------------------------------ Abschnitt
function paintRange() {
  if (document.activeElement !== inField) inField.value = tc(E.a);
  if (document.activeElement !== outField) outField.value = tc(E.b);
  lenEl.textContent = span(E.b - E.a);
}
function setRange(a, b, edge, commit) {
  a = clamp(a, 0, Math.max(0, E.dur - 0.2));
  b = clamp(b, a + 0.2, E.dur);
  E.a = Math.round(a * 100) / 100;
  E.b = Math.round(b * 100) / 100;
  paintRange();
  tl.set({ a: E.a, b: E.b });
  if (edge === 'a' || edge === 'move') seek(E.a, !commit);
  else if (edge === 'b') seek(E.b, !commit);
  if (commit) commitRange();
}
const commitRange = debounce(() => { if (ins && E.meta) { ins.foot(); ins.rangeChanged(); } }, 60);
function markEdge(edge) {
  if (edge === 'a') setRange(E.t, E.t >= E.b - 0.2 ? Math.min(E.dur, E.t + 30) : E.b, null, true);
  else setRange(E.t <= E.a + 0.2 ? Math.max(0, E.t - 30) : E.a, E.t, null, true);
}
function addClip() {
  if (E.clips.some(c => Math.abs(c.a - E.a) < 0.05 && Math.abs(c.b - E.b) < 0.05)) return toast(t('This clip is already in the list.'), 'info');
  E.clips.push({ a: E.a, b: E.b });
  tl.set({ clips: E.clips });
  ins.refresh();
  ins.foot();
  toast(t('Added clip {n}. Pick the next part, then export them all at once.', { n: E.clips.length }), 'success');
}
function removeClip(i) {
  E.clips.splice(i, 1);
  tl.set({ clips: E.clips });
  ins.refresh();
  ins.foot();
}

function paintMoments() {
  const out = [];
  const heat = E.meta.heatmap || [];
  if (heat.length > 3) {
    const peaks = [];
    for (let i = 1; i < heat.length - 1; i++) {
      const v = heat[i].v || 0;
      if (v >= (heat[i - 1].v || 0) && v > (heat[i + 1].v || 0) && v > 0.35 && (heat[i].s || 0) > 2) peaks.push({ t: heat[i].s || 0, v });
    }
    peaks.sort((x, y) => y.v - x.v);
    const picked = [];
    for (const pk of peaks) { if (picked.length < 5 && !picked.some(q => Math.abs(q.t - pk.t) < Math.max(20, E.dur * 0.04))) picked.push(pk); }
    picked.sort((x, y) => x.t - y.t);
    for (const pk of picked) out.push(h('button.chip', { type: 'button', tip: t('One of the most replayed moments'), onclick: () => jumpMoment(pk.t) }, icon('flame'), clock(pk.t)));
  }
  const hy = E.chat.hype;
  if (hy && hy.peaks) {
    for (const pk of hy.peaks.slice(0, 6).sort((x, y) => x.t - y.t)) {
      out.push(h('button.chip', { type: 'button', tip: t('The chat went wild here ({n} messages)', { n: pk.count }), onclick: () => jumpMoment(pk.t) }, icon('message-square'), clock(pk.t)));
    }
  }
  clear(momentsEl, out.length ? out : h('span.dim', t('Drag the white frame to pick your clip. Scroll to zoom.')));
}
function jumpMoment(time) {
  const a = Math.max(0, time - 4);
  setRange(a, Math.min(E.dur, a + 30), 'a', true);
  if (tl.zoomed || E.dur > 600) tl.zoomSel();
}

// ------------------------------------------------------------------ Aktionen
async function snapshot() {
  try {
    const r = await api('snapshot', { vid: E.meta.id, t: E.t });
    toast(t('Frame saved as an image'), 'success', { action: { label: t('Show in folder'), fn: () => api('reveal', { path: r.file }) } });
  } catch (e) { toast(e.message, 'error'); }
}

async function detectFacecam(onProgress, handle) {
  const meta = E.meta;
  const sar = (meta.width && meta.height) ? meta.width / meta.height : 16 / 9;
  const res = await runTask('facecam_detect', { vid: meta.id, start: E.a, end: E.b, aspect: sar }, onProgress, handle);
  if (E.meta !== meta) return res;
  E.fmt.detect = { ok: !!res.ok, message: res.message || '', fullscreen: !!res.fullscreen };
  if (res.ok && res.box && !res.fullscreen) {
    E.fmt.layout = null;
    if (res.layout) {
      const sizes = E.fmt.remember ? (S.cfg.fc_sizes || {}) : {};
      E.fmt.layout = Object.assign({}, res.layout, { cam: res.box }, sizes.split ? { split: sizes.split, gzoom: sizes.gzoom || 1, czoom: sizes.czoom || 1, cam_bottom: !!sizes.cam_bottom } : {});
    }
    setCam(res.box, res.px || null);
  }
  applyFormat();
  return res;
}

async function loadChat(onProgress, handle) {
  const meta = E.meta;
  const a = E.clips.length ? Math.min(E.a, ...E.clips.map(c => c.a)) : E.a;
  const b = E.clips.length ? Math.max(E.b, ...E.clips.map(c => c.b)) : E.b;
  const res = await runTask('chat_load', { vid: meta.id, start: a, end: b }, onProgress, handle);
  if (E.meta !== meta) return res;
  E.chat.messages = res.messages || [];
  E.chat.badges = res.badge_urls || {};
  E.chat.range = [a, b];
  applyFormat();
  return res;
}
async function findHype(onProgress, handle) {
  const meta = E.meta;
  const res = await runTask('chat_hype', { vid: meta.id }, onProgress, handle);
  if (E.meta !== meta) return res;
  E.chat.hype = res;
  tl.set({ hype: res });
  paintMoments();
  return res;
}

/** Stellt den Auftrag zusammen (ein Auftrag je Clip) und startet den Export. */
async function exportNow() {
  const meta = E.meta;
  if (!meta) return;
  const f = E.fmt, fx = E.fx, o = E.out;
  const video = o.kind !== 'audio';
  if (video && (f.aspect === 'facecam' || f.aspect === 'facecam_raw') && !f.cam) {
    ins.show('format');
    return toast(t('Find the facecam first, or draw its frame in the picture.'), 'warn');
  }
  const spec = {};
  if (fx.speed !== 1) spec.speed = fx.speed;
  if (fx.volume_db) spec.volume_db = fx.volume_db;
  if (fx.normalize) spec.normalize = true;
  if (fx.fade_in) spec.fade_in = fx.fade_in;
  if (fx.fade_out) spec.fade_out = fx.fade_out;
  if (!video && fx.speed !== 1) spec.speed_on = true;
  let layout = null, camPx = null;
  if (video) {
    if (fx.mute) spec.mute = true;
    if (fx.brightness || fx.contrast || fx.saturation) spec.eq = { brightness: fx.brightness, contrast: fx.contrast, saturation: fx.saturation };
    if (fx.sharpen) spec.sharpen = fx.sharpen;
    if (fx.fps) spec.fps = fx.fps;
    if (fx.up_target) spec.upscale = { target: fx.up_target, engine: fx.up_engine, model: 'video' };
    if (f.aspect === 'crop916') spec.crop_x = f.crop_x;
    if (o.kind === 'gif') spec.gif = { fps: o.gif_fps, width: o.gif_width };
    else {
      if (o.size_mb) spec.size_mb = o.size_mb;
      if (o.hevc) spec.codec_hevc = true;
    }
    if (E.cap.on && E.cap.words.length && (E.cap.burn || E.cap.srt)) spec.captions = { style: stripStyle(E.cap.style), burn: !!E.cap.burn, srt: !!E.cap.srt };
    const ch = E.chat;
    if ((ch.burn || ch.alpha) && ch.messages.length) {
      spec.chat = { messages: ch.messages, badge_urls: ch.badges, style: ch.style, burn: !!ch.burn, box: chatBox(), alpha: ch.alpha || null };
      if (ch.alpha && !ch.burn) spec.chat.style = Object.assign({}, ch.style, { width: 840, height: 1440, font_size: (Number(ch.style.font_size) || 22) * 2 });
    } else if (ch.burn || ch.alpha) {
      ins.show('chat');
      return toast(t('Load the chat first.'), 'warn');
    }
    if (f.aspect === 'facecam' || f.aspect === 'facecam_raw') {
      const W = meta.width || 1920, H = meta.height || 1080;
      const c = f.cam;
      camPx = f.camPx || { x: Math.round(c[0] * W), y: Math.round(c[1] * H), w: Math.round(c[2] * W / 2) * 2, h: Math.round(c[3] * H / 2) * 2, ref_w: W, ref_h: H };
      layout = f.aspect === 'facecam' ? Object.assign({}, f.layout, { cam: c }) : null;
    }
  }
  const list = E.clips.length ? E.clips : [{ a: E.a, b: E.b }];
  const custom = (o.name || '').trim();
  const clips = list.map((c, i) => {
    const whole = c.a <= 0.01 && c.b >= E.dur - 0.05;
    const item = { start: whole ? 0 : c.a, end: whole ? E.dur : c.b };
    if (custom) item.name = list.length > 1 ? `${custom} ${i + 1}` : custom;
    if (spec.captions) {
      item.caption_words = E.cap.words.filter(w => w.t1 > c.a && w.t0 < c.b)
        .map(w => ({ w: w.w, t0: Math.round(Math.max(0, w.t0 - c.a) * 1000) / 1000, t1: Math.round((Math.min(c.b, w.t1) - c.a) * 1000) / 1000 }));
    }
    return item;
  });
  const ed = S.editors.find(x => x.id === S.cfg.open_in);
  const opts = { kind: video ? 'video' : 'audio', quality: o.quality, audio_fmt: o.audio_fmt, aspect: video ? f.aspect : 'original', exact: o.exact, spec, layout, cam_px: camPx,
    also_full: video && (f.aspect === 'facecam' || f.aspect === 'facecam_raw') && f.also_full, open_in: ed ? ed.id : null, open_mode: ed && ed.kind === 'premiere' ? (S.cfg.premiere_mode || 'bin') : null };
  for (const k of ['kind', 'quality', 'audio_fmt', 'exact']) setCfg(k, opts[k]);
  setCfg('aspect', f.aspect);
  try {
    await api('export', { vid: meta.id, clips, opts });
  } catch (e) { return toast(e.message, 'error'); }
  toast(clips.length > 1 ? t('Exporting {n} clips', { n: clips.length }) : t('Export started'), 'info', { action: { label: t('Show'), fn: () => go('exports') } });
  if (E.clips.length) { E.clips = []; tl.set({ clips: [] }); ins.refresh(); ins.foot(); }
}

// ------------------------------------------------------------------ Tasten
function onKey(e) {
  if (S.page !== 'editor' || !E.meta) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const mod = e.ctrlKey || e.metaKey;
  let used = true;
  if (k === ' ') togglePlay();
  else if (mod && k === 'Enter') exportNow();
  else if (mod) used = false;
  else if (k === 'i') markEdge('a');
  else if (k === 'o') markEdge('b');
  else if (k === 'q') seek(E.a);
  else if (k === 'w') seek(E.b);
  else if (k === 'ArrowLeft' || k === 'ArrowRight') seek(E.t + (k === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 5 : e.altKey ? 1 / 30 : 1));
  else if (k === 'j') seek(E.t - 10);
  else if (k === 'l') seek(E.t + 10);
  else if (k === 'k') { if (E.playing) togglePlay(); }
  else if (k === 'a') addClip();
  else if (k === 's') snapshot();
  else if (k === 'm') toggleMute();
  else if (k === '+' || k === '=') tl.zoom(1 / 1.6, E.t);
  else if (k === '-') tl.zoom(1.6, E.t);
  else if (k === 'Home') seek(0);
  else if (k === 'End') seek(E.dur);
  else used = false;
  if (used) e.preventDefault();
}
