# WC2026 Fantasy Football

FIFA World Cup 2026 Fantasy Football platform built with **Python / Flask**. All game logic runs server-side; the UI uses Jinja2 templates and vanilla JavaScript `fetch()` calls.

Build a 15-player squad, manage transfers and boosters, track live points, and compete in global and mini-league leaderboards — powered by a hybrid of free football data sources.

Live: [https://fantasy.g1orga.dev](https://fantasy.g1orga.dev)

---

## Features

- **Welcome guide** — guests and managers without a squad land on `/`; managers with a squad go to the dashboard (`/dashboard` always available)
- **Squad builder** — pick a formation, fill the XI slot-by-slot, then unlock 4 bench places (2 GK / 5 DEF / 5 MID / 3 FWD total, budget + captain)
- **Player photos** — headshots from TheSportsDB (primary) and API-Football squads; manual URL overrides; initials fallback (no nation-flag avatars)
- **Transfers** — free transfers, hit penalties, budget tracking across matchdays
- **Boosters** — Wildcard, 12th Man, Max Captain, Qualification Booster, Mystery
- **Live points** — matchday scoring with live updates while fixtures are in play
- **Leaderboards** — overall, by country, and by matchday
- **Mini-leagues** — create or join private leagues with friends
- **Admin sync** — seed/refresh tournament data and manage player photos via authenticated API
- **Production boot** — optional auto-migrate + auto-seed on Postgres (Render-friendly)

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | Flask 3, SQLAlchemy, Flask-Migrate, Flask-Login |
| Frontend | Jinja2, vanilla JS, Tailwind CDN + Championship Pulse design system |
| Data | football-data.org · worldcup26.ir · API-Football · TheSportsDB · openfootball |
| Jobs | APScheduler (live scores, fixtures, post-match stats, photo backfill) |
| DB | SQLite (dev) / PostgreSQL (production) |

## Data Sources (free tier)

| Source | Used for | Auth |
|--------|----------|------|
| [football-data.org](https://www.football-data.org/) | Fixtures, teams, standings, match detail, squad roster | Free API token |
| [worldcup26.ir](https://worldcup26.ir) | Live scores, groups, teams (fallback) | None |
| [API-Football](https://www.api-football.com/) | Post-match player stats; optional national-squad photos | Free API key (~100 req/day) |
| [TheSportsDB](https://www.thesportsdb.com/) | Player headshot cutouts/thumbs | Free (no key for search) |
| [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) | One-time DB seed (CLI / AUTO_SEED) | None |

### Fallback chain

- **Live scores:** worldcup26.ir → football-data.org → cached DB
- **Fixtures:** football-data.org → worldcup26.ir → cached DB
- **Player stats:** api-football only (skipped gracefully if quota exhausted)
- **Player photos:** manual map → TheSportsDB → API-Football national squads (if key + quota) → initials

When fallback/cached data is served, the UI shows: *"Data may be delayed"*.

---

## Quick Start

### Requirements

- Python 3.11+
- Free API keys for football-data.org and API-Football (optional for seed/live fallbacks / extra photos)

### Setup

```bash
git clone https://github.com/G10rga/Fantasy-World-cup-2026.git
cd Fantasy-World-cup-2026

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env — set SECRET_KEY, FOOTBALL_DATA_TOKEN, API_FOOTBALL_KEY, ADMIN_EMAILS
```

### Initialize database & data

```bash
flask db upgrade
flask seed-db          # one-time: countries + fixture shells from openfootball
flask sync-players     # teams from football-data.org or worldcup26.ir
flask sync-fixtures    # update scores/status
```

On Postgres (e.g. Render), `AUTO_MIGRATE` / `AUTO_SEED` can do the first boot for you — see [Production Notes](#production-notes).

### Run

```bash
flask run
# or
python run.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## Environment Variables

Copy `.env.example` to `.env`:

```env
SECRET_KEY=change-me-to-a-random-secret-key
FLASK_ENV=development
FLASK_DEBUG=1

DATABASE_URL=sqlite:///wc2026_fantasy.db

# Production / Postgres (defaults ON when DATABASE_URL is postgres:// or postgresql://)
# AUTO_MIGRATE=1
# AUTO_SEED=1

FOOTBALL_DATA_TOKEN=your_football_data_token_here
API_FOOTBALL_KEY=your_api_football_key_here

ADMIN_EMAILS=you@example.com

CACHE_TYPE=SimpleCache
# CACHE_REDIS_URL=redis://localhost:6379/0

MYSTERY_BOOSTER_TYPE=WILDCARD
```

No keys needed for worldcup26.ir, TheSportsDB search, or openfootball JSON.

### API keys — how to get them

1. **football-data.org** — [Register](https://www.football-data.org/client/register)  
   Free tier: 10 requests/minute. WC competition code: `WC`, season `2026`.

2. **API-Football** — [Register](https://dashboard.api-football.com/register)  
   Free tier: ~100 requests/day. Used for post-match player statistics and optional photo fills. App stops at **90 calls/day**.

3. **worldcup26.ir** / **TheSportsDB** — No registration required for the endpoints we use.

4. **openfootball** — Static JSON, fetched once via `flask seed-db` / AUTO_SEED.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `flask seed-db` | One-time seed from openfootball JSON (countries + fixtures) |
| `flask sync-players` | Sync teams/players from football-data.org (fallback: worldcup26.ir) |
| `flask sync-fixtures` | Update fixture statuses and scores |
| `flask sync-all` | sync-players + sync-fixtures |

---

## Pages

| Path | Who | Description |
|------|-----|-------------|
| `/` | Everyone | Welcome guide if guest or no squad; dashboard if squad exists |
| `/dashboard` | Managers | Home dashboard |
| `/squad` | Managers | Formation + XI-first squad builder |
| `/my-team` | Managers | Current squad view |
| `/transfers` | Managers | Transfer market |
| `/points` | Managers | Matchday points |
| `/fixtures` | Everyone | Fixture list |
| `/leagues` | Managers | Mini-leagues |
| `/leaderboard` | Everyone | Rankings |
| `/login`, `/register` | Guests | Auth |

---

## Project Structure

```
Fantasy-World-cup-2026/
├── app/
│   ├── auth/           # Login, register, session
│   ├── fantasy/        # Squad, transfers, scoring, boosters, photo APIs
│   ├── leagues/        # Mini-leagues
│   ├── data/           # External clients, sync, scheduler, photo map
│   │   ├── football_data.py
│   │   ├── worldcup26.py
│   │   ├── api_football.py
│   │   ├── openfootball.py
│   │   ├── player_photos.py   # Manual photo URL overrides (applied on boot)
│   │   ├── cache_utils.py
│   │   ├── sync.py
│   │   └── scheduler.py
│   ├── templates/      # Jinja2 pages (welcome, dashboard, squad, …)
│   ├── models.py
│   ├── config.py
│   └── __init__.py
├── static/
│   ├── css/
│   └── js/             # squad_builder, avatars, transfers, live_points, …
├── scripts/            # Optional photo backfill helpers (local)
├── migrations/         # Alembic migrations
├── .env.example
├── requirements.txt
├── run.py
└── README.md
```

---

## Fantasy Rules (summary)

| Setting | Value |
|---------|--------|
| Squad size | 15 (11 starters + 4 bench) |
| Positions | 2 GK, 5 DEF, 5 MID, 3 FWD |
| Builder flow | Choose formation → fill XI slots → unlock bench |
| Formations | 3-4-3, 3-5-2, 4-3-3, 4-4-2, 5-2-3, 5-3-2 (min 2 starting FWDs) |
| Group-stage budget | 100.0 |
| Knockout budget | 105.0 |
| Transfer hit | −3 points |
| Free transfers | 2 (group) / 1 (knockout), +1 max rollover |

Scoring follows FIFA WC 2026-style rules (appearance, goals by position, assists, clean sheets, cards, GK saves, etc.) — see `app/config.py` and `app/fantasy/scoring.py`.

---

## Player photos

Photos are stored on `players.photo_url`:

| Value | Meaning |
|-------|---------|
| real URL | Headshot to show in the UI |
| `NULL` | Not tried yet |
| `""` | First auto-pass found nothing (eligible for one retry) |
| `"-"` | Exhausted after retry — stop auto-trying |

### Automatic

- Boot / scheduler backfill via TheSportsDB search
- Optional API-Football national squad photos when `API_FOOTBALL_KEY` has quota
- On-demand fetch for visible squad / player-list rows

Coverage is never guaranteed to be 100% for obscure players.

### Manual overrides (path to 100%)

1. Edit `app/data/player_photos.py` → `PLAYER_PHOTO_URLS` (keys: football-data player **id** or unique **name**).
2. Redeploy, or call `POST /api/admin/players/photos/apply-manual` as an admin.
3. Or set URLs via admin APIs (see below).

Local helpers (optional):

```bash
python scripts/fetch_tsdb_photos.py --resume          # roster → TheSportsDB URLs
python scripts/fetch_tsdb_photos.py --resume --apply   # merge into player_photos.py
python scripts/build_player_photos.py                 # AF national squads when quota resets
```

---

## API Overview

### Public / authenticated

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/meta` | App meta + API-Football quota |
| GET | `/api/players` | Player list (filters); may kick a small photo fetch |
| GET | `/api/players/<id>` | Player detail |
| GET | `/api/team` | Current user squad (ensures roster photos) |
| POST | `/api/team/save` | Save squad |
| PUT | `/api/team/captain` | Set captain |
| POST | `/api/team/substitute` | Bench ↔ XI |
| GET | `/api/team/points` | Matchday points |
| GET/POST | `/api/transfers` | List / make transfers |
| GET | `/api/boosters` | Booster status |
| POST | `/api/boosters/activate` | Activate booster |
| GET | `/api/fixtures` | Fixtures |
| GET | `/api/live/points` | Live points feed |
| GET | `/api/leaderboard/overall` | Overall leaderboard |
| POST | `/api/photos/sync` | Run one photo backfill batch (debug / after deploy) |

### Admin (email in `ADMIN_EMAILS`)

```
POST /api/admin/seed-db
POST /api/admin/sync/players
POST /api/admin/sync/fixtures
POST /api/admin/sync/livescores
POST /api/admin/sync/stats/<fixture_id>
POST /api/admin/recalculate/<matchday>

GET  /api/admin/players/missing-photos?limit=200
PUT  /api/admin/players/<id>/photo          body: { "photo_url": "https://..." }
POST /api/admin/players/photos              body: { "photos": [ { "player_id"| "name", "photo_url" }, ... ] }
POST /api/admin/players/photos/apply-manual ?only_missing=1
```

Unauthenticated `/api/*` calls return JSON `401` (not an HTML login redirect).

---

## Background Jobs

| Job | Interval | Action |
|-----|----------|--------|
| `sync_live_scores` | 60s | Live scores via worldcup26.ir |
| `sync_fixtures` | 10 min | Fixture updates via football-data.org |
| `sync_finished_stats` | 10 min | Player stats for FT matches (api-football) |
| `sync_player_photos` | periodic | TheSportsDB (+ AF if available) photo backfill |

## API-Football Quota Protection

- Fetches player stats **once**, only after a fixture reaches **FT**
- Tracks daily usage in `ApiQuotaLog`
- Stops at **90 calls/day** (buffer under the free limit)
- Never polls player stats during live matches
- Never re-fetches finished matches (24h cache)
- Photo squad pulls share the same daily budget — prefer TheSportsDB / manual map first

Check quota: `GET /api/meta` → `api_football_quota`

---

## Production Notes

- Set a strong `SECRET_KEY` and prefer `FLASK_ENV=production`
- Prefer PostgreSQL: `DATABASE_URL=postgresql://user:pass@host/dbname`
- With Postgres, **`AUTO_MIGRATE`** and **`AUTO_SEED`** default **on** (even if `FLASK_ENV` is still `development`) so Render can create tables and seed without Shell access
- Boot also applies `PLAYER_PHOTO_URLS` and can start a background photo worker when players lack photos
- Serve with Gunicorn (included in `requirements.txt` on non-Windows):

```bash
gunicorn -w 2 -b 0.0.0.0:8000 "run:app"
```

- Keep API keys out of git; only `.env.example` is committed

---

## Notes

- football-data.org free tier may restrict WC2026 endpoints until the tournament; worldcup26.ir serves as fallback for fixtures and live scores.
- Player data populates from football-data.org squads when available, and from API-Football lineups after each finished match.
- Photo auto-sync finishing does **not** mean every player has an image — use the manual map / admin APIs for full coverage.
- Run `flask seed-db` once before first use locally; re-run only on a fresh database (or rely on AUTO_SEED in production).

## License

MIT — see [LICENSE](LICENSE).
