# WC2026 Fantasy Football

FIFA World Cup 2026 Fantasy Football platform built with **Python / Flask**. All game logic runs server-side; the UI uses Jinja2 templates and vanilla JavaScript `fetch()` calls.

Build a 15-player squad, manage transfers and boosters, track live points, and compete in global and mini-league leaderboards — powered by a hybrid of four free football data sources.

---

## Features

- **Squad builder** — 15 players (2 GK / 5 DEF / 5 MID / 3 FWD), formations, captain, budget
- **Transfers** — free transfers, hit penalties, budget tracking across matchdays
- **Boosters** — Wildcard, 12th Man, Max Captain, Qualification Booster, Mystery
- **Live points** — matchday scoring with live updates while fixtures are in play
- **Leaderboards** — overall, by country, and by matchday
- **Mini-leagues** — create or join private leagues with friends
- **Admin sync** — seed and refresh tournament data via CLI or authenticated API

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | Flask 3, SQLAlchemy, Flask-Migrate, Flask-Login |
| Frontend | Jinja2, vanilla JS, custom CSS design system |
| Data | football-data.org · worldcup26.ir · API-Football · openfootball |
| Jobs | APScheduler (live scores, fixtures, post-match stats) |
| DB | SQLite (dev) / PostgreSQL (production) |

## Data Sources (100% free tier)

| Source | Used for | Auth |
|--------|----------|------|
| [football-data.org](https://www.football-data.org/) | Fixtures, teams, standings, match detail | Free API token |
| [worldcup26.ir](https://worldcup26.ir) | Live scores, groups, teams (fallback) | None |
| [API-Football](https://www.api-football.com/) | Player stats after FT only (100 req/day) | Free API key |
| [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) | One-time DB seed (CLI only) | None |

### Fallback chain

- **Live scores:** worldcup26.ir → football-data.org → cached DB
- **Fixtures:** football-data.org → worldcup26.ir → cached DB
- **Player stats:** api-football only (skipped gracefully if quota exhausted)

When fallback/cached data is served, the UI shows: *"Data may be delayed"*.

---

## Quick Start

### Requirements

- Python 3.11+
- Free API keys for football-data.org and API-Football (optional for seed/live fallbacks)

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
# Edit .env — set SECRET_KEY, FOOTBALL_DATA_TOKEN, API_FOOTBALL_KEY
```

### Initialize database & data

```bash
flask db upgrade
flask seed-db          # one-time: countries + fixture shells from openfootball
flask sync-players     # teams from football-data.org or worldcup26.ir
flask sync-fixtures    # update scores/status
```

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

FOOTBALL_DATA_TOKEN=your_football_data_token_here
API_FOOTBALL_KEY=your_api_football_key_here

ADMIN_EMAILS=you@example.com

CACHE_TYPE=SimpleCache
# CACHE_REDIS_URL=redis://localhost:6379/0

MYSTERY_BOOSTER_TYPE=WILDCARD
```

No keys needed for worldcup26.ir or openfootball JSON.

### API keys — how to get them

1. **football-data.org** — [Register](https://www.football-data.org/client/register)  
   Free tier: 10 requests/minute. WC competition code: `WC`, season `2026`.

2. **API-Football** — [Register](https://dashboard.api-football.com/register)  
   Free tier: 100 requests/day. Used only for post-match player statistics.

3. **worldcup26.ir** — No registration required.

4. **openfootball** — Static JSON, fetched once via `flask seed-db`.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `flask seed-db` | One-time seed from openfootball JSON (countries + fixtures) |
| `flask sync-players` | Sync teams/players from football-data.org (fallback: worldcup26.ir) |
| `flask sync-fixtures` | Update fixture statuses and scores |
| `flask sync-all` | sync-players + sync-fixtures |

---

## Project Structure

```
Fantasy-World-cup-2026/
├── app/
│   ├── auth/           # Login, register, session
│   ├── fantasy/        # Squad, transfers, scoring, boosters, APIs
│   ├── leagues/        # Mini-leagues
│   ├── data/           # External clients, sync, scheduler
│   │   ├── football_data.py
│   │   ├── worldcup26.py
│   │   ├── api_football.py
│   │   ├── openfootball.py
│   │   ├── cache_utils.py
│   │   ├── sync.py
│   │   └── scheduler.py
│   ├── templates/      # Jinja2 pages
│   ├── models.py
│   ├── config.py
│   └── __init__.py
├── static/
│   ├── css/style.css
│   └── js/             # squad_builder, transfers, live_points
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
| Group-stage budget | 100.0 |
| Knockout budget | 105.0 |
| Transfer hit | −3 points |
| Free transfers | 2 (group) / 1 (knockout), +1 max rollover |

Scoring follows FIFA WC 2026-style rules (appearance, goals by position, assists, clean sheets, cards, GK saves, etc.) — see `app/config.py` and `app/fantasy/scoring.py`.

---

## API Overview

### Public / authenticated

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/meta` | App meta + API-Football quota |
| GET | `/api/players` | Player list (filters) |
| GET | `/api/team` | Current user squad |
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

### Admin (admin email required)

```
POST /api/admin/seed-db
POST /api/admin/sync/players
POST /api/admin/sync/fixtures
POST /api/admin/sync/livescores
POST /api/admin/sync/stats/<fixture_id>
POST /api/admin/recalculate/<matchday>
```

---

## Background Jobs

| Job | Interval | Action |
|-----|----------|--------|
| `sync_live_scores` | 60s | Live scores via worldcup26.ir |
| `sync_fixtures` | 10 min | Fixture updates via football-data.org |
| `sync_finished_stats` | 10 min | Player stats for FT matches (api-football) |

## API-Football Quota Protection

- Fetches player stats **once**, only after a fixture reaches **FT**
- Tracks daily usage in `ApiQuotaLog`
- Stops at **90 calls/day** (buffer under the 100 free limit)
- Never polls player stats during live matches
- Never re-fetches finished matches (24h cache)

Check quota: `GET /api/meta` → `api_football_quota`

---

## Production Notes

- Set a strong `SECRET_KEY` and `FLASK_ENV=production`
- Prefer PostgreSQL: `DATABASE_URL=postgresql://user:pass@host/dbname`
- Serve with Gunicorn (included in `requirements.txt` on non-Windows):

```bash
gunicorn -w 2 -b 0.0.0.0:8000 "run:app"
```

- Keep API keys out of git; only `.env.example` is committed

---

## Notes

- football-data.org free tier may restrict WC2026 endpoints until the tournament; worldcup26.ir serves as fallback for fixtures and live scores.
- Player data populates from football-data.org squads when available, and from API-Football lineups after each finished match.
- Run `flask seed-db` once before first use; re-run only on a fresh database.

## License

MIT — see [LICENSE](LICENSE).
