# Ludo

Play on one device or invite friends to a private room. Every match has 2–4 seats and four pawns per seat; two-player games use opposite colors. The backend rolls the dice, validates moves, and saves each turn. Accounts are optional.

## Run locally

Create a Supabase project. In **Connect**, copy the PostgreSQL session pooler URI, supply the URL-encoded database password, and enable TLS with `sslmode=require`. Use that URI as the backend's `DATABASE_URL`; a local Postgres database also works. The API creates and updates its tables itself when it starts (see [Database migrations](#database-migrations)).

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

Accounts send codes by email. Locally, start the API with `LUDO_MAIL_DEV=1` to print each email in the API's terminal instead of sending it.

Open http://localhost:5173. In Codespaces, run both servers in the same Codespace, leave `VITE_API_URL` unset, and open forwarded port 5173. Visit `/api/health` on that frontend URL to check the connection.

## Playing

- **Pass and play** shares one device. Local games have no timers and can be resumed from the lobby at any time; Leave game returns to the lobby with the game saved.
- **Create online room** chooses the seat count, then share the invite link or room code. Each friend joins from their own browser or device, and the match starts when every seat is filled. Starting or joining another match replaces the browser's saved seat.
- **How to play** and **About** in the menu explain the rules and what data is kept.

### Rules

- Roll a six to bring a pawn out, or move a pawn already in play. Each color has its own clockwise route and home lane.
- Roll again after a six, a capture, or an exact finish. A third six in a row forfeits the roll. With no legal move the turn passes (a six still grants a reroll).
- Starts and starred squares are safe. Landing on another ordinary track square sends every opposing pawn there back to its yard. Stacks do not block passage.
- Finishing needs an exact roll. The first player with all four pawns home wins.
- Each player can enable automatic movement: when exactly one pawn can move, it moves without a tap.

### Online rooms

A player has 5 seconds to roll, shown as a ring draining around the die, and 15 seconds to move, shown as a ring around their portrait that turns red and blinks, with the movable pawns, in the last 5 seconds. When a timer runs out the server rolls, or moves a random legal pawn, for that player. Each timer starts once the previous roll or move has finished animating.

The room's creator chooses whether computer substitutes are on (the default). Every player sees each seat's status:

- **Disconnected** (network drop or closed browser): shown as Offline after 15 seconds. The timers keep playing for the seat; its move is made 1 second after its roll. The player reconnects with Resume game in the same browser or, when signed in, from any device. After 5 minutes away a computer takes over (CPU) until they return; without substitutes the seat is removed instead.
- **Leave game** (chosen on purpose): the player cannot return. A computer takes the seat at once, or without substitutes the seat is removed.
- **Removed** (Left): the seat's pawns leave the board and turns skip it. When one player remains, they win.

Only the room's creator, or the local device, can end a game for everyone.

### Accounts

Signing up is optional and needs a username, email address and password. The account is created only after the player enters the 6-digit code emailed to them (valid for 10 minutes, 5 tries). **Forgot password?** emails a code that sets a new password and signs out every other device. Players sign in with their username or email. An account keeps a display name and avatar, records finished online games and wins, and lists unfinished online games so they can be resumed on any device; resuming moves the seat and signs the previous device out of that game. Players can change their password (which signs out other devices) or delete their account from the account page.

## Security

- The server rolls every die and checks every move. Seat credentials and sign-in tokens are random 256-bit values stored only as SHA-256 hashes. Passwords are hashed with scrypt.
- Requests are rate limited per signed-in account, or per client address for guests, with tighter limits for creating rooms, joining, moves, sign-up and sign-in (also limited per username). Limited requests get `429` with `Retry-After`.
- Behind a reverse proxy, set `LUDO_PROXY_HOPS` to the number of proxies that append to `X-Forwarded-For` (the Docker image sets 1, which suits Azure App Service). The client address is the entry the outermost trusted proxy added, so a forged header cannot change it.
- Sign-up and password-reset replies are identical whether or not an email address has an account. Code guesses are capped per email across codes, and each recipient gets at most a few emails every few minutes.
- Request bodies are limited to 16 KB. API responses carry `nosniff`, `no-store` and a deny-all Content-Security-Policy; the web image adds a strict Content-Security-Policy that only allows its own API origin, plus HSTS and frame denial.
- Finished rooms are deleted after two days and idle rooms after thirty.

