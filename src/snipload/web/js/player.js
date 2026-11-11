// Snipload – Wiedergabe im Editor.
// Reihenfolge der Versuche: YouTube-/Twitch-Einbettung -> direkte Videodatei -> Standbilder.
// Alle Varianten haben dieselben Methoden, damit der Editor nicht wissen muss, was gerade spielt.
import { h, frameUrl } from './core.js';

const WAIT = 9000;

function loadScript(src, ready, timeout = WAIT) {
  return new Promise((resolve, reject) => {
    if (ready()) return resolve();
    const s = document.createElement('script');
    const to = setTimeout(() => { s.remove(); reject(new Error('timeout ' + src)); }, timeout);
    s.src = src;
    s.async = true;
    s.onload = () => {
      const t0 = Date.now();
      (function poll() {
        if (ready()) { clearTimeout(to); resolve(); }
        else if (Date.now() - t0 > timeout) reject(new Error('not ready ' + src));
        else setTimeout(poll, 40);
      })();
    };
    s.onerror = () => { clearTimeout(to); s.remove(); reject(new Error('load ' + src)); };
    document.head.append(s);
  });
}

let hlsLoading = null;
function loadHls() {
  if (!hlsLoading) hlsLoading = loadScript('/app/js/vendor/hls.light.min.js', () => !!window.Hls).catch(e => { hlsLoading = null; throw e; });
  return hlsLoading;
}

/** Video-Element an eine Quelle haengen (Datei direkt, HLS nativ oder ueber hls.js). */
async function attachSource(video, url, kind) {
  if (kind !== 'hls') { video.src = url; return null; }
  if (video.canPlayType('application/vnd.apple.mpegurl')) { video.src = url; return null; }
  await loadHls();
  if (!window.Hls.isSupported()) throw new Error('hls unsupported');
  const hls = new window.Hls({ maxBufferLength: 12, maxMaxBufferLength: 20, startLevel: 0, capLevelToPlayerSize: true });
  hls.loadSource(url);
  hls.attachMedia(video);
  return hls;
}

function waitFor(video, timeout = WAIT) {
  return new Promise((resolve, reject) => {
    if (video.readyState >= 1) return resolve();
    const to = setTimeout(() => done(new Error('timeout')), timeout);
    const ok = () => done();
    const bad = () => done(new Error('media error'));
    function done(err) {
      clearTimeout(to);
      video.removeEventListener('loadedmetadata', ok);
      video.removeEventListener('error', bad);
      err ? reject(err) : resolve();
    }
    video.addEventListener('loadedmetadata', ok);
    video.addEventListener('error', bad);
  });
}

class Base {
  constructor(host, meta) {
    this.host = host;
    this.meta = meta;
    this.rate = 1;
    this.video = null;      // <video>, aus dem die 9:16-Vorschau zeichnen kann
    this.sound = true;
    this.onState = () => {};
    this.onFail = null;     // wird aufgerufen, wenn die Wiedergabe nachtraeglich scheitert (z. B. Einbetten verboten)
    this._raw = 0;
    this._at = 0;
  }
  /** Weiche Zeit zwischen den Meldungen des eingebetteten Players. */
  _smooth(raw, playing) {
    const now = performance.now();
    if (raw !== this._raw) { this._raw = raw; this._at = now; }
    return playing ? raw + Math.min(0.5, (now - this._at) / 1000) * this.rate : raw;
  }
  setRate(r) { this.rate = r; }
  setMuted() {}
  destroy() {}
}

// ------------------------------------------------------------------ YouTube
let ytLoading = null;
function loadYT() {
  if (!ytLoading) {
    ytLoading = new Promise((resolve, reject) => {
      if (window.YT && window.YT.Player) return resolve();
      const to = setTimeout(() => reject(new Error('yt timeout')), WAIT);
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => { clearTimeout(to); if (prev) prev(); resolve(); };
      const s = document.createElement('script');
      s.src = 'https://www.youtube.com/iframe_api';
      s.onerror = () => { clearTimeout(to); reject(new Error('yt load')); };
      document.head.append(s);
    }).catch(e => { ytLoading = null; throw e; });
  }
  return ytLoading;
}

