// Snipload – Inspector des Editors: Format, Untertitel, Chat, Verbessern, Export.
import { S, api, runTask, t, h, icon, clear, toast, modal, Btn, busy, Switch, Seg, Select, Swatch, SliderRow, Row, Sec, Note, clock, span, setCfg, debounce, pathText } from './core.js';
import { ensureFont, outputSize } from './preview.js';

const TABS = [['format', 'crop', 'Format'], ['captions', 'captions', 'Captions'], ['chat', 'message-square', 'Chat'], ['enhance', 'wand-sparkles', 'Enhance'], ['export', 'download', 'Export']];
const FORMATS = [['original', 'Original'], ['crop916', 'Vertical'], ['blur916', 'Vertical, full picture'], ['facecam', 'Gameplay and facecam'], ['facecam_raw', 'Facecam only']];
const FORMAT_SHORT = { original: 'Original', crop916: 'Vertical 9:16', blur916: 'Vertical 9:16 with blur', facecam: 'Gameplay and facecam 9:16', facecam_raw: 'Facecam only' };
const ART = {
  original: '<rect class="f" x="4" y="9" width="36" height="22" rx="3"/>',
  crop916: '<rect class="o" x="2.75" y="9.75" width="38.5" height="20.5" rx="3"/><rect class="f" x="14" y="2" width="16" height="36" rx="3"/>',
  blur916: '<rect class="d" x="12" y="2" width="20" height="36" rx="3"/><rect class="f" x="12" y="14" width="20" height="12"/>',
  facecam: '<rect class="f" x="12" y="2" width="20" height="13" rx="3"/><rect class="f" x="12" y="17" width="20" height="21" rx="3"/>',
  facecam_raw: '<rect class="o" x="2.75" y="7.75" width="38.5" height="24.5" rx="3"/><rect class="f" x="25" y="11" width="13" height="10" rx="2"/>',
};
const LANGS = [['auto', null], ['en', 'English'], ['de', 'Deutsch'], ['es', 'Español'], ['fr', 'Français'], ['pt', 'Português'], ['it', 'Italiano'], ['nl', 'Nederlands'], ['pl', 'Polski'],
  ['tr', 'Türkçe'], ['ru', 'Русский'], ['uk', 'Українська'], ['ja', '日本語'], ['ko', '한국어'], ['zh', '中文'], ['ar', 'العربية'], ['hi', 'हिन्दी']];
const PRESET_NAMES = { bold: 'Bold', hormozi: 'Punch', beast: 'Beast', karaoke: 'Karaoke', boxed: 'Boxed', clean: 'Clean', cinema: 'Cinema', comic: 'Comic' };

function art(id) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 44 40');
  s.setAttribute('class', 'art');
  s.innerHTML = ART[id] || '';
  return s;
}
const pct = v => Math.round(v) + ' %';
const signed = v => (v > 0 ? '+' : '') + Math.round(v);

