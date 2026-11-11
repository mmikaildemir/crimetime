// CrimeTime 2.0 — Pyodide worker. Runs the Python sentencing engine
// (crimetime/ + webapp/bridge.py, shipped as engine.zip) off the main thread.
//
// The reference data is NOT in engine.zip: it is fetched from data/ at
// startup so a new data bundle can be deployed without rebuilding the site
// (docs/HOSTING.md). With ?admin=1 the worker also loads admin_bridge.py for
// the admin tool (site/admin/).

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
const params = new URL(self.location.href).searchParams;
const BUILD = params.get('v') || '';
const ADMIN = params.get('admin') === '1';
const ROOT = '/home/pyodide/ct';

importScripts(PYODIDE_URL + 'pyodide.js');

const status = (text) => self.postMessage({ type: 'status', text });

async function fetchOk(url, opts) {
  const resp = await fetch(url, opts);
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
  return resp;
}

const ready = (async () => {
  status('Loading Python runtime…');
  const py = await loadPyodide({ indexURL: PYODIDE_URL });
  status('Loading pydantic…');
  await py.loadPackage('pydantic');
  status('Loading sentencing engine…');
  const [zip, lists, tables] = await Promise.all([
    fetchOk('engine.zip?v=' + BUILD).then(r => r.arrayBuffer()),
    fetchOk('data/lists.json', { cache: 'no-cache' }).then(r => r.text()),
    fetchOk('data/sentencing_tables.json', { cache: 'no-cache' }).then(r => r.text()),
  ]);
  py.unpackArchive(zip, 'zip', { extractDir: ROOT });
  py.FS.mkdirTree(ROOT + '/data');
  py.FS.writeFile(ROOT + '/data/lists.json', lists);
  py.FS.writeFile(ROOT + '/data/sentencing_tables.json', tables);
  py.runPython(`import sys; sys.path.insert(0, '${ROOT}'); import bridge`);
  const mods = { bridge: py.pyimport('bridge') };
  if (ADMIN) {
    py.runPython('import admin_bridge');
    mods.admin = py.pyimport('admin_bridge');
    mods.admin.load_published_json(lists, tables);
  }
  // Warm the reference-data cache so the first calculation is instant.
  py.runPython('bridge.list_offenses()');
  return mods;
})();

ready.then(
  () => self.postMessage({ type: 'ready' }),
  (e) => self.postMessage({ type: 'failed', error: String(e) }),
);

const FUNCS = {
  resolve_json: 'bridge',
  set_draft_json: 'admin',
  check_draft_json: 'admin',
  impact_json: 'admin',
  try_case_json: 'admin',
  bundle_json: 'admin',
  read_bundle_json: 'admin',
};

self.onmessage = async ({ data: { id, fn, args } }) => {
  try {
    const mods = await ready;
    const mod = mods[FUNCS[fn]];
    if (!mod) throw new Error(`Unknown function ${fn}`);
    self.postMessage({ id, result: mod[fn](...args) });
  } catch (e) {
    self.postMessage({ id, error: String(e) });
  }
};