class YouTubePlayer extends Base {
  constructor(host, meta) { super(host, meta); this.kind = 'youtube'; this.state = -1; this.want = false; this.primed = false; }
  async init(start) {
    await loadYT();
    const holder = h('div');
    this.host.append(holder);
    await new Promise((resolve, reject) => {
      const to = setTimeout(() => reject(new Error('yt ready timeout')), WAIT);
      this.p = new window.YT.Player(holder, {
        videoId: this.meta.embed.id, width: '100%', height: '100%',
        playerVars: { autoplay: 0, controls: 0, disablekb: 1, fs: 0, rel: 0, iv_load_policy: 3, modestbranding: 1, playsinline: 1,
          origin: location.origin, start: Math.max(0, Math.floor(start || 0)) },
        events: {
          onReady: () => { clearTimeout(to); resolve(); },
          onStateChange: e => this._onState(e.data),
          onError: e => { clearTimeout(to); reject(new Error('yt error ' + e.data)); if (this.ready && this.onFail) this.onFail(e.data); },
        },
      });
    });
    this.ready = true;
    try { this.p.getIframe().setAttribute('tabindex', '-1'); } catch (_) { /* egal */ }
    // Einmal stumm anspielen: danach bleibt der Player beim Spulen pausiert und zeigt das Bild.
    this.p.mute();
    this.p.playVideo();
    setTimeout(() => { if (!this.primed) { this.primed = true; if (!this.want) this.p.pauseVideo(); if (!this.muted) this.p.unMute(); } }, 4000);
  }
  _onState(s) {
    this.state = s;
    if (!this.primed && s === 1) {
      this.primed = true;
      if (!this.want) this.p.pauseVideo();
      if (!this.muted) this.p.unMute();
      return;
    }
    if (s === 1 && !this.want) { this.p.pauseVideo(); return; }
    if (s === 0) this.want = false;          // Video zu Ende
    this.onState(this.playing);
  }
  get time() { try { return this._smooth(this.p.getCurrentTime() || 0, this.state === 1); } catch (_) { return this._raw; } }
  get playing() { return this.want; }
  play() { this.want = true; try { this.p.playVideo(); } catch (_) { /* egal */ } }
  pause() { this.want = false; try { this.p.pauseVideo(); } catch (_) { /* egal */ } }
  seek(t) { this._raw = t; this._at = performance.now(); try { this.p.seekTo(t, true); } catch (_) { /* egal */ } }
  setRate(r) {
    this.rate = r;
    try {
      const ok = this.p.getAvailablePlaybackRates() || [1];
      this.rate = ok.reduce((a, b) => (Math.abs(b - r) < Math.abs(a - r) ? b : a), 1);
      this.p.setPlaybackRate(this.rate);
    } catch (_) { /* egal */ }
  }
  setMuted(m) { this.muted = m; try { m ? this.p.mute() : this.p.unMute(); } catch (_) { /* egal */ } }
  destroy() { try { this.p.destroy(); } catch (_) { /* egal */ } }
}

// ------------------------------------------------------------------ Twitch
class TwitchPlayer extends Base {
  constructor(host, meta) { super(host, meta); this.kind = 'twitch'; this.want = false; }
  async init(start) {
    await loadScript('https://player.twitch.tv/js/embed/v1.js', () => !!(window.Twitch && window.Twitch.Player));
    const holder = h('div', { style: { width: '100%', height: '100%' } });
    this.host.append(holder);
    const T = window.Twitch.Player;
    const s = Math.max(0, Math.floor(start || 0));
    await new Promise((resolve, reject) => {
      const to = setTimeout(() => reject(new Error('twitch ready timeout')), WAIT + 4000);
      this.p = new T(holder, {
        video: String(this.meta.embed.video), parent: [location.hostname], autoplay: false, muted: false,
        time: `${Math.floor(s / 3600)}h${Math.floor((s % 3600) / 60)}m${s % 60}s`, width: '100%', height: '100%',
      });
      this.p.addEventListener(T.READY, () => { clearTimeout(to); resolve(); });
    });
    this.p.addEventListener(T.PLAYING, () => { if (!this.want) this.p.pause(); else this.onState(true); });
    this.p.addEventListener(T.PAUSE, () => { if (this.want) { this.want = false; this.onState(false); } });
    this.p.addEventListener(T.ENDED, () => { this.want = false; this.onState(false); });
    const frame = holder.querySelector('iframe');
    if (frame) frame.setAttribute('tabindex', '-1');
    try { this.p.setVolume(1); } catch (_) { /* egal */ }
  }
  get time() { try { return this._smooth(this.p.getCurrentTime() || 0, this.want && !this.p.isPaused()); } catch (_) { return this._raw; } }
  get playing() { return this.want; }
  play() { this.want = true; try { this.p.play(); } catch (_) { /* egal */ } }
  pause() { this.want = false; try { this.p.pause(); } catch (_) { /* egal */ } }
  seek(t) { this._raw = t; this._at = performance.now(); try { this.p.seek(t); } catch (_) { /* egal */ } }
  setMuted(m) { try { this.p.setMuted(!!m); } catch (_) { /* egal */ } }
  destroy() { try { this.p.destroy && this.p.destroy(); } catch (_) { /* egal */ } }
}

