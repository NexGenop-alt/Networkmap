# Wyyerd Optical Monitor

Live optical monitoring dashboard for the Wyyerd Pacific IP Backbone.

The project includes:

- Python mock/SSH collector with the integrated Ciena parser.
- SQLite storage for aggregate and per-lane optical readings.
- FastAPI API for topology, nodes, links, health, history, and as-of snapshots.
- React/Vite frontend with SVG topology map, multi-node selection, and date rewind controls.
- Docker Compose deployment files.

## Run Locally First time setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m collector.collector --mock --once
python -m uvicorn api.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:3000/`.

## Docker

```bash
docker compose up --build
```







## Run Locally when already set up

```bash
. .venv/bin/activate
python -m uvicorn api.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev
```
