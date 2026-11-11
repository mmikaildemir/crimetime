// CrimeTime 2.0 — main-thread client for the Pyodide engine worker.
// The public page only needs resolve(); the admin page (site/admin/) loads
// this script with data-admin and uses call() for the admin_bridge functions.

const engine = (() => {
  const script = document.currentScript;
  const build = new URL(script.src).searchParams.get('v') || '';
  const workerUrl = new URL('engine-worker.js', script.src);
  workerUrl.searchParams.set('v', build);
  if (script.hasAttribute('data-admin')) workerUrl.searchParams.set('admin', '1');
  const worker = new Worker(workerUrl);
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
    call,
    onStatus: (fn) => statusListeners.push(fn),
    resolve: (body) => call('resolve_json', JSON.stringify(body)),
  };
})();
