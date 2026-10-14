// CrimeTime 2.0 — frontend logic (static GitHub Pages build).
// Offense data comes from offenses.json (precomputed by scripts/build_site.py);
// sentencing runs in-browser through `engine` (engine.js → Pyodide worker).

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};

const BUILD = new URL(document.currentScript.src).searchParams.get('v') || '';
const LIST_LIMIT = 300;

const state = {
  offenses: [],
  bySection: new Map(),
  selectedSection: null,
  offenseDetail: null,
  lastResult: null,
  view: 'structured',
  engineReady: false,
  resolving: false,
};

// ---------------------------------------------------------------------------
// Engine status
// ---------------------------------------------------------------------------
function setStatus(text, cls) {
  $('#statusText').textContent = text;
  $('#status').className = 'status' + (cls ? ' ' + cls : '');
}

engine.onStatus((text) => setStatus(text));
engine.ready.then(
  () => {
    state.engineReady = true;
    setStatus('Engine ready', 'ok');
    updateResolveButton();
  },
  (e) => {
    setStatus('Engine failed to load', 'err');
    $('#result').innerHTML = `<div class="alert alert-danger"><strong>The sentencing engine could not start.</strong><br>${escapeHtml(e.message)}<br><span class="small">Try reloading the page. A recent desktop browser is required.</span></div>`;
  },
);

function updateResolveButton() {
  const btn = $('#resolveBtn');
  btn.disabled = !state.offenseDetail || !state.engineReady || state.resolving;
  if (state.resolving) {
    btn.innerHTML = '<span class="spinner"></span> Calculating…';
  } else if (state.offenseDetail && !state.engineReady) {
    btn.innerHTML = '<span class="spinner"></span> Waiting for engine…';
  } else {
    btn.innerHTML = 'Calculate Sentence <i class="fa-solid fa-arrow-right"></i>';
  }
}

