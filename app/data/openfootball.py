"""One-time seed from openfootball/worldcup.json — CLI only, never at runtime."""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OPENFOOTBALL_URL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
)


class OpenFootballSeeder:
    """Fetch and parse openfootball JSON. Only used by flask seed-db."""

    def fetch_json(self) -> Optional[dict]:
        try:
            response = requests.get(OPENFOOTBALL_URL, timeout=60)
            if response.status_code >= 400:
                logger.error("openfootball fetch failed: HTTP %s", response.status_code)
                return None
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.error("openfootball fetch failed: %s", exc)
            return None

    @staticmethod
    def stable_country_id(name: str) -> int:
        digest = hashlib.md5(name.strip().lower().encode()).hexdigest()
        return int(digest[:7], 16) % 900000 + 100000

    @staticmethod
    def stable_fixture_id(team1: str, team2: str, date_str: str) -> int:
        key = f"{team1}|{team2}|{date_str}".lower()
        digest = hashlib.md5(key.encode()).hexdigest()
        return int(digest[:8], 16) % 90000000 + 10000000

    @staticmethod
    def parse_kickoff(date_str: str, time_str: str = None) -> datetime:
        try:
            if time_str:
                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

    @staticmethod
    def map_stage(round_name: str) -> str:
        r = (round_name or "").lower()
        if "group" in r or r.isdigit():
            return "group"
        if "32" in r or "round of 32" in r:
            return "RO32"
        if "quarter" in r or "qf" in r:
            return "QF"
        if "semi" in r:
            return "SF"
        if "final" in r:
            return "F"
        return "group"

    @staticmethod
    def parse_matchday(round_name: str, group: str = None) -> int:
        r = (round_name or "").strip()
        if r.isdigit():
            return int(r)
        if group:
            return 1
        return 1

    def parse(self, data: dict) -> dict:
        countries = {}
        fixtures = []
        team_names = set()

        for match in data.get("matches") or []:
            t1 = (match.get("team1") or "").strip()
            t2 = (match.get("team2") or "").strip()
            if t1:
                team_names.add(t1)
            if t2:
                team_names.add(t2)

        for name in sorted(team_names):
            countries[name] = {
                "id": self.stable_country_id(name),
                "name": name,
                "code": None,
                "flag_url": None,
                "confederation": None,
            }

        matchday_counter = {}
        for match in data.get("matches") or []:
            t1 = (match.get("team1") or "").strip()
            t2 = (match.get("team2") or "").strip()
            if not t1 or not t2:
                continue

            date_str = match.get("date") or "2026-06-11"
            time_str = match.get("time")
            group = match.get("group")
            round_name = match.get("round") or "1"
            stage = self.map_stage(round_name)
            md_key = f"{group or stage}-{round_name}"
            matchday_counter.setdefault(md_key, len(matchday_counter) + 1)
            matchday = matchday_counter[md_key]

            score = match.get("score") or {}
            home_score = away_score = None
            if isinstance(score, dict):
                ft = score.get("ft") or score.get("fulltime") or score
                if isinstance(ft, (list, tuple)) and len(ft) >= 2:
                    home_score, away_score = ft[0], ft[1]
                elif isinstance(ft, dict):
                    home_score = ft.get("home")
                    away_score = ft.get("away")

            status = "FT" if home_score is not None else "NS"

            fixtures.append({
                "id": self.stable_fixture_id(t1, t2, date_str),
                "home_team_id": countries[t1]["id"],
                "away_team_id": countries[t2]["id"],
                "home_team_name": t1,
                "away_team_name": t2,
                "kickoff_utc": self.parse_kickoff(date_str, time_str),
                "matchday": matchday,
                "stage": stage,
                "status": status,
                "home_score": home_score,
                "away_score": away_score,
                "group": group,
            })

        return {
            "name": data.get("name", "World Cup 2026"),
            "countries": list(countries.values()),
            "fixtures": fixtures,
        }