// ------------------------------------------------------------------ Direkte Videodatei
class VideoPlayer extends Base {
  constructor(host, meta, src) { super(host, meta); this.kind = 'video'; this.src = src; this.sound = !!src.audio; }
  async init(start) {
    const v = h('video', { playsInline: true, preload: 'auto' });
    v.disablePictureInPicture = true;
    this.video = v;
    this.host.append(v);
    this.hls = await attachSource(v, this.src.url, this.src.kind);
    await waitFor(v, WAIT + 3000);
    if (start) v.currentTime = start;
    v.addEventListener('play', () => this.onState(true));
    v.addEventListener('pause', () => this.onState(false));
  }
  get time() { return this.video.currentTime || 0; }
  get playing() { return !this.video.paused && !this.video.ended; }
  play() { const p = this.video.play(); if (p && p.catch) p.catch(() => {}); }
  pause() { this.video.pause(); }
  seek(t) { try { this.video.currentTime = t; } catch (_) { /* egal */ } }
  setRate(r) { this.rate = r; this.video.playbackRate = r; }
  setMuted(m) { this.video.muted = !!m; }
  destroy() {
    try { if (this.hls) this.hls.destroy(); } catch (_) { /* egal */ }
    try { this.video.pause(); this.video.removeAttribute('src'); this.video.load(); } catch (_) { /* egal */ }
  }
}

// ------------------------------------------------------------------ Standbilder (funktioniert immer, ohne Ton)
class StillsPlayer extends Base {
  constructor(host, meta) { super(host, meta); this.kind = 'stills'; this.sound = false; this.t = 0; this.on = false; this.busy = false; this.shown = -1; }
  async init(start) {
    this.img = h('img.still', { alt: '' });
    this.host.append(this.img);
    this.t = start || 0;
    this._load();
  }
  _load() {
    if (this.busy || this.dead) return;
    const want = Math.round(this.time * (this.on ? 1 : 10)) / (this.on ? 1 : 10);
    if (want === this.shown) return;
    this.busy = true;
    const pic = new Image();
    const done = ok => {
      this.busy = false;
      if (this.dead) return;
      if (ok) { this.img.src = pic.src; this.img.classList.add('ok'); }
      this.shown = want;
      if (Math.abs(this.time - want) > (this.on ? 0.9 : 0.05)) this._load();
    };
    pic.onload = () => done(true);
    pic.onerror = () => done(false);
    pic.src = frameUrl(this.meta.id, want, 960);
  }
  get time() { return this.on ? Math.min(this.meta.duration || 1e9, this.t + (performance.now() - this.at) / 1000 * this.rate) : this.t; }
  get playing() { return this.on; }
  play() { if (this.on) return; this.at = performance.now(); this.on = true; this.onState(true); this._tick(); }
  _tick() { if (!this.on || this.dead) return; this._load(); setTimeout(() => this._tick(), 400); }
  pause() { if (!this.on) return; this.t = this.time; this.on = false; this.onState(false); this._load(); }
  seek(t) { this.t = t; this.at = performance.now(); this._load(); }
  setRate(r) { this.t = this.time; this.at = performance.now(); this.rate = r; }
  destroy() { this.dead = true; }
}

/** Probiert die Wiedergabearten der Reihe nach durch und liefert die erste, die funktioniert. */
export async function createPlayer(host, meta, start, skip = []) {
  const e = meta.embed || {};
  const tries = [];
  if (e.type === 'youtube' && e.id && !skip.includes('youtube')) tries.push(() => new YouTubePlayer(host, meta));
  if (e.type === 'twitch' && e.video && !skip.includes('twitch')) tries.push(() => new TwitchPlayer(host, meta));
  if (e.type === 'direct' && e.src) tries.push(() => new VideoPlayer(host, meta, { url: e.src, kind: 'file', audio: true }));
  if (meta.preview_src && !(e.type === 'direct' && e.src === meta.preview_src.url)) tries.push(() => new VideoPlayer(host, meta, meta.preview_src));
  tries.push(() => new StillsPlayer(host, meta));
  for (const make of tries) {
    const p = make();
    try {
      await p.init(start);
      return p;
    } catch (err) {
      console.warn('[Snipload] player', p.kind, String(err && err.message || err));
      p.destroy();
      host.replaceChildren();
    }
  }
  throw new Error('no player');
}

