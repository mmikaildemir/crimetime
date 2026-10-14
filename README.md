# CrimeTime 2.0

New York State sentencing decision engine (`crimetime/`). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for how the pipeline, sentencing tracks and data tables fit together.

## Web demo (GitHub Pages)

The demo in `site/` is a static page that runs the real Python engine in the browser via
[Pyodide](https://pyodide.org): `webapp/bridge.py` is the entry point, and offense data is
precomputed at build time. Nothing is sent to a server.

```sh
python scripts/build_site.py --serve   # build into _site/ and serve on http://localhost:8080
```

Pushing to `main` runs the tests, builds `_site/`, and deploys it via
`.github/workflows/pages.yml` (repo Settings → Pages → Source: **GitHub Actions**).

For local development against a FastAPI backend instead: `./run_webapp.sh` (needs `fastapi` and `uvicorn`).
