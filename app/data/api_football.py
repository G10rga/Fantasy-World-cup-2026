"""API-Football (api-sports.io) client — player stats only, strict quota."""

import logging
import os
import time
from datetime import date
from typing import Any, Optional

import requests

from app.data.cache_utils import cached_fetch

logger = logging.getLogger(__name__)

TTL_STATS = 86400
TTL_LIVE_STATS = 60
QUOTA_SOURCE = "api_football"
QUOTA_DAILY_LIMIT = 90
LEAGUE_ID = 1
SEASON = 2026


class ApiFootballClient:
    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY", "")
        self._last_request = 0.0
        self._min_interval = 1.0

    def _headers(self) -> dict:
        return {"x-apisports-key": self.api_key} if self.api_key else {}

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()

    def _check_quota(self) -> bool:
        from app import db
        from app.models import ApiQuotaLog

        today = date.today()
        log = ApiQuotaLog.query.filter_by(date=today, source=QUOTA_SOURCE).first()
        if not log:
            log = ApiQuotaLog(date=today, source=QUOTA_SOURCE, calls_made=0)
            db.session.add(log)
            db.session.commit()
        if log.calls_made >= QUOTA_DAILY_LIMIT:
            logger.warning(
                "API-Football daily quota reached (%s/%s) — skipping fetch",
                log.calls_made,
                QUOTA_DAILY_LIMIT,
            )
            return False
        return True

    def _increment_quota(self) -> None:
        from app import db
        from app.models import ApiQuotaLog

        today = date.today()
        log = ApiQuotaLog.query.filter_by(date=today, source=QUOTA_SOURCE).first()
        if not log:
            log = ApiQuotaLog(date=today, source=QUOTA_SOURCE, calls_made=0)
            db.session.add(log)
        log.calls_made += 1
        db.session.commit()

    def _request(self, path: str, params: dict = None, use_quota: bool = True) -> Optional[dict]:
        if not self.api_key:
            logger.warning("API_FOOTBALL_KEY not set")
            return None

        self._rate_limit()
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        try:
            response = requests.get(url, headers=self._headers(), params=params or {}, timeout=30)
            if use_quota:
                self._increment_quota()
            if response.status_code >= 400:
                logger.error("api-football %s: HTTP %s %s", path, response.status_code, response.text[:200])
                return None
            body = response.json()
            if body.get("errors"):
                logger.error("api-football errors: %s", body["errors"])
                return None
            return body
        except requests.RequestException as exc:
            logger.error("api-football request failed: %s", exc)
            return None

    def _get(self, path: str, cache_key: str, ttl: int, params: dict = None, use_quota: bool = True) -> Optional[dict]:
        from app.data.cache_utils import get_flask_cache

        cache = get_flask_cache()
        if cache and ttl:
            hit = cache.get(cache_key)
            if hit is not None:
                return hit

        if use_quota and not self._check_quota():
            return None

        result = self._request(path, params, use_quota=use_quota)
        if cache and ttl and result is not None:
            cache.set(cache_key, result, timeout=ttl)
        return result

    @staticmethod
    def map_position(raw: str) -> str:
        pos = (raw or "").upper()
        if pos in ("G", "GK", "GOALKEEPER"):
            return "GK"
        if pos in ("D", "DEF", "DEFENDER"):
            return "DEF"
        if pos in ("M", "MID", "MIDFIELDER"):
            return "MID"
        if pos in ("F", "FWD", "ATT", "FORWARD", "ATTACKER"):
            return "FWD"
        return "MID"

    def find_fixture_id(self, home_name: str, away_name: str, match_date: str) -> Optional[int]:
        """Resolve api-football fixture id by team names and date (uses 1 quota call)."""
        fixture_id = self._find_fixture_in_list(home_name, away_name, match_date, use_league=False)
        if fixture_id:
            return fixture_id
        return self._find_fixture_in_list(home_name, away_name, match_date, use_league=True)

    def _find_fixture_in_list(
        self, home_name: str, away_name: str, match_date: str, *, use_league: bool
    ) -> Optional[int]:
        if use_league:
            cache_key = f"af:fixtures:{LEAGUE_ID}:{SEASON}:{match_date}"
            params = {"league": LEAGUE_ID, "season": SEASON, "date": match_date}
        else:
            cache_key = f"af:fixtures:date:{match_date}"
            params = {"date": match_date}

        data = self._get("fixtures", cache_key, 3600, params=params)
        if not data:
            return None

        home_l = home_name.lower()
        away_l = away_name.lower()
        for fx in data.get("response") or []:
            teams = fx.get("teams") or {}
            h = (teams.get("home") or {}).get("name", "").lower()
            a = (teams.get("away") or {}).get("name", "").lower()
            if (home_l in h or h in home_l) and (away_l in a or a in away_l):
                return fx.get("fixture", {}).get("id")
        return None

    def get_fixture_players(self, fixture_id: int, *, live: bool = False) -> Optional[list[dict]]:
        ttl = TTL_LIVE_STATS if live else TTL_STATS
        suffix = ":live" if live else ""
        data = self._get(
            "fixtures/players",
            f"af:fixture_players:{fixture_id}{suffix}",
            ttl,
            params={"fixture": fixture_id},
        )
        if not data:
            return None
        return data.get("response") or []

    def get_fixture_lineups(self, fixture_id: int, *, live: bool = False) -> Optional[list[dict]]:
        ttl = TTL_LIVE_STATS if live else TTL_STATS
        suffix = ":live" if live else ""
        data = self._get(
            "fixtures/lineups",
            f"af:fixture_lineups:{fixture_id}{suffix}",
            ttl,
            params={"fixture": fixture_id},
        )
        if not data:
            return None
        return data.get("response") or []

    def get_fixture_events(self, fixture_id: int, *, live: bool = False) -> Optional[list[dict]]:
        ttl = TTL_LIVE_STATS if live else TTL_STATS
        suffix = ":live" if live else ""
        data = self._get(
            "fixtures/events",
            f"af:fixture_events:{fixture_id}{suffix}",
            ttl,
            params={"fixture": fixture_id},
        )
        if not data:
            return None
        return data.get("response") or []

    def get_teams(self) -> Optional[list[dict]]:
        data = self._get(
            "teams",
            f"af:teams:{LEAGUE_ID}:{SEASON}",
            3600,
            params={"league": LEAGUE_ID, "season": SEASON},
        )
        if not data:
            return None
        return data.get("response") or []

    def get_squad(self, team_id: int) -> Optional[list[dict]]:
        data = self._get(
            "players/squads",
            f"af:squad:{team_id}:{SEASON}",
            3600,
            params={"team": team_id},
        )
        if not data:
            return None
        resp = data.get("response") or []
        return resp[0].get("players") if resp else []

    @staticmethod
    def get_quota_usage() -> dict:
        from app.models import ApiQuotaLog

        today = date.today()
        log = ApiQuotaLog.query.filter_by(date=today, source=QUOTA_SOURCE).first()
        used = log.calls_made if log else 0
        return {"date": str(today), "used": used, "limit": QUOTA_DAILY_LIMIT, "remaining": max(0, QUOTA_DAILY_LIMIT - used)}
