# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] — 2026-07-20

### Added
- Full Flask fantasy football platform for FIFA World Cup 2026
- Hybrid free-tier data sources: football-data.org, worldcup26.ir, API-Football, openfootball
- Auth (register/login), squad builder, transfers, boosters, live points
- Overall / country / matchday leaderboards and mini-leagues
- APScheduler jobs for live scores, fixtures, and post-match player stats
- Alembic migrations and CLI seed/sync commands
- Quota-safe API-Football usage (post-FT only, daily cap)