// ------------------------------------------------------------------ Bildquelle fuer die Ergebnis-Vorschau
/**
 * Liefert zu jeder Zeit ein zeichenbares Bild des Videos: das <video> des Players, ein eigenes stummes
 * <video> (laeuft synchron mit) oder – wenn beides nicht geht – Standbilder.
 */
export class FrameFeed {
  constructor(meta, player) {
    this.meta = meta;
    this.player = player;
    this.mode = 'stills';
    this.video = null;
    this.still = null;
    this.cache = new Map();
    this.busy = false;
    this.want = null;
    this.version = 0;         // zaehlt hoch, sobald ein neues Bild da ist
  }
  async init() {
    if (this.player && this.player.video) { this.mode = 'player'; this.video = this.player.video; return; }
    const src = this.meta.preview_src;
    if (src) {
      const v = document.createElement('video');
      v.muted = true; v.playsInline = true; v.preload = 'auto';
      try {
        this.hls = await attachSource(v, src.url, src.kind);
        await waitFor(v, 7000);
        if (this.dead) return;
        this.video = v;
        this.mode = 'video';
        v.addEventListener('error', () => { if (this.mode === 'video') { this.mode = 'stills'; this.video = null; } });
        return;
      } catch (err) {
        console.warn('[Snipload] preview feed', String(err && err.message || err));
        try { if (this.hls) this.hls.destroy(); } catch (_) { /* egal */ }
      }
    }
    this.mode = 'stills';
  }
  /** In jedem Bild aufrufen: haelt das Vorschau-Video synchron bzw. laedt das passende Standbild. */
  sync(t, playing, rate) {
    if (this.dead) return;
    if (this.mode === 'video' && this.video) {
      const v = this.video;
      if (v.playbackRate !== rate) v.playbackRate = rate;
      const drift = Math.abs(v.currentTime - t);
      if (playing) {
        if (v.paused) { const p = v.play(); if (p && p.catch) p.catch(() => {}); }
        if (drift > 0.4 && !v.seeking) v.currentTime = t;
      } else {
        if (!v.paused) v.pause();
        if (drift > 0.04 && !v.seeking) v.currentTime = t;
      }
    } else if (this.mode === 'stills') {
      const step = playing ? 1 : 0.1;
      const key = (Math.round(t / step) * step).toFixed(1);
      if (this.cache.has(key)) { this._show(this.cache.get(key)); return; }
      this.want = key;
      if (!this.busy) this._fetch();
    }
  }
  _show(pic) { if (this.still !== pic) { this.still = pic; this.version++; } }
  _fetch() {
    const key = this.want;
    if (key == null || this.dead) return;
    this.busy = true;
    const pic = new Image();
    const done = ok => {
      this.busy = false;
      if (this.dead) return;
      if (ok) {
        this.cache.set(key, pic);
        if (this.cache.size > 48) this.cache.delete(this.cache.keys().next().value);
        this._show(pic);
      }
      if (this.want !== key) this._fetch(); else this.want = null;
    };
    pic.onload = () => done(true);
    pic.onerror = () => done(false);
    pic.src = frameUrl(this.meta.id, Number(key), 640);
  }
  /** Zeichenbares Element (oder null, solange noch nichts da ist). */
  get drawable() {
    if (this.video && this.video.readyState >= 2 && this.video.videoWidth) return this.video;
    return this.still;
  }
  get size() {
    const d = this.drawable;
    if (!d) return null;
    return d.videoWidth ? { w: d.videoWidth, h: d.videoHeight } : { w: d.naturalWidth, h: d.naturalHeight };
  }
  destroy() {
    this.dead = true;
    try { if (this.hls) this.hls.destroy(); } catch (_) { /* egal */ }
    if (this.mode === 'video' && this.video) { try { this.video.pause(); this.video.removeAttribute('src'); this.video.load(); } catch (_) { /* egal */ } }
    this.cache.clear();
  }
}
