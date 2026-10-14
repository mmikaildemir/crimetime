#!/usr/bin/env bash
# CrimeTime 2.0 mockup — start the web app.
# Requires: fastapi, uvicorn (install with: uv pip install fastapi 'uvicorn[standard]')
set -e
cd "$(dirname "$0")"
PORT="${1:-8000}"
exec .venv/bin/uvicorn webapp.api:app --reload --port "$PORT"
