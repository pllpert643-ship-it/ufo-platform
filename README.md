# UFO Intelligence Platform

A small, self-hosted UFO sighting dashboard built with FastAPI, SQLite, and vanilla JavaScript. It includes a Thai/English interface, sighting search and filters, an interactive map, analytics, CSV import/export, and manual camera-detection records.

> **Status:** MVP. This app has a real backend and database, but it does not provide continuous real-time updates. The camera detector is currently an adapter placeholder and does not run an inference model. All routes and data APIs are public without login; do not deploy this version with sensitive data or unrestricted public write access.

## Run locally (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` for the Orbit landing page or `http://127.0.0.1:8000/console` for the Command Center.

The SQLite database is created at `data/ufo_platform.sqlite3` by default. Set `UFO_DATABASE_PATH` to use another location. Local database files are intentionally excluded from Git.

## API

- `GET /api/health`
- `GET /api/sightings?limit=100` (supports source, search, shape, country, and mapped filters)
- `GET /api/stats`
- `GET /api/analytics`
- `GET /api/detections?limit=100`
- `POST /api/detections`
- `PATCH /api/detections/{id}`
- `POST /api/import/nuforc` (CSV/TXT)
- `GET /api/export/sightings.csv`

## Tests

```powershell
py -m pytest -q
```

## Security and deployment notes

This MVP intentionally has no login: visitors can read data and API clients can create/update records or import CSVs. Keep deployments private or behind an access-control layer until public write access is deliberately secured. The project seeds a few demo sightings into an empty local database on startup.