## Settings

| Setting | Service | Purpose |
| --- | --- | --- |
| `VITE_API_URL` | Frontend, **at build time** | Public HTTPS API origin for separate deployments. Defaults to `/api` on the frontend origin; Vite forwards this to FastAPI on port 8000. |
| `LUDO_ORIGINS` | Backend | Comma-separated exact frontend origins allowed by CORS, e.g. `https://play.example.com`. |
| `DATABASE_URL` | Backend | Postgres connection URI. Required. |
| `LUDO_PROXY_HOPS` | Backend | Trusted proxies in front of the API (default 0; the Docker image sets 1). |
| `LUDO_AUTO_MIGRATE` | Backend | `0` turns off applying `backend/migrations` at startup (default on). |
| `RESEND_API_KEY` | Backend | [Resend](https://resend.com) API key for sign-up and password-reset emails. Without it (and without `LUDO_MAIL_DEV`), account creation and password reset are unavailable. |
| `LUDO_MAIL_FROM` | Backend | Sender, on a domain verified in Resend, e.g. `Ludo <no-reply@example.com>`. |
| `LUDO_MAIL_DEV` | Backend | Development only: `1` prints emails instead of sending them; with `LUDO_MAIL_DIR`, also writes them there as JSON. Never set in production. |

Rate limits are kept in memory per API instance. Health check: `GET /health`. API docs: `/docs`.

## Database migrations

The SQL files in [`backend/migrations`](backend/migrations) run automatically, in name order, each time the API starts. Each file runs once and is recorded in `ludo.schema_migrations`; a database lock makes several instances starting together wait for each other, and a file that fails is rolled back and stops the API from starting, so it never serves an outdated schema. To change the schema, add a new file with a later name rather than editing an applied one. The database user needs permission to create tables (Supabase's `postgres` user has it). To apply the files yourself instead, set `LUDO_AUTO_MIGRATE=0` and run them in order, for example in Supabase's SQL Editor.

## Containers

From the repository root:

```sh
docker build -t ludo-api backend
docker run -p 8000:8000 -e DATABASE_URL='postgresql://...' -e LUDO_ORIGINS=https://play.example.com ludo-api
docker build -t ludo-web --build-arg VITE_API_URL=https://api.example.com frontend
docker run -p 8080:80 ludo-web
```

The API listens on port 8000 and the web server on port 80. On a container host such as Azure App Service, set the API's settings in the host's configuration and use `/health` as the API health check. Rebuild the web image whenever the API origin changes.

## Tests

Use a dedicated test Postgres database as `DATABASE_URL`; the tests create the schema through the same automatic migrations, and the migration tests also create and drop temporary databases, so the user needs permission to create databases. Run `python -m pytest` inside `backend` with the development requirements installed, and `npm run lint && npm run build` inside `frontend`. The browser suite in `tests/` uses Python Playwright against both running services on their default local ports, with the API started with `LUDO_MAIL_DEV=1 LUDO_MAIL_DIR=/tmp/ludo-mail` so the tests can read emailed codes: install Chromium with `python -m playwright install chromium`, then run `python -m pytest tests/` from the repository root. GitHub Actions runs these checks on every push and pull request.

## Existing SQLite matches

Stop writes to the old backend and keep a copy of its SQLite file. From `backend/`, with the destination `DATABASE_URL` set, run `python import_sqlite.py /path/to/ludo.sqlite3` before starting the new backend; it creates the schema first. The import preserves room codes, seat credentials and turn revisions. Identical rooms are skipped; conflicting rooms roll back the import.
