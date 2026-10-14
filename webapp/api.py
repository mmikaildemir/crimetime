"""CrimeTime 2.0 — Web API.

FastAPI app that wraps the existing sentencing decision engine and
reference data, exposing them as JSON endpoints for the single-page
frontend in static/. The engine-facing logic lives in webapp/bridge.py,
which the static GitHub Pages build also runs in-browser via Pyodide.

Run:
    uvicorn webapp.api:app --reload --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from webapp import bridge
from webapp.bridge import ResolveRequest, UnknownSection

app = FastAPI(title="CrimeTime 2.0", version="2.0.0-mockup")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "engine": "crimetime.sentencing", "version": "2.0.0-mockup"}


@app.get("/api/offenses")
def list_offenses(q: str | None = None) -> list[dict]:
    return bridge.list_offenses(q)


@app.get("/api/offenses/{section}")
def get_offense(section: str) -> dict:
    try:
        return bridge.offense_detail(section)
    except UnknownSection as e:
        raise HTTPException(404, str(e.args[0]))


@app.post("/api/resolve")
def resolve(req: ResolveRequest) -> dict:
    try:
        return bridge.resolve(req.model_dump())
    except UnknownSection as e:
        raise HTTPException(404, str(e.args[0]))
    except Exception as e:
        raise HTTPException(400, f"Engine error: {e}")


@app.get("/api/report/{section}", response_class=PlainTextResponse)
def report(section: str) -> str:
    """Resolve with default case facts and return just the markdown report."""
    try:
        return bridge.default_report(section)
    except UnknownSection as e:
        raise HTTPException(404, str(e.args[0]))


# Static frontend (mounted last so it doesn't shadow API routes)
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "static", html=True), name="static")