export function buildInspector(E, A) {
  let cur = 'format';
  const tabEls = {};
  const body = h('div.ins-body');
  const sum = h('div.ins-sum');
  const exportBtn = Btn(t('Export'), { kind: 'play', lg: true, block: true, icon: 'download', key: 'Ctrl+Enter', onclick: () => busy(exportBtn, A.exportNow) });
  const el = h('aside.ins',
    h('div.ins-tabs', TABS.map(([id, ic, label]) => (tabEls[id] = h('button.ins-tab', { type: 'button', onclick: () => show(id) }, icon(ic), h('span', t(label)))))),
    body, h('div.ins-foot', sum, exportBtn));
  const tasks = {};
  let capList = null, capNow = null, nameInput = null;

  function show(id) { cur = id; refresh(true); }
  function refresh(top) {
    const y = top ? 0 : body.scrollTop;
    for (const [id] of TABS) tabEls[id].classList.toggle('on', id === cur);
    capList = null; nameInput = null;
    clear(body, { format: tabFormat, captions: tabCaptions, chat: tabChat, enhance: tabEnhance, export: tabExport }[cur]());
    body.scrollTop = y;
    dots();
  }
  const refreshSoon = debounce(() => { if (!body.querySelector(':active')) refresh(); }, 250);
  function dots() {
    const on = { captions: E.cap.on && E.cap.words.length > 0, chat: (E.chat.burn || E.chat.alpha) && E.chat.messages.length > 0,
      enhance: E.fx.speed !== 1 || E.fx.brightness || E.fx.contrast || E.fx.saturation || E.fx.sharpen || E.fx.volume_db || E.fx.normalize || E.fx.mute || E.fx.fade_in || E.fx.fade_out || E.fx.fps || E.fx.up_target };
    for (const [id] of TABS) {
      const old = tabEls[id].querySelector('.dot');
      if (on[id] && !old) tabEls[id].append(h('i.dot'));
      if (!on[id] && old) old.remove();
    }
  }

  // ---------------------------------------------------------------- laufende Arbeiten (mit Abbrechen)
  function taskUI(kind) {
    const st = tasks[kind];
    if (!st) return null;
    const label = h('div.task-label.grow', st.label || t('Starting…'));
    const bar = h('i');
    const prog = h('div.progress', bar);
    st.paint = () => {
      label.textContent = st.label || t('Starting…');
      prog.classList.toggle('wait', !st.progress);
      bar.style.width = Math.round((st.progress || 0) * 100) + '%';
    };
    st.paint();
    return h('div.task-row', h('div.hstack', label, Btn(t('Cancel'), { sm: true, kind: 'ghost', onclick: () => st.handle.cancel && st.handle.cancel() })), prog);
  }
  async function runUI(kind, fn) {
    if (tasks[kind]) return null;
    const meta = E.meta;
    const st = tasks[kind] = { label: '', progress: 0, handle: {} };
    refresh();
    try {
      return await fn(d => { st.label = d.label || st.label; st.progress = d.progress || 0; if (st.paint) st.paint(); }, st.handle);
    } catch (e) {
      if (!e.cancelled) toast(e.message, 'error');
      return null;
    } finally {
      delete tasks[kind];
      if (E.meta === meta) refresh();
    }
  }

  // ---------------------------------------------------------------- Format
  function tabFormat() {
    const f = E.fmt;
    const out = [];
    if (E.out.kind === 'audio') out.push(Note('info', t('You are exporting sound only, so the picture format doesn’t matter. Change this on the Export tab.')));
    out.push(Sec(null, h('div.fmt-grid', FORMATS.map(([id, label]) => h('button.fmt' + (f.aspect === id ? '.on' : ''), { type: 'button', onclick: () => { f.aspect = id; A.changed('format'); refresh(); } }, art(id), h('span', t(label)))))));
    if (f.aspect === 'crop916') {
      out.push(Sec(t('Crop'),
        SliderRow(t('Position'), { min: 0, max: 100, value: Math.round(f.crop_x * 100), format: pct, reset: 50, onInput: v => { f.crop_x = v / 100; A.changed('draw'); } }),
        h('p.hint', t('You can also drag the frame in the picture, or the result itself.'))));
    } else if (f.aspect === 'blur916') {
      out.push(h('p.hint', t('The whole picture stays visible. The space above and below is filled with a blurred copy of the video.')));
    } else if (f.aspect === 'facecam' || f.aspect === 'facecam_raw') {
      out.push(camSection(f));
    }
    return out;
  }
  function camSection(f) {
    const kids = [];
    if (tasks.cam) kids.push(taskUI('cam'));
    else {
      kids.push(h('div.hstack.wrap',
        Btn(f.cam ? t('Find it again') : t('Find the facecam'), { kind: f.cam ? '' : 'primary', icon: 'scan-face', onclick: () => runUI('cam', A.detectFacecam) }),
        f.cam ? null : Btn(t('Draw it myself'), { kind: 'ghost', icon: 'crop', onclick: () => { f.detect = null; A.setCam([0.7, 0.05, 0.27, 0.3]); A.changed('format'); refresh(); } })));
      if (f.detect && f.detect.message) kids.push(h('div', { style: { marginTop: '10px' } }, Note(f.detect.ok && !f.detect.fullscreen ? 'ok' : 'warn', f.detect.message)));
      else if (!f.cam) kids.push(h('p.hint', { style: { marginTop: '10px' } }, t('Snipload looks at ten frames of your clip and finds the camera on its own. You can adjust the frame afterwards.')));
    }
    const out = [Sec(t('Facecam'), kids)];
    if (f.cam && f.aspect === 'facecam' && f.layout) {
      const L = f.layout;
      const upd = (k, v) => { L[k] = v; A.changed('draw'); A.rememberSizes(); };
      out.push(Sec(h('span.grow', t('Layout')),
        SliderRow(t('Facecam height'), { min: 18, max: 65, value: Math.round(L.split * 100), format: pct, onInput: v => upd('split', v / 100) }),
        SliderRow(t('Gameplay zoom'), { min: 30, max: 300, value: Math.round((L.gzoom || 1) * 100), format: pct, reset: 100, onInput: v => upd('gzoom', v / 100) }),
        SliderRow(t('Facecam zoom'), { min: 30, max: 300, value: Math.round((L.czoom || 1) * 100), format: pct, reset: 100, onInput: v => upd('czoom', v / 100) }),
        Row(t('Facecam at the bottom'), Switch(!!L.cam_bottom, v => upd('cam_bottom', v))),
        Row(t('Remember this layout'), Switch(f.remember, v => { f.remember = v; if (v) A.rememberSizes(); else setCfg('fc_sizes', null); }), { hint: t('Use the same sizes for your next videos') }),
        h('p.hint', t('Tip: drag inside the result to move the picture, scroll to zoom, and drag the border between the two parts.'))));
    }
    if (f.cam) out.push(Sec(null, Row(t('Also keep the uncropped clip'), Switch(f.also_full, v => { f.also_full = v; setCfg('also_full', v); }))));
    return out;
  }

  // ---------------------------------------------------------------- Untertitel
  function capRange() {
    const list = E.clips.length ? E.clips.concat([{ a: E.a, b: E.b }]) : [{ a: E.a, b: E.b }];
    return [Math.min(...list.map(c => c.a)), Math.max(...list.map(c => c.b))];
  }
  async function createCaps() {
    const c = E.cap, meta = E.meta;
    const [a, b] = capRange();
    setCfg('caption_model', c.model);
    setCfg('caption_lang', c.lang);
    const res = await runUI('caps', (onP, handle) => runTask('captions_generate', { vid: meta.id, start: a, end: b, source: c.source, model: c.model, lang: c.lang, translate: c.translate }, onP, handle));
    if (!res || E.meta !== meta) return;
    c.words = (res.words || []).map(w => ({ w: w.w, t0: w.t0 + a, t1: w.t1 + a }));
    c.range = [a, b];
    c.on = c.words.length > 0;
    if (!c.words.length) toast(t('No speech found in this part of the video.'), 'warn');
    A.changed('caps');
    refresh();
  }
  function tabCaptions() {
    const c = E.cap, st = c.style;
    if (E.out.kind === 'audio') return [Note('info', t('Captions are for video exports. You are exporting sound only.'))];
    if (tasks.caps) return [taskUI('caps'), h('p.hint', { style: { marginTop: '12px' } }, t('You can keep working while the captions are created.'))];
    if (!c.words.length) {
      const srcs = [['ai', t('AI transcription (works with every video)')]].concat((E.meta.captions || []).map(s => [s.id, t('YouTube subtitles: {name}', { name: s.name }) + (s.auto ? ' ' + t('(automatic)') : '')]));
      const kids = [Row(t('From'), Select(srcs, c.source, v => { c.source = v; refresh(); }), { stack: true })];
      if (c.source === 'ai') {
        const mdl = (S.whisper && S.whisper.models) || {};
        kids.push(Row(t('Accuracy'), Seg([['fast', t('Fast')], ['balanced', t('Balanced')], ['best', t('Best')]], c.model, v => { c.model = v; refresh(); }, { block: true }), { stack: true }),
          Row(t('Spoken language'), Select(LANGS.map(([k, n]) => [k, n || t('Detect automatically')]), c.lang, v => { c.lang = v; })),
          Row(t('Translate to English'), Switch(c.translate, v => { c.translate = v; })));
        const m = mdl[c.model];
        if (m && !(S.whisper.engine && m.ready)) kids.push(h('p.hint', t('The speech model ({mb} MB) is downloaded once. Everything runs on your PC, nothing is uploaded.', { mb: m.mb })));
      }
      kids.push(h('div', { style: { marginTop: '12px' } }, Btn(t('Create captions for this clip'), { kind: 'primary', icon: 'captions', block: true, onclick: createCaps })));
      return [h('p.hint', { style: { marginBottom: '6px' } }, t('Animated captions like in Premiere or CapCut: word by word, in your font and colors.')), Sec(null, kids)];
    }
    const upd = (k, v, redo) => { st[k] = v; st.preset = 'custom'; A.changed('caps'); if (redo) refresh(); };
    const out = [];
    const [ra, rb] = capRange();
    if (c.range && (ra < c.range[0] - 0.05 || rb > c.range[1] + 0.05)) {
      out.push(Note('warn', t('Your clip now reaches beyond the captions.'), ' ', h('button.link-btn', { type: 'button', onclick: createCaps }, t('Create them again'))));
    }
    out.push(Sec(null, Row(t('Show captions'), Switch(c.on, v => { c.on = v; A.changed('caps'); dots(); }))));
    // Vorlagen
    const presets = S.boot.presets || {};
    out.push(Sec(t('Style'), h('div.preset-grid', Object.keys(presets).map(name => {
      const p = presets[name];
      const hl = p.hl_mode === 'none' || p.hl_mode === 'box';
      const sample = h('span', { style: {
        fontFamily: `"${p.font}"`, color: hl ? p.color : p.hl_color, textTransform: p.uppercase ? 'uppercase' : 'none',
        webkitTextStroke: p.box ? '0' : `${Math.round(15 * p.outline / 100 * 2 * 10) / 10}px ${p.hl_mode === 'box' ? p.hl_color : p.outline_color}`,
        background: p.box ? 'rgba(0,0,0,.6)' : 'none', padding: p.box ? '2px 5px' : '0',
      } }, PRESET_NAMES[name] || name);
      return h('button.preset' + (st.preset === name ? '.on' : ''), { type: 'button', tip: t(PRESET_NAMES[name] || name),
        onclick: () => { c.style = Object.assign({}, p); A.changed('caps'); refresh(); } }, sample);
    }))));
    // Schrift
    const fontBtn = h('button.btn.font-btn', { type: 'button', onclick: fontPicker }, h('span.ellipsis', { style: { fontFamily: `"${st.font}"` } }, st.font), icon('chevron-down'));
    out.push(Sec(t('Text'),
      Row(t('Font'), fontBtn, { stack: true }),
      SliderRow(t('Size'), { min: 2, max: 14, step: 0.1, value: st.size, format: v => v.toFixed(1), onInput: v => upd('size', v) }),
      SliderRow(t('Position'), { min: 6, max: 94, value: st.pos, format: pct, onInput: v => upd('pos', v), tip: t('From the top of the picture. You can also drag the captions in the preview.') }),
      SliderRow(t('Words at once'), { min: 1, max: 8, value: st.words, onInput: v => upd('words', v) }),
      Row(t('Lines'), Seg([[1, '1'], [2, '2']], Number(st.lines) || 1, v => upd('lines', v))),
      Row(t('All caps'), Switch(!!st.uppercase, v => upd('uppercase', v))),
      SliderRow(t('Letter spacing'), { min: -2, max: 12, step: 0.5, value: Number(st.spacing) || 0, format: v => String(v), reset: 0, onInput: v => upd('spacing', v) })));
    // Farben
    const box = !!st.box;
    out.push(Sec(t('Colors'),
      h('div.swatch-set',
        h('div.swatch-item', Swatch(st.color, v => upd('color', v)), t('Text')),
        st.hl_mode !== 'none' ? h('div.swatch-item', Swatch(st.hl_color, v => upd('hl_color', v)), t('Spoken word')) : null,
        box ? h('div.swatch-item', Swatch(st.box_color, v => upd('box_color', v)), t('Box')) : h('div.swatch-item', Swatch(st.outline_color, v => upd('outline_color', v)), t('Outline')),
        box ? null : h('div.swatch-item', Swatch(st.shadow_color, v => upd('shadow_color', v)), t('Shadow'))),
      h('div', { style: { height: '8px' } }),
      Row(t('Spoken word'), Seg([['color', t('Color')], ['box', t('Glow')], ['scale', t('Grow')], ['none', t('Off')]], st.hl_mode || 'color', v => upd('hl_mode', v, true)), { stack: true }),
      Row(t('Box behind the text'), Switch(box, v => upd('box', v, true))),
      box ? SliderRow(t('Box opacity'), { min: 10, max: 100, value: Math.round((Number(st.box_opacity) || 0.6) * 100), format: pct, onInput: v => upd('box_opacity', v / 100) }) : [
        SliderRow(t('Outline'), { min: 0, max: 20, step: 0.5, value: Number(st.outline) || 0, format: v => String(v), onInput: v => upd('outline', v) }),
        SliderRow(t('Shadow'), { min: 0, max: 12, step: 0.5, value: Number(st.shadow) || 0, format: v => String(v), onInput: v => upd('shadow', v) })]));
    out.push(Sec(t('Motion'),
      Row(t('New words appear with'), Seg([['pop', t('Pop')], ['fade', t('Fade')], ['slide', t('Slide')], ['none', t('Cut')]], st.anim || 'pop', v => upd('anim', v)), { stack: true }),
      st.hl_mode !== 'none' ? Row(t('Spoken word bounces'), Switch(!!st.word_pop, v => upd('word_pop', v))) : null,
      st.hl_mode !== 'none' ? Row(t('Dim the words not yet spoken'), Switch(!!st.dim_upcoming, v => upd('dim_upcoming', v))) : null));
    // Text bearbeiten
    capList = h('div.cap-lines');
    capNow = null;
    paintCapList();
    out.push(Sec(h('span.grow', t('Words')), h('p.hint', { style: { marginBottom: '6px' } }, t('Click a line to fix a word. Click the time to jump there.')), capList));
    out.push(Sec(t('Save as'),
      Row(t('Part of the video'), Switch(c.burn, v => { c.burn = v; A.changed('caps'); })),
      Row(t('Separate .srt file'), Switch(c.srt, v => { c.srt = v; A.changed('caps'); }), { hint: t('For Premiere, CapCut or YouTube') }),
      h('div.hstack.wrap', { style: { marginTop: '10px' } },
        Btn(t('Check the exact look'), { sm: true, icon: 'eye', onclick: e => busy(e.currentTarget, exactLook) }),
        Btn(t('Start over'), { sm: true, kind: 'ghost', icon: 'rotate-ccw', onclick: () => { c.words = []; c.range = null; c.on = false; A.changed('caps'); refresh(true); } }))));
    return out;
  }
  function paintCapList() {
    if (!capList) return;
    if (capList.contains(document.activeElement)) return;
    const c = E.cap;
    const pages = A.capPages() || [];
    clear(capList, pages.map(pg => {
      const tx = h('div.tx', { contentEditable: 'plaintext-only', spellcheck: false }, pg.text);
      tx.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); tx.blur(); } if (e.key === 'Escape') { tx.textContent = pg.text; tx.blur(); } e.stopPropagation(); });
      tx.addEventListener('blur', () => {
        const words = tx.textContent.trim().split(/\s+/).filter(Boolean);
        const old = pg.flat;
        if (words.join(' ') === old.map(w => w.w).join(' ')) return;
        const i0 = c.words.indexOf(old[0]);
        if (i0 < 0) return;
        let fresh = [];
        if (words.length === old.length) fresh = old.map((w, i) => ({ w: words[i], t0: w.t0, t1: w.t1 }));
        else if (words.length) {
          const t0 = old[0].t0, t1 = old[old.length - 1].t1;
          const total = words.reduce((s, w) => s + w.length + 1, 0);
          let acc = 0;
          fresh = words.map(w => { const a = t0 + (t1 - t0) * acc / total; acc += w.length + 1; return { w, t0: a, t1: t0 + (t1 - t0) * acc / total }; });
        }
        c.words.splice(i0, old.length, ...fresh);
        A.changed('caps');
      });
      const row = h('div.cap-item', h('button.at', { type: 'button', onclick: () => A.seek(pg.t0 + 0.02) }, clock(pg.t0)), tx);
      row._pg = pg;
      return row;
    }));
    if (!pages.length) capList.append(h('p.hint', t('Captions are hidden.')));
    capNow = null;
  }
  async function exactLook() {
    const c = E.cap;
    const size = outputSize({ aspect: E.fmt.aspect, cam: E.fmt.cam }, E.meta, E.fx.up_target);
    const st = Object.assign({}, c.style);
    delete st.font_url;
    try {
      const url = await api('caption_preview', { vid: E.meta.id, t: E.t, words: c.words, style: st, width: Math.round(size.w), height: Math.round(size.h), offset: E.t });
      if (!url) throw new Error(t('Couldn’t render the preview.'));
      modal({ title: t('Exactly as it will be exported'), cls: size.w > size.h ? 'wide' : 'mid', body: h('img.exact-img', { src: url, alt: '' }) });
    } catch (e) { toast(e.message, 'error'); }
  }

  function fontPicker() {
    const c = E.cap;
    const search = h('input.field', { placeholder: t('Search fonts'), spellcheck: false, autofocus: true });
    const list = h('div.font-list');
    let fonts = (S.boot.bundled_fonts || []).map(f => ({ name: f.name, source: 'snipload' }));
    const seen = new Set(fonts.map(f => f.name));
    const io = new IntersectionObserver(entries => {
      for (const en of entries) {
        if (!en.isIntersecting) continue;
        io.unobserve(en.target);
        const f = en.target._font;
        ensureFont({ font: f.name, font_url: f.url }).then(() => { en.target.querySelector('.name').style.fontFamily = `"${f.name}", "Geist"`; });
      }
    }, { root: list, rootMargin: '200px' });
    const pick = f => {
      c.style.font = f.name;
      if (f.file) { c.style.font_file = f.file; c.style.font_url = f.url; } else { delete c.style.font_file; delete c.style.font_url; }
      c.style.preset = 'custom';
      A.changed('caps');
      refresh();
      m.close();
    };
    const paint = () => {
      const q = search.value.trim().toLowerCase();
      const groups = [['snipload', t('Made for captions')], ['user', t('Your font files')], ['system', t('Installed on this PC')]];
      const kids = [];
      for (const [src, label] of groups) {
        const rows = fonts.filter(f => f.source === src && (!q || f.name.toLowerCase().includes(q)));
        if (!rows.length) continue;
        kids.push(h('div.font-group', label));
        for (const f of rows.slice(0, 400)) {
          const row = h('button.font-row' + (c.style.font === f.name ? '.on' : ''), { type: 'button', onclick: () => pick(f) }, h('span.name.ellipsis', f.name));
          row._font = f;
          io.observe(row);
          kids.push(row);
        }
      }
      clear(list, kids.length ? kids : h('p.hint', { style: { padding: '24px 12px' } }, t('No font with this name.')));
    };
    const m = modal({
      title: t('Font'), cls: 'mid', pearl: true,
      body: [h('div.hstack', h('div.field-icon.grow', icon('search'), search),
        Btn(t('Add a font file'), { icon: 'plus', onclick: async () => {
          try {
            const f = await api('add_font');
            if (f) { fonts = fonts.filter(x => x.name !== f.name).concat([f]); toast(t('Added “{name}”', { name: f.name }), 'success'); pick(f); }
          } catch (e) { toast(e.message, 'error'); }
        } })), list],
      onClose: () => io.disconnect(),
    });
    search.addEventListener('input', paint);
    search.addEventListener('keydown', e => e.stopPropagation());
    paint();
    api('fonts').then(sys => { if (m.closed) return; fonts = fonts.concat((sys || []).filter(f => !seen.has(f.name))); paint(); }).catch(() => {});
  }

  // ---------------------------------------------------------------- Chat
  function tabChat() {
    const c = E.chat, st = c.style;
    if (E.out.kind === 'audio') return [Note('info', t('Chat is for video exports. You are exporting sound only.'))];
    if (!E.meta.chat) return [Note('info', t('This video has no chat replay. Chat works with Twitch VODs and with YouTube streams that have a chat replay.'))];
    const out = [];
    const upd = (k, v, redo) => { st[k] = v; A.changed('chat'); if (redo) refresh(); };
    const load = () => runUI('chat', A.loadChat).then(res => { if (res && !(res.messages || []).length) toast(t('Nobody wrote in the chat during this part.'), 'info'); });
    if (tasks.chat) out.push(taskUI('chat'));
    else if (!c.range) {
      out.push(h('p.hint', { style: { marginBottom: '12px' } }, t('Get the chat of your clip. Show it in the video, or save it as its own transparent video for Premiere, After Effects or CapCut.')),
        Btn(t('Load the chat of this clip'), { kind: 'primary', icon: 'message-square', block: true, onclick: load }));
    } else {
      const [ra, rb] = capRange();
      const stale = ra < c.range[0] - 0.05 || rb > c.range[1] + 0.05;
      out.push(Note(stale ? 'warn' : 'ok', stale ? t('Your clip now reaches beyond the loaded chat.') : t('{n} messages loaded', { n: c.messages.length }), ' ',
        h('button.link-btn', { type: 'button', onclick: load }, t('Load again'))));
    }
    if (c.range) {
      out.push(Sec(t('In the video'),
        Row(t('Show the chat in the video'), Switch(c.burn, v => {
          c.burn = v;
          if (v && !c.sized) {      // sinnvolle Startgroesse je nach Format: hochkant breiter, quer schmaler
            c.sized = true;
            const tall = E.fmt.aspect !== 'original' && E.fmt.aspect !== 'facecam_raw';
            c.w = tall ? 0.62 : 0.27;
            c.h = tall ? 0.26 : 0.5;
            c.style.font_size = tall ? 26 : 22;
          }
          A.changed('chat');
          refresh();
        })),
        c.burn ? [
          Row(t('Corner'), Seg([['tl', t('Top left')], ['tr', t('Top right')], ['bl', t('Bottom left')], ['br', t('Bottom right')]].map(([k, l]) => [k, l]), c.corner, v => { c.corner = v; A.changed('chat'); }, { block: true }), { stack: true }),
          SliderRow(t('Width'), { min: 15, max: 94, value: Math.round(c.w * 100), format: pct, onInput: v => { c.w = v / 100; A.changed('chat'); } }),
          SliderRow(t('Height'), { min: 10, max: 94, value: Math.round(c.h * 100), format: pct, onInput: v => { c.h = v / 100; A.changed('chat'); } })] : null));
      out.push(Sec(t('As its own file'),
        Select([['', t('Don’t save the chat separately')], ['mov', t('Transparent MOV (Premiere, After Effects, DaVinci)')], ['webm', t('Transparent WebM (CapCut, browsers)')], ['green', t('Green screen MP4 (works everywhere)')]],
          c.alpha, v => { c.alpha = v; A.changed('chat'); dots(); }, { style: { width: '100%' } }),
        c.alpha ? h('p.hint', { style: { marginTop: '8px' } }, t('The chat is saved next to your clip, with the same length. Put it on a track above the video.')) : null));
      const solid = st.bg === 'solid';
      out.push(Sec(t('Look'),
        SliderRow(t('Text size'), { min: 14, max: 40, value: Number(st.font_size) || 22, onInput: v => upd('font_size', v) }),
        Row(t('Bubble behind each message'), Switch(st.msg_bg !== false, v => upd('msg_bg', v, true))),
        Row(t('Dark panel behind the chat'), Switch(solid, v => upd('bg', v ? 'solid' : 'none', true))),
        (st.msg_bg !== false || solid) ? SliderRow(t('Darkness'), { min: 10, max: 100, value: Math.round((st.bg_opacity == null ? 0.55 : Number(st.bg_opacity)) * 100), format: pct, onInput: v => upd('bg_opacity', v / 100) }) : null,
        Row(t('Badges'), Switch(st.badges !== false, v => upd('badges', v))),
        Row(t('Emotes'), Switch(st.emotes !== false, v => upd('emotes', v))),
        Row(t('Colored names'), Switch(st.name_colors !== false, v => upd('name_colors', v))),
        SliderRow(t('Messages stay for'), { min: 0, max: 60, value: Number(st.max_age) || 0, format: v => (v ? t('{n} s', { n: v }) : t('Always')), onInput: v => upd('max_age', v) })));
    }
    out.push(Sec(t('Best moments'),
      tasks.hype ? taskUI('hype') : [
        h('p.hint', { style: { marginBottom: '10px' } }, E.chat.hype ? t('The busiest moments are marked on the timeline. Click one of the chips above the timeline to jump there.') : t('Snipload reads the whole chat and marks where it was busiest. That is usually where the best clips are.')),
        Btn(E.chat.hype ? t('Search again') : t('Find the best moments'), { icon: 'flame', sm: true, onclick: () => runUI('hype', A.findHype) })]));
    return out;
  }

  // ---------------------------------------------------------------- Verbessern
  function tabEnhance() {
    const fx = E.fx;
    const upd = (k, v) => { fx[k] = v; A.changed('fx'); dots(); };
    const out = [];
    out.push(Sec(t('Speed'), Seg([[0.5, '0.5×'], [0.75, '0.75×'], [1, '1×'], [1.25, '1.25×'], [1.5, '1.5×'], [2, '2×']], fx.speed, v => upd('speed', v), { block: true })));
    if (E.out.kind !== 'audio') {
      out.push(Sec(t('Picture'),
        SliderRow(t('Brightness'), { min: -100, max: 100, value: Math.round(fx.brightness * 100), format: signed, reset: 0, onInput: v => upd('brightness', v / 100) }),
        SliderRow(t('Contrast'), { min: -100, max: 100, value: Math.round(fx.contrast * 100), format: signed, reset: 0, onInput: v => upd('contrast', v / 100) }),
        SliderRow(t('Color'), { min: -100, max: 100, value: Math.round(fx.saturation * 100), format: signed, reset: 0, onInput: v => upd('saturation', v / 100) }),
        SliderRow(t('Sharpen'), { min: 0, max: 100, value: Math.round(fx.sharpen * 100), format: v => String(v), reset: 0, onInput: v => upd('sharpen', v / 100) })));
      const up = S.upscale || {};
      const engines = [['lanczos', t('Fast')], ['esrgan', t('AI (Real-ESRGAN)')]];
      if (up.topaz) engines.push(['topaz', 'Topaz Video AI']);
      if (fx.up_engine === 'topaz' && !up.topaz) fx.up_engine = 'lanczos';
      const kids = [Seg([[0, t('Off')], [1080, '1080p'], [1440, '1440p'], [2160, '4K']], fx.up_target, v => { upd('up_target', v); refresh(); }, { block: true })];
      if (fx.up_target) {
        kids.push(h('div', { style: { height: '6px' } }), Row(t('Method'), Seg(engines, fx.up_engine, v => { fx.up_engine = v; setCfg('upscale_engine', v); refresh(); })));
        if (fx.up_engine === 'esrgan') {
          if (tasks.esrgan) kids.push(taskUI('esrgan'));
          else if (!up.esrgan) kids.push(Note('warn', t('The AI upscaler is downloaded once (about 45 MB).'), ' ', h('button.link-btn', { type: 'button', onclick: () => runUI('esrgan', (onP, hd) => runTask('install_esrgan', {}, onP, hd)).then(r => { if (r) { S.upscale = r; refresh(); } }) }, t('Download now'))));
          else kids.push(h('p.hint', t('The AI redraws every frame. That looks much sharper, but takes a few minutes per minute of video.')));
        } else if (fx.up_engine === 'topaz') kids.push(h('p.hint', t('Uses the Topaz Video AI installed on this PC. You need to be signed in to Topaz.')));
        else kids.push(h('p.hint', t('Scales the picture up and sharpens it. Quick, and fine for most clips.')));
        if (!up.topaz) kids.push(h('p.hint', t('Topaz Video AI appears here as soon as it is installed.')));
      }
      out.push(Sec(t('Upscale'), kids));
      out.push(Sec(t('Frames per second'), Seg([[0, t('As in the video')], [30, '30'], [60, '60']], fx.fps, v => upd('fps', v), { block: true })));
    }
    out.push(Sec(t('Sound'),
      SliderRow(t('Volume'), { min: -20, max: 20, value: fx.volume_db, format: v => signed(v) + ' dB', reset: 0, onInput: v => upd('volume_db', v) }),
      Row(t('Even out the loudness'), Switch(fx.normalize, v => upd('normalize', v)), { hint: t('The usual level for Shorts, Reels and TikTok') }),
      E.out.kind !== 'audio' ? Row(t('Remove the sound'), Switch(fx.mute, v => upd('mute', v))) : null,
      SliderRow(t('Fade in'), { min: 0, max: 3, step: 0.1, value: fx.fade_in, format: v => t('{n} s', { n: v.toFixed(1) }), reset: 0, onInput: v => upd('fade_in', v) }),
      SliderRow(t('Fade out'), { min: 0, max: 3, step: 0.1, value: fx.fade_out, format: v => t('{n} s', { n: v.toFixed(1) }), reset: 0, onInput: v => upd('fade_out', v) })));
    return out;
  }

  // ---------------------------------------------------------------- Export
  const paintName = debounce(() => {
    const inp = nameInput, meta = E.meta;
    if (!inp || !meta) return;
    const whole = E.a <= 0.01 && E.b >= E.dur - 0.05;
    api('name_preview', { vid: meta.id, start: whole ? 0 : E.a, end: whole ? E.dur : E.b }).then(n => { if (inp.isConnected) inp.placeholder = n; }).catch(() => {});
  }, 200);
  function tabExport() {
    const o = E.out;
    const out = [];
    out.push(Sec(null, Seg([['video', t('Video'), 'film'], ['audio', t('Sound only'), 'music'], ['gif', 'GIF', 'image']], o.kind, v => { o.kind = v; A.changed('out'); refresh(); }, { block: true })));
    if (o.kind === 'video') {
      out.push(Sec(null,
        Row(t('Quality'), Select([['best', t('Best available')], ['2160', '2160p (4K)'], ['1440', '1440p'], ['1080', '1080p'], ['720', '720p'], ['480', '480p']], o.quality, v => { o.quality = v; foot(); })),
        Row(t('Cut exactly to the frame'), Switch(o.exact, v => { o.exact = v; }), { hint: t('Off is faster, but the clip can start a moment early') }),
        Row(t('Keep the file under'), Select([[0, t('No limit')], [10, '10 MB (Discord)'], [25, '25 MB'], [50, '50 MB'], [100, '100 MB'], [500, '500 MB']], o.size_mb, v => { o.size_mb = Number(v); foot(); })),
        Row(t('Smaller file (H.265)'), Switch(o.hevc, v => { o.hevc = v; }), { hint: t('Half the size, but some apps can’t open it') })));
    } else if (o.kind === 'audio') {
      out.push(Sec(null, Row(t('Format'), Seg([['mp3', 'MP3'], ['m4a', 'M4A'], ['wav', 'WAV']], o.audio_fmt, v => { o.audio_fmt = v; foot(); }))));
    } else {
      out.push(Sec(null,
        Row(t('Frames per second'), Seg([[10, '10'], [15, '15'], [24, '24']], o.gif_fps, v => { o.gif_fps = v; })),
        Row(t('Width'), Seg([[360, '360'], [480, '480'], [640, '640']], o.gif_width, v => { o.gif_width = v; })),
        h('p.hint', t('GIFs get big quickly. Keep them short, a few seconds work best.'))));
    }
    // Datei
    nameInput = h('input.field', { value: o.name, spellcheck: false, style: { width: '100%' }, 'aria-label': t('File name'), oninput: e => { o.name = e.target.value; } });
    nameInput.addEventListener('keydown', e => e.stopPropagation());
    paintName();
    const path = h('span.path.ellipsis', { tip: S.cfg.folder || '' }, pathText(S.cfg.folder));
    out.push(Sec(t('File'),
      Row(t('Name'), nameInput, { stack: true }),
      h('div.folder-row', icon('folder'), path,
        Btn(t('Change'), { sm: true, onclick: async () => { const p = await api('pick_folder').catch(() => null); if (p) { S.cfg.folder = p; path.textContent = pathText(p); path.dataset.tip = p; } } }))));
    // Clips
    const clipKids = E.clips.map((c, i) => h('div.clip-item' + (Math.abs(c.a - E.a) < 0.05 && Math.abs(c.b - E.b) < 0.05 ? '.on' : ''),
      h('span.n', String(i + 1)),
      h('button.r', { type: 'button', onclick: () => A.setRange(c.a, c.b) }, clock(c.a) + ' – ' + clock(c.b)),
      h('span.l', span(c.b - c.a)),
      Btn('', { icon: 'x', kind: 'ghost', sm: true, tip: t('Remove'), onclick: () => A.removeClip(i) })));
    out.push(Sec(t('Several clips at once'),
      clipKids.length ? h('div.clip-list', { style: { marginBottom: '8px' } }, clipKids) : h('p.hint', { style: { marginBottom: '8px' } }, t('Pick a part, add it to the list, pick the next one. All clips are exported with the same settings.')),
      Btn(t('Add the current clip'), { sm: true, icon: 'list-plus', key: 'A', onclick: A.addClip })));
    // Schnittprogramm
    const eds = S.editors || [];
    const sel = eds.find(e => e.id === S.cfg.open_in);
    const edKids = [Select([['', t('Don’t open')]].concat(eds.map(e => [e.id, e.name])), sel ? sel.id : '', v => { setCfg('open_in', v || null); refresh(); foot(); }, { style: { width: '100%' } })];
    if (sel && sel.kind === 'premiere') {
      edKids.push(h('div', { style: { height: '8px' } }), Seg([['bin', t('Project bin')], ['timeline', t('At the playhead')], ['sequence', t('New sequence')]], S.cfg.premiere_mode || 'bin', v => setCfg('premiere_mode', v), { block: true }));
      edKids.push(h('p.hint', { style: { marginTop: '8px' } }, S.boot.premiere_bridge ? t('The clip appears in your open Premiere project by itself.') : t('The first time, Premiere needs one restart. After that every clip appears in your open project by itself.')));
    } else if (sel && sel.kind === 'aftereffects') edKids.push(h('p.hint', { style: { marginTop: '8px' } }, t('The clip is imported into After Effects and opened as a composition.')));
    else if (sel) edKids.push(h('p.hint', { style: { marginTop: '8px' } }, t('{name} opens and the clip is in your clipboard: press Ctrl+V in its media panel.', { name: sel.name })));
    else if (!eds.length) edKids.push(h('p.hint', { style: { marginTop: '8px' } }, t('No editing program found on this PC. You can add one in the settings.')));
    out.push(Sec(t('Then open in'), edKids));
    return out;
  }

  // ---------------------------------------------------------------- Fusszeile
  function foot() {
    const o = E.out, fx = E.fx;
    const parts = [];
    if (o.kind === 'audio') parts.push(t('Sound only') + ' (' + o.audio_fmt.toUpperCase() + ')');
    else {
      parts.push(t(FORMAT_SHORT[E.fmt.aspect] || 'Original'));
      if (o.kind === 'gif') parts.push('GIF');
      else parts.push(o.quality === 'best' ? t('best quality') : o.quality + 'p');
      if (E.cap.on && E.cap.words.length && (E.cap.burn || E.cap.srt)) parts.push(t('captions'));
      if ((E.chat.burn || E.chat.alpha) && E.chat.messages.length) parts.push(t('chat'));
      if (fx.up_target) parts.push(t('upscaled to {p}', { p: fx.up_target === 2160 ? '4K' : fx.up_target + 'p' }));
      if (o.kind === 'video' && o.size_mb) parts.push(t('under {n} MB', { n: o.size_mb }));
    }
    if (fx.speed !== 1) parts.push(fx.speed + '×');
    const n = E.clips.length;
    clear(sum, h('b', n ? t('{n} clips', { n }) : span((E.b - E.a) / (fx.speed || 1))), ', ' + parts.join(', '));
    const ed = (S.editors || []).find(e => e.id === S.cfg.open_in);
    const label = ed ? (n > 1 ? t('Export {n} clips to {name}', { n, name: ed.name }) : t('Export to {name}', { name: ed.name })) : (n > 1 ? t('Export {n} clips', { n }) : t('Export'));
    const sp = exportBtn.querySelector('span:not(.spin)');
    if (sp) sp.textContent = label;
    dots();
  }

  refresh(true);
  foot();
  return {
    el, show, refresh: () => refresh(false), refreshSoon, foot,
    capsChanged: () => { if (cur === 'captions') paintCapList(); dots(); },
    rangeChanged: () => { if (cur === 'export') { paintName(); refresh(); } else if ((cur === 'captions' && E.cap.words.length) || (cur === 'chat' && E.chat.range)) refresh(); },
    tick: time => {
      if (cur !== 'captions' || !capList) return;
      let now = null;
      for (const row of capList.children) { const pg = row._pg; if (pg && time >= pg.t0 && time < pg.t1) { now = row; break; } }
      if (now === capNow) return;
      if (capNow) capNow.classList.remove('now');
      capNow = now;
      if (now) {
        now.classList.add('now');
        if (E.playing && !capList.contains(document.activeElement)) {   // nur die Liste selbst rollen, nicht den ganzen Inspector
          const top = now.offsetTop - capList.offsetTop;
          if (top < capList.scrollTop || top + now.offsetHeight > capList.scrollTop + capList.clientHeight) capList.scrollTop = Math.max(0, top - capList.clientHeight / 2);
        }
      }
    },
  };
}
