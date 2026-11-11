// Snipload – "Finden": Link einfuegen, YouTube/Twitch durchsuchen, Kanaele oeffnen.
import { S, api, t, h, icon, img, clear, go, definePage, toast, menu, Btn, Seg, Empty, compact, ago, clock, setCfg } from './core.js';
import { openVideo } from './editor.js';

const V = { view: 'start', platform: 'youtube', query: '', kind: 'videos', channel: null, tab: null, req: 0 };
let root, input, clearBtn, body, platformSeg, headEl;

const TAB_LABELS = {
  videos: 'Videos', streams: 'Streams', shorts: 'Shorts', archives: 'Past broadcasts', highlights: 'Highlights', uploads: 'Uploads',
  clips_7d: 'Top clips this week', clips_30d: 'Top clips this month', clips_all: 'Top clips of all time',
};
const NAME = { youtube: 'YouTube', twitch: 'Twitch' };

export function initHome() {
  V.platform = S.cfg.platform === 'twitch' ? 'twitch' : 'youtube';
  root = document.getElementById('page-home');
  input = h('input', { type: 'text', spellcheck: false, autocomplete: 'off', 'aria-label': t('Search or paste a link') });
  clearBtn = Btn('', { icon: 'x', kind: 'ghost', sm: true, tip: t('Clear'), class: 'hidden', onclick: () => { input.value = ''; onType(); showStart(); input.focus(); } });
  platformSeg = Seg([['youtube', 'YouTube'], ['twitch', 'Twitch']], V.platform, p => {
    V.platform = p;
    setCfg('platform', p);
    paintPlaceholder();
    if (V.view === 'search' && V.query) runSearch(V.query, 'videos');
    input.focus();
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); openText(input.value); }
    if (e.key === 'Escape' && input.value) { e.stopPropagation(); input.value = ''; onType(); showStart(); }
  });
  input.addEventListener('input', onType);
  input.addEventListener('paste', () => setTimeout(() => {
    // eingefuegte Links sofort oeffnen – kein Enter noetig
    if (/^(https?:\/\/|www\.)\S+$/i.test(input.value.trim())) openText(input.value);
  }, 0));
  headEl = h('div.home-head',
    h('h1.home-title', t('What do you want to clip?')),
    h('div.home-bar', h('label.omni.lg', icon('search'), input, clearBtn), platformSeg));
  body = h('div.home-body');
  clear(root, h('div.home', headEl, body));
  paintPlaceholder();
  definePage('home', { show: arg => { if (arg && arg.fresh) showStart(); else if (V.view === 'start') showStart(); } });
}
function paintPlaceholder() {
  input.placeholder = V.platform === 'twitch' ? t('Paste a link or type a Twitch channel') : t('Paste a link or search YouTube');
}
function onType() { clearBtn.classList.toggle('hidden', !input.value); }
export function focusSearch() { if (S.page === 'home' && input) { input.focus(); input.select(); } }

/** Text aus dem Suchfeld, der Zwischenablage oder einem hineingezogenen Link verarbeiten. */
export async function openText(text) {
  text = (text || '').trim();
  if (!text) return;
  let r;
  try { r = await api('resolve', { text, platform: V.platform }); } catch (e) { return toast(e.message, 'error'); }
  if (r.kind === 'video') return openVideo(r.url);
  go('home');
  if (r.kind === 'channel') {
    V.platform = r.platform;
    platformSeg.set(r.platform);
    paintPlaceholder();
    return showChannel(r.platform, r.id);
  }
  input.value = r.query;
  onType();
  runSearch(r.query, 'videos');
}

