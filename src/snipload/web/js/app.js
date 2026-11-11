// Snipload – Start der Oberflaeche: Navigation, Ereignisse vom Programm, Dialoge, Tastenkuerzel.
import { S, api, on, fire, connectEvents, runTask, t, h, icon, clear, go, toast, modal, ask, Btn, typing, topModal, closeMenu } from './core.js';
import { initHome, openText, focusSearch } from './home.js';
import { initEditor } from './editor.js';
import { initExports, initLibrary, initSettings } from './pages.js';

// ------------------------------------------------------------------ Navigation (links)
const NAV = [
  ['home', 'search', 'Find'],
  ['editor', 'scissors', 'Editor'],
  ['exports', 'download', 'Exports'],
  ['library', 'library', 'Library'],
];
let exportsBtn, updateBtn;

function railBtn(page, ic, label, extra = {}) {
  return h('button.rail-btn', Object.assign({ type: 'button', tip: t(label), data: { page, tipSide: 'right' }, 'aria-label': t(label), onclick: () => go(page) }, extra), icon(ic));
}
function buildRail() {
  const rail = document.getElementById('rail');
  clear(rail, h('img.rail-logo', { src: '/app/img/logo.png', alt: 'Snipload', draggable: false }));
  for (const [page, ic, label] of NAV) {
    const b = railBtn(page, ic, label);
    if (page === 'exports') exportsBtn = b;
    rail.append(b);
  }
  rail.append(h('div.rail-space'));
  updateBtn = h('button.rail-btn.update.hidden', { type: 'button', tip: t('Update available'), data: { tipSide: 'right' }, onclick: showUpdate }, icon('circle-arrow-up'));
  rail.append(updateBtn, railBtn('settings', 'settings', 'Settings'));
  paintExports();
}
/** Zahl und Fortschrittsring am Exporte-Knopf. */
function paintExports() {
  if (!exportsBtn) return;
  for (const el of exportsBtn.querySelectorAll('.rail-count, .rail-ring')) el.remove();
  const active = S.jobs.filter(j => j.status === 'running' || j.status === 'waiting');
  if (!active.length) return;
  const p = active.reduce((a, j) => a + (j.progress || 0), 0) / active.length;
  const c = 2 * Math.PI * 16;
  const ring = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  ring.setAttribute('viewBox', '0 0 36 36');
  ring.setAttribute('class', 'rail-ring');
  ring.innerHTML = `<circle class="bg" cx="18" cy="18" r="16"/><circle class="fg" cx="18" cy="18" r="16" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - p)}"/>`;
  exportsBtn.append(ring, h('span.rail-count', String(active.length)));
}

// ------------------------------------------------------------------ Ereignisse vom Programm
function wireEvents() {
  on('job', j => {
    const i = S.jobs.findIndex(x => x.id === j.id);
    const before = i >= 0 ? S.jobs[i].status : null;
    if (i >= 0) S.jobs[i] = j; else S.jobs.push(j);
    if (before !== j.status) {
      if (j.status === 'done') {
        toast(t('Exported “{name}”', { name: j.name }), 'success', S.page === 'exports' ? {} : { action: { label: t('Show'), fn: () => go('exports') } });
      } else if (j.status === 'failed') {
        toast(t('Export failed: {error}', { error: j.error || j.name }), 'error', S.page === 'exports' ? {} : { action: { label: t('Show'), fn: () => go('exports') } });
      }
    }
    paintExports();
    fire('jobs-changed', j);
  });
  on('jobs', list => { S.jobs = list || []; paintExports(); fire('jobs-changed', null); });
  on('toast', d => toast(d.text, d.kind || 'info'));
  on('tools', st => { S.tools = st; S.whisper = st.whisper || S.whisper; S.upscale = st.upscale || S.upscale; fire('tools-changed', st); });
  on('tools_missing', names => showToolsMissing(names || []));
  on('update', u => {
    S.update = u;
    const show = u && ['available', 'downloading', 'ready'].includes(u.state);
    updateBtn.classList.toggle('hidden', !show);
    if (show) updateBtn.dataset.tip = u.state === 'ready' ? t('Update {v} is ready – restart to install', { v: u.version }) : t('Update {v} is available', { v: u.version });
    fire('update-changed', u);
  });
  on('confirm_quit', async d => {
    const ok = await ask({
      title: t('Quit while exporting?'),
      text: d && d.count > 1 ? t('{n} exports are still running. They are cancelled if you quit now.', { n: d.count }) : t('An export is still running. It is cancelled if you quit now.'),
      ok: t('Quit'), cancel: t('Keep exporting'), danger: true,
    });
    if (ok) api('quit', { force: true }).catch(() => {});
  });
}

