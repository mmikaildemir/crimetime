// CrimeTime Legal Review — check the calculator crime by crime.
// Sheets come from ../data/review_sheets.json (webapp/review_bridge.py, built at
// deploy time). Answers stay in localStorage until the reviewer downloads them.

const DATA = '../data/';
const STORE_KEY = 'crimetime-legal-review-v2';
const FORMAT = 'crimetime-legal-review';
const BUILD = new URL(document.currentScript.src).searchParams.get('v') || '';

const state = { meta: null, sheets: [], bySection: {}, statutes: null, current: null,
  store: { reviewer: {}, answers: {} } };

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// --- storage --------------------------------------------------------------

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
    if (s && s.answers) state.store = { reviewer: {}, ...s };
  } catch { /* blocked or corrupt: start empty */ }
}
function save() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state.store)); } catch { /* still in memory */ }
}
function hideHowtoPref(set) {
  try {
    if (set) localStorage.setItem('crimetime-review-howto', 'hidden');
    return localStorage.getItem('crimetime-review-howto') === 'hidden';
  } catch { return false; }
}

// --- status helpers -------------------------------------------------------

function status(sheet) {
  const a = state.store.answers[sheet.section];
  if (!a || !a.done) return 'todo';
  if (a.hash !== sheet.hash) return 'stale';
  return Object.keys(a.wrong || {}).length ? 'wrong' : 'ok';
}

function renderProgress() {
  const done = state.sheets.filter(s => ['ok', 'wrong'].includes(status(s))).length;
  const wrong = state.sheets.filter(s => status(s) === 'wrong').length;
  $('#progress').textContent = `${done} of ${state.sheets.length} crimes checked` + (wrong ? ` · ${wrong} with problems` : '');
}

// --- crime list -----------------------------------------------------------

function renderList() {
  const q = $('#search').value.trim().toLowerCase();
  const f = $('#filter').value;
  let html = '';
  let art = null;
  for (const s of state.sheets) {
    const st = status(s);
    if (q && !s.section.toLowerCase().includes(q) && !s.name.toLowerCase().includes(q)) continue;
    if (f === 'todo' && !['todo', 'stale'].includes(st)) continue;
    if (f === 'wrong' && st !== 'wrong') continue;
    if (f === 'felony' && !/felony/i.test(s.classification)) continue;
    if (s.article !== art) { art = s.article; html += `<div class="art">Article ${esc(art)}</div>`; }
    const icon = { ok: 'fa-solid fa-circle-check', wrong: 'fa-solid fa-circle-xmark', stale: 'fa-solid fa-rotate', todo: '' }[st];
    html += `<button type="button" class="crime-item ${s.section === state.current ? 'current' : ''}" data-section="${esc(s.section)}" role="listitem">
      <span class="sec">${esc(s.section)}</span><span class="nm">${esc(s.name)}</span>
      <span class="mk">${icon ? `<i class="${icon}" title="${st}"></i>` : ''}</span></button>`;
  }
  $('#crimeList').innerHTML = html || '<p class="hint-line" style="padding:16px 24px">No crimes match.</p>';
}

// --- sheet ----------------------------------------------------------------

function answerFor(sheet) {
  const a = state.store.answers[sheet.section];
  if (!a || a.hash !== sheet.hash) return { wrong: {}, comment: '' };
  return a;
}

