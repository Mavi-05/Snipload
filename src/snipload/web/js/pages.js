// Snipload – Exporte (Warteschlange), Bibliothek (fertige Clips) und Einstellungen.
import { S, api, on, runTask, t, h, icon, img, clear, go, definePage, toast, modal, ask, menu, Btn, busy, Switch, Seg, Select, Row, Sec, Empty, clock, bytes, ago, setCfg, debounce, pathText } from './core.js';
import { openVideo } from './editor.js';

// ================================================================== Gemeinsames: Clip an ein Schnittprogramm geben
function editorMenu(anchor, files, extra = []) {
  const eds = S.editors || [];
  const items = eds.map(e => ({ label: e.name, icon: 'send', hint: e.direct ? '' : t('Via clipboard'), onClick: () => api('send_to_editor', { editor: e.id, files }).catch(err => toast(err.message, 'error')) }));
  if (!items.length) items.push({ label: t('No editing program found'), disabled: true });
  menu(anchor, [{ heading: t('Open in') }, ...items, '-', { label: t('Add a program…'), icon: 'plus', onClick: () => go('settings') }, ...extra], { right: true });
}
const copyFile = path => api('copy_file', { path }).then(ok => toast(ok ? t('Copied. Press Ctrl+V in your editing program or in a chat.') : t('Copying files only works on Windows.'), ok ? 'success' : 'warn')).catch(e => toast(e.message, 'error'));

// ================================================================== Exporte
let exRoot, exList;
export function initExports() {
  exRoot = document.getElementById('page-exports');
  definePage('exports', { show: paintExports });
  on('jobs-changed', j => {
    if (S.page !== 'exports') return;
    const row = j && exList && exList.querySelector(`[data-id="${j.id}"]`);
    if (row) row.replaceWith(jobRow(j)); else paintExports();
  });
}
function paintExports() {
  const jobs = S.jobs.slice().reverse();
  const done = jobs.some(j => j.status !== 'running' && j.status !== 'waiting');
  exList = h('div.jobs', jobs.map(jobRow));
  clear(exRoot, h('div.narrow',
    h('div.page-head', h('div.grow', h('h1.page-title', t('Exports')),
      h('div.page-sub', S.cfg.folder ? [t('Saved in'), ' ', h('a', { onclick: () => api('open_file', { path: S.cfg.folder }).catch(e => toast(e.message, 'error')) }, S.cfg.folder)] : null)),
      done ? Btn(t('Clear finished'), { kind: 'ghost', icon: 'check', onclick: () => api('jobs_clear').catch(() => {}) }) : null),
    jobs.length ? exList : Empty(t('Nothing exported yet'), t('Cut a clip in the editor and press Export. You can follow the progress here.'), Btn(t('Find a video'), { kind: 'primary', icon: 'search', onclick: () => go('home') }))));
}
function jobRow(j) {
  const active = j.status === 'running' || j.status === 'waiting';
  let line, cls = '';
  if (j.status === 'waiting') line = t('Waiting for its turn');
  else if (j.status === 'running') line = [j.stage || t('Working…'), j.detail ? h('span.dim', ' ' + j.detail) : null];
  else if (j.status === 'done') {
    const bits = [(j.format || '').replace(/ · /g, ', '), bytes(j.size), (j.files || []).length > 1 ? t('{n} files', { n: j.files.length }) : null].filter(Boolean).join(', ');
    const ed = j.sent_to && (S.editors || []).find(e => e.id === j.sent_to);
    line = [bits, ed ? h('span.sent', icon('send'), t('Sent to {name}', { name: ed.name })) : null, j.hint === 'upscale_failed' ? h('span.dim', ' ' + t('AI upscaling didn’t work, the fast method was used instead.')) : null];
    cls = '.done';
  } else if (j.status === 'failed') { line = j.error || t('Something went wrong.'); cls = '.failed'; }
  else { line = t('Cancelled'); cls = '.off'; }
  const acts = [];
  if (active) acts.push(Btn(t('Cancel'), { kind: 'ghost', sm: true, onclick: () => api('job_cancel', { id: j.id }).catch(() => {}) }));
  else if (j.status === 'done' && j.file) {
    acts.push(Btn(t('Open in'), { sm: true, after: 'chevron-down', onclick: e => editorMenu(e.currentTarget, [j.file]) }),
      Btn('', { icon: 'play', kind: 'ghost', sm: true, tip: t('Play'), onclick: () => api('open_file', { path: j.file }).catch(e => toast(e.message, 'error')) }),
      Btn('', { icon: 'folder-open', kind: 'ghost', sm: true, tip: t('Show in folder'), onclick: () => api('reveal', { path: j.file }).catch(e => toast(e.message, 'error')) }),
      Btn('', { icon: 'copy', kind: 'ghost', sm: true, tip: t('Copy the file'), onclick: () => copyFile(j.file) }),
      Btn('', { icon: 'x', kind: 'ghost', sm: true, tip: t('Remove from this list'), onclick: () => api('job_remove', { id: j.id }).catch(() => {}) }));
  } else {
    acts.push(Btn(t('Try again'), { sm: true, icon: 'refresh-cw', onclick: () => api('job_retry', { id: j.id }).catch(e => toast(e.message, 'error')) }),
      Btn('', { icon: 'x', kind: 'ghost', sm: true, tip: t('Remove from this list'), onclick: () => api('job_remove', { id: j.id }).catch(() => {}) }));
  }
  return h('div.job' + cls, { data: { id: j.id } },
    h('div.thumb', img(j.thumb), j.end != null ? h('span.tag.br', clock(Math.max(0, (j.end || 0) - (j.start || 0)))) : null),
    h('div.job-main',
      h('div.job-name.ellipsis', j.name || j.title),
      h('div.job-line', line),
      active ? h('div.job-prog', h('div.progress' + (j.status === 'waiting' || !j.progress ? '.wait' : ''), h('i', { style: { width: Math.round((j.progress || 0) * 100) + '%' } })), j.status === 'running' ? h('span', Math.round((j.progress || 0) * 100) + ' %') : null) : null),
    h('div.job-acts', acts));
}

