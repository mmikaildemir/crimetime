// CrimeTime Admin — edit the data bundle (offenses, statutory lists, sentencing
// tables), check it with the real engine, and download a new bundle to publish.
//
// Everything runs in the browser. The draft lives in memory, with a copy in
// localStorage as crash recovery only. The checks run in the Pyodide worker
// (webapp/admin_bridge.py) through engine.call().

'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clone = (o) => JSON.parse(JSON.stringify(o));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const isPair = (v) => Array.isArray(v) && v.length === 2 && v.every(isNum);
const DATA = '../data/';
const AUTOSAVE_KEY = 'crimetime-admin-draft';
const SECTION_RE = /^\d{1,3}\.\d{2}(-[A-Za-z])?$/;

const state = {
  published: null,      // { lists, tables, manifest }
  draft: null,          // { lists, tables }
  check: { issues: [], changes: [] },
  checking: false,
  impact: null,
  impactStale: true,
  selectedSection: null,
  selectedTable: null,
  lastBundleVersion: null,
};

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

const CLASSES = [
  ['ClassA_I_Felony', 'Class A-I felony'], ['ClassA_II_Felony', 'Class A-II felony'],
  ['ClassB_Felony', 'Class B felony'], ['ClassC_Felony', 'Class C felony'],
  ['ClassD_Felony', 'Class D felony'], ['ClassE_Felony', 'Class E felony'],
  ['ClassA_Misdemeanor', 'Class A misdemeanor'], ['ClassB_Misdemeanor', 'Class B misdemeanor'],
  ['Unclassified_Misdemeanor', 'Unclassified misdemeanor'], ['Violation', 'Violation'],
];
const CLASS_LABEL = Object.fromEntries(CLASSES);

const TABLE_NAMES = {
  nonViolentFelony: ['Non-violent felonies', 'PL 70.00 / 70.06 / 70.10'],
  violentFelony: ['Violent felonies', 'PL 70.02 / 70.04 / 70.08'],
  drugFelony: ['Drug felonies', 'PL 70.70 / 70.71'],
  sexOffenseFelony: ['Sex-offense felonies', 'PL 70.80'],
  juvenileOffender: ['Juvenile offenders', 'PL 70.05'],
  misdemeanor: ['Misdemeanors', 'PL 70.15'],
  violation: ['Violations', 'PL 70.15(4)'],
  offenseOverrides: ['Offense-specific rules', 'e.g. murder 1st, aggravated murder'],
  hateCrimeBump: ['Hate-crime minimums', 'PL 485.10'],
  classificationModifiers: ['Class changes (SMF, hate, terrorism)', 'PL 130.91 / 485.10 / 490.25'],
  dispositions: ['Probation, discharge & split sentences', 'PL 60.01 / 65.00'],
  exceptions: ['Exceptions', 'Armed felony, domestic violence, DWI'],
  financial: ['Fines, surcharges & fees', 'PL 80.00 / 60.35'],
  collateral: ['Collateral requirements', 'Registration, orders of protection…'],
  restitution: ['Restitution', 'PL 60.27'],
};

const KEY_LABELS = {
  termYears: 'Term (years)', prsYears: 'Post-release supervision (years)', maxTermYears: 'Maximum term (years)',
  minTermYears: 'Minimum term (years)', minPeriodFloor: 'Minimum period floor (years)', minPeriodCeiling: 'Minimum period ceiling',
  minPeriodRef: 'Minimum period cite', maxTermRef: 'Maximum term cite', statute: 'Statute', label: 'Label shown to users',
  sentenceType: 'Sentence type', prsRef: 'PRS cite', type: 'Type', maxTermMonths: 'Maximum term (months)',
  maxTermDays: 'Maximum term (days)', maxImprisonmentDays: 'Maximum jail (days)', fineMax: 'Maximum fine ($)',
  probationEligible: 'Probation allowed', probationEligibleYears: 'Probation term (years)', wholeOrHalfYears: 'Whole or half years only',
  altDefiniteMax1yr: 'Definite sentence of up to 1 year allowed', minYearsFixed: 'Fixed minimum (years)',
};

function humanize(key) {
  if (KEY_LABELS[key]) return KEY_LABELS[key];
  const m = /^Class([A-E])(?:_(I{1,2}))?(?:_(Felony|Misdemeanor|Violent_Felony))?$/.exec(key);
  if (m) return `Class ${m[1]}${m[2] ? '-' + m[2] : ''}${m[3] ? ' ' + m[3].replace('_', ' ').toLowerCase() : ''}`;
  if (/^class[A-E]$/.test(key)) return `Class ${key.slice(5)}`;
  return String(key)
    .replace(/_/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/^./, c => c.toUpperCase());
}

// Statutory lists an offense can belong to (besides VFO, which is per class).
const MEMBER_LISTS = [
  { list: 'SMF_LIST', key: 'sections', label: 'Sexually motivated felony', help: 'Can be charged as sexually motivated' },
  { list: 'HATECRIME_LIST', key: 'sections', label: 'Hate crime', help: 'Specified offense for a hate crime' },
  { list: 'TERRORISM_LIST', key: 'sections', label: 'Crime of terrorism', help: 'Specified offense for terrorism. By statute this list currently matches the hate-crime list.' },
  { list: 'FOR_HIRE_LIST', key: 'completedSections', label: 'For-hire driver victim (completed)', help: 'Enhancement when the victim was driving a taxi, livery or black car' },
  { list: 'FOR_HIRE_LIST', key: 'attemptOfSections', label: 'For-hire driver victim (attempt)', help: 'Same enhancement, for an attempt of this offense' },
];
const VFO_CLASSES = ['classB', 'classC', 'classD', 'classE'];
const LIST_NAMES = {
  VFO_LIST: 'Violent felony list', SMF_LIST: 'Sexually motivated felony list', HATECRIME_LIST: 'Hate crime list',
  TERRORISM_LIST: 'Terrorism list', FOR_HIRE_LIST: 'For-hire driver list',
};

// ---------------------------------------------------------------------------
// Path helpers over the draft
// ---------------------------------------------------------------------------