// ------------------------------------------------------------------ Karten
function meta(parts) { return h('div.vcard-meta', parts.filter(Boolean).map(p => h('span', p))); }
function videoCard(it, o = {}) {
  const tags = [];
  if (it.live) tags.push(h('span.tag.live.tl', t('Live')));
  else if (it.upcoming) tags.push(h('span.tag.tl', t('Upcoming')));
  if (it.duration) tags.push(h('span.tag.br', clock(it.duration)));
  const card = h('button.vcard', {
    type: 'button', onclick: () => openVideo(it.url),
    oncontextmenu: e => {
      e.preventDefault();
      menu({ x: e.clientX, y: e.clientY }, [
        { label: t('Open in the editor'), icon: 'scissors', onClick: () => openVideo(it.url) },
        it.vod && { label: t('Open the full stream at this moment'), icon: 'history', onClick: () => openVideo(`https://www.twitch.tv/videos/${it.vod}?t=${Math.max(0, Math.floor(it.vod_offset || 0))}s`) },
        it.channel_url && { label: t('Go to the channel'), icon: 'user', onClick: () => openText(it.channel_url) },
        { label: t('Copy link'), icon: 'link', onClick: () => navigator.clipboard.writeText(it.url).then(() => toast(t('Link copied'), 'success')).catch(() => {}) },
        o.onRemove && '-',
        o.onRemove && { label: t('Remove from this list'), icon: 'x', onClick: o.onRemove },
      ]);
    },
  },
    h('div.thumb', img(it.thumb), tags),
    h('div.vcard-title', it.title || t('Untitled')),
    meta([o.hideChannel ? null : it.channel, it.game, it.views != null ? t('{n} views', { n: compact(it.views) }) : null, it.ts ? ago(it.ts) : null]));
  return card;
}
function channelCard(it) {
  return h('button.ccard', { type: 'button', onclick: () => showChannel(it.platform, it.platform === 'twitch' ? it.id : (it.url || it.id)) },
    h('span.avatar' + (it.live ? '.live' : ''), img(it.avatar)),
    h('span.ccard-text',
      h('span.ccard-name.ellipsis', it.title, it.verified ? icon('badge-check') : null),
      h('span.ccard-sub.ellipsis', it.live ? [h('span.tag.live', t('Live')), ' ', it.game || it.live_title || ''] :
        (it.followers != null ? t(it.platform === 'twitch' ? '{n} followers' : '{n} subscribers', { n: compact(it.followers) }) : (it.handle || '')))));
}
function skeleton(n = 8) {
  return h('div.grid', Array.from({ length: n }, () => h('div.vcard', h('div.thumb.skel'), h('div.skel.skel-line'), h('div.skel.skel-line.short'))));
}
function section(title, side, content) {
  return h('section.home-sec', h('div.home-sec-head', h('h2', title), side || null), content);
}
function setCompact(compactHead) { headEl.classList.toggle('compact', compactHead); }

// ------------------------------------------------------------------ Startansicht
export function showStart() {
  V.view = 'start';
  V.req++;
  const recent = S.cfg.recent || [];
  const favs = S.cfg.favorites || [];
  const empty = !recent.length && !favs.length;
  root.firstChild.classList.toggle('blank', empty);
  setCompact(false);
  clear(body);
  if (empty) {
    body.append(h('p.home-hint', t('Works with YouTube videos, streams and Shorts, and with Twitch VODs and clips. Copy a link and press Ctrl+V anywhere in Snipload to open it.')));
    return;
  }
  if (favs.length) {
    body.append(section(t('Saved channels'), null, h('div.fav-row', favs.map(f => h('button.fav', {
      type: 'button', onclick: () => showChannel(f.platform, f.platform === 'twitch' ? f.id : (f.url || f.id)),
      oncontextmenu: e => {
        e.preventDefault();
        menu({ x: e.clientX, y: e.clientY }, [{ label: t('Remove from saved channels'), icon: 'x', onClick: async () => { S.cfg.favorites = await api('favorites', { action: 'remove', item: f }); showStart(); } }]);
      },
    }, h('span.avatar', img(f.avatar)), h('span.ellipsis', f.title || f.handle || f.id))))));
  }
  if (recent.length) {
    body.append(section(t('Recently opened'), null, h('div.grid', recent.slice(0, 12).map(r => videoCard(r, {
      onRemove: () => { S.cfg.recent = (S.cfg.recent || []).filter(x => x.id !== r.id); setCfg('recent', S.cfg.recent); showStart(); },
    })))));
  }
}

// ------------------------------------------------------------------ Suche
async function runSearch(query, kind) {
  V.view = 'search';
  V.query = query;
  V.kind = kind;
  const req = ++V.req;
  root.firstChild.classList.remove('blank');
  setCompact(true);
  const tabs = V.platform === 'youtube' ? h('div.tabs', [['videos', 'Videos'], ['channels', 'Channels'], ['live', 'Live']].map(([k, label]) =>
    h('button', { type: 'button', class: k === kind ? 'on' : '', onclick: () => runSearch(query, k) }, t(label)))) : null;
  clear(body, tabs, skeleton());
  let items;
  try {
    items = (await api('search', { query, platform: V.platform, kind })).items || [];
  } catch (e) {
    if (req !== V.req) return;
    clear(body, tabs, Empty(t('The search didn’t work'), e.message, Btn(t('Try again'), { icon: 'refresh-cw', onclick: () => runSearch(query, kind) })));
    return;
  }
  if (req !== V.req) return;
  if (!items.length) {
    clear(body, tabs, Empty(t('Nothing found for “{q}”', { q: query }),
      V.platform === 'twitch' ? t('Twitch search finds channels. Type the name of a streamer, or paste a link to a VOD or clip.') : t('Check the spelling, or paste the link of the video instead.')));
    return;
  }
  const channels = items.filter(i => i.kind === 'channel');
  const videos = items.filter(i => i.kind !== 'channel');
  clear(body, tabs,
    channels.length ? h('div.cgrid', channels.map(channelCard)) : null,
    videos.length ? h('div.grid', videos.map(v => videoCard(v))) : null);
}

