"""football-data.org API v4 client (primary fixtures/teams source)."""

import logging
import os
import time
from typing import Any, Optional

import requests

from app.data.cache_utils import cached_fetch, get_flask_cache

logger = logging.getLogger(__name__)

TTL_FIXTURES = 600
TTL_LIVE = 60
TTL_STANDINGS = 300
TTL_TEAMS = 3600
TTL_MATCH = 86400

STATUS_MAP = {
    "SCHEDULED": "NS",
    "TIMED": "NS",
    "LIVE": "LIVE",
    "IN_PLAY": "LIVE",
    "PAUSED": "HT",
    "FINISHED": "FT",
    "POSTPONED": "POSTP",
    "SUSPENDED": "SUSP",
    "CANCELLED": "CANC",
    "AWARDED": "FT",
}


class FootballDataClient:
    BASE_URL = "https://api.football-data.org/v4"
    COMPETITION = "WC"
    SEASON = 2026

    def __init__(self, token: str = None):
        self.token = token or os.getenv("FOOTBALL_DATA_TOKEN", "")
        self._last_request = 0.0
        self._min_interval = 6.5  # 10 req/min

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()

    def _headers(self) -> dict:
        return {"X-Auth-Token": self.token} if self.token else {}

    def _request(self, path: str, params: dict = None) -> Optional[dict]:
        if not self.token:
            logger.warning("FOOTBALL_DATA_TOKEN not set")
            return None
        self._rate_limit()
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        try:
            response = requests.get(url, headers=self._headers(), params=params or {}, timeout=30)
            if response.status_code == 429:
                time.sleep(60)
                return self._request(path, params)
            if response.status_code >= 400:
                logger.error("football-data.org %s: HTTP %s %s", path, response.status_code, response.text[:200])
                return None
            return response.json()
        except requests.RequestException as exc:
            logger.error("football-data.org request failed: %s", exc)
            return None

    def _get(self, path: str, cache_key: str, ttl: int, params: dict = None) -> Optional[dict]:
        return cached_fetch(
            cache_key,
            ttl,
            lambda: self._request(path, params),
        )

    @staticmethod
    def map_status(fd_status: str) -> str:
        return STATUS_MAP.get((fd_status or "").upper(), "NS")

    @staticmethod
    def map_position(raw: str) -> str:
        pos = (raw or "").upper()
        mapping = {
            "GOALKEEPER": "GK",
            "DEFENCE": "DEF",
            "DEFENSE": "DEF",
            "DEFENDER": "DEF",
            "MIDFIELD": "MID",
            "MIDFIELDER": "MID",
            "OFFENCE": "FWD",
            "OFFENSE": "FWD",
            "OFFENSIVE_MIDFIELD": "MID",
            "DEFENSIVE_MIDFIELD": "MID",
            "CENTRAL_MIDFIELD": "MID",
            "ATTACKING_MIDFIELD": "MID",
            "LEFT_WING": "FWD",
            "RIGHT_WING": "FWD",
            "CENTRE_FORWARD": "FWD",
            "LEFT_BACK": "DEF",
            "RIGHT_BACK": "DEF",
            "CENTRE_BACK": "DEF",
        }
        if pos in ("GK", "DEF", "MID", "FWD"):
            return pos
        return mapping.get(pos, "MID")

    def get_matches(self) -> Optional[list[dict]]:
        data = self._get(
            f"competitions/{self.COMPETITION}/matches",
            f"fd:matches:{self.COMPETITION}:{self.SEASON}",
            TTL_FIXTURES,
            params={"season": self.SEASON},
        )
        if not data:
            return None
        return data.get("matches") or []

    def get_teams(self) -> Optional[list[dict]]:
        data = self._get(
            f"competitions/{self.COMPETITION}/teams",
            f"fd:teams:{self.COMPETITION}",
            TTL_TEAMS,
        )
        if not data:
            return None
        return data.get("teams") or []

    def get_standings(self) -> Optional[dict]:
        return self._get(
            f"competitions/{self.COMPETITION}/standings",
            f"fd:standings:{self.COMPETITION}",
            TTL_STANDINGS,
        )

    def get_scorers(self) -> Optional[list[dict]]:
        data = self._get(
            f"competitions/{self.COMPETITION}/scorers",
            f"fd:scorers:{self.COMPETITION}",
            TTL_TEAMS,
            params={"season": self.SEASON},
        )
        if not data:
            return None
        return data.get("scorers") or []

    def get_match(self, match_id: int) -> Optional[dict]:
        return self._get(
            f"matches/{match_id}",
            f"fd:match:{match_id}",
            TTL_MATCH,
        )

    def get_team(self, team_id: int) -> Optional[dict]:
        return self._get(
            f"teams/{team_id}",
            f"fd:team:{team_id}",
            TTL_TEAMS,
        )

    def get_live_matches(self) -> Optional[list[dict]]:
        matches = self.get_matches()
        if not matches:
            return None
        live = [m for m in matches if self.map_status(m.get("status")) in ("LIVE", "HT")]
        return live or None