// ================================================================== Bibliothek
let libRoot, libItems = [], libQuery = '', libGrid;
export function initLibrary() {
  libRoot = document.getElementById('page-library');
  definePage('library', { show: loadLibrary });
  on('library', () => { if (S.page === 'library') loadLibrary(); });
}
async function loadLibrary() {
  try { libItems = await api('library'); } catch (e) { libItems = []; toast(e.message, 'error'); }
  paintLibrary();
}
function paintLibrary() {
  const search = h('input.field', { placeholder: t('Search your clips'), value: libQuery, spellcheck: false, style: { width: '240px' } });
  search.addEventListener('input', debounce(() => { libQuery = search.value; paintGrid(); }, 120));
  search.addEventListener('keydown', e => e.stopPropagation());
  libGrid = h('div');
  clear(libRoot, h('div.wide',
    h('div.page-head', h('div.grow', h('h1.page-title', t('Library')), h('div.page-sub', libItems.length ? t('{n} clips', { n: libItems.length }) : '')),
      libItems.length ? h('div.field-icon', icon('search'), search) : null,
      libItems.length ? Btn('', { icon: 'ellipsis', kind: 'ghost', tip: t('More'), onclick: e => menu(e.currentTarget, [
        { label: t('Clear the list (keeps your files)'), icon: 'trash-2', danger: true, onClick: async () => {
          if (await ask({ title: t('Clear the library?'), text: t('The list is emptied. Your video files stay where they are.'), ok: t('Clear'), danger: true })) { await api('library_clear'); loadLibrary(); }
        } }], { right: true }) }) : null),
    libGrid));
  paintGrid();
}
function paintGrid() {
  const q = libQuery.trim().toLowerCase();
  const items = libItems.filter(i => !q || (i.title || '').toLowerCase().includes(q) || (i.channel || '').toLowerCase().includes(q));
  if (!libItems.length) return clear(libGrid, Empty(t('Your clips will collect here'), t('Everything you export shows up in the library, ready to play, send to your editing program or clip again.'), Btn(t('Find a video'), { kind: 'primary', icon: 'search', onclick: () => go('home') })));
  if (!items.length) return clear(libGrid, Empty(t('No clip matches “{q}”', { q: libQuery }), ''));
  clear(libGrid, h('div.grid', items.map(libCard)));
}
function libActions(it, anchor, after) {
  const again = () => openVideo(it.url + (it.start ? (it.url.includes('?') ? '&' : '?') + 't=' + Math.floor(it.start) + 's' : ''));
  const files = [it.file].concat(it.files || []).filter(Boolean);
  menu(anchor, [
    it.exists && { heading: t('Open in') },
    ...(it.exists ? (S.editors || []).map(e => ({ label: e.name, icon: 'send', onClick: () => api('send_to_editor', { editor: e.id, files: [it.file] }).catch(err => toast(err.message, 'error')) })) : []),
    it.exists && (S.editors || []).length ? '-' : null,
    it.exists && { label: t('Play'), icon: 'play', onClick: () => api('open_file', { path: it.file }).catch(e => toast(e.message, 'error')) },
    it.exists && { label: t('Show in folder'), icon: 'folder-open', onClick: () => api('reveal', { path: it.file }).catch(e => toast(e.message, 'error')) },
    it.exists && { label: t('Copy the file'), icon: 'copy', onClick: () => copyFile(it.file) },
    it.url && { label: t('Clip this video again'), icon: 'scissors', onClick: again },
    '-',
    { label: t('Remove from the library'), icon: 'x', onClick: async () => { await api('library_remove', { file: it.file }); if (after) after(); loadLibrary(); } },
    it.exists && { label: files.length > 1 ? t('Delete the files') : t('Delete the file'), icon: 'trash-2', danger: true, onClick: async () => {
      if (!await ask({ title: t('Delete this clip?'), text: t('“{name}” is deleted from your PC. This can’t be undone.', { name: it.title }), ok: t('Delete'), danger: true })) return;
      try { await api('library_remove', { file: it.file, delete_file: true }); } catch (e) { toast(e.message, 'error'); }
      if (after) after();
      loadLibrary();
    } },
  ], { right: true });
}
function libCard(it) {
  const vertical = ['crop916', 'blur916', 'facecam'].includes(it.aspect);
  const thumb = h('div.thumb', img(it.thumb_url),
    it.duration ? h('span.tag.br', clock(it.duration)) : null,
    !it.exists ? h('span.tag.tl', t('File is gone')) : (it.kind === 'audio' ? h('span.tag.tl', icon('music')) : vertical ? h('span.tag.tl', '9:16') : null));
  const card = h('button.vcard' + (it.exists ? '' : '.gone'), { type: 'button',
    onclick: () => (it.exists ? libPlayer(it) : libActions(it, card)),
    oncontextmenu: e => { e.preventDefault(); libActions(it, { x: e.clientX, y: e.clientY }); } },
    thumb, h('div.vcard-title', it.title || t('Untitled')),
    h('div.vcard-meta', [(it.format || '').replace(/ · /g, ', '), bytes(it.size), it.ts ? ago(it.ts) : null].filter(Boolean).map(x => h('span', x))));
  // Beim Ueberfahren laeuft der Clip stumm an
  if (it.exists && it.file_url && it.kind !== 'audio' && !/\.gif$/i.test(it.file || '')) {
    let timer = 0, vid = null;
    card.addEventListener('mouseenter', () => { timer = setTimeout(() => {
      vid = h('video', { src: it.file_url, muted: true, loop: true, playsInline: true, preload: 'auto', style: { objectFit: vertical ? 'contain' : 'cover', background: '#000' } });
      thumb.insertBefore(vid, thumb.children[1] || null);
      const p = vid.play();
      if (p && p.catch) p.catch(() => {});
    }, 350); });
    card.addEventListener('mouseleave', () => { clearTimeout(timer); if (vid) { vid.pause(); vid.remove(); vid = null; } });
  }
  return card;
}
function libPlayer(it) {
  const isGif = /\.gif$/i.test(it.file || '');
  const media = it.kind === 'audio' ? h('audio.lib-audio', { src: it.file_url, controls: true, autoplay: true })
    : isGif ? h('img.lib-video', { src: it.file_url, alt: '' })
      : h('video.lib-video', { src: it.file_url, controls: true, autoplay: true, playsInline: true });
  const m = modal({
    title: it.title || '', cls: 'wide',
    body: [media, h('div.vcard-meta', { style: { marginTop: '10px' } }, [it.channel, (it.format || '').replace(/ · /g, ', '), bytes(it.size), it.ts ? ago(it.ts) : null].filter(Boolean).map(x => h('span', x)))],
    foot: [Btn(t('More'), { kind: 'ghost', after: 'chevron-down', onclick: e => libActions(it, e.currentTarget, () => m.close()) }),
      Btn(t('Show in folder'), { icon: 'folder-open', onclick: () => api('reveal', { path: it.file }).catch(e => toast(e.message, 'error')) }),
      Btn(t('Open in'), { kind: 'primary', after: 'chevron-down', onclick: e => editorMenu(e.currentTarget, [it.file]) })],
  });
}