// ------------------------------------------------------------------ Kanal
async function showChannel(platform, id, tab) {
  V.view = 'channel';
  const req = ++V.req;
  root.firstChild.classList.remove('blank');
  setCompact(true);
  const back = Btn(t('Back'), { icon: 'arrow-left', kind: 'ghost', sm: true, onclick: () => (V.query ? runSearch(V.query, V.kind) : showStart()) });
  if (!V.channel || V.channel.key !== platform + ':' + id) clear(body, h('div.ch-back', back), h('div.ch-head', h('span.avatar.xl.skel'), h('div.grow', h('div.skel.skel-line', { style: { width: '220px', height: '22px' } }), h('div.skel.skel-line.short'))), skeleton());
  else { const g = body.querySelector('.ch-items'); if (g) clear(g, skeleton()); }
  let res;
  try {
    res = await api('channel', { platform, id, tab: tab || null });
  } catch (e) {
    if (req !== V.req) return;
    clear(body, h('div.ch-back', back), Empty(t('Couldn’t open this channel'), e.message, Btn(t('Try again'), { icon: 'refresh-cw', onclick: () => showChannel(platform, id, tab) })));
    return;
  }
  if (req !== V.req) return;
  const ch = res.channel || {};
  V.channel = { key: platform + ':' + id, ch };
  const isFav = () => (S.cfg.favorites || []).some(f => f.platform === ch.platform && f.id === ch.id);
  const favBtn = Btn('', { sm: true, onclick: async () => {
    const was = isFav();
    S.cfg.favorites = await api('favorites', { action: was ? 'remove' : 'add', item: { platform: ch.platform, id: ch.id, title: ch.title, avatar: ch.avatar, handle: ch.handle, url: ch.url } });
    paintFav();
    toast(was ? t('Removed from saved channels') : t('Saved. You’ll find the channel on the start page.'), 'success');
  } });
  const paintFav = () => { const on = isFav(); clear(favBtn, icon('star', on ? 'fill' : ''), h('span', on ? t('Saved') : t('Save channel'))); favBtn.classList.toggle('on', on); };
  paintFav();
  const sub = [ch.handle && (String(ch.handle).startsWith('@') || ch.platform !== 'youtube' ? ch.handle : '@' + ch.handle),
    ch.followers != null ? t(ch.platform === 'twitch' ? '{n} followers' : '{n} subscribers', { n: compact(ch.followers) }) : null].filter(Boolean);
  const head = h('div.ch-head',
    h('span.avatar.xl' + (ch.stream || ch.live ? '.live' : ''), img(ch.avatar)),
    h('div.grow', h('h2.ch-name', ch.title || id, ch.verified ? icon('badge-check') : null), h('div.vcard-meta', sub.map(s => h('span', s)))),
    favBtn,
    Btn(t('Open on {site}', { site: NAME[ch.platform] || 'the web' }), { sm: true, kind: 'ghost', icon: 'external-link', onclick: () => api('open_url', { url: ch.url }) }));
  let live = null;
  if (ch.stream) {
    const st = ch.stream;
    live = h('button.live-strip', { type: 'button', onclick: () => {
      if (st.vod) openVideo('https://www.twitch.tv/videos/' + st.vod);
      else toast(t('This stream has no recording yet. The streamer may have turned VODs off.'), 'warn');
    } },
      h('div.thumb', img(st.thumb), h('span.tag.live.tl', t('Live'))),
      h('div.grow', h('div.vcard-title', st.title || ''), meta([st.game, st.viewers != null ? t('{n} watching', { n: compact(st.viewers) }) : null])),
      h('span.live-go', t('Clip the running stream'), icon('arrow-right')));
  }
  const tabsEl = h('div.tabs', (res.tabs || []).map(k => h('button', { type: 'button', class: k === res.tab ? 'on' : '', onclick: () => showChannel(platform, id, k) }, t(TAB_LABELS[k] || k))));
  const items = res.items || [];
  const grid = h('div.ch-items', items.length ? h('div.grid', items.map(v => videoCard(v, { hideChannel: true }))) :
    Empty(t('Nothing here yet'), t('This channel has no {what}.', { what: t(TAB_LABELS[res.tab] || res.tab || '').toLowerCase() })));
  clear(body, h('div.ch-back', back), head, live, tabsEl, grid);
}
export { showChannel, runSearch };
