# Hosting CrimeTime

CrimeTime is a set of static files. It has no application server and no
database, and the sentencing engine runs in each visitor's browser. Any web
server that can serve files works, e.g. IIS, nginx, Apache, S3 or Azure Static
Web Apps.

## What to serve

Build once per code release:

```sh
python scripts/build_site.py        # writes _site/
```

```
_site/
  index.html, app.js, styles.css, engine.js, engine-worker.js, assets/
  engine.zip            sentencing engine (code only)
  admin/                the admin tool  ← put behind your login
  data/                 the data bundle ← replaced by admins, no rebuild needed
    lists.json
    sentencing_tables.json
    manifest.json       data version + change history
    offenses.json
```

Requirements:

- Serve `data/*.json` with revalidation (`Cache-Control: no-cache` or a short
  max-age) so a new bundle is picked up on the next page load. The pages
  request these files with `cache: 'no-cache'`, so a plain static host works.
- Visitors' browsers load Pyodide from `cdn.jsdelivr.net` and fonts and icons
  from Google Fonts and cdnjs. If your network blocks those, allow them or ask
  the developers for a self-contained build.
- **Restrict `/admin/` to NYPTI admins** with your existing sign-in (SSO, IIS
  Windows auth, basic auth, ...). The admin tool can't change the live site by
  itself: it only produces a file for you to deploy. Still, keep it private.

## Publishing a data change

1. An admin opens `/admin/`, makes the change, and runs the checks on the
   **Review & publish** tab.
2. They click **Download data bundle** and get `crimetime-data-<version>.zip`,
   e.g. `crimetime-data-2026-11-12.1.zip`.
3. Unzip it into the site's `data/` folder, replacing the four files there.
4. Reload the site. The offense list header and the admin page's top bar show
   the new data version.

Keep every bundle zip you deploy, for example in a shared folder. Together they
are the full record of the data, and the change history inside each bundle
(`manifest.json`) records who changed what, when and why.

## Rolling back

In `/admin/` → **History**, choose **Open a saved bundle…** and pick the zip of
the version to return to. It becomes the draft. Review it and publish it as a
new version, then deploy that bundle as usual. If the admin tool isn't usable,
unzip the old bundle into `data/` directly.

## Code releases vs. data releases

| Change | Who | How |
|---|---|---|
| Sentencing range, citation, offense, list membership | NYPTI admin | admin tool → data bundle → replace `data/` |
| New sentencing scheme, offender status, pipeline logic | developers | code change → tests → `build_site.py` → replace everything except `data/` |

When you deploy a code release, keep the live `data/` folder unless the release
notes say the data format changed.

Developers can also commit an admin's bundle to the repository: unzip it into
`data/` (`offenses.json` is git-ignored). CI then runs the tests, and
`uv run python scripts/snapshot.py --diff` shows the change's effect on the
golden snapshot, which must be accepted with `uv run python scripts/snapshot.py`.