// ---------------------------------------------------------------------------
// Offense list
// ---------------------------------------------------------------------------
async function loadOffenses() {
  const list = $('#offenseList');
  try {
    const r = await fetch('offenses.json?v=' + BUILD);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    state.offenses = await r.json();
    state.bySection = new Map(state.offenses.map(o => [o.section, o]));
    $('#offenseCount').textContent = `${state.offenses.length} offenses`;
    renderOffenseList($('#search').value);
    const fromHash = decodeURIComponent(location.hash.replace(/^#s=/, ''));
    if (location.hash.startsWith('#s=') && state.bySection.has(fromHash)) selectOffense(fromHash, { scroll: false });
  } catch (e) {
    list.innerHTML = `<div class="alert alert-danger">Failed to load offenses: ${escapeHtml(e.message)}</div>`;
  }
}

function renderOffenseList(filter) {
  const list = $('#offenseList');
  const f = filter.toLowerCase().trim();
  const items = f
    ? state.offenses.filter(o => o.section.includes(f) || o.name.toLowerCase().includes(f))
    : state.offenses;
  list.innerHTML = '';
  if (!items.length) {
    list.innerHTML = '<div class="muted pad">No matches.</div>';
    return;
  }
  let lastArticle = null;
  for (const o of items.slice(0, LIST_LIMIT)) {
    if (o.article !== lastArticle) {
      list.appendChild(el('div', 'article-head', `Article ${o.article}`));
      lastArticle = o.article;
    }
    const item = el('button', 'offense-item' + (o.section === state.selectedSection ? ' active' : ''));
    item.type = 'button';
    item.innerHTML = `<span class="sec">§${o.section}</span><span class="nm">${escapeHtml(o.name)}</span><span class="cls ${clsKind(o.classification)}">${shortCls(o.classification)}</span>`;
    item.onclick = () => selectOffense(o.section);
    list.appendChild(item);
  }
  if (items.length > LIST_LIMIT) {
    list.appendChild(el('div', 'muted small pad', `…${items.length - LIST_LIMIT} more — refine your search.`));
  }
}

function shortCls(c) {
  return c.replace('Class', '').replace('_Felony', 'F').replace('_Misdemeanor', 'M').replace('_Violent_', 'V');
}

function clsKind(c) {
  if (c.includes('Felony')) return 'fel';
  if (c.includes('Misdemeanor')) return 'misd';
  return 'viol';
}

// ---------------------------------------------------------------------------
// Select offense -> render case facts form
// ---------------------------------------------------------------------------
function selectOffense(section, { scroll = true } = {}) {
  const d = state.bySection.get(section);
  if (!d) return;
  state.selectedSection = section;
  state.offenseDetail = d;
  history.replaceState(null, '', '#s=' + encodeURIComponent(section));
  renderOffenseList($('#search').value);
  const list = $('#offenseList'), active = list.querySelector('.offense-item.active');
  if (active) list.scrollTop = active.offsetTop - list.offsetTop - list.clientHeight / 3;
  renderBadges(d);
  renderCaseFacts(d);
  updateResolveButton();
  if (!state.lastResult || state.lastResult.section !== section) {
    state.lastResult = null;
    $('#result').innerHTML = emptyResult();
  }
  if (scroll && window.matchMedia('(max-width: 900px)').matches) {
    document.querySelector('.panel-center').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function renderBadges(detail) {
  const wrap = $('#offenseBadge');
  wrap.innerHTML = '';
  const e = detail.eligibility;
  if (e.vfo) wrap.appendChild(badge('VFO', 'danger', 'Violent felony offense (PL 70.02)'));
  if (e.smf_eligible) wrap.appendChild(badge('SMF', 'warning', 'Sexually motivated felony eligible (PL 130.91)'));
  if (e.hatecrime_eligible) wrap.appendChild(badge('Hate Crime', 'info', 'Hate crime eligible (PL 485.05)'));
  if (e.terrorism_eligible) wrap.appendChild(badge('Terrorism', 'info', 'Crime of terrorism eligible (PL 490.25)'));
  if (e.predicate_exposure) wrap.appendChild(badge('Predicate', 'primary', 'Predicate-felony exposure'));
  if (e.yo_eligible) wrap.appendChild(badge('YO', 'success', 'Youthful offender eligible'));
}

function badge(label, kind, title) {
  const b = el('span', 'label label-' + kind, label);
  if (title) b.title = title;
  return b;
}

function renderCaseFacts(d) {
  const wrap = $('#caseFacts');
  wrap.innerHTML = '';
  const e = d.eligibility;

  // Offense summary
  const head = el('div', 'offense-summary');
  head.innerHTML = `
    <div class="os-sec">PL §${escapeHtml(d.section)} · Article ${d.article}</div>
    <div class="os-name">${escapeHtml(d.name)}</div>
    <div class="os-cls">${escapeHtml(prettyCls(d.classification))}</div>
    ${d.elements ? `<details class="elements"><summary>Elements</summary><p>${escapeHtml(d.elements)}</p></details>` : ''}`;
  wrap.appendChild(head);

  // Prior record (felonies only)
  if (e.is_felony) {
    wrap.appendChild(group('Defendant prior record', 'fa-user', `
      <div class="field-row">
        <label class="field"><span>Prior predicate felonies</span>
          <input type="number" id="cf_pred_felonies" min="0" step="1" value="0"></label>
        <label class="field"><span>…of which violent (VFO)</span>
          <input type="number" id="cf_pred_vfos" min="0" step="1" value="0"></label>
      </div>
      <div class="hint-line">Qualifying predicates per PL 70.06(1)(b) (10-year lookback). The engine derives the offender status for this offense.</div>`));
  }

  // Offense shape (felony/misdemeanor)
  if (e.is_felony || e.is_misdemeanor) {
    const preview = d.attempt_preview && !d.attempt_preview.error
      ? `<div class="hint-line">Attempt of §${escapeHtml(d.attempt_preview.target_section)} (${escapeHtml(prettyCls(d.attempt_preview.target_classification))}) resolves to <strong>${escapeHtml(prettyCls(String(d.attempt_preview.resolved)))}</strong></div>`
      : '';
    wrap.appendChild(group('Offense shape', 'fa-shapes', `
      <label class="check-row"><input type="checkbox" id="cf_attempt" ${d.is_attempt ? 'checked' : ''}> Attempt <span class="hint">PL 110.05</span></label>
      <div id="attempt_extra" class="sub-fields">
        <div class="field-row">
          <label class="field"><span>Target section</span>
            <input type="text" id="cf_attempt_of" value="${escapeHtml(d.attempt_of || d.section)}" placeholder="e.g. 125.25"></label>
          <label class="field"><span>Target subdivision</span>
            <input type="text" id="cf_subdivision" placeholder="e.g. 2"></label>
        </div>
        ${preview}
      </div>
      <label class="check-row"><input type="checkbox" id="cf_conspiracy" ${d.is_conspiracy ? 'checked' : ''}> Conspiracy <span class="hint">PL Art. 105</span></label>
      <div id="conspiracy_extra" class="sub-fields">
        <label class="field"><span>Object crime section</span>
          <input type="text" id="cf_conspiracy_of" value="${escapeHtml(d.conspiracy_of || d.section)}"></label>
      </div>`, true));
  }

  // Conditional classification
  if (d.conditional_classification) {
    const cc = d.conditional_classification;
    let html = '';
    if (cc.prompt_fields?.includes('intended_underlying_offense_class')) {
      html += `<label class="field"><span>Intended underlying offense class</span>
        <select id="cf_intended_class">
          <option value="">— none —</option>
          ${['ClassA_I_Felony', 'ClassA_II_Felony', 'ClassB_Felony', 'ClassB_Violent_Felony', 'ClassC_Felony', 'ClassD_Felony', 'ClassE_Felony']
            .map(c => `<option value="${c}">${prettyCls(c)}</option>`).join('')}
        </select></label>`;
    }
    if (cc.prompt_fields?.includes('prior_conviction_same_section_within_years')) {
      html += `<label class="field"><span>Prior conviction of same section within (years)</span>
        <input type="number" id="cf_prior_same_years" min="0" value="0"></label>`;
    }
    wrap.appendChild(group('Conditional classification', 'fa-code-branch', html));
  }

  // Enhancements
  if (e.hatecrime_eligible || e.smf_eligible || e.terrorism_eligible) {
    let html = '';
    if (e.hatecrime_eligible) html += `<label class="check-row"><input type="checkbox" id="cf_hate"> Hate crime motivated <span class="hint">PL 485.05</span></label>`;
    if (e.smf_eligible) html += `<label class="check-row"><input type="checkbox" id="cf_smf"> Sexually motivated felony <span class="hint">PL 130.91</span></label>`;
    if (e.terrorism_eligible) html += `<label class="check-row"><input type="checkbox" id="cf_terror"> Terrorism motivated <span class="hint">PL 490.25</span></label>`;
    wrap.appendChild(group('Enhancements', 'fa-arrow-up-right-dots', html, true));
  }

  // Exception triggers
  if (e.armed_eligible || e.dv_eligible) {
    let html = '';
    if (e.armed_eligible) {
      html += `<label class="check-row"><input type="checkbox" id="cf_armed_plea"> Plea from armed-felony indictment <span class="hint">CPL 220.10(5)(d)</span></label>
      <div id="armed_extra" class="sub-fields">
        <label class="check-row"><input type="checkbox" id="cf_armed_mitig"> Mitigating circumstances</label>
        <label class="check-row"><input type="checkbox" id="cf_armed_minor"> Minor participation</label>
        <label class="check-row"><input type="checkbox" id="cf_armed_proof"> Proof deficiencies</label>
      </div>`;
    }
    if (e.dv_eligible) {
      html += `<label class="check-row"><input type="checkbox" id="cf_dv"> Domestic violence by victim <span class="hint">PL 60.12</span></label>`;
    }
    wrap.appendChild(group('Exception triggers', 'fa-code-fork', html, true));
  }

  // Other circumstances
  let adv = `
    <label class="check-row"><input type="checkbox" id="cf_dwi"> DWI offense <span class="hint">PL 60.21</span></label>
    <label class="check-row"><input type="checkbox" id="cf_other_sent"> Defendant under other sentence &gt; 15 days</label>
    <label class="check-row"><input type="checkbox" id="cf_restitution"> Victim seeking restitution</label>
    <label class="check-row"><input type="checkbox" id="cf_for_hire"> Victim is for-hire vehicle operator <span class="hint">PL 60.07</span></label>`;
  if (e.is_felony || e.is_misdemeanor) {
    const ageOpts = e.yo_eligible
      ? `<option value="adult">Adult</option><option value="youthful_offender_eligible">Youthful offender eligible</option><option value="juvenile_offender">Juvenile offender</option>`
      : `<option value="adult">Adult</option><option value="juvenile_offender">Juvenile offender</option>`;
    adv += `<label class="field"><span>Age category</span><select id="cf_age">${ageOpts}</select></label>`;
  }
  wrap.appendChild(group('Other circumstances', 'fa-list-check', adv, true));

  wireToggle('cf_attempt', 'attempt_extra');
  wireToggle('cf_conspiracy', 'conspiracy_extra');
  wireToggle('cf_armed_plea', 'armed_extra');
}

function wireToggle(triggerId, targetId) {
  const t = document.getElementById(triggerId);
  const target = document.getElementById(targetId);
  if (!t || !target) return;
  const update = () => { target.hidden = !t.checked; };
  t.addEventListener('change', update);
  update();
}

// Collapsible panel, open by default unless `collapsed`.
function group(label, icon, html, collapsed) {
  const g = el('details', 'field-group');
  g.open = !collapsed;
  g.innerHTML = `<summary><i class="fa-solid ${icon}"></i> ${label}</summary><div class="group-body">${html}</div>`;
  return g;
}

function prettyCls(c) {
  return String(c)
    .replace(/^Class/, 'Class ')
    .replace('_Violent_Felony', ' Violent Felony')
    .replace('_Felony', ' Felony')
    .replace('_Misdemeanor', ' Misdemeanor')
    .replace('A_I ', 'A-I ').replace('A_II ', 'A-II ')
    .replace('_', ' ');
}

// ---------------------------------------------------------------------------
// Resolve
// ---------------------------------------------------------------------------
async function resolve() {
  const d = state.offenseDetail;
  if (!d || !state.engineReady) return;
  const body = buildRequestBody(d);
  state.resolving = true;
  updateResolveButton();
  $('#result').innerHTML = '<div class="muted pad"><span class="spinner dark"></span> Calculating…</div>';
  try {
    const out = await engine.resolve(body);
    state.lastResult = out;
    renderCurrentView();
    if (window.matchMedia('(max-width: 900px)').matches) {
      document.querySelector('.panel-right').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } catch (e) {
    $('#result').innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
  } finally {
    state.resolving = false;
    updateResolveButton();
  }
}

function buildRequestBody(d) {
  const e = d.eligibility;
  const val = (id) => {
    const elx = document.getElementById(id);
    return elx ? (elx.type === 'checkbox' ? elx.checked : elx.value) : undefined;
  };
  const num = (id) => {
    const v = val(id);
    if (v === '' || v === undefined || v === null) return null;
    const n = Number(v);
    return isNaN(n) ? null : n;
  };
  const body = {
    section: d.section,
    predicate_felonies: e.is_felony ? (num('cf_pred_felonies') || 0) : 0,
    predicate_vfos: e.is_felony ? (num('cf_pred_vfos') || 0) : 0,
    hate_crime_motivated: !!val('cf_hate'),
    sexually_motivated: !!val('cf_smf'),
    terrorism_motivated: !!val('cf_terror'),
    domestic_violence_by_victim: !!val('cf_dv'),
    is_dwi: !!val('cf_dwi'),
    defendant_under_other_sentence_over_15_days: !!val('cf_other_sent'),
    victim_seeking_restitution: !!val('cf_restitution'),
    victim_is_for_hire_operator: !!val('cf_for_hire'),
    defendant_age_category: val('cf_age') || 'adult',
  };
  if (e.is_felony || e.is_misdemeanor) {
    body.is_attempt = !!val('cf_attempt');
    if (body.is_attempt) {
      body.attempt_of_section = val('cf_attempt_of') || d.section;
      body.subdivision = val('cf_subdivision') || null;
    }
    body.is_conspiracy = !!val('cf_conspiracy');
    if (body.is_conspiracy) body.conspiracy_of_section = val('cf_conspiracy_of') || d.section;
  }
  if (e.armed_eligible) {
    body.plea_from_armed_felony_indictment = !!val('cf_armed_plea');
    body.armed_felony_mitigating_factor = !!val('cf_armed_mitig');
    body.armed_felony_minor_participation = !!val('cf_armed_minor');
    body.armed_felony_proof_deficiencies = !!val('cf_armed_proof');
  }
  if (d.conditional_classification) {
    body.intended_underlying_offense_class = val('cf_intended_class') || null;
    body.prior_conviction_same_section_within_years = num('cf_prior_same_years');
  }
  return body;
}

// ---------------------------------------------------------------------------
// Render result
// ---------------------------------------------------------------------------
function renderCurrentView() {
  if (!state.lastResult) return;
  state.view === 'memo' ? renderMemo(state.lastResult) : renderResult(state.lastResult);
}

function renderResult(out) {
  const wrap = $('#result');
  wrap.innerHTML = '';

  const head = el('div', 'result-header');
  head.appendChild(metric('Final classification', prettyCls(out.classification), true));
  head.appendChild(metric('Base classification', out.base_classification ? prettyCls(out.base_classification) : 'No modifier'));
  head.appendChild(metric('Violent felony', out.is_vfo ? 'Yes' : 'No'));
  if (out.offender_status_label) head.appendChild(metric('Offender status', out.offender_status_label));
  head.appendChild(metric('Dispositions', out.available_dispositions.length));
  wrap.appendChild(head);

  if (out.modifiers_applied?.length) {
    wrap.appendChild(sectionTitle('Modifiers applied'));
    const row = el('div', 'pill-row');
    for (const m of out.modifiers_applied) {
      row.appendChild(el('span', 'modifier-pill',
        `<strong>${escapeHtml(m.modifier_type)}</strong> ${escapeHtml(prettyCls(m.base_classification))} <i class="fa-solid fa-arrow-right"></i> <strong>${escapeHtml(prettyCls(m.resulting_classification))}</strong>${m.branch ? ` <span class="muted">(${escapeHtml(m.branch)})</span>` : ''}`));
    }
    wrap.appendChild(row);
  }

  if (out.available_dispositions.length) {
    wrap.appendChild(sectionTitle('Authorized dispositions'));
    out.available_dispositions.forEach((d, i) => wrap.appendChild(dispositionCard(d, i === 0)));
  }

  if (out.exception_paths?.length) {
    wrap.appendChild(sectionTitle('Exception paths'));
    out.exception_paths.forEach(e => wrap.appendChild(exceptionCard(e)));
  }

  if (out.financial_obligations?.length) {
    wrap.appendChild(sectionTitle('Financial obligations'));
    wrap.appendChild(financialTable(out.financial_obligations));
  }

  if (out.collateral_requirements?.length) {
    wrap.appendChild(sectionTitle('Collateral requirements'));
    for (const c of out.collateral_requirements) {
      const card = el('div', 'card');
      card.innerHTML = `<div class="card-label">${escapeHtml(humanize(c.type))}</div>
        <div class="card-title">${escapeHtml(c.label)}</div>
        <div class="muted small">${escapeHtml(c.description)}</div>
        ${refs(c.statute_refs)}`;
      wrap.appendChild(card);
    }
  }

  if (out.trace?.length) {
    wrap.appendChild(sectionTitle('How this was decided'));
    const ol = el('ol', 'trace');
    for (const t of out.trace) {
      ol.appendChild(el('li', '',
        `<span class="trace-stage">${escapeHtml(t.stage.replace(/_/g, ' '))}</span> ${escapeHtml(t.detail)}` +
        (t.statute_refs?.length ? ` <span class="muted small">${escapeHtml(t.statute_refs.join('; '))}</span>` : '')));
    }
    wrap.appendChild(ol);
  }

  const raw = el('details', 'raw-json');
  raw.innerHTML = `<summary>Raw JSON output</summary><pre>${escapeHtml(JSON.stringify(out, null, 2))}</pre>`;
  wrap.appendChild(raw);
}

function metric(label, value, accent) {
  return el('div', 'metric' + (accent ? ' accent' : ''),
    `<div class="lbl">${escapeHtml(label)}</div><div class="val">${escapeHtml(String(value))}</div>`);
}

function sectionTitle(t) {
  return el('h3', 'section-title', t);
}

function humanize(s) {
  return String(s ?? '').replace(/_/g, ' ');
}

function refs(list, prefix = '') {
  return list?.length ? `<div class="refs"><i class="fa-solid fa-section"></i> ${prefix}${list.map(escapeHtml).join('; ')}</div>` : '';
}

function dispositionCard(d, isPrimary) {
  const card = el('div', 'card disposition' + (isPrimary ? ' primary' : ''));
  const row = (k, v) => `<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  let html = `<div class="card-label">${isPrimary ? '<span class="label label-primary">Recommended</span> ' : ''}${escapeHtml(humanize(d.type))}</div>`;
  html += `<div class="card-title">${escapeHtml(d.label)}</div>`;
  if (d.term) html += row('Term', escapeHtml(formatTerm(d.term)));
  if (d.prs) html += row('Post-release supervision', `${d.prs.min_years}–${d.prs.max_years} years`);
  if (d.probation_years) html += row('Probation', `${d.probation_years.join(', ')} years`);
  if (d.conditional_discharge_years != null) html += row('Conditional discharge', `${d.conditional_discharge_years} years`);
  if (d.split_imprisonment_max_months != null) html += row('Split — max imprisonment', `${d.split_imprisonment_max_months} months`);
  if (d.fine_max_amount != null) html += row('Maximum fine', `$${Number(d.fine_max_amount).toLocaleString()}${d.fine_alt_double_gain ? ' or double the gain' : ''}`);
  if (d.record_statement_required) html += row('Record statement', 'Required');
  if (d.conditions) html += `<div class="conditions">${escapeHtml(d.conditions)}</div>`;
  html += refs(d.statute_refs);
  card.innerHTML = html;
  return card;
}

function exceptionCard(e) {
  const card = el('div', 'card exception');
  let html = `<div class="card-label">${escapeHtml(humanize(e.type))}</div>`;
  html += `<div class="card-title">${escapeHtml(e.label)}</div>`;
  html += `<div class="muted small">${escapeHtml(e.description)}</div>`;
  if (e.triggering_factors?.length) html += `<div class="refs"><i class="fa-solid fa-bolt"></i> ${e.triggering_factors.map(escapeHtml).join('; ')}</div>`;
  html += refs(e.statute_refs);
  if (e.resulting_disposition) html += `<div class="kv"><span class="k">Resulting disposition</span><span class="v">${escapeHtml(e.resulting_disposition.label)}</span></div>`;
  card.innerHTML = html;
  return card;
}

function financialTable(items) {
  const wrap = el('div', 'table-wrap');
  wrap.innerHTML = `<table class="table-striped"><thead><tr><th>Obligation</th><th class="amount">Amount</th><th>Authority</th></tr></thead><tbody>${
    items.map(f => `<tr><td>${escapeHtml(f.label)}</td><td class="amount">${f.amount != null ? '$' + Number(f.amount).toLocaleString() : '—'}</td><td class="small muted">${(f.statute_refs || []).map(escapeHtml).join('; ')}</td></tr>`).join('')
  }</tbody></table>`;
  return wrap;
}

function formatTerm(term) {
  if (!term) return '—';
  if (term.max_value >= 999) return `${term.min_value} ${term.unit} to life`;
  if (term.min_value === term.max_value) return `${term.min_value} ${term.unit}`;
  return `${term.min_value}–${term.max_value} ${term.unit}`;
}

// ---------------------------------------------------------------------------
// Memorandum view
// ---------------------------------------------------------------------------
function renderMemo(out) {
  const md = out.report_markdown || '';
  const wrap = $('#result');
  wrap.innerHTML = '';
  const bar = el('div', 'memo-actions');
  bar.innerHTML = `<button class="btn btn-default btn-sm" id="copyMemo"><i class="fa-regular fa-copy"></i> Copy</button>
    <button class="btn btn-default btn-sm" id="downloadMemo"><i class="fa-solid fa-download"></i> Download .md</button>
    <button class="btn btn-default btn-sm" id="printMemo"><i class="fa-solid fa-print"></i> Print</button>`;
  wrap.appendChild(bar);
  wrap.appendChild(el('article', 'memo', renderMarkdown(md)));

  $('#copyMemo').onclick = async (ev) => {
    try {
      await navigator.clipboard.writeText(md);
      ev.currentTarget.innerHTML = '<i class="fa-solid fa-check"></i> Copied';
    } catch {
      ev.currentTarget.textContent = 'Copy failed';
    }
  };
  $('#downloadMemo').onclick = () => {
    const a = el('a');
    a.href = URL.createObjectURL(new Blob([md], { type: 'text/markdown' }));
    a.download = `sentencing_memo_${out.section}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  $('#printMemo').onclick = () => window.print();
}

// Minimal markdown renderer for render_report() output:
// headings, hr, pipe tables, nested "-" lists, `code`, **bold**, trailing-space breaks.
function renderMarkdown(md) {
  const lines = md.split('\n');
  let html = '';
  let inTable = false, para = [];
  const listStack = [];
  const flushPara = () => {
    if (para.length) { html += `<p>${para.join('')}</p>`; para = []; }
  };
  const closeLists = (depth = 0) => {
    while (listStack.length > depth) { html += '</li></ul>'; listStack.pop(); }
  };
  const closeTable = () => { if (inTable) { html += '</tbody></table></div>'; inTable = false; } };
  const closeAll = () => { flushPara(); closeLists(); closeTable(); };
  const cells = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => mdInline(c.trim()));

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const h = line.match(/^(#{1,4}) (.*)/);
    if (h) { closeAll(); html += `<h${h[1].length}>${mdInline(h[2])}</h${h[1].length}>`; continue; }
    if (/^---\s*$/.test(line)) { closeAll(); html += '<hr>'; continue; }
    if (/^\|/.test(line)) {
      flushPara(); closeLists();
      if (!inTable) {
        html += `<div class="table-wrap"><table class="table-striped"><thead><tr>${cells(line).map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>`;
        inTable = true;
        if (/^\|[\s|:-]+\|?\s*$/.test(lines[i + 1] || '')) i++;
      } else {
        html += `<tr>${cells(line).map(c => `<td>${c}</td>`).join('')}</tr>`;
      }
      continue;
    }
    closeTable();
    const li = line.match(/^(\s*)- (.*)/);
    if (li) {
      flushPara();
      const depth = Math.floor(li[1].length / 2) + 1;
      if (depth > listStack.length) {
        while (listStack.length < depth) { html += '<ul><li>'; listStack.push(true); }
      } else {
        closeLists(depth);
        html += '</li><li>';
      }
      html += mdInline(li[2]);
      continue;
    }
    if (!line.trim()) { flushPara(); closeLists(); continue; }
    closeLists();
    para.push(mdInline(line.replace(/\s+$/, '')) + (/ {2,}$/.test(line) ? '<br>' : ' '));
  }
  closeAll();
  return html;
}

function mdInline(s) {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
}

function emptyResult() {
  return `<div class="empty-state">
    <i class="fa-regular fa-file-lines big-icon"></i>
    <p>No result yet.</p>
    <p class="muted small">Calculate to see dispositions, exception paths, financial obligations, and collateral requirements.</p>
  </div>`;
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Wire up
// ---------------------------------------------------------------------------
$('#search').addEventListener('input', (e) => renderOffenseList(e.target.value));
$('#resolveBtn').addEventListener('click', resolve);
document.querySelectorAll('.seg').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.seg').forEach(x => x.classList.toggle('active', x === b));
    state.view = b.dataset.view;
    renderCurrentView();
  });
});

$('#result').innerHTML = emptyResult();
loadOffenses();