function renderSheet(section) {
  const s = state.bySection[section];
  if (!s) return;
  state.current = section;
  const a = answerFor(s);
  const old = state.store.answers[section];
  const st = status(s);
  const statute = state.statutes?.[section];
  const rows = s.lines.map(l => {
    const isWrong = l.key in (a.wrong || {});
    return `<tr class="${isWrong ? 'is-wrong' : ''}" data-key="${esc(l.key)}">
        <th scope="row">${esc(l.label)}</th><td>${esc(l.value)}</td>
        <td class="wrong-cell"><label class="wrong-toggle"><input type="checkbox" data-wrong="${esc(l.key)}" ${isWrong ? 'checked' : ''} /> Wrong?</label></td>
      </tr>
      <tr class="fix-row" data-fix="${esc(l.key)}" ${isWrong ? '' : 'hidden'}><td colspan="3">
        <textarea rows="2" data-fix-text="${esc(l.key)}" placeholder="What should it say? (a citation helps if you have one)">${esc(a.wrong?.[l.key] || '')}</textarea>
      </td></tr>`;
  }).join('');
  const idx = state.sheets.indexOf(s);
  $('#sheet').innerHTML = `<div class="panel-body">
    <div class="sheet-head">
      <h2>§${esc(s.section)} ${esc(s.name)}</h2>
      <span class="cls">${idx + 1} of ${state.sheets.length}</span>
    </div>
    ${st === 'stale' ? '<div class="stale-note"><i class="fa-solid fa-rotate"></i> The calculator changed for this crime after you checked it. Please look again.</div>' : ''}
    <div class="links">
      <a href="https://www.nysenate.gov/legislation/laws/PEN/${encodeURIComponent(s.section)}" target="_blank" rel="noopener">Read §${esc(s.section)} on nysenate.gov <i class="fa-solid fa-arrow-up-right-from-square"></i></a>
      <a href="../#s=${encodeURIComponent(s.section)}" target="_blank" rel="noopener">Open in the calculator <i class="fa-solid fa-arrow-up-right-from-square"></i></a>
    </div>
    ${statute ? `<details class="statute"><summary>Statute text</summary><div class="statute-text">${esc(statute.text)}</div></details>` : ''}
    <table class="facts"><tbody>${rows}</tbody></table>
    <div class="sheet-foot">
      <label class="field"><span>Anything else about this crime? <em class="muted">(optional)</em></span>
        <textarea id="comment" rows="2" placeholder="e.g. something the calculator should ask about but doesn't">${esc(a.comment || '')}</textarea></label>
      <div class="foot-actions">
        <button class="btn btn-ok" type="button" id="doneBtn"><i class="fa-solid fa-check"></i> <span id="doneLabel"></span></button>
        <button class="btn btn-default" type="button" id="skipBtn">Skip for now</button>
        <span class="saved-note" id="savedNote">${old?.done && st !== 'stale' ? 'Checked ✓' : ''}</span>
      </div>
    </div>
  </div>`;
  updateDoneLabel();
  wireSheet(s);
  renderList();
  $('#crimeList .current')?.scrollIntoView({ block: 'nearest' });
  if (location.hash.slice(1) !== section) history.replaceState(null, '', `#${section}`);
}

function collect(sheet) {
  const wrong = {};
  document.querySelectorAll('[data-wrong]').forEach(cb => {
    if (cb.checked) wrong[cb.dataset.wrong] = $(`[data-fix-text="${CSS.escape(cb.dataset.wrong)}"]`).value.trim();
  });
  return { wrong, comment: $('#comment').value.trim() };
}

function updateDoneLabel() {
  const anyWrong = !!document.querySelector('[data-wrong]:checked');
  $('#doneLabel').textContent = anyWrong ? 'Save and go to next crime' : 'Everything is correct — next crime';
}

function store(sheet, done) {
  const prev = state.store.answers[sheet.section] || {};
  state.store.answers[sheet.section] = {
    ...collect(sheet), done: done || (prev.done && prev.hash === sheet.hash),
    hash: sheet.hash, at: new Date().toISOString(),
  };
  save();
  renderProgress();
}

function nextSheet(sheet) {
  const i = state.sheets.indexOf(sheet);
  const rest = [...state.sheets.slice(i + 1), ...state.sheets.slice(0, i)];
  return rest.find(s => ['todo', 'stale'].includes(status(s))) || state.sheets[i + 1];
}

function wireSheet(sheet) {
  document.querySelectorAll('[data-wrong]').forEach(cb => cb.addEventListener('change', () => {
    const key = cb.dataset.wrong;
    cb.closest('tr').classList.toggle('is-wrong', cb.checked);
    const fix = $(`[data-fix="${CSS.escape(key)}"]`);
    fix.hidden = !cb.checked;
    if (cb.checked) $('textarea', fix).focus();
    updateDoneLabel();
    if (state.store.answers[sheet.section]?.done) store(sheet, true);
  }));
  document.querySelectorAll('[data-fix-text], #comment').forEach(t => t.addEventListener('input', () => {
    if (state.store.answers[sheet.section]?.done) store(sheet, true);
  }));
  $('#doneBtn').addEventListener('click', () => {
    store(sheet, true);
    const next = nextSheet(sheet);
    if (next) renderSheet(next.section); else renderList();
    window.scrollTo({ top: 0 });
  });
  $('#skipBtn').addEventListener('click', () => {
    const i = state.sheets.indexOf(sheet);
    const next = state.sheets[i + 1];
    if (next) renderSheet(next.section);
    window.scrollTo({ top: 0 });
  });
}

