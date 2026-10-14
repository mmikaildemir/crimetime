// CrimeTime 2.0 mockup — frontend logic

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};

const state = {
  offenses: [],
  selectedSection: null,
  offenseDetail: null,
  caseFacts: {},
  lastResult: null,
  view: 'structured',
};

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
async function checkHealth() {
  try {
    const r = await fetch('/api/health');
    const j = await r.json();
    $('#statusDot').classList.add('ok');
    $('#statusText').textContent = `engine: ${j.engine}`;
  } catch {
    $('#statusText').textContent = 'offline';
  }
}

// ---------------------------------------------------------------------------
// Offense list
// ---------------------------------------------------------------------------
async function loadOffenses() {
  const list = $('#offenseList');
  list.innerHTML = '<div class="muted">Loading offenses…</div>';
  try {
    const r = await fetch('/api/offenses');
    state.offenses = await r.json();
    renderOffenseList('');
  } catch (e) {
    list.innerHTML = `<div class="muted">Failed to load: ${e}</div>`;
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
    list.innerHTML = '<div class="muted">No matches.</div>';
    return;
  }
  for (const o of items.slice(0, 300)) {
    const item = el('div', 'offense-item' + (o.section === state.selectedSection ? ' active' : ''));
    item.innerHTML = `<span class="sec">§${o.section}</span><span class="nm">${escapeHtml(o.name)}</span><span class="cls">${shortCls(o.classification)}</span>`;
    item.onclick = () => selectOffense(o.section);
    list.appendChild(item);
  }
  if (items.length > 300) {
    list.appendChild(el('div', 'muted small', `…${items.length - 300} more, refine search.`));
  }
}

function shortCls(c) {
  return c.replace('Class', '').replace('_Felony', 'F').replace('_Misdemeanor', 'M').replace('_Violent_', 'V');
}

// ---------------------------------------------------------------------------
// Select offense -> render case facts form
// ---------------------------------------------------------------------------
async function selectOffense(section) {
  state.selectedSection = section;
  state.caseFacts = { section };
  renderOffenseList($('#search').value);
  $('#resolveBtn').disabled = false;

  const r = await fetch(`/api/offenses/${encodeURIComponent(section)}`);
  state.offenseDetail = await r.json();
  renderBadges(state.offenseDetail);
  renderCaseFacts(state.offenseDetail);
  // clear previous result
  if (!state.lastResult || state.lastResult.section !== section) {
    $('#result').innerHTML = emptyResult();
  }
}

function renderBadges(detail) {
  const wrap = $('#offenseBadge');
  wrap.innerHTML = '';
  const e = detail.eligibility;
  if (e.vfo) wrap.appendChild(badge('VFO', 'vfo'));
  if (e.smf_eligible) wrap.appendChild(badge('SMF', 'smf'));
  if (e.hatecrime_eligible) wrap.appendChild(badge('Hate Crime', 'hc'));
  if (e.terrorism_eligible) wrap.appendChild(badge('Terror', 'terror'));
  if (e.predicate_exposure) wrap.appendChild(badge('Predicate', 'pred'));
  if (e.yo_eligible) wrap.appendChild(badge('YO', 'yo'));
}

function badge(label, cls) {
  return el('span', 'badge ' + cls, label);
}

