# Ludo

Play on one device or invite friends to a private room. Every match has 2–4 seats and four pawns per seat. Two-player games use opposite colors. The backend rolls the dice, validates moves, and saves each turn.

## Run locally

Use Python 3.12 and Node.js 24. Start the API from the repository root:

```sh
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Choose **Pass and play** to share a device. For **Create online room**, choose the seat count first, then share the invite link or room code. Each friend joins from a separate browser profile or device. The match starts when all seats are filled. Refreshing restores your latest seat in that browser. Starting or joining another match replaces the saved seat. In Codespaces, run both servers in the same Codespace, leave VITE_API_URL unset, and open forwarded port 5173. Visit /api/health on that frontend URL to check the connection.

## Rules used here

- Roll six to bring a pawn out, or move a pawn already in play. Each color has its own clockwise route and home lane.
- Roll again after a six, capture, or exact finish. A third consecutive six forfeits the roll. If there is no legal move, the turn passes (a six still grants a reroll).
- Starts and starred squares are safe. Landing on another ordinary track square sends all opposing pawns there back to their yards. Stacks do not block passage.
- Finishing requires an exact roll. First to finish all four wins. Click a highlighted square or use the numbered pawn controls; the controls also let you pick a specific pawn in a stack.

## Separate frontend and backend hosts

| Setting | Service | Purpose |
| --- | --- | --- |
| VITE_API_URL | Frontend, **at build time** | Public HTTPS API origin for separate deployments. Defaults to /api on the frontend origin; Vite forwards this to FastAPI on port 8000. |
| LUDO_ORIGINS | Backend, at runtime | Comma-separated list of exact frontend origins, e.g. https://play.example.com. |
| LUDO_DB | Backend, at runtime | SQLite file path. Defaults to ludo.sqlite3 in the working directory. |

Serve the frontend's built `dist/` as static files. Run the API with `uvicorn app.main:app --host 0.0.0.0 --port 8000`. For App Service, configure the container target port and use one backend instance with a durable writable volume that supports SQLite locking. Create the database directory before starting the API. Container-local ephemeral storage loses rooms on replacement. For a multi-instance backend use a shared database service. Online clients poll for changes. Health check: `GET /health`. API docs: `/docs`.

## Tests

Run `python -m pytest` inside backend with the development requirements installed. Run `npm run lint && npm run build` inside frontend. The browser suite in `tests/` uses Python Playwright and pytest against both running services on their default local ports. Install Chromium with `python -m playwright install chromium`, then run `python -m pytest tests/` from the repo root. GitHub Actions runs these checks on every push and pull request.