// --- download / continue --------------------------------------------------

function exportAnswers() {
  const answers = Object.fromEntries(Object.entries(state.store.answers).filter(([, a]) => a.done));
  const payload = {
    format: FORMAT, formatVersion: 2, reviewer: state.store.reviewer, build: BUILD,
    data_version: state.meta.data_version, exported: new Date().toISOString(), answers,
  };
  const name = (state.store.reviewer?.name || 'reviewer').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'reviewer';
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  a.download = `crimetime-review-${name}-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  showMsg(`Downloaded your answers on ${Object.keys(answers).length} crimes. Email the file back. You can keep going and send an updated file later.`, 'success');
}

async function importAnswers(file) {
  try {
    const data = JSON.parse(await file.text());
    if (data.format !== FORMAT || typeof data.answers !== 'object') throw new Error('this is not a CrimeTime review file');
    let n = 0;
    for (const [sec, ans] of Object.entries(data.answers)) {
      const mine = state.store.answers[sec];
      if (!mine || (ans.at || '') > (mine.at || '')) { state.store.answers[sec] = ans; n++; }
    }
    if (!state.store.reviewer?.name && data.reviewer?.name) {
      state.store.reviewer = data.reviewer;
      $('#revName').value = data.reviewer.name;
    }
    save();
    renderProgress();
    renderList();
    if (state.current) renderSheet(state.current);
    showMsg(`Loaded ${n} answer${n === 1 ? '' : 's'} from ${file.name}.`, 'success');
  } catch (e) {
    showMsg(`Couldn't read that file: ${e.message}.`, 'warning');
  }
}

function showMsg(text, kind) {
  $('#importMsg').innerHTML = `<div class="alert alert-${kind}">${esc(text)}</div>`;
}

// --- init -----------------------------------------------------------------

async function init() {
  load();
  $('#revName').value = state.store.reviewer?.name || '';
  $('#revName').addEventListener('input', (e) => { state.store.reviewer = { ...state.store.reviewer, name: e.target.value.trim() }; save(); });
  $('#howto').hidden = hideHowtoPref(false);
  $('#hideHowto').addEventListener('click', () => { $('#howto').hidden = true; hideHowtoPref(true); });
  $('#search').addEventListener('input', renderList);
  $('#filter').addEventListener('change', renderList);
  $('#crimeList').addEventListener('click', (e) => {
    const b = e.target.closest('[data-section]');
    if (b) renderSheet(b.dataset.section);
  });
  $('#exportBtn').addEventListener('click', exportAnswers);
  $('#importFile').addEventListener('change', (e) => { if (e.target.files[0]) importAnswers(e.target.files[0]); e.target.value = ''; });

  try {
    const res = await fetch(`${DATA}review_sheets.json`, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.meta = data;
    state.sheets = data.sheets;
    state.bySection = Object.fromEntries(data.sheets.map(s => [s.section, s]));
    $('#statusText').textContent = `${data.count} crimes · data ${data.data_version}`;
    $('#status').className = 'status ok';
  } catch (e) {
    $('#statusText').textContent = `Couldn't load crimes: ${e.message}`;
    $('#status').className = 'status err';
    return;
  }
  renderProgress();
  renderList();
  const fromHash = decodeURIComponent(location.hash.slice(1));
  if (state.bySection[fromHash]) renderSheet(fromHash);
  fetch(`${DATA}statutes.json`, { cache: 'no-cache' }).then(r => r.json()).then(st => {
    state.statutes = st;
    const cur = state.statutes[state.current];
    if (cur && !document.querySelector('#sheet details.statute')) {
      const d = document.createElement('details');
      d.className = 'statute';
      d.innerHTML = `<summary>Statute text</summary><div class="statute-text">${esc(cur.text)}</div>`;
      $('#sheet .facts').before(d);
    }
  }).catch(() => { state.statutes = {}; });
}

init();
