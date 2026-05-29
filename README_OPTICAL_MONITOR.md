# Wyyerd Optical Monitor

Full-stack monitor for the Pacific IP Backbone:

- `collector/` polls Ciena optics and writes SQLite readings.
- `api/` exposes FastAPI endpoints over the SQLite store.
- `frontend/` renders a React/Vite SVG topology using `topology.json`.

Run locally:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m collector.collector --mock --once
uvicorn api.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

Useful endpoints:

- `GET /api/health`
- `GET /api/nodes`
- `GET /api/links`
- `GET /api/nodes/{id}`
- `GET /api/nodes/{id}/history`
- `WS /api/ws/live`

Docker:

```bash
docker compose up --build
```