// ------------------------------------------------------------------ Dialoge
let toolsDialog = null;
function showToolsMissing(names) {
  if (toolsDialog || !names.length) return;
  const bar = h('div.progress', h('i'));
  const status = h('div.hint', { style: { marginTop: '10px', minHeight: '18px' } });
  const go2 = Btn(t('Download now'), {
    kind: 'primary', icon: 'download', onclick: async () => {
      go2.classList.add('disabled');
      later.classList.add('hidden');
      bar.classList.remove('hidden');
      try {
        await runTask('install_tools', { names }, d => { bar.firstChild.style.width = Math.round((d.progress || 0) * 100) + '%'; status.textContent = d.label || ''; });
        toolsDialog.close();
        toast(t('Everything is set up. You can start clipping.'), 'success');
      } catch (e) {
        status.textContent = e.message;
        go2.classList.remove('disabled');
        later.classList.remove('hidden');
      }
    },
  });
  const later = Btn(t('Later'), { kind: 'ghost', onclick: () => toolsDialog.close() });
  bar.classList.add('hidden');
  toolsDialog = modal({
    title: t('One-time setup'),
    body: [h('p', t('Snipload needs {names} to download and cut videos. They are downloaded once (about 110 MB) and kept up to date automatically.', { names: names.join(' + ') })),
      h('div', { style: { marginTop: '16px' } }, bar), status],
    foot: [later, go2], onClose: () => { toolsDialog = null; },
  });
}

function showUpdate() {
  const u = S.update || {};
  const body = h('div');
  const foot = h('div.hstack');
  const m = modal({ title: t('Snipload {v}', { v: u.version || '' }), body, foot: [foot] });
  const paint = () => {
    const s = S.update || {};
    clear(body, s.notes ? h('div.selectable', { style: { whiteSpace: 'pre-wrap', maxHeight: '320px', overflow: 'auto' } }, s.notes) : h('p', t('A new version is available.')));
    clear(foot);
    if (s.state === 'downloading') {
      body.append(h('div.progress', { style: { marginTop: '16px' } }, h('i', { style: { width: Math.round((s.progress || 0) * 100) + '%' } })));
      foot.append(h('span.dim', t('Downloading the update… {p} %', { p: Math.round((s.progress || 0) * 100) })));
    } else if (s.state === 'ready') {
      foot.append(Btn(t('Later'), { kind: 'ghost', onclick: () => m.close() }),
        Btn(t('Restart and update'), { kind: 'primary', icon: 'rotate-cw', onclick: () => api('update_restart').catch(e => toast(e.message, 'error')) }));
    } else {
      foot.append(Btn(t('Later'), { kind: 'ghost', onclick: () => m.close() }),
        Btn(S.boot.can_self_update ? t('Download update') : t('Open the download page'), { kind: 'primary', icon: 'download', onclick: () => api('update_download').catch(e => toast(e.message, 'error')) }));
    }
  };
  paint();
  const off = on('update-changed', () => { if (m.closed) off(); else paint(); });
}