function getAt(obj, path) {
  return path.reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
function setAt(obj, path, value) {
  const parent = getAt(obj, path.slice(0, -1));
  parent[path[path.length - 1]] = value;
}

const offenses = () => state.draft.lists.offenses;
const pubOffenses = () => state.published.lists.offenses;
const listArr = (lists, name, key) => lists.lists?.[name]?.[key] || [];

function vfoClassOf(lists, section) {
  return VFO_CLASSES.find(c => (lists.lists.VFO_LIST[c]?.sections || []).includes(section)) || '';
}

function setMembership(listName, key, section, on) {
  const holder = listName === 'VFO_LIST' ? state.draft.lists.lists.VFO_LIST[key] : state.draft.lists.lists[listName];
  const arrKey = listName === 'VFO_LIST' ? 'sections' : key;
  const arr = holder[arrKey] || (holder[arrKey] = []);
  const i = arr.indexOf(section);
  if (on && i < 0) arr.push(section);
  if (!on && i >= 0) arr.splice(i, 1);
}

function setVfoClass(section, cls) {
  for (const c of VFO_CLASSES) setMembership('VFO_LIST', c, section, c === cls);
}

function removeFromAllLists(section) {
  setVfoClass(section, '');
  for (const m of MEMBER_LISTS) setMembership(m.list, m.key, section, false);
}

// ---------------------------------------------------------------------------
// Draft sync: push to the worker, re-check, autosave
// ---------------------------------------------------------------------------

let syncTimer = null;
let syncSeq = 0;

function draftChanged() {
  state.impactStale = true;
  state.checking = true;
  clearTimeout(syncTimer);
  syncTimer = setTimeout(syncDraft, 300);
  autosave();
  renderDraftBar();
}

async function syncDraft() {
  const seq = ++syncSeq;
  state.checking = true;
  renderDraftBar();
  try {
    await engine.call('set_draft_json', JSON.stringify(state.draft.lists), JSON.stringify(state.draft.tables));
    const check = await engine.call('check_draft_json');
    if (seq !== syncSeq) return;  // a newer edit is on its way
    state.check = check;
  } catch (e) {
    console.error(e);
    setStatus(`Check failed: ${e.message}`, 'err');
  } finally {
    if (seq === syncSeq) state.checking = false;
  }
  renderDraftBar();
  if (currentTab() === 'publish') renderPublish();
  renderOffenseList();
}

function autosave() {
  try {
    localStorage.setItem(AUTOSAVE_KEY, JSON.stringify({
      basedOn: state.published.manifest.version,
      savedAt: new Date().toISOString(),
      downloadedAs: state.lastBundleVersion,
      lists: state.draft.lists,
      tables: state.draft.tables,
    }));
  } catch { /* storage full or blocked: the draft still lives in memory */ }
}

function clearAutosave() {
  try { localStorage.removeItem(AUTOSAVE_KEY); } catch { /* ignore */ }
}

function readAutosave() {
  try { return JSON.parse(localStorage.getItem(AUTOSAVE_KEY) || 'null'); } catch { return null; }
}

function isDirty() {
  return !same(state.draft.lists, state.published.lists) || !same(state.draft.tables, state.published.tables);
}

// ---------------------------------------------------------------------------
// Status / draft bar / tabs
// ---------------------------------------------------------------------------

function setStatus(text, cls = '') {
  $('#statusText').textContent = text;
  $('#status').className = 'status ' + cls;
}

function renderDraftBar() {
  const n = state.check.changes.length;
  const dirty = isDirty();
  const errors = state.check.issues.filter(i => i.level === 'error' && i.new).length;
  $('#draftBar').classList.toggle('dirty', dirty);
  $('#discardBtn').disabled = !dirty;
  let txt = !dirty ? 'No changes yet'
    : state.checking ? 'Checking your changes…'
    : `${n} change${n === 1 ? '' : 's'} not yet published` + (errors ? ` · ${errors} problem${errors === 1 ? '' : 's'} to fix` : '');
  $('#draftSummary').textContent = txt;
  const pill = $('#navChangeCount');
  pill.hidden = !dirty || !n;
  pill.textContent = n;
}

function currentTab() {
  return document.body.dataset.tab;
}

function showTab(name) {
  if (!$(`[data-tab-panel="${name}"]`)) name = 'offenses';
  document.body.dataset.tab = name;
  $$('[data-tab-panel]').forEach(p => { p.hidden = p.dataset.tabPanel !== name; });
  $$('[data-tab-link]').forEach(a => a.classList.toggle('active', a.dataset.tabLink === name));
  if (!state.draft) return;
  if (name === 'lists') renderLists();
  if (name === 'tables') renderTableNav();
  if (name === 'publish') renderPublish();
  if (name === 'history') renderHistory();
}

window.addEventListener('hashchange', () => showTab(location.hash.slice(1)));

// Two-click confirmation without browser dialogs.
function confirmClick(btn, label, action) {
  if (btn.dataset.armed) {
    delete btn.dataset.armed;
    action();
    return;
  }
  const orig = btn.innerHTML;
  btn.dataset.armed = '1';
  btn.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> ${esc(label)}`;
  setTimeout(() => {
    if (btn.dataset.armed) { delete btn.dataset.armed; btn.innerHTML = orig; }
  }, 4000);
}

// ---------------------------------------------------------------------------
// Offenses
// ---------------------------------------------------------------------------

function sortedSections() {
  return Object.keys(offenses()).sort((a, b) => {
    const [aa, ab] = a.split('.'), [ba, bb] = b.split('.');
    return (+aa - +ba) || ab.localeCompare(bb, undefined, { numeric: true });
  });
}

function renderOffenseList() {
  const box = $('#adminOffenseList');
  if (!box || !state.draft) return;
  const q = $('#offenseSearch').value.trim().toLowerCase();
  const showRepealed = $('#showRepealed').checked;
  const pub = pubOffenses();
  const rows = [];
  for (const s of sortedSections()) {
    const o = offenses()[s];
    if (o.repealed && !showRepealed) continue;
    if (q && !s.toLowerCase().includes(q) && !(o.name || '').toLowerCase().includes(q)) continue;
    const changed = !same(o, pub[s]) || membershipChanged(s);
    rows.push(`<button type="button" class="a-item${s === state.selectedSection ? ' active' : ''}${o.repealed ? ' repealed' : ''}" data-section="${esc(s)}" role="option">
      <span class="sec">§${esc(s)}${changed ? '<i class="fa-solid fa-circle changed-dot" title="Changed in your draft" style="font-size:7px"></i>' : ''}</span>
      <span><span class="nm">${esc(o.name)}</span><br><span class="muted small">${esc(CLASS_LABEL[o.classification] || o.classification)}${o.repealed ? ' · repealed' : ''}${!pub[s] ? ' · new' : ''}</span></span>
    </button>`);
  }
  box.innerHTML = rows.join('') || '<div class="pad muted">No offenses match.</div>';
}

function membershipChanged(section) {
  const a = state.published.lists, b = state.draft.lists;
  if (vfoClassOf(a, section) !== vfoClassOf(b, section)) return true;
  return MEMBER_LISTS.some(m => listArr(a, m.list, m.key).includes(section) !== listArr(b, m.list, m.key).includes(section));
}

function fieldChanged(section, field) {
  const p = pubOffenses()[section];
  return p ? !same(p[field] ?? null, offenses()[section][field] ?? null) : false;
}

function renderOffenseEditor() {
  const panel = $('#offenseEditor');
  const s = state.selectedSection;
  const o = s && offenses()[s];
  if (!o) {
    panel.innerHTML = `<div class="empty-state"><div class="big-icon"><i class="fa-solid fa-book-open"></i></div><p>Pick an offense to edit it, or add a new one.</p></div>`;
    return;
  }
  const isNew = !pubOffenses()[s];
  const ch = (f) => fieldChanged(s, f) ? ' changed' : '';
  const vfo = vfoClassOf(state.draft.lists, s);
  const pubVfo = isNew ? '' : vfoClassOf(state.published.lists, s);
  const classOpts = CLASSES.map(([v, l]) => `<option value="${v}"${v === o.classification ? ' selected' : ''}>${l}</option>`).join('');
  const members = MEMBER_LISTS.map((m, i) => {
    const on = listArr(state.draft.lists, m.list, m.key).includes(s);
    const was = listArr(state.published.lists, m.list, m.key).includes(s);
    const src = state.draft.lists.lists[m.list]?.source || '';
    return `<label class="member${on !== was && !isNew ? ' field changed' : ''}">
      <span class="check-row"><input type="checkbox" data-member="${i}"${on ? ' checked' : ''} /> <strong>${esc(m.label)}</strong></span>
      <span class="src">${esc(m.help)}${src ? ` — ${esc(src.split(' — ')[0])}` : ''}</span>
    </label>`;
  }).join('');
  const cond = o.conditionalClassification;
  panel.innerHTML = `
    <div class="panel-body">
      <div class="editor-head">
        <div>
          <div class="muted small">Penal Law §${esc(s)} · Article ${esc(o.article)}${isNew ? ' · <span class="label label-success">New</span>' : ''}${o.repealed ? ' · <span class="label label-danger">Repealed</span>' : ''}</div>
          <h2>${esc(o.name || 'Untitled offense')}</h2>
        </div>
        <a class="btn btn-default btn-sm" href="../#${encodeURIComponent(s)}" target="_blank" rel="noopener"><i class="fa-solid fa-arrow-up-right-from-square"></i> Open live page</a>
      </div>

      ${o.repealed ? `<div class="alert alert-warning" style="margin-top:16px"><i class="fa-solid fa-ban"></i> Repealed ${esc(o.repealed.date)}${o.repealed.note ? ` — ${esc(o.repealed.note)}` : ''}. It is hidden from the public offense list.</div>` : ''}

      <div class="form-section">
        <h3>Offense</h3>
        <div class="form-grid">
          <label class="field wide${ch('name')}"><span>Name</span><input type="text" data-f="name" value="${esc(o.name)}" /></label>
          <label class="field${ch('classification')}"><span>Classification</span><select data-f="classification">${classOpts}</select></label>
          <label class="field"><span>Article</span><input type="text" value="${esc(o.article)}" disabled /><small>Set from the section number.</small></label>
          <label class="field wide${ch('elements')}"><span>Elements <em class="muted">(shown to users)</em></span><textarea data-f="elements" rows="4">${esc(o.elements || '')}</textarea></label>
        </div>
      </div>

      <div class="form-section">
        <h3>Attempt / conspiracy</h3>
        <div class="form-grid">
          <div class="field${ch('isAttempt')}${ch('attemptOf')}">
            <label class="check-row"><input type="checkbox" data-f="isAttempt"${o.isAttempt ? ' checked' : ''} /> This section is an attempt of another offense</label>
            ${o.isAttempt ? `<input type="text" data-f="attemptOf" value="${esc(o.attemptOf || '')}" placeholder="Target section, e.g. 125.25" />` : ''}
          </div>
          <div class="field${ch('isConspiracy')}${ch('conspiracyOf')}">
            <label class="check-row"><input type="checkbox" data-f="isConspiracy"${o.isConspiracy ? ' checked' : ''} /> This section is a conspiracy to commit another offense</label>
            ${o.isConspiracy ? `<input type="text" data-f="conspiracyOf" value="${esc(o.conspiracyOf || '')}" placeholder="Target section, e.g. 125.25" />` : ''}
          </div>
        </div>
      </div>

      <div class="form-section">
        <h3>Statutory lists</h3>
        <div class="member-grid">
          <label class="member${vfo !== pubVfo && !isNew ? ' field changed' : ''}">
            <span><strong>Violent felony offense</strong></span>
            <select data-vfo>
              <option value="">Not a violent felony offense</option>
              ${VFO_CLASSES.map(c => `<option value="${c}"${c === vfo ? ' selected' : ''}>Violent felony, ${humanize(c)}</option>`).join('')}
            </select>
            <span class="src">PL 70.02(1)</span>
          </label>
          ${members}
        </div>
      </div>

      ${cond || o.subdivisions ? `<div class="form-section"><h3>Special rules</h3><div class="readonly-box">
        ${cond ? `Classification depends on the facts: ${esc(CLASS_LABEL[cond.fallback] || cond.fallback)} by default, ${cond.rules.map(r => `${esc(CLASS_LABEL[r.resulting_classification] || r.resulting_classification)} when ${esc(humanize(r.field).toLowerCase())}`).join('; ')}.` : ''}
        ${o.subdivisions ? `This offense has subdivision-specific rules.` : ''}
        <br><span class="muted">These rules are part of the engine's logic. Ask the CrimeTime developers to change them.</span>
      </div></div>` : ''}

      <div class="danger-zone">
        ${isNew ? `<h3>Remove this new offense</h3>
          <p class="note">It hasn't been published yet, so it can be removed completely.</p>
          <button class="btn btn-danger-outline btn-sm" type="button" data-action="delete-new"><i class="fa-solid fa-trash"></i> Remove offense</button>`
        : o.repealed ? `<h3>Repealed</h3>
          <button class="btn btn-default btn-sm" type="button" data-action="unrepeal"><i class="fa-solid fa-rotate-left"></i> Undo repeal</button>`
        : `<h3>Repeal</h3>
          <p class="note">Use this when the legislature repeals the section. It stays in the data for the record but is hidden from users.</p>
          <div class="row-actions">
            <label class="field"><span>Repeal date</span><input type="date" id="repealDate" /></label>
            <label class="field"><span>Note (e.g. chapter law)</span><input type="text" id="repealNote" /></label>
            <label class="check-row"><input type="checkbox" id="repealLists" checked /> Also remove it from all lists</label>
            <button class="btn btn-danger-outline btn-sm" type="button" data-action="repeal"><i class="fa-solid fa-ban"></i> Mark repealed</button>
          </div>`}
      </div>
    </div>`;
}

function onOffenseEdit(e) {
  const s = state.selectedSection;
  const o = s && offenses()[s];
  if (!o) return;
  const t = e.target;
  if (t.dataset.f) {
    const f = t.dataset.f;
    if (t.type === 'checkbox') {
      o[f] = t.checked;
      const ref = f === 'isAttempt' ? 'attemptOf' : 'conspiracyOf';
      if (!t.checked) o[ref] = null;
      renderOffenseEditor();
    } else {
      const v = t.value.trim();
      o[f] = (f === 'elements' || f === 'attemptOf' || f === 'conspiracyOf') && !v ? null : v;
      t.closest('.field')?.classList.toggle('changed', fieldChanged(s, f));
      if (f === 'name') $('#offenseEditor h2').textContent = v || 'Untitled offense';
    }
  } else if (t.dataset.member !== undefined) {
    const m = MEMBER_LISTS[+t.dataset.member];
    setMembership(m.list, m.key, s, t.checked);
    renderOffenseEditor();
  } else if (t.hasAttribute('data-vfo')) {
    setVfoClass(s, t.value);
    renderOffenseEditor();
  } else {
    return;
  }
  draftChanged();
}

function onOffenseAction(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const s = state.selectedSection;
  const o = offenses()[s];
  const act = btn.dataset.action;
  if (act === 'delete-new') {
    confirmClick(btn, 'Click again to remove', () => {
      removeFromAllLists(s);
      delete offenses()[s];
      state.selectedSection = null;
      renderOffenseEditor();
      renderOffenseList();
      draftChanged();
    });
  } else if (act === 'repeal') {
    const date = $('#repealDate').value;
    if (!date) { $('#repealDate').focus(); $('#repealDate').reportValidity?.(); return; }
    o.repealed = { date, note: $('#repealNote').value.trim() };
    if ($('#repealLists').checked) removeFromAllLists(s);
    renderOffenseEditor();
    renderOffenseList();
    draftChanged();
  } else if (act === 'unrepeal') {
    delete o.repealed;
    renderOffenseEditor();
    renderOffenseList();
    draftChanged();
  } else if (act === 'create') {
    createOffense();
  }
}

function renderNewOffenseForm() {
  state.selectedSection = null;
  renderOffenseList();
  $('#offenseEditor').innerHTML = `
    <div class="panel-body">
      <div class="editor-head"><h2>Add an offense</h2></div>
      <p class="hint-line">For a section the legislature has added. You can set its lists and other details on the next screen.</p>
      <div class="form-grid" style="margin-top:16px">
        <label class="field"><span>Section number</span><input type="text" id="newSection" placeholder="e.g. 120.19" /></label>
        <label class="field"><span>Classification</span><select id="newClass">${CLASSES.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select></label>
        <label class="field wide"><span>Name</span><input type="text" id="newName" placeholder="e.g. Assault on a transit worker" /></label>
      </div>
      <div id="newError" class="alert alert-danger" style="margin-top:16px" hidden></div>
      <div style="margin-top:16px"><button class="btn btn-navy" type="button" data-action="create"><i class="fa-solid fa-plus"></i> Add offense</button></div>
    </div>`;
  $('#newSection').focus();
}

function createOffense() {
  const section = $('#newSection').value.trim();
  const name = $('#newName').value.trim();
  const err = (msg) => { const el = $('#newError'); el.textContent = msg; el.hidden = false; };
  if (!SECTION_RE.test(section)) return err('Section number must look like 120.05 (or 120.05-a).');
  if (offenses()[section]) return err(`§${section} already exists. Pick it from the list to edit it.`);
  if (!name) return err('Enter the offense name.');
  offenses()[section] = {
    article: parseInt(section.split('.')[0], 10),
    section,
    name,
    classification: $('#newClass').value,
    elements: null,
    isAttempt: false,
    attemptOf: null,
    isConspiracy: false,
    conspiracyOf: null,
  };
  state.selectedSection = section;
  $('#offenseSearch').value = '';
  renderOffenseList();
  renderOffenseEditor();
  draftChanged();
}

// ---------------------------------------------------------------------------
// Statutory lists
// ---------------------------------------------------------------------------

function listGroups() {
  const L = state.draft.lists.lists;
  return [
    { title: 'Violent felony offenses', src: L.VFO_LIST.source, subs: VFO_CLASSES.map(c => ({ path: ['VFO_LIST', c, 'sections'], title: `${humanize(c)} violent felonies` })) },
    { title: 'Sexually motivated felonies', src: L.SMF_LIST.source, subs: [{ path: ['SMF_LIST', 'sections'], title: 'Eligible sections' }] },
    { title: 'Hate crimes', src: L.HATECRIME_LIST.source, subs: [{ path: ['HATECRIME_LIST', 'sections'], title: 'Specified offenses' }] },
    { title: 'Crimes of terrorism', src: L.TERRORISM_LIST.source, subs: [{ path: ['TERRORISM_LIST', 'sections'], title: 'Specified offenses' }] },
    { title: 'For-hire driver victims', src: L.FOR_HIRE_LIST.source, subs: [
      { path: ['FOR_HIRE_LIST', 'completedSections'], title: 'Completed offenses' },
      { path: ['FOR_HIRE_LIST', 'attemptOfSections'], title: 'Attempts of' },
    ] },
  ];
}

function renderLists() {
  const D = state.draft.lists.lists, P = state.published.lists.lists;
  const off = offenses();
  $('#listsEditor').innerHTML = listGroups().map(g => `
    <section class="list-block">
      <header><h3>${esc(g.title)}</h3><p>${esc(g.src || '')}</p></header>
      ${g.subs.map(sub => {
        const cur = getAt(D, sub.path) || [];
        const was = getAt(P, sub.path) || [];
        const removed = was.filter(s => !cur.includes(s));
        const pathAttr = esc(JSON.stringify(sub.path));
        return `<div class="sublist">
          <h4>${esc(sub.title)} <span class="muted small">(${cur.length})</span></h4>
          <div class="chips">${cur.map(s => `<span class="chip${was.includes(s) ? '' : ' added'}${off[s] ? '' : ' unknown'}" title="${esc(off[s]?.name || 'Not in the offense list')}">§${esc(s)}<button type="button" aria-label="Remove §${esc(s)}" data-remove="${esc(s)}" data-path="${pathAttr}">×</button></span>`).join('')}</div>
          ${removed.length ? `<div class="removed-note">Removed in your draft: ${removed.map(s => '§' + esc(s)).join(', ')}</div>` : ''}
          <form class="add-row" data-path="${pathAttr}"><input type="text" placeholder="Add section, e.g. 120.05" aria-label="Add a section to ${esc(sub.title)}" /><button class="btn btn-default btn-sm" type="submit">Add</button></form>
        </div>`;
      }).join('')}
    </section>`).join('');
}

function onListsClick(e) {
  const b = e.target.closest('[data-remove]');
  if (!b) return;
  const arr = getAt(state.draft.lists.lists, JSON.parse(b.dataset.path));
  const i = arr.indexOf(b.dataset.remove);
  if (i >= 0) arr.splice(i, 1);
  renderLists();
  draftChanged();
}

function onListsSubmit(e) {
  const form = e.target.closest('form.add-row');
  if (!form) return;
  e.preventDefault();
  const input = form.querySelector('input');
  const s = input.value.trim();
  if (!SECTION_RE.test(s)) { input.setCustomValidity('Enter a section number like 120.05'); input.reportValidity(); input.setCustomValidity(''); return; }
  if (!offenses()[s]) { input.setCustomValidity(`§${s} is not in the offense list. Add the offense first.`); input.reportValidity(); input.setCustomValidity(''); return; }
  const arr = getAt(state.draft.lists.lists, JSON.parse(form.dataset.path));
  if (!arr.includes(s)) arr.push(s);
  renderLists();
  draftChanged();
}

// ---------------------------------------------------------------------------
// Sentencing tables (generic, structure-preserving editor)
// ---------------------------------------------------------------------------

function renderTableNav() {
  const keys = Object.keys(state.draft.tables).filter(k => !k.startsWith('_'));
  const order = Object.keys(TABLE_NAMES);
  keys.sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99));
  $('#tableNav').innerHTML = keys.map(k => {
    const [name, sub] = TABLE_NAMES[k] || [humanize(k), ''];
    const changed = !same(state.draft.tables[k], state.published.tables[k]);
    return `<button type="button" data-table="${esc(k)}" class="${k === state.selectedTable ? 'active' : ''}">${esc(name)}${changed ? ' <i class="fa-solid fa-circle" style="font-size:7px;color:var(--gold)" title="Changed"></i>' : ''}<small>${esc(sub)}</small></button>`;
  }).join('');
}

function renderTableEditor() {
  const k = state.selectedTable;
  const panel = $('#tableEditor');
  if (!k) return;
  const [name, sub] = TABLE_NAMES[k] || [humanize(k), ''];
  panel.innerHTML = `<div class="panel-body">
    <div class="editor-head"><div><div class="muted small">${esc(sub)}</div><h2>${esc(name)}</h2></div></div>
    <p class="hint-line">Change values when the statute changes. Highlighted cells differ from the live data.
    To add a new kind of sentence or offender status, ask the CrimeTime developers.</p>
    <div style="margin-top:16px">${renderNode(state.draft.tables[k], [k], 0)}</div>
  </div>`;
}

function notesHtml(obj) {
  const notes = Object.entries(obj).filter(([k]) => k.startsWith('_'));
  if (!notes.length) return '';
  return notes.map(([, v]) => `<div class="notes">${esc(Array.isArray(v) ? v.join('\n') : typeof v === 'object' ? JSON.stringify(v, null, 1) : v)}</div>`).join('');
}

const isScalar = (v) => v === null || ['string', 'number', 'boolean'].includes(typeof v);
const isFlat = (v) => isScalar(v) || (Array.isArray(v) && v.every(isScalar));

function isGrid(obj) {
  const vals = Object.entries(obj).filter(([k]) => !k.startsWith('_')).map(([, v]) => v);
  return vals.length >= 2 && vals.every(v => v && typeof v === 'object' && !Array.isArray(v)
    && Object.entries(v).every(([k, x]) => k.startsWith('_') || isFlat(x)));
}

function pubAt(path) {
  return getAt(state.published.tables, path);
}

// Keys whose values are engine codes (read by the pipeline's logic, not legal
// numbers or citations). Shown, but only developers change them.
const LOCKED_KEYS = new Set([
  'type', 'sentenceType', 'vfo', 'eligibilityList', 'factField', 'order', 'triggeringFactor',
  'triggeringFactors', 'activeVersion', 'name', 'minTermRule', 'effect',
]);
const LADDER_CLASSES = [
  'ClassA_I_Felony', 'ClassA_II_Felony', 'ClassB_Felony', 'ClassB_Violent_Felony', 'ClassC_Felony', 'ClassC_Violent_Felony',
  'ClassD_Felony', 'ClassD_Violent_Felony', 'ClassE_Felony', 'ClassE_Violent_Felony',
  'ClassA_Misdemeanor', 'ClassB_Misdemeanor', 'Unclassified_Misdemeanor', 'Violation',
];

function inputFor(value, path) {
  const p = esc(JSON.stringify(path));
  const key = [...path].reverse().find(k => typeof k === 'string');
  if (value === null) return '<span class="muted">—</span>';
  if (LOCKED_KEYS.has(key) && !(typeof value === 'number' || typeof value === 'boolean')) {
    return `<span class="locked" title="Engine setting — ask the CrimeTime developers to change it"><i class="fa-solid fa-lock"></i> ${esc(Array.isArray(value) ? value.join(', ') : value)}</span>`;
  }
  if (typeof value === 'string' && LADDER_CLASSES.includes(value)) {
    return `<select data-path="${p}" data-kind="str">${LADDER_CLASSES.map(c => `<option value="${c}"${c === value ? ' selected' : ''}>${esc(humanize(c))}</option>`).join('')}</select>`;
  }
  if (typeof value === 'boolean') return `<label class="check-row"><input type="checkbox" data-path="${p}" data-kind="bool"${value ? ' checked' : ''} /> Yes</label>`;
  if (isNum(value)) return `<input type="number" step="any" data-path="${p}" data-kind="num" value="${value}" />`;
  if (typeof value === 'string') {
    return value.length > 70
      ? `<textarea rows="2" data-path="${p}" data-kind="str">${esc(value)}</textarea>`
      : `<input type="text" data-path="${p}" data-kind="str" value="${esc(value)}" />`;
  }
  if (isPair(value)) {
    return `<span class="pair"><input type="number" step="any" data-path="${p}" data-kind="pair0" value="${value[0]}" aria-label="minimum" /><span class="to">to</span><input type="number" step="any" data-path="${p}" data-kind="pair1" value="${value[1]}" aria-label="maximum" /></span>`;
  }
  if (Array.isArray(value) && value.every(isNum)) return `<input type="text" data-path="${p}" data-kind="numlist" value="${esc(value.join(', '))}" />`;
  if (Array.isArray(value) && value.every(v => typeof v === 'string')) return `<input type="text" data-path="${p}" data-kind="strlist" value="${esc(value.join(', '))}" />`;
  return `<code class="small">${esc(JSON.stringify(value))}</code>`;
}

function renderGrid(obj, path) {
  const rows = Object.keys(obj).filter(k => !k.startsWith('_'));
  const cols = [];
  for (const r of rows) for (const c of Object.keys(obj[r])) if (!c.startsWith('_') && !cols.includes(c)) cols.push(c);
  const rowNotes = rows.flatMap(r => Object.entries(obj[r]).filter(([c]) => c.startsWith('_')).map(([, v]) => `${humanize(r)}: ${v}`));
  return `<div class="grid-wrap"><table class="grid">
    <thead><tr><th></th>${cols.map(c => `<th>${esc(humanize(c))}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr><th>${esc(humanize(r))}</th>${cols.map(c => {
      if (!(c in obj[r])) return '<td class="na">—</td>';
      const changed = !same(obj[r][c], pubAt([...path, r, c]));
      return `<td class="${changed ? 'changed' : ''}">${inputFor(obj[r][c], [...path, r, c])}</td>`;
    }).join('')}</tr>`).join('')}</tbody>
  </table></div>${rowNotes.length ? `<div class="notes">${esc(rowNotes.join('\n'))}</div>` : ''}`;
}

function renderNode(obj, path, depth) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return `<div class="kv"><span class="k">${esc(humanize(path[path.length - 1]))}</span><span>${inputFor(obj, path)}</span></div>`;
  }
  let html = notesHtml(obj);
  if (isGrid(obj)) return html + renderGrid(obj, path);
  for (const [k, v] of Object.entries(obj)) {
    if (k.startsWith('_')) continue;
    const p = [...path, k];
    if (isFlat(v)) {
      const changed = !same(v, pubAt(p));
      html += `<div class="kv${changed ? ' changed' : ''}"><span class="k">${esc(humanize(k))}</span><span>${inputFor(v, p)}</span></div>`;
    } else if (Array.isArray(v)) {
      html += v.map((item, i) => `<details class="tbl-block"${depth < 1 ? ' open' : ''}><summary>${esc(humanize(k))} ${i + 1}</summary><div class="tbl-body">${renderNode(item, [...p, i], depth + 1)}</div></details>`).join('');
    } else if (k === 'statuses' || k === 'rows') {
      html += `<div class="tbl-body" style="padding:0">${renderNode(v, p, depth)}</div>`;
    } else {
      const title = v.label || humanize(k);
      const changed = !same(v, pubAt(p));
      html += `<details class="tbl-block"${depth < 1 || changed ? ' open' : ''}><summary>${esc(title)}${changed ? ' <i class="fa-solid fa-circle" style="font-size:7px;color:var(--gold)"></i>' : ''}<span class="key">${esc(humanize(k) !== title ? humanize(k) : '')}</span></summary><div class="tbl-body">${renderNode(v, p, depth + 1)}</div></details>`;
    }
  }
  return html;
}

function onTableEdit(e) {
  const t = e.target;
  if (!t.dataset.path) return;
  const path = JSON.parse(t.dataset.path);
  const cur = getAt(state.draft.tables, path);
  let v;
  switch (t.dataset.kind) {
    case 'bool': v = t.checked; break;
    case 'num': v = t.value === '' ? cur : Number(t.value); break;
    case 'str': v = t.value; break;
    case 'pair0': v = [t.value === '' ? cur[0] : Number(t.value), cur[1]]; break;
    case 'pair1': v = [cur[0], t.value === '' ? cur[1] : Number(t.value)]; break;
    case 'numlist': {
      const parts = t.value.split(',').map(x => x.trim()).filter(Boolean).map(Number);
      if (parts.some(n => !Number.isFinite(n))) { t.setCustomValidity('Numbers separated by commas'); t.reportValidity(); t.setCustomValidity(''); return; }
      v = parts; break;
    }
    case 'strlist': v = t.value.split(',').map(x => x.trim()).filter(Boolean); break;
    default: return;
  }
  setAt(state.draft.tables, path, v);
  const changed = !same(v, pubAt(path));
  (t.closest('td') || t.closest('.kv'))?.classList.toggle('changed', changed);
  renderTableNav();
  draftChanged();
}

// ---------------------------------------------------------------------------
// Review & publish
// ---------------------------------------------------------------------------

function fmtVal(v) {
  if (v === null || v === undefined) return '<em class="muted">none</em>';
  if (isPair(v)) return esc(`${v[0]} to ${v[1]}`);
  if (Array.isArray(v)) return esc(v.join(', '));
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  const s = String(v);
  return esc(s.length > 140 ? s.slice(0, 140) + '…' : s);
}

function describePath(c) {
  const p = c.path;
  if (p[0] === 'offenses') {
    const o = offenses()[p[1]] || pubOffenses()[p[1]];
    return `§${p[1]} ${o?.name || ''} › ${humanize(p.slice(2).join(' ') || 'record')}`;
  }
  if (p[0] === 'lists') return [LIST_NAMES[p[1]] || humanize(p[1]), ...p.slice(2).map(humanize)].join(' › ');
  const [name] = TABLE_NAMES[p[0]] || [humanize(p[0])];
  const parts = [name];
  let node = state.draft.tables[p[0]] ?? state.published.tables[p[0]];
  for (const k of p.slice(1)) {
    node = node?.[k];
    if (k === 'statuses' || k === 'rows') continue;
    parts.push(node && typeof node === 'object' && node.label ? node.label : humanize(k));
  }
  return parts.join(' › ');
}

function changeLine(c) {
  if (c.added || c.removed) {
    const bits = [];
    if (c.added?.length) bits.push(`added <span class="new">${c.added.map(s => '§' + esc(s)).join(', ')}</span>`);
    if (c.removed?.length) bits.push(`removed <span class="old">${c.removed.map(s => '§' + esc(s)).join(', ')}</span>`);
    return bits.join('; ');
  }
  if (c.old === null && typeof c.new === 'object' && c.new !== null) return '<span class="new">added</span>';
  return `<span class="old">${fmtVal(c.old)}</span> → <span class="new">${fmtVal(c.new)}</span>`;
}

function summarizeChanges(changes) {
  // Collapse whole-offense additions (one line per new offense).
  const out = [];
  const seenNew = new Set();
  for (const c of changes) {
    const p = c.path;
    if (p[0] === 'offenses' && !pubOffenses()[p[1]]) {
      if (!seenNew.has(p[1])) { seenNew.add(p[1]); out.push({ where: `§${p[1]} ${offenses()[p[1]]?.name || ''}`, html: '<span class="new">new offense</span>', text: `Added §${p[1]}` }); }
      continue;
    }
    out.push({ where: describePath(c), html: changeLine(c), text: `${describePath(c)}: ${JSON.stringify(c.old)} → ${JSON.stringify(c.new)}` });
  }
  return out;
}

function renderPublish() {
  const { issues, changes } = state.check;
  const dirty = isDirty();
  const lines = summarizeChanges(changes);
  $('#changesBody').innerHTML = !dirty
    ? '<p class="muted">Your draft matches the live data. Edit offenses, lists or tables first.</p>'
    : state.checking && !changes.length ? '<p class="muted"><span class="spinner dark"></span> Checking…</p>'
    : `<ul class="change-list">${lines.map(l => `<li><div class="where">${esc(l.where)}</div>${l.html}</li>`).join('')}</ul>`;

  const newIssues = issues.filter(i => i.new);
  const oldIssues = issues.filter(i => !i.new);
  const issueHtml = (i) => `<div class="issue"><i class="fa-solid ${i.level === 'error' ? 'fa-circle-xmark' : 'fa-triangle-exclamation'}"></i><span><strong>${esc(i.where)}:</strong> ${esc(i.message)}</span></div>`;
  $('#issuesBody').innerHTML = `
    ${newIssues.length ? newIssues.map(issueHtml).join('') : `<p class="ok"><i class="fa-solid fa-circle-check" style="color:var(--success)"></i> Your changes introduce no problems.</p>`}
    ${oldIssues.length ? `<details class="more"><summary>${oldIssues.length} existing note${oldIssues.length === 1 ? '' : 's'} in the live data (not caused by you)</summary>${oldIssues.map(issueHtml).join('')}</details>` : ''}`;

  renderImpact();
  renderChecklist();
}

function renderImpact() {
  const body = $('#impactBody');
  const r = state.impact;
  const intro = `<p class="hint-line">Runs the sentencing engine on every affected offense, prior record and special circumstance,
    once with the live data and once with your changes, and lists every result that changes.</p>`;
  if (!r) { body.innerHTML = intro; return; }
  if (r.running) { body.innerHTML = `${intro}<p><span class="spinner dark"></span> Running… a change to the sentencing tables re-checks all 42,000+ scenarios and can take a minute.</p>`; return; }
  if (r.error) { body.innerHTML = `${intro}<div class="alert alert-danger">${esc(r.error)}</div>`; return; }
  const stale = state.impactStale ? `<div class="alert alert-warning" style="margin-bottom:12px">You've edited since this check. Run it again before publishing.</div>` : '';
  body.innerHTML = `${stale}
    <div class="impact-stats">
      <div class="metric"><div class="lbl">Checked</div><div class="val">${r.scenarios_checked.toLocaleString()} scenarios</div><div class="small muted">${esc(r.scope)}</div></div>
      <div class="metric"><div class="lbl">Changed</div><div class="val">${r.scenarios_changed.toLocaleString()} in ${r.sections_changed} offense${r.sections_changed === 1 ? '' : 's'}</div></div>
      <div class="metric"><div class="lbl">Now failing</div><div class="val" style="color:${r.severe ? 'var(--danger)' : 'inherit'}">${r.severe}</div></div>
    </div>
    ${r.scenarios_changed === 0 ? '<p class="muted">No sentencing result changes. (Expected for edits to names or descriptions only.)</p>' : ''}
    ${r.groups.map(g => {
      const severe = g.changes.some(c => c.severe);
      return `<div class="impact-group${severe ? ' severe' : ''}">
        <header><strong>§${esc(g.section)}</strong> ${esc(g.name)}</header>
        <div class="body">
          ${g.changes.map(c => `<div><strong>${esc(humanize(c.field))}:</strong> ${c.old == null ? '' : `<span class="old">${fmtVal(c.old)}</span> → `}${c.new == null ? '<span class="old">removed</span>' : `<span class="new">${fmtVal(c.new)}</span>`}</div>`).join('')}
          <div class="scen">${g.scenarios.length} scenario${g.scenarios.length === 1 ? '' : 's'}: ${esc(g.scenarios.slice(0, 6).join(' · '))}${g.scenarios.length > 6 ? ` · and ${g.scenarios.length - 6} more` : ''}</div>
        </div></div>`;
    }).join('')}
    ${r.truncated ? `<p class="muted">…and ${r.truncated} more groups of changes.</p>` : ''}`;
}

async function runImpact() {
  const btn = $('#impactBtn');
  btn.disabled = true;
  clearTimeout(syncTimer);
  await syncDraft();
  state.impact = { running: true };
  state.impactStale = false;
  renderImpact();
  try {
    state.impact = await engine.call('impact_json');
  } catch (e) {
    state.impact = { error: e.message };
    state.impactStale = true;
  }
  btn.disabled = false;
  renderPublish();
}

function recordFields() {
  return {
    author: $('#recAuthor').value.trim(),
    reason: $('#recReason').value.trim(),
    source: $('#recSource').value.trim(),
    effective: $('#recEffective').value,
  };
}

function publishChecks() {
  const errors = state.check.issues.filter(i => i.level === 'error').length;
  const rec = recordFields();
  return [
    [isDirty() && state.check.changes.length > 0, 'There are changes to publish'],
    [!state.checking && errors === 0, errors ? `Fix ${errors} problem${errors === 1 ? '' : 's'} (step 2)` : 'No problems'],
    [!!state.impact && !state.impact.running && !state.impact.error && !state.impactStale, 'Effect on sentences checked after your last edit (step 3)'],
    [!!(rec.author && rec.reason && rec.source), 'Name, source and reason filled in (step 5)'],
  ];
}

function renderChecklist() {
  const checks = publishChecks();
  $('#publishChecklist').innerHTML = checks.map(([ok, label]) =>
    `<li class="${ok ? 'ok' : 'no'}"><i class="fa-solid ${ok ? 'fa-circle-check' : 'fa-circle'}"></i> ${esc(label)}</li>`).join('');
  $('#publishBtn').disabled = !checks.every(([ok]) => ok);
}

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function nextVersion(prev) {
  const t = today();
  const m = /^(\d{4}-\d{2}-\d{2})\.(\d+)$/.exec(prev || '');
  return m && m[1] === t ? `${t}.${+m[2] + 1}` : `${t}.1`;
}

async function publish() {
  const btn = $('#publishBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Building bundle…';
  try {
    await syncDraft();
    const rec = recordFields();
    const prev = state.published.manifest;
    const version = nextVersion(prev.version);
    const manifest = {
      version,
      published: today(),
      basedOn: prev.version,
      changes: [{
        version, date: today(), ...rec,
        summary: summarizeChanges(state.check.changes).map(l => l.text).slice(0, 300),
      }, ...(prev.changes || [])],
    };
    const b64 = await engine.call('bundle_json', JSON.stringify(manifest));
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `crimetime-data-${version}.zip` });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    state.lastBundleVersion = version;
    autosave();
    $('#publishDone').innerHTML = `<div class="alert alert-success">
      <strong><i class="fa-solid fa-circle-check"></i> Downloaded crimetime-data-${esc(version)}.zip.</strong>
      <ol>
        <li>Keep a copy of the file. It's your record of this version and lets you roll back later.</li>
        <li>Give it to whoever manages the CrimeTime server, or upload it yourself the way your hosting guide describes
          (unzip it into the site's <code>data/</code> folder, replacing the files there).</li>
        <li>Reload this page once it's live: the top bar should show data <strong>${esc(version)}</strong>.</li>
      </ol></div>`;
  } catch (e) {
    $('#publishDone').innerHTML = `<div class="alert alert-danger">Could not build the bundle: ${esc(e.message)}</div>`;
  }
  btn.innerHTML = '<i class="fa-solid fa-file-zipper"></i> Download data bundle';
  renderChecklist();
}

async function tryCase(e) {
  e.preventDefault();
  const out = $('#tryResult');
  const section = $('#trySection').value.trim();
  if (!offenses()[section]) { out.innerHTML = `<div class="alert alert-danger">§${esc(section)} is not in the offense list.</div>`; return; }
  const attempt = $('#tryAttempt').checked;
  const body = {
    section,
    predicate_felonies: +$('#tryPriors').value || 0,
    predicate_vfos: +$('#tryVfos').value || 0,
    is_attempt: attempt,
    attempt_of_section: attempt ? section : null,
    hate_crime_motivated: $('#tryHate').checked,
    sexually_motivated: $('#trySmf').checked,
    terrorism_motivated: $('#tryTerror').checked,
  };
  out.innerHTML = '<p><span class="spinner dark"></span> Calculating…</p>';
  try {
    clearTimeout(syncTimer);
    await syncDraft();
    const r = await engine.call('try_case_json', JSON.stringify(body));
    const col = (title, x) => {
      if (!x) return `<div class="metric"><div class="lbl">${title}</div><div class="val muted">Not in this version</div></div>`;
      if (x.error) return `<div class="metric"><div class="lbl">${title}</div><div class="val" style="color:var(--danger)">${esc(x.error)}</div></div>`;
      return `<div class="metric"><div class="lbl">${title}</div>
        <div class="val">${esc(CLASS_LABEL[x.classification] || x.classification)}${x.is_vfo ? ' (violent)' : ''}</div>
        <div class="small muted">${esc(x.offender_status_label || '')}</div>
        <ul class="small" style="margin:8px 0 0;padding-left:18px">${(x.available_dispositions || []).map(d => `<li>${esc(d.label)}</li>`).join('')}</ul></div>`;
    };
    out.innerHTML = `<div class="impact-stats" style="display:grid;grid-template-columns:1fr 1fr">${col('Live data', r.live)}${col('With your changes', r.draft)}</div>`;
  } catch (err) {
    out.innerHTML = `<div class="alert alert-danger">${esc(err.message)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// History & opening a saved bundle
// ---------------------------------------------------------------------------

function renderHistory() {
  const m = state.published.manifest;
  $('#historyBody').innerHTML = (m.changes || []).map(c => `
    <div class="hist">
      <h3>Version ${esc(c.version)}</h3>
      <div class="meta">${esc(c.date)} · ${esc(c.author || 'unknown')}${c.effective ? ` · effective ${esc(c.effective)}` : ''}${c.source ? ` · ${esc(c.source)}` : ''}</div>
      <p>${esc(c.reason || '')}</p>
      ${c.summary?.length ? `<details class="more"><summary>${c.summary.length} change${c.summary.length === 1 ? '' : 's'}</summary><ul>${c.summary.map(s => `<li>${esc(s)}</li>`).join('')}</ul></details>` : ''}
    </div>`).join('') || '<p class="muted">No history recorded yet.</p>';
}

async function openBundle(file) {
  const msg = $('#openBundleMsg');
  msg.innerHTML = '<p><span class="spinner dark"></span> Opening…</p>';
  try {
    const buf = new Uint8Array(await file.arrayBuffer());
    let bin = '';
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    const r = await engine.call('read_bundle_json', btoa(bin));
    state.draft = { lists: r.lists, tables: r.tables };
    state.selectedSection = null;
    renderAll();
    draftChanged();
    const v = r.manifest?.version || 'unknown version';
    msg.innerHTML = `<div class="alert alert-info">Your draft now matches <strong>${esc(v)}</strong> from ${esc(file.name)}.
      Review &amp; publish it to make it live again${isDirty() ? '' : ' — it is identical to the live data, so there is nothing to publish'}.</div>`;
  } catch (e) {
    msg.innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

function renderAll() {
  renderOffenseList();
  renderOffenseEditor();
  renderDraftBar();
  showTab(currentTab());
  if (state.selectedTable) renderTableEditor();
}

async function fetchJson(name) {
  const r = await fetch(DATA + name, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  return r.json();
}

async function boot() {
  engine.onStatus(t => setStatus(t));
  const enginePromise = engine.ready.then(
    () => setStatus('Engine ready', 'ok'),
    (e) => setStatus(`Engine failed: ${e.message}`, 'err'),
  );

  let lists, tables, manifest;
  try {
    [lists, tables, manifest] = await Promise.all([
      fetchJson('lists.json'), fetchJson('sentencing_tables.json'),
      fetchJson('manifest.json').catch(() => ({ version: 'unversioned', changes: [] })),
    ]);
  } catch (e) {
    $('main').innerHTML = `<div class="alert alert-danger">Could not load the data bundle: ${esc(e.message)}</div>`;
    return;
  }
  state.published = { lists, tables, manifest };
  state.draft = { lists: clone(lists), tables: clone(tables) };
  $('#liveVersion').textContent = manifest.version;

  // Crash recovery: offer an unpublished draft from an earlier visit.
  const saved = readAutosave();
  if (saved && saved.downloadedAs && saved.downloadedAs === manifest.version) {
    clearAutosave();  // that draft is now live
  } else if (saved && saved.basedOn === manifest.version
      && (!same(saved.lists, lists) || !same(saved.tables, tables))) {
    $('#restoreWhen').textContent = new Date(saved.savedAt).toLocaleString();
    $('#restoreBanner').hidden = false;
    $('#restoreYes').onclick = () => {
      state.draft = { lists: saved.lists, tables: saved.tables };
      state.lastBundleVersion = saved.downloadedAs || null;
      $('#restoreBanner').hidden = true;
      renderAll();
      draftChanged();
    };
    $('#restoreNo').onclick = () => { clearAutosave(); $('#restoreBanner').hidden = true; };
  } else if (saved) {
    clearAutosave();  // based on older live data; don't silently re-apply it
  }

  // Wiring
  $('#offenseSearch').addEventListener('input', renderOffenseList);
  $('#showRepealed').addEventListener('change', renderOffenseList);
  $('#adminOffenseList').addEventListener('click', (e) => {
    const b = e.target.closest('[data-section]');
    if (!b) return;
    state.selectedSection = b.dataset.section;
    renderOffenseList();
    renderOffenseEditor();
  });
  $('#newOffenseBtn').addEventListener('click', renderNewOffenseForm);
  $('#offenseEditor').addEventListener('change', onOffenseEdit);
  $('#offenseEditor').addEventListener('click', onOffenseAction);
  $('#listsEditor').addEventListener('click', onListsClick);
  $('#listsEditor').addEventListener('submit', onListsSubmit);
  $('#tableNav').addEventListener('click', (e) => {
    const b = e.target.closest('[data-table]');
    if (!b) return;
    state.selectedTable = b.dataset.table;
    renderTableNav();
    renderTableEditor();
  });
  $('#tableEditor').addEventListener('change', onTableEdit);
  $('#impactBtn').addEventListener('click', runImpact);
  $('#tryForm').addEventListener('submit', tryCase);
  ['#recAuthor', '#recReason', '#recSource', '#recEffective'].forEach(s => $(s).addEventListener('input', renderChecklist));
  try { $('#recAuthor').value = localStorage.getItem('crimetime-admin-author') || ''; } catch { /* ignore */ }
  $('#recAuthor').addEventListener('change', () => { try { localStorage.setItem('crimetime-admin-author', $('#recAuthor').value.trim()); } catch { /* ignore */ } });
  $('#publishBtn').addEventListener('click', publish);
  $('#discardBtn').addEventListener('click', (e) => confirmClick(e.currentTarget, 'Click again to discard all changes', () => {
    state.draft = { lists: clone(state.published.lists), tables: clone(state.published.tables) };
    state.impact = null;
    state.lastBundleVersion = null;
    clearAutosave();
    renderAll();
    draftChanged();
  }));
  $('#bundleFile').addEventListener('change', (e) => {
    const f = e.target.files[0];
    e.target.value = '';
    if (f) openBundle(f);
  });

  showTab(location.hash.slice(1) || 'offenses');
  renderAll();
  await enginePromise;
}

boot();
