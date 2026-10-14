// CrimeTime 2.0 — Pyodide worker. Runs the Python sentencing engine
// (crimetime/ + webapp/bridge.py, shipped as engine.zip) off the main thread.

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
const BUILD = new URL(self.location.href).searchParams.get('v') || '';

importScripts(PYODIDE_URL + 'pyodide.js');

const status = (text) => self.postMessage({ type: 'status', text });

const ready = (async () => {
  status('Loading Python runtime…');
  const py = await loadPyodide({ indexURL: PYODIDE_URL });
  status('Loading pydantic…');
  await py.loadPackage('pydantic');
  status('Loading sentencing engine…');
  const resp = await fetch('engine.zip?v=' + BUILD);
  if (!resp.ok) throw new Error(`engine.zip: HTTP ${resp.status}`);
  py.unpackArchive(await resp.arrayBuffer(), 'zip', { extractDir: '/home/pyodide/ct' });
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide/ct'); import bridge");
  const bridge = py.pyimport('bridge');
  // Warm the reference-data cache so the first calculation is instant.
  py.runPython('bridge.list_offenses()');
  return bridge;
})();

ready.then(
  () => self.postMessage({ type: 'ready' }),
  (e) => self.postMessage({ type: 'failed', error: String(e) }),
);

const FUNCS = new Set(['resolve_json']);

self.onmessage = async ({ data: { id, fn, args } }) => {
  try {
    if (!FUNCS.has(fn)) throw new Error(`Unknown function ${fn}`);
    const bridge = await ready;
    self.postMessage({ id, result: bridge[fn](...args) });
  } catch (e) {
    self.postMessage({ id, error: String(e) });
  }
};
