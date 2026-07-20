"""worldcup26.ir API client (live scores fallback, no auth)."""

import logging
from typing import Any, Optional

import requests

from app.data.cache_utils import cached_fetch

logger = logging.getLogger(__name__)

TTL_FIXTURES = 600
TTL_LIVE = 60
TTL_TEAMS = 3600


class WorldCup26Client:
    BASE_URL = "https://worldcup26.ir"

    def _request(self, path: str) -> Optional[dict]:
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        try:
            response = requests.get(url, timeout=20)
            if response.status_code >= 400:
                logger.error("worldcup26.ir %s: HTTP %s", path, response.status_code)
                return None
            return response.json()
        except requests.RequestException as exc:
            logger.error("worldcup26.ir request failed: %s", exc)
            return None

    def _get(self, path: str, cache_key: str, ttl: int) -> Optional[dict]:
        return cached_fetch(cache_key, ttl, lambda: self._request(path))

    @staticmethod
    def map_status(game: dict) -> str:
        finished = str(game.get("finished", "")).upper()
        elapsed = (game.get("time_elapsed") or "").lower()
        if finished == "TRUE" or elapsed == "finished":
            return "FT"
        if elapsed and elapsed not in ("", "null", "0", "finished"):
            if "half" in elapsed or elapsed == "ht":
                return "HT"
            return "LIVE"
        return "NS"

    @staticmethod
    def map_stage(game_type: str) -> str:
        t = (game_type or "group").lower()
        if t == "group":
            return "group"
        if "32" in t or "round of 32" in t:
            return "RO32"
        if "quarter" in t:
            return "QF"
        if "semi" in t:
            return "SF"
        if "final" in t:
            return "F"
        return "group"

    def get_games(self) -> Optional[list[dict]]:
        data = self._get("get/games", "wc26:games", TTL_LIVE)
        if not data:
            return None
        return data.get("games") or []

    def get_teams(self) -> Optional[list[dict]]:
        data = self._get("get/teams", "wc26:teams", TTL_TEAMS)
        if not data:
            return None
        return data.get("teams") or []

    def get_groups(self) -> Optional[list[dict]]:
        data = self._get("get/groups", "wc26:groups", TTL_TEAMS)
        if not data:
            return None
        return data.get("groups") or data if isinstance(data, list) else None

    def get_stadiums(self) -> Optional[list[dict]]:
        data = self._get("get/stadiums", "wc26:stadiums", TTL_TEAMS)
        if not data:
            return None
        return data.get("stadiums") or []

    def get_live_games(self) -> Optional[list[dict]]:
        games = self.get_games()
        if not games:
            return None
        live = [g for g in games if self.map_status(g) in ("LIVE", "HT")]
        return live if live else None