const SHORTCUTS = [
  ['Editor', [['Space', 'Play or pause'], ['I', 'Set the start of the clip'], ['O', 'Set the end of the clip'], ['Q / W', 'Jump to the start or end of the clip'],
    ['← / →', 'Step 1 second (Shift: 5 seconds, Alt: one frame)'], ['J / L', 'Jump 10 seconds back or forward'], ['A', 'Add the clip to the list'],
    ['S', 'Save the current frame as an image'], ['M', 'Mute'], ['+ / −', 'Zoom the timeline'], ['Ctrl+Enter', 'Export']]],
  ['Everywhere', [['Ctrl+K', 'Search or paste a link'], ['Ctrl+V', 'Open the link from the clipboard'], ['Ctrl+1 … 4', 'Switch between Find, Editor, Exports and Library'], ['?', 'Show these shortcuts']]],
];
function showShortcuts() {
  modal({
    title: t('Keyboard shortcuts'), cls: 'mid', pearl: true,
    body: SHORTCUTS.map(([group, rows]) => h('div.keys', h('div.sec-title', t(group)), rows.map(([k, label]) => h('div.keys-row', h('span', t(label)), h('span.kbd', k))))),
  });
}

// ------------------------------------------------------------------ Tasten, Einfuegen, Hineinziehen
function wireInput() {
  // Escape schliesst Menues und Dialoge – auch wenn gerade in einem Feld getippt wird
  addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    closeMenu();
    const m = topModal();
    if (m && !m.sticky) { m.close(); e.preventDefault(); e.stopPropagation(); }
  }, true);
  addEventListener('keydown', e => {
    if (e.key === 'Escape' || topModal()) return;
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); go('home'); focusSearch(); return; }
    if (mod && /^[1-4]$/.test(e.key)) { e.preventDefault(); go(NAV[Number(e.key) - 1][0]); return; }
    if (mod && e.key === ',') { e.preventDefault(); go('settings'); return; }
    if (typing(e)) return;
    if (e.key === '?') { e.preventDefault(); showShortcuts(); return; }
    fire('key', e);
  });
  // Link aus der Zwischenablage: Strg+V irgendwo (ausser in Textfeldern) oeffnet ihn direkt
  document.addEventListener('paste', e => {
    if (typing(e) || topModal()) return;
    const text = (e.clipboardData && e.clipboardData.getData('text') || '').trim();
    if (text) { e.preventDefault(); openText(text); }
  });
  let veil = null, depth = 0;
  const hasLink = e => e.dataTransfer && Array.from(e.dataTransfer.types || []).some(x => x === 'text/uri-list' || x === 'text/plain');
  addEventListener('dragenter', e => {
    if (!hasLink(e)) return;
    depth++;
    if (!veil) { veil = h('div.drop-veil', t('Drop the link to open it')); document.body.append(veil); }
  });
  addEventListener('dragover', e => { if (hasLink(e)) e.preventDefault(); });
  const endDrag = () => { depth = 0; if (veil) { veil.remove(); veil = null; } };
  addEventListener('dragleave', () => { depth--; if (depth <= 0) endDrag(); });
  addEventListener('drop', e => {
    if (!hasLink(e)) return;
    e.preventDefault();
    endDrag();
    const text = (e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain') || '').split('\n')[0].trim();
    if (text) openText(text);
  });
  addEventListener('contextmenu', e => { if (!typing(e) && !e.target.closest('.selectable')) e.preventDefault(); });
}

// ------------------------------------------------------------------ Start
async function start() {
  const bootEl = document.getElementById('boot');
  const t0 = performance.now();
  let b;
  try {
    b = await api('boot');
  } catch (e) {
    bootEl.append(h('p', { style: { position: 'absolute', bottom: '18%', color: '#a1a8c4', textAlign: 'center', padding: '0 24px' } }, 'Snipload could not start: ' + e.message));
    return;
  }
  Object.assign(S, { boot: b, cfg: b.cfg || {}, strings: b.strings || {}, lang: b.lang || 'en', jobs: b.jobs || [], editors: b.editors || [], whisper: b.whisper, upscale: b.upscale });
  document.documentElement.lang = S.lang;
  buildRail();
  wireEvents();
  initHome();
  initEditor();
  initExports();
  initLibrary();
  initSettings();
  wireInput();
  go('home');
  connectEvents();
  // das Logo zeichnet sich einmal fertig, dann oeffnet sich die Oberflaeche
  setTimeout(() => { bootEl.classList.add('done'); setTimeout(() => bootEl.remove(), 500); focusSearch(); }, Math.max(0, 1050 - (performance.now() - t0)));
}

export { showShortcuts, showUpdate };
start();
