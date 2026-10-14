// CrimeTime 2.0 — main-thread client for the Pyodide engine worker.
// Offense data is static (offenses.json); only resolve() needs Python.

const engine = (() => {
  const build = new URL(document.currentScript.src).searchParams.get('v') || '';
  const worker = new Worker('engine-worker.js?v=' + build);
  const pending = new Map();
  const statusListeners = [];
  let nextId = 1;
  let resolveReady, rejectReady;
  const ready = new Promise((res, rej) => { resolveReady = res; rejectReady = rej; });

  worker.onmessage = ({ data }) => {
    if (data.type === 'status') return statusListeners.forEach(fn => fn(data.text));
    if (data.type === 'ready') return resolveReady();
    if (data.type === 'failed') return rejectReady(new Error(data.error));
    const p = pending.get(data.id);
    if (!p) return;
    pending.delete(data.id);
    data.error ? p.reject(new Error(data.error)) : p.resolve(data.result);
  };
  worker.onerror = (e) => rejectReady(new Error(e.message || 'Engine worker failed'));

  function call(fn, ...args) {
    const id = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      worker.postMessage({ id, fn, args });
    }).then((json) => {
      const env = JSON.parse(json);
      if (!env.ok) throw Object.assign(new Error(env.error), { status: env.status });
      return env.data;
    });
  }

  return {
    ready,
    onStatus: (fn) => statusListeners.push(fn),
    resolve: (body) => call('resolve_json', JSON.stringify(body)),
  };
})();