// ================================================================== Einstellungen
let setRoot;
const setTasks = {};
export function initSettings() {
  setRoot = document.getElementById('page-settings');
  definePage('settings', { show: () => { paintSettings(); api('tools_status').catch(() => {}); api('editors').then(r => { S.editors = r.editors; S.boot.premiere_bridge = r.premiere_bridge; if (S.page === 'settings') paintSettings(); }).catch(() => {}); } });
  on('tools-changed', () => { if (S.page === 'settings') paintSettings(); });
  on('update-changed', () => { if (S.page === 'settings') paintSettings(); });
}
function taskLine(key) {
  const st = setTasks[key];
  if (!st) return null;
  const label = h('span.task-label.grow', st.label || t('Starting…'));
  const bar = h('i', { style: { width: Math.round((st.progress || 0) * 100) + '%' } });
  st.paint = () => { label.textContent = st.label || t('Starting…'); bar.style.width = Math.round((st.progress || 0) * 100) + '%'; };
  return h('div.task-row', { style: { margin: '8px 0' } }, h('div.hstack', label), h('div.progress', bar));
}
async function setTask(key, name, args) {
  if (setTasks[key]) return null;
  const st = setTasks[key] = { label: '', progress: 0 };
  paintSettings();
  try { return await runTask(name, args || {}, d => { st.label = d.label || st.label; st.progress = d.progress || 0; if (st.paint) st.paint(); }); }
  catch (e) { toast(e.message, 'error'); return null; }
  finally { delete setTasks[key]; if (S.page === 'settings') paintSettings(); }
}
function paintSettings() {
  const y = setRoot.scrollTop;
  const cfg = S.cfg, b = S.boot;
  const tools = S.tools || {};
  const out = [h('div.page-head', h('h1.page-title', t('Settings')))];

  // Allgemein
  const tmpl = h('input.field', { value: cfg.name_template || '', spellcheck: false, style: { width: '100%' } });
  const tmplPreview = h('span.hint');
  const showPreview = debounce(() => api('name_preview', { vid: '', start: 83, end: 112.5, template: tmpl.value || null }).then(n => { tmplPreview.textContent = t('Example: {name}.mp4', { name: n }); }).catch(() => {}), 150);
  tmpl.addEventListener('input', () => { setCfg('name_template', tmpl.value); showPreview(); });
  tmpl.addEventListener('keydown', e => e.stopPropagation());
  showPreview();
  const folder = h('span.path.ellipsis', pathText(cfg.folder));
  out.push(Sec(t('General'),
    Row(t('Language'), Select(b.languages.map(([code, name]) => [code, name]), S.lang, async code => {
      setCfg('language', code === 'en' ? null : code);
      if (await ask({ title: t('Restart Snipload?'), text: t('The new language is used after a restart.'), ok: t('Restart now'), cancel: t('Later') })) setTimeout(() => api('restart').catch(e => toast(e.message, 'error')), 500);
    })),
    Row(t('Save clips in'), h('div.folder-row', folder,
      Btn(t('Change'), { sm: true, onclick: async () => { const p = await api('pick_folder').catch(() => null); if (p) { cfg.folder = p; folder.textContent = pathText(p); } } }),
      Btn('', { sm: true, kind: 'ghost', icon: 'folder-open', tip: t('Open the folder'), onclick: () => api('open_file', { path: cfg.folder }).catch(e => toast(e.message, 'error')) })), { stack: true }),
    Row(t('File names'), [tmpl], { stack: true, hint: null }),
    h('div.hint', { style: { margin: '-2px 0 8px' } }, tmplPreview, h('br'), t('You can use {title}, {channel}, {start}, {end}, {date} and {id}.')),
    Row(t('Play a sound when exports are done'), Switch(cfg.sound !== false, v => setCfg('sound', v))),
    Row(t('Use the graphics card for exports'), Switch(cfg.hw_encode !== false, v => setCfg('hw_encode', v)), { hint: t('Much faster. Turn it off if exports fail or look wrong.') }),
    Row(t('Sign in with your browser'), Select([['', t('Off')], ['chrome', 'Chrome'], ['edge', 'Edge'], ['firefox', 'Firefox'], ['brave', 'Brave'], ['opera', 'Opera'], ['vivaldi', 'Vivaldi']], cfg.cookies_browser || '', v => { cfg.cookies_browser = v || null; api('set_cfg', { key: 'cookies_browser', value: v || null }).catch(() => {}); }),
      { hint: t('For age-restricted and members-only videos. Snipload uses the sign-in of this browser.') })));

  // Schnittprogramme
  const eds = S.editors || [];
  const edRows = eds.map(e => h('div.set-item',
    h('span.set-ico', icon(e.kind === 'premiere' || e.kind === 'aftereffects' ? 'clapperboard' : 'film')),
    h('div.grow', h('div.set-name', e.name), h('div.hint.ellipsis', e.path)),
    h('span.tag.soft', e.direct ? t('Direct import') : t('Via clipboard')),
    e.custom ? Btn('', { icon: 'x', kind: 'ghost', sm: true, tip: t('Remove'), onclick: async () => { S.editors = await api('remove_editor', { id: e.id }); paintSettings(); } }) : null));
  const hasPr = eds.some(e => e.kind === 'premiere');
  out.push(Sec(t('Editing programs'),
    eds.length ? h('div.set-list', edRows) : h('p.hint', { style: { marginBottom: '10px' } }, t('Snipload looks for Premiere Pro, After Effects, DaVinci Resolve, VEGAS and CapCut. None of them was found. You can add any other program yourself.')),
    h('div.hstack', { style: { marginTop: '10px' } }, Btn(t('Add a program…'), { sm: true, icon: 'plus', onclick: async () => { const r = await api('add_editor').catch(e => { toast(e.message, 'error'); return null; }); if (r) { S.editors = r; paintSettings(); } } })),
    hasPr ? Row(t('Connection to Premiere Pro'), [h('span.tag.soft', b.premiere_bridge ? t('Installed') : t('Not installed')),
      Btn(b.premiere_bridge ? t('Install again') : t('Install'), { sm: true, onclick: async () => {
        try { await api('install_premiere_bridge'); b.premiere_bridge = true; toast(t('Installed. Restart Premiere once, after that clips arrive in your project by themselves.'), 'success'); paintSettings(); }
        catch (e) { toast(e.message, 'error'); }
      } })], { hint: t('A small extension that puts every exported clip into your open project.') }) : null,
    hasPr ? Row(t('Clips arrive in Premiere'), Seg([['bin', t('Project bin')], ['timeline', t('At the playhead')], ['sequence', t('New sequence')]], cfg.premiere_mode || 'bin', v => setCfg('premiere_mode', v)), { stack: true }) : null));

  // KI-Untertitel
  const wh = S.whisper || { models: {} };
  const labels = { fast: t('Fast'), balanced: t('Balanced'), best: t('Best') };
  out.push(Sec(t('AI captions'),
    h('p.hint', { style: { marginBottom: '8px' } }, t('Speech recognition runs on your PC. A model is downloaded the first time you use it.')),
    setTasks.whisper ? taskLine('whisper') : null,
    Object.keys(wh.models || {}).map(k => {
      const m = wh.models[k];
      const ready = wh.engine && m.ready;
      return Row(labels[k] || k, [h('span.tag.soft', ready ? t('Ready') : m.mb + ' MB'),
        ready ? null : Btn(t('Download'), { sm: true, onclick: () => setTask('whisper', 'install_whisper', { model: k }).then(r => { if (r) { S.whisper = r; paintSettings(); } }) })]);
    })));

  // Hochskalieren
  const up = S.upscale || {};
  out.push(Sec(t('Upscaling'),
    setTasks.esrgan ? taskLine('esrgan') : null,
    Row('Real-ESRGAN', [h('span.tag.soft', up.esrgan ? t('Ready') : t('Not installed')),
      up.esrgan ? null : Btn(t('Download'), { sm: true, onclick: () => setTask('esrgan', 'install_esrgan').then(r => { if (r) { S.upscale = r; paintSettings(); } }) })], { hint: t('AI upscaling that runs on any graphics card') }),
    Row('Topaz Video AI', h('span.tag.soft', up.topaz ? t('Found') : t('Not found')), { hint: t('Used automatically when it is installed on this PC') })));

  // Werkzeuge
  const age = tools.ytdlp_age;
  out.push(Sec(t('Download engine'),
    setTasks.tools ? taskLine('tools') : null,
    Row('yt-dlp', [h('span.tag.soft', tools.ytdlp || t('Missing')),
      tools.ytdlp ? Btn(t('Update'), { sm: true, onclick: e => busy(e.currentTarget, () => runTask('update_ytdlp', {}).catch(err => toast(err.message, 'error'))) })
        : Btn(t('Download'), { sm: true, onclick: () => setTask('tools', 'install_tools', { names: ['yt-dlp'] }) })],
    { hint: age != null && tools.ytdlp ? (age > 30 ? t('{n} days old. YouTube changes often, an update is a good idea.', { n: age }) : t('Up to date. Snipload updates it by itself.')) : t('Reads and downloads the videos') }),
    Row('ffmpeg', [h('span.tag.soft', tools.ffmpeg ? String(tools.ffmpeg).slice(0, 28) : t('Missing')),
      tools.ffmpeg ? null : Btn(t('Download'), { sm: true, onclick: () => setTask('tools', 'install_tools', { names: ['ffmpeg'] }) })], { hint: t('Cuts and converts the clips') })));

  // Updates
  const u = S.update || {};
  const state = { checking: t('Checking…'), available: t('Version {v} is available', { v: u.version }), downloading: t('Downloading version {v}…', { v: u.version }), ready: t('Version {v} is ready. It is installed when you close Snipload.', { v: u.version }),
    current: t('You have the newest version.'), error: u.error || '' }[u.state] || '';
  out.push(Sec(t('About'),
    Row('Snipload ' + b.version, Btn(t('Check for updates'), { sm: true, icon: 'refresh-cw', onclick: e => busy(e.currentTarget, () => api('update_check').catch(err => toast(err.message, 'error'))) }), { hint: state }),
    Row(t('Update automatically'), Switch(cfg.auto_update !== false, v => setCfg('auto_update', v))),
    h('div.hstack.wrap', { style: { marginTop: '10px' } },
      Btn(t('Keyboard shortcuts'), { sm: true, kind: 'ghost', icon: 'keyboard', onclick: () => import('./app.js').then(m => m.showShortcuts()) }),
      Btn('GitHub', { sm: true, kind: 'ghost', icon: 'external-link', onclick: () => api('open_url', { url: 'https://github.com/Mavi-05/Snipload' }) }),
      Btn(t('Licenses'), { sm: true, kind: 'ghost', icon: 'file-text', onclick: showLicenses })),
    h('p.about-note', OWNER + '. ' + t('Snipload is free to use. Copying it, uploading it somewhere else or passing it off as your own is not allowed.'))));

  clear(setRoot, h('div.settings', out));
  setRoot.scrollTop = y;
}
const OWNER = '© 2026 Mavi-05';
async function showLicenses() {
  const get = async p => { try { const r = await fetch(p); return r.ok ? await r.text() : ''; } catch (_) { return ''; } };
  const [own, third] = await Promise.all([get('/app/LICENSE'), get('/app/LICENSES.txt')]);
  // Zuerst die Lizenz von Snipload selbst, darunter die der verwendeten Bausteine
  const mine = own.trim() || 'Snipload\n' + OWNER + '. All rights reserved.\nhttps://github.com/Mavi-05/Snipload/blob/main/LICENSE';
  modal({ title: t('Licenses'), cls: 'mid', body: h('pre.selectable.licenses', mine + '\n\n\n' + '='.repeat(50) + '\n\n' + third.trim()
    + '\n\nyt-dlp (Unlicense), ffmpeg (LGPL/GPL), whisper.cpp (MIT), Real-ESRGAN (BSD-3-Clause), Geist, Inter, Montserrat, Poppins, Bebas Neue, Anton, Bangers, Luckiest Guy, Archivo Black, Kanit (SIL Open Font License).') });
}