function renderCaseFacts(d) {
  const wrap = $('#caseFacts');
  wrap.innerHTML = '';
  const e = d.eligibility;

  // Offense summary
  wrap.appendChild(group('Offense', `
    <div class="field-row">
      <label class="field"><span>Section</span><input type="text" value="${d.section}" disabled></label>
      <label class="field"><span>Classification</span><input type="text" value="${d.classification}" disabled></label>
    </div>
    ${d.elements ? `<div class="muted small" style="margin-top:6px">${escapeHtml(d.elements)}</div>` : ''}
  `));

  // Prior record (felonies only)
  if (e.is_felony) {
    wrap.appendChild(group('Defendant prior record', `
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
    let html = `
      <label class="check-row"><input type="checkbox" id="cf_attempt" ${d.is_attempt ? 'checked' : ''}> Is this an attempt?<span class="hint">PL 110.05</span></label>
      <div id="attempt_extra" style="display:none; padding-left:18px; margin-top:6px">
        <label class="field"><span>Attempt of (target section)</span>
          <input type="text" id="cf_attempt_of" value="${d.attempt_of || d.section}" placeholder="e.g. 125.25">
        </label>
        <label class="field" style="margin-top:6px"><span>Target subdivision</span>
          <input type="text" id="cf_subdivision" placeholder="e.g. 2">
        </label>
      </div>
      <label class="check-row" style="margin-top:6px"><input type="checkbox" id="cf_conspiracy" ${d.is_conspiracy ? 'checked' : ''}> Is this a conspiracy?</label>
      <div id="conspiracy_extra" style="display:none; padding-left:18px; margin-top:6px">
        <label class="field"><span>Conspiracy of (section)</span>
          <input type="text" id="cf_conspiracy_of" value="${d.conspiracy_of || d.section}"></label>
      </div>
    `;
    wrap.appendChild(group('Offense shape', html));
  }

  // Conditional classification
  if (d.conditional_classification) {
    const cc = d.conditional_classification;
    let html = '';
    if (cc.prompt_fields?.includes('intended_underlying_offense_class')) {
      html += `<label class="field"><span>Intended underlying offense class</span>
        <select id="cf_intended_class">
          <option value="">— none —</option>
          <option>ClassA_I_Felony</option><option>ClassA_II_Felony</option>
          <option>ClassB_Felony</option><option>ClassB_Violent_Felony</option>
          <option>ClassC_Felony</option><option>ClassD_Felony</option><option>ClassE_Felony</option>
        </select></label>`;
    }
    if (cc.prompt_fields?.includes('prior_conviction_same_section_within_years')) {
      html += `<label class="field" style="margin-top:6px"><span>Prior conviction of same section within (years)</span>
        <input type="number" id="cf_prior_same_years" min="0" value="0"></label>`;
    }
    wrap.appendChild(group('Conditional classification', html));
  }

  // Enhancements
  if (e.hatecrime_eligible || e.smf_eligible || e.terrorism_eligible) {
    let html = '';
    if (e.hatecrime_eligible) html += `<label class="check-row"><input type="checkbox" id="cf_hate"> Hate crime motivated <span class="hint">PL 485</span></label>`;
    if (e.smf_eligible) html += `<label class="check-row"><input type="checkbox" id="cf_smf"> Sexually motivated felony <span class="hint">PL 130.91</span></label>`;
    if (e.terrorism_eligible) html += `<label class="check-row"><input type="checkbox" id="cf_terror"> Terrorism motivated <span class="hint">PL 490.25</span></label>`;
    wrap.appendChild(group('Enhancements', html));
  }

  // Exception triggers
  if (e.armed_eligible || e.dv_eligible) {
    let html = '';
    if (e.armed_eligible) {
      html += `<label class="check-row"><input type="checkbox" id="cf_armed_plea"> Plea from armed-felony indictment</label>`;
      html += `<div id="armed_extra" style="display:none; padding-left:18px">
        <label class="check-row"><input type="checkbox" id="cf_armed_mitig"> …mitigating factor</label>
        <label class="check-row"><input type="checkbox" id="cf_armed_minor"> …minor participation</label>
        <label class="check-row"><input type="checkbox" id="cf_armed_proof"> …proof deficiencies</label>
      </div>`;
    }
    if (e.dv_eligible) {
      html += `<label class="check-row"><input type="checkbox" id="cf_dv"> Domestic violence by victim <span class="hint">PL 60.12</span></label>`;
    }
    wrap.appendChild(group('Exception triggers', html));
  }

  // Advanced
  let adv = `
    <label class="check-row"><input type="checkbox" id="cf_dwi"> DWI offense <span class="hint">PL 60.21</span></label>
    <label class="check-row"><input type="checkbox" id="cf_other_sent"> Defendant under other sentence &gt; 15 days</label>
    <label class="check-row"><input type="checkbox" id="cf_restitution"> Victim seeking restitution</label>
    <label class="check-row"><input type="checkbox" id="cf_for_hire"> Victim is for-hire vehicle operator <span class="hint">PL 60.07</span></label>
  `;
  if (e.is_felony || e.is_misdemeanor) {
    const ageOpts = e.yo_eligible
      ? `<option value="adult">Adult</option><option value="youthful_offender_eligible">Youthful offender eligible</option><option value="juvenile_offender">Juvenile offender</option>`
      : `<option value="adult">Adult</option><option value="juvenile_offender">Juvenile offender</option>`;
    adv += `<label class="field" style="margin-top:6px"><span>Age category</span><select id="cf_age">${ageOpts}</select></label>`;
  }
  wrap.appendChild(group('Advanced', adv));

  // wire up toggles
  wireToggle('cf_attempt', 'attempt_extra');
  wireToggle('cf_conspiracy', 'conspiracy_extra');
  wireToggle('cf_armed_plea', 'armed_extra');
}

function wireToggle(triggerId, targetId) {
  const t = document.getElementById(triggerId);
  const target = document.getElementById(targetId);
  if (!t || !target) return;
  const update = () => { target.style.display = t.checked ? 'block' : 'none'; };
  t.addEventListener('change', update);
  update();
}

function group(label, html) {
  const g = el('div', 'field-group');
  g.innerHTML = `<label class="group-label">${label}</label>${html}`;
  return g;
}

// ---------------------------------------------------------------------------
// Resolve
// ---------------------------------------------------------------------------
async function resolve() {
  const d = state.offenseDetail;
  if (!d) return;
  const body = buildRequestBody(d);
  const btn = $('#resolveBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Resolving…';
  $('#result').innerHTML = '<div class="muted">Resolving…</div>';
  try {
    const r = await fetch('/api/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || 'Request failed');
    }
    const out = await r.json();
    state.lastResult = out;
    renderResult(out);
  } catch (e) {
    $('#result').innerHTML = `<div class="error-box">Engine error: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Resolve Sentencing →';
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
function renderResult(out) {
  if (state.view === 'memo') {
    renderMemo(out);
    return;
  }
  const wrap = $('#result');
  wrap.innerHTML = '';

  // header metrics
  const head = el('div', 'result-header');
  head.appendChild(metric('Final classification', out.classification, true));
  head.appendChild(metric('Base classification', out.base_classification || '(no modifier)'));
  head.appendChild(metric('VFO', out.is_vfo ? 'Yes' : 'No'));
  if (out.offender_status_label) head.appendChild(metric('Offender status', out.offender_status_label));
  head.appendChild(metric('Dispositions', out.available_dispositions.length));
  wrap.appendChild(head);

  // modifiers
  if (out.modifiers_applied?.length) {
    wrap.appendChild(sectionTitle('Modifiers applied'));
    const row = el('div', '');
    for (const m of out.modifiers_applied) {
      const pill = el('span', 'modifier-pill',
        `<strong>${escapeHtml(m.modifier_type)}</strong> ${escapeHtml(m.base_classification)} <span class="arrow">→</span> <strong>${escapeHtml(m.resulting_classification)}</strong>${m.branch ? ` <span class="muted small">(${escapeHtml(m.branch)})</span>` : ''}`);
      row.appendChild(pill);
    }
    wrap.appendChild(row);
  }

  // dispositions
  if (out.available_dispositions.length) {
    wrap.appendChild(sectionTitle('Available dispositions'));
    out.available_dispositions.forEach((d, i) => {
      wrap.appendChild(dispositionCard(d, i === 0));
    });
  }

  // exceptions
  if (out.exception_paths?.length) {
    wrap.appendChild(sectionTitle('Exception paths'));
    for (const e of out.exception_paths) {
      wrap.appendChild(exceptionCard(e));
    }
  }

  // financials
  if (out.financial_obligations?.length) {
    wrap.appendChild(sectionTitle('Financial obligations'));
    wrap.appendChild(financialTable(out.financial_obligations));
  }

  // collateral
  if (out.collateral_requirements?.length) {
    wrap.appendChild(sectionTitle('Collateral requirements'));
    for (const c of out.collateral_requirements) {
      const card = el('div', 'card alt');
      card.innerHTML = `<div class="card-label">${escapeHtml(c.type)}</div>
        <div class="card-title">${escapeHtml(c.label)}</div>
        <div class="muted small">${escapeHtml(c.description)}</div>
        ${c.statute_refs?.length ? `<div class="refs">${c.statute_refs.map(escapeHtml).join(', ')}</div>` : ''}`;
      wrap.appendChild(card);
    }
  }

  // decision trace
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

  // raw JSON expander
  const raw = el('details', '');
  raw.innerHTML = `<summary class="muted small" style="cursor:pointer; margin-top:14px">Raw JSON output</summary>
    <pre style="background:var(--bg-2); padding:10px; border-radius:8px; overflow:auto; font-size:11px; color:var(--muted)">${escapeHtml(JSON.stringify(out, null, 2))}</pre>`;
  wrap.appendChild(raw);
}

function metric(label, value, accent) {
  const m = el('div', 'metric');
  m.innerHTML = `<div class="lbl">${escapeHtml(label)}</div><div class="val${accent ? ' accent' : ''}">${escapeHtml(String(value))}</div>`;
  return m;
}

function sectionTitle(t) {
  return el('div', 'section-title', t);
}

const DISP_COLOR = {
  determinate: '#4f8cff', indeterminate: '#fb923c', definite: '#34d399',
  life_without_parole: '#f87171', probation: '#a78bfa', conditional_discharge: '#8c564b',
  unconditional_discharge: '#7f7f7f', split: '#f472b6', intermittent: '#bcbd22', fine: '#17becf',
};

function dispositionCard(d, isPrimary) {
  const card = el('div', 'card ' + (isPrimary ? 'primary' : 'alt'));
  const color = DISP_COLOR[d.type] || '#444';
  const termStr = formatTerm(d.term);
  let html = `<div class="card-label" style="color:${color}">${isPrimary ? 'PRIMARY' : 'ALT'} · ${escapeHtml(d.type.toUpperCase())}</div>`;
  html += `<div class="card-title">${escapeHtml(d.label)}</div>`;
  if (d.term) html += `<div class="row"><span class="k">Term</span><span class="v">${escapeHtml(termStr)}</span></div>`;
  if (d.prs) html += `<div class="row"><span class="k">Post-release supervision</span><span class="v">${d.prs.min_years}–${d.prs.max_years} years</span></div>`;
  if (d.probation_years) html += `<div class="row"><span class="k">Probation years</span><span class="v">${d.probation_years.join(', ')}</span></div>`;
  if (d.conditional_discharge_years != null) html += `<div class="row"><span class="k">Conditional discharge (yr)</span><span class="v">${d.conditional_discharge_years}</span></div>`;
  if (d.split_imprisonment_max_months != null) html += `<div class="row"><span class="k">Split imprison max (mo)</span><span class="v">${d.split_imprisonment_max_months}</span></div>`;
  if (d.fine_max_amount != null) html += `<div class="row"><span class="k">Fine max</span><span class="v">$${Number(d.fine_max_amount).toLocaleString()}${d.fine_alt_double_gain ? ' · alt double gain' : ''}</span></div>`;
  if (d.record_statement_required) html += `<div class="row"><span class="k">Record statement</span><span class="v">required</span></div>`;
  if (d.conditions) html += `<div class="conditions">${escapeHtml(d.conditions)}</div>`;
  if (d.statute_refs?.length) html += `<div class="refs">Refs: ${d.statute_refs.map(escapeHtml).join(', ')}</div>`;
  card.innerHTML = html;
  return card;
}

function exceptionCard(e) {
  const card = el('div', 'card exception');
  let html = `<div class="card-label">${escapeHtml(e.type)} · ${escapeHtml(e.label)}</div>`;
  html += `<div class="card-title">${escapeHtml(e.label)}</div>`;
  html += `<div class="muted small">${escapeHtml(e.description)}</div>`;
  if (e.triggering_factors?.length) html += `<div class="refs">Triggers: ${e.triggering_factors.map(escapeHtml).join(', ')}</div>`;
  if (e.statute_refs?.length) html += `<div class="refs">Refs: ${e.statute_refs.map(escapeHtml).join(', ')}</div>`;
  if (e.resulting_disposition) html += `<div class="row" style="margin-top:6px"><span class="k">→ Resulting</span><span class="v">${escapeHtml(e.resulting_disposition.label)}</span></div>`;
  card.innerHTML = html;
  return card;
}

function financialTable(items) {
  const t = el('table', 'fin');
  t.innerHTML = `<thead><tr><th>Type</th><th>Label</th><th>Amount</th><th>Refs</th></tr></thead><tbody>${
    items.map(f => `<tr><td>${escapeHtml(f.type)}</td><td>${escapeHtml(f.label)}</td><td class="amount">${f.amount != null ? '$' + Number(f.amount).toLocaleString() : '—'}</td><td class="muted small">${(f.statute_refs || []).map(escapeHtml).join(', ')}</td></tr>`).join('')
  }</tbody>`;
  return t;
}

function formatTerm(term) {
  if (!term) return '—';
  if (term.max_value >= 999) return `${term.min_value} ${term.unit} to life`;
  if (term.min_value === term.max_value) return `${term.min_value} ${term.unit}`;
  return `${term.min_value}–${term.max_value} ${term.unit}`;
}

// Memo view
function renderMemo(out) {
  const md = out.report_markdown || '';
  $('#result').innerHTML = '';
  const memo = el('div', 'memo');
  memo.innerHTML = renderMarkdown(md);
  $('#result').appendChild(memo);
}

// Minimal markdown renderer (h1/h2/hr/table/list/code/p)
function renderMarkdown(md) {
  const lines = md.split('\n');
  let html = '';
  let inTable = false, inList = false;
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  const closeTable = () => { if (inTable) { html += '</tbody></table>'; inTable = false; } };
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    if (/^# /.test(line)) { closeList(); closeTable(); html += `<h1>${mdInline(line.slice(2))}</h1>`; continue; }
    if (/^## /.test(line)) { closeList(); closeTable(); html += `<h2>${mdInline(line.slice(3))}</h2>`; continue; }
    if (/^---\s*$/.test(line)) { closeList(); closeTable(); html += '<hr>'; continue; }
    if (/^\|/.test(line)) {
      closeList();
      if (!inTable) {
        html += '<table><thead><tr>';
        const cells = line.split('|').slice(1, -1);
        html += cells.map(c => `<th>${mdInline(c.trim())}</th>`).join('');
        html += '</tr></thead><tbody>';
        inTable = true;
        i++; // skip separator row
        continue;
      } else {
        const cells = line.split('|').slice(1, -1);
        html += `<tr>${cells.map(c => `<td>${mdInline(c.trim())}</td>`).join('')}</tr>`;
        continue;
      }
    }
    if (inTable && !/^\|/.test(line)) { closeTable(); }
    if (/^- /.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${mdInline(line.slice(2))}</li>`;
      continue;
    }
    if (inList && !line.trim()) { closeList(); continue; }
    if (!line.trim()) { closeList(); continue; }
    closeList();
    html += `<p>${mdInline(line)}</p>`;
  }
  closeList(); closeTable();
  return html;
}

function mdInline(s) {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

function emptyResult() {
  return `<div class="empty-state">
    <div class="big-icon">📄</div>
    <p>No output yet.</p>
    <p class="muted small">Run the engine to see dispositions, exceptions, financials, and collateral.</p>
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
    document.querySelectorAll('.seg').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    state.view = b.dataset.view;
    if (state.lastResult) {
      state.view === 'memo' ? renderMemo(state.lastResult) : renderResult(state.lastResult);
    }
  });
});

// Boot
checkHealth();
loadOffenses();
