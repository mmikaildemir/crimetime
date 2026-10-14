"""Build the static GitHub Pages site into _site/.

    python scripts/build_site.py            # build
    python scripts/build_site.py --serve    # build, then serve on :8080

Output:
    _site/              copy of site/ with __BUILD__ replaced by a content hash
    _site/engine.zip    crimetime/ engine + webapp/bridge.py + runtime data,
                        unpacked into Pyodide by engine-worker.js
    _site/offenses.json precomputed offense details (list order) for the UI
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SITE_SRC = ROOT / "site"
OUT = ROOT / "_site"
ENGINE_EXCLUDE = {"legislation.py"}  # needs requests/dotenv; not used by the engine
DATA_FILES = ["lists.json", "sentencing_tables.json"]
TEMPLATED = {".html", ".js"}


def engine_files() -> list[tuple[Path, str]]:
    files = [
        (p, f"crimetime/{p.name}")
        for p in sorted((ROOT / "crimetime").glob("*.py"))
        if p.name not in ENGINE_EXCLUDE
    ]
    files.append((ROOT / "webapp" / "bridge.py", "bridge.py"))
    files += [(ROOT / "data" / name, f"data/{name}") for name in DATA_FILES]
    return files


def build() -> str:
    from webapp import bridge

    files = engine_files()
    offenses = [bridge.offense_detail(o["section"]) for o in bridge.list_offenses()]
    offenses_json = json.dumps(offenses, separators=(",", ":")).encode()

    digest = hashlib.sha256(offenses_json)
    for src, _ in files:
        digest.update(src.read_bytes())
    for src in sorted(SITE_SRC.rglob("*")):
        if src.is_file():
            digest.update(src.read_bytes())
    build_id = digest.hexdigest()[:10]

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE_SRC, OUT)
    for p in OUT.rglob("*"):
        if p.suffix in TEMPLATED:
            p.write_text(p.read_text().replace("__BUILD__", build_id))

    # Fixed timestamps keep the zip byte-identical across builds of the same source.
    with zipfile.ZipFile(OUT / "engine.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arc in files:
            info = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, src.read_bytes())

    (OUT / "offenses.json").write_bytes(offenses_json)
    (OUT / ".nojekyll").touch()

    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"Built {OUT.relative_to(ROOT)}/ — build {build_id}, {len(offenses)} offenses, "
          f"{len(files)} engine files, {size / 1024:.0f} KB total")
    return build_id


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serve", action="store_true", help="serve _site/ after building")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    build()
    if args.serve:
        import functools
        import http.server

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        print(f"Serving http://localhost:{args.port}/")
        http.server.ThreadingHTTPServer(("", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
