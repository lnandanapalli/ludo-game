# Ludo

Play on one device or invite friends to a private room. Every match has 2–4 seats and four pawns per seat. Two-player games use opposite colors. The backend rolls the dice, validates moves, and saves each turn.

## Run locally

Create a Supabase project and run [the room schema](supabase/migrations/202611240001_rooms.sql) in its SQL Editor. In **Connect**, copy the PostgreSQL session pooler URI, supply the URL-encoded database password, and enable TLS with `sslmode=require`. Store the resulting URI as a backend `DATABASE_URL` secret (for example in Codespaces secrets or Azure backend App Service settings). A local Postgres database with the same schema also works.

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

Open http://localhost:5173. Choose **Pass and play** to share a device. For **Create online room**, choose the seat count first, then share the invite link or room code. Each friend joins from a separate browser profile or device. The match starts when all seats are filled. Opening or refreshing shows the lobby. Resume game reopens your saved seat. Local games can be resumed indefinitely. Leave game in an online room gives up your seat (see below). Only the online host (or the local device) can end the game for everyone. Starting or joining another match replaces the saved seat. In Codespaces, run both servers in the same Codespace, leave VITE_API_URL unset, and open forwarded port 5173. Visit /api/health on that frontend URL to check the connection.

## Rules used here

- Roll six to bring a pawn out, or move a pawn already in play. Each color has its own clockwise route and home lane.
- Roll again after a six, capture, or exact finish. A third consecutive six forfeits the roll. If there is no legal move, the turn passes (a six still grants a reroll).
- Starts and starred squares are safe. Landing on another ordinary track square sends all opposing pawns there back to their yards. Stacks do not block passage.
- Finishing requires an exact roll. First to finish all four wins. Choose a name and avatar before play. Tap the die beside the active player to roll and select a highlighted cell to move your pawn. Equivalent pawns stacked on the same square move one at a time. Each player can enable automatic movement before starting or joining. When enabled, exactly one legal pawn moves immediately; multiple legal pawns still require a tap.

## Separate frontend and backend hosts

| Setting | Service | Purpose |
| --- | --- | --- |
| VITE_API_URL | Frontend, **at build time** | Public HTTPS API origin for separate deployments. Defaults to /api on the frontend origin; Vite forwards this to FastAPI on port 8000. |
| LUDO_ORIGINS | Backend, at runtime | Comma-separated list of exact frontend origins, e.g. https://play.example.com. |
| DATABASE_URL | Backend, at runtime | Supabase Postgres connection URI. Required. |

Serve the frontend's built `dist/` as static files. Run the API with `uvicorn app.main:app --host 0.0.0.0 --port 8000`. For App Service, configure the container target port. All backend instances use the same Postgres database. Online clients poll for changes. Health check: `GET /health`. API docs: `/docs`.

## Tests

Use a dedicated test Postgres database with the room schema applied as DATABASE_URL. Run `python -m pytest` inside backend with the development requirements installed. Run `npm run lint && npm run build` inside frontend. The browser suite in `tests/` uses Python Playwright and pytest against both running services on their default local ports. Install Chromium with `python -m playwright install chromium`, then run `python -m pytest tests/` from the repo root. GitHub Actions runs these checks on every push and pull request.

## Existing SQLite matches

Stop writes to the old backend, keep a copy of its SQLite file, and apply the Postgres schema above. From `backend/`, with the destination DATABASE_URL set, run `python import_sqlite.py /path/to/ludo.sqlite3` before starting the new backend. The import preserves room codes, seat credentials and turn revisions. Identical rooms are skipped; conflicting rooms roll back the import.

In online rooms a player has 5 seconds to roll, shown as a ring draining around the die, and 15 seconds to move, shown as a ring around their portrait. The ring turns red and the portrait and movable pawns blink during the last 5 seconds. When a timer runs out, the server rolls, or moves a random legal pawn, for that player. Each timer starts once the previous roll or move has finished animating.

The creator of a new online room chooses whether computer substitutes are on (the default; only the creator sees this setting). Every player sees each seat's status on its card:

- **Disconnected** (network drop or closed browser): shown as Offline after 15 seconds. The timers keep playing for the seat: its roll still waits 5 seconds, but its move is made after 1 second. Only that player can reconnect, with Resume game from the same browser, until the game ends. After 5 minutes away, a computer takes over (CPU) and plays without waiting for the timers; reconnecting hands the seat back. Without substitutes the seat is instead removed after 5 minutes.
- **Leave game** (chosen on purpose): the player cannot return. With substitutes a computer plays the seat at once; without them the seat is removed.
- **Removed** (Left): the seat's pawns leave the board and turns skip it. If only one player remains, they win.

Local games have no timers, and Leave game there returns to the lobby with the game saved. Only the creator (or the local device) can end the game for everyone. New rooms still wait for all human players to join initially.
