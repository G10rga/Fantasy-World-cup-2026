import logging
import random
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

import requests

from app import db
from app.data.api_football import ApiFootballClient
from app.data.cache_utils import clear_data_delayed, is_data_delayed, set_data_delayed
from app.data.football_data import FootballDataClient
from app.data.openfootball import OpenFootballSeeder
from app.data.worldcup26 import WorldCup26Client
from app.models import ApiQuotaLog, Country, Fixture, Player, PlayerMatchStat

logger = logging.getLogger(__name__)

DEFAULT_PRICES = {
    "GK": Decimal("4.5"),
    "DEF": Decimal("5.0"),
    "MID": Decimal("6.0"),
    "FWD": Decimal("7.0"),
}

NAME_ALIASES = {
    "korea republic": "south korea",
    "republic of korea": "south korea",
    "usa": "united states",
    "us": "united states",
    "cote d'ivoire": "ivory coast",
    "côte d'ivoire": "ivory coast",
    "czechia": "czech republic",
}

TBD_NAME_FRAGMENTS = (
    "tbd",
    "winner",
    "runner-up",
    "runners-up",
    "loser",
    "3rd place",
    "best third",
    "play-off",
    "playoff",
)

LIVE_STATUSES = ("LIVE", "HT", "1H", "2H", "ET", "BT", "PEN_LIVE")


def wc26_countries_query():
    return Country.query.filter(Country.worldcup26_id.isnot(None))


def wc26_fixtures_query():
    wc26_country_ids = db.session.query(Country.id).filter(Country.worldcup26_id.isnot(None))
    return Fixture.query.filter(
        Fixture.worldcup26_id.isnot(None),
        Fixture.home_team_id.in_(wc26_country_ids),
        Fixture.away_team_id.in_(wc26_country_ids),
        Fixture.home_team_id != Fixture.away_team_id,
    )


def wc26_players_query():
    return Player.query.join(Country).filter(Country.worldcup26_id.isnot(None))


def _is_placeholder_team_name(name: str) -> bool:
    n = _normalize_name(name)
    if not n:
        return True
    return any(fragment in n for fragment in TBD_NAME_FRAGMENTS)


def _is_valid_wc26_game(game: dict, wc_team_ids: set[str]) -> bool:
    home_id = str(game.get("home_team_id") or "")
    away_id = str(game.get("away_team_id") or "")
    if not home_id or not away_id or home_id == away_id:
        return False
    if wc_team_ids and (home_id not in wc_team_ids or away_id not in wc_team_ids):
        return False
    home_name = game.get("home_team_name_en") or game.get("home_team_name") or ""
    away_name = game.get("away_team_name_en") or game.get("away_team_name") or ""
    if _is_placeholder_team_name(home_name) or _is_placeholder_team_name(away_name):
        return False
    return True


def _sync_wc26_countries(teams: list[dict]) -> dict[str, Country]:
    by_wc_id: dict[str, Country] = {}
    for team in teams:
        wc_id = str(team.get("id") or "")
        if not wc_id:
            continue
        country = _upsert_country(
            team.get("name_en") or team.get("name", "Unknown"),
            worldcup26_id=wc_id,
            code=team.get("fifa_code"),
            flag_url=team.get("flag"),
        )
        by_wc_id[wc_id] = country
    db.session.flush()
    return by_wc_id


def _wc26_country_lookup(countries) -> dict[str, Country]:
    lookup: dict[str, Country] = {}
    for country in countries:
        lookup[_normalize_name(country.name)] = country
        if country.code:
            lookup[_normalize_name(country.code)] = country
    return lookup


def _find_wc26_country_for_team_name(name: str, lookup: dict[str, Country]) -> Country | None:
    return lookup.get(_normalize_name(name))


def _sync_wc26_players_from_football_data(wc26_countries) -> tuple[int, str | None]:
    fd = FootballDataClient()
    if not fd.token:
        logger.warning("FOOTBALL_DATA_TOKEN not set — cannot sync WC2026 squads")
        return 0, None

    lookup = _wc26_country_lookup(wc26_countries)
    fd_teams = fd.get_teams()
    if not fd_teams:
        logger.warning("No WC teams returned from football-data.org")
        return 0, None

    synced = 0
    for fd_team in fd_teams:
        country = _find_wc26_country_for_team_name(fd_team.get("name", ""), lookup)
        if not country and fd_team.get("tla"):
            country = lookup.get(_normalize_name(fd_team.get("tla")))
        if not country:
            logger.debug("Skipping football-data team with no wc26 match: %s", fd_team.get("name"))
            continue

        country.football_data_id = fd_team.get("id")
        detail = fd.get_team(fd_team.get("id"))
        if not detail:
            continue

        for member in detail.get("squad") or []:
            player_id = member.get("id")
            if not player_id:
                continue
            position = FootballDataClient.map_position(member.get("position"))
            name = member.get("name") or f"Player {player_id}"
            player = db.session.get(Player, player_id)
            if not player:
                player = Player(
                    id=player_id,
                    name=name,
                    position=position,
                    country_id=country.id,
                    price=_estimate_price(position, member),
                    football_data_team_id=fd_team.get("id"),
                )
                db.session.add(player)
            else:
                player.name = name
                player.position = position
                player.country_id = country.id
                player.football_data_team_id = fd_team.get("id")
            synced += 1

        db.session.commit()

    return synced, "football-data.org"


PHOTO_CDN = "https://media.api-sports.io/football/players/{}.png"
THESPORTSDB_SEARCH = "https://www.thesportsdb.com/api/v1/json/3/searchplayers.php"
# Stored when SportsDB has no usable headshot (after first try / retry).
PHOTO_NONE = "-"


def _has_real_photo(url: str | None) -> bool:
    return bool(url) and url not in ("", PHOTO_NONE)


def _photo_stats() -> dict:
    with_photo = Player.query.filter(
        Player.photo_url.isnot(None),
        Player.photo_url != "",
        Player.photo_url != PHOTO_NONE,
    ).count()
    untried = Player.query.filter(Player.photo_url.is_(None)).count()
    no_match = Player.query.filter(Player.photo_url == "").count()
    exhausted = Player.query.filter(Player.photo_url == PHOTO_NONE).count()
    return {
        "with_photo": with_photo,
        "untried": untried,
        "no_match": no_match,
        "exhausted": exhausted,
    }


def _af_team_payload(entry: dict) -> dict:
    """Normalize API-Football team list entry to a team dict."""
    if not entry:
        return {}
    if entry.get("team"):
        return entry.get("team") or {}
    return entry


def _thesportsdb_search_raw(query: str) -> list:
    try:
        response = requests.get(
            THESPORTSDB_SEARCH,
            params={"p": query},
            headers={"User-Agent": "wc2026-fantasy/1.0"},
            timeout=20,
        )
        if response.status_code >= 400:
            logger.warning("TheSportsDB HTTP %s for %s", response.status_code, query)
            return []
        return (response.json() or {}).get("player") or []
    except Exception as exc:
        logger.warning("TheSportsDB lookup failed for %s: %s", query, exc)
        return []


def _pick_tsdb_photo(rows: list, player_name: str, nationality: str | None, *, strict: bool = False) -> str | None:
    nationality_l = (nationality or "").strip().lower()
    exact = []
    soft = []
    for row in rows:
        if (row.get("strSport") or "").lower() != "soccer":
            continue
        photo = row.get("strCutout") or row.get("strThumb")
        if not photo:
            continue
        row_name = (row.get("strPlayer") or "").strip()
        row_nat = (row.get("strNationality") or "").strip().lower()
        nat_ok = (not nationality_l) or (not row_nat) or nationality_l in row_nat or row_nat in nationality_l
        if _player_names_match(player_name, row_name):
            if nat_ok:
                exact.append(photo)
            else:
                soft.append(photo)
        elif nat_ok and not strict:
            soft.append(photo)
    return (exact or soft or [None])[0]


def _thesportsdb_photo(player_name: str, nationality: str | None = None) -> str | None:
    """Fetch a soccer player cutout/thumb from TheSportsDB (free, no API key)."""
    name = (player_name or "").strip()
    if not name:
        return None

    parts = name.split()
    queries = [name]
    if len(parts) >= 2:
        last = parts[-1]
        first = parts[0]
        queries.extend([
            last,
            f"{first} {last}",
            f"{first[0]} {last}",
            f"{last} {first}",
        ])

    tried = set()
    for i, query in enumerate(queries):
        key = query.lower()
        if key in tried or len(query) < 3:
            continue
        tried.add(key)
        rows = _thesportsdb_search_raw(query)
        # Last-name-only searches must match more carefully to avoid wrong faces
        strict = query.lower() == (parts[-1].lower() if parts else "")
        photo = _pick_tsdb_photo(rows, name, nationality, strict=strict)
        if photo:
            return photo
        if i < len(queries) - 1:
            time.sleep(0.12)
    return None


def ensure_player_photos(players: list, *, limit: int = 20, retry_failed: bool = False) -> int:
    """Fetch and store headshots for specific players (used by API on demand)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Resolve relationships here (app context) before handing work to threads
    todo: list[tuple[Player, str | None]] = []
    for player in players:
        if player is None:
            continue
        if _has_real_photo(player.photo_url):
            continue
        if player.photo_url == PHOTO_NONE and not retry_failed:
            continue
        if player.photo_url == "" and not retry_failed:
            continue
        nation = player.country.name if player.country else None
        todo.append((player, nation))
        if len(todo) >= limit:
            break
    if not todo:
        return 0

    def fetch_one(item: tuple[Player, str | None]):
        player, nation = item
        photo = _thesportsdb_photo(player.name, nation)
        # On demand / retry: mark exhausted if still nothing
        return player.id, photo or PHOTO_NONE

    results: dict[int, str] = {}
    workers = min(8, len(todo))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_one, item) for item in todo]
        for fut in as_completed(futures):
            try:
                pid, photo = fut.result()
                results[pid] = photo
            except Exception as exc:
                logger.warning("ensure_player_photos worker failed: %s", exc)

    updated = 0
    by_id = {p.id: p for p, _ in todo}
    for pid, photo in results.items():
        player = by_id.get(pid)
        if not player:
            continue
        player.photo_url = photo
        if _has_real_photo(photo):
            updated += 1
    db.session.commit()
    return updated


def _find_player_loose(api_player_id: int, player_name: str, country_id: int, position: str) -> Player | None:
    player = _find_player_for_api_stat(api_player_id, player_name, country_id, position)
    if player:
        return player
    needle = _normalize_player_name(player_name)
    if not needle:
        return None
    last = needle.split()[-1]
    candidates = []
    for candidate in Player.query.filter_by(country_id=country_id).all():
        cand = _normalize_player_name(candidate.name)
        if not cand:
            continue
        if cand.split()[-1] != last:
            continue
        candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0]
    by_pos = [c for c in candidates if c.position == position]
    if len(by_pos) == 1:
        return by_pos[0]
    return None


def sync_player_photos(*, force: bool = False, batch_size: int = 60, retry_failed: bool = False) -> dict:
    """Attach real player headshots.

    Prefer TheSportsDB cutouts (no key required). Also try API-Football squads when
    API_FOOTBALL_KEY is configured. Processes up to ``batch_size`` missing photos
    per call so boot/scheduler can finish gradually.

    ``photo_url is None`` = not tried yet
    ``photo_url == ""`` = first pass found nothing (eligible for one retry)
    ``photo_url == "-"`` = retry also found nothing (stop trying)
    non-empty URL = real headshot
    """
    query = Player.query
    if force:
        pass
    elif retry_failed:
        query = query.filter(Player.photo_url == "")
    else:
        query = query.filter(Player.photo_url.is_(None))
    missing_players = query.order_by(Player.id.asc()).limit(batch_size).all()
    remaining_before = query.count()

    updated = 0
    tsdb_hits = 0
    af_hits = 0

    # 1) TheSportsDB for this batch
    for player in missing_players:
        if force:
            pass
        elif retry_failed:
            if player.photo_url != "":
                continue
        elif player.photo_url is not None:
            continue

        nation = player.country.name if player.country else None
        photo = _thesportsdb_photo(player.name, nation)
        time.sleep(0.15)
        # First miss -> ""; after retry miss -> "-" so we never loop forever
        if photo:
            player.photo_url = photo
            updated += 1
            tsdb_hits += 1
        else:
            player.photo_url = PHOTO_NONE if retry_failed else ""
    db.session.commit()
    try:
        db.session.remove()
    except Exception:
        pass

    # 2) API-Football national squads (fills more + links api ids)
    af = ApiFootballClient()
    linked = 0
    teams_matched = 0
    if af.api_key:
        quota = ApiFootballClient.get_quota_usage()
        if quota["remaining"] >= 10:
            # Resolve national team per country that still needs photos
            photo_missing = (
                Player.photo_url.is_(None)
                | (Player.photo_url == "")
                | (Player.photo_url == PHOTO_NONE)
            )
            countries_q = (
                db.session.query(Country)
                .join(Player, Player.country_id == Country.id)
                .distinct()
            )
            if not force:
                countries_q = countries_q.filter(photo_missing)
            countries = countries_q.limit(20).all()
            for country in countries:
                data = af._get(
                    "teams",
                    f"af:teams:name:{_normalize_name(country.name)}",
                    86400,
                    params={"name": country.name},
                )
                if not data:
                    continue
                national = None
                for entry in data.get("response") or []:
                    team = _af_team_payload(entry)
                    if team.get("national") is True or _normalize_name(team.get("name", "")) == _normalize_name(country.name):
                        national = team
                        if team.get("national") is True:
                            break
                if not national or not national.get("id"):
                    continue
                teams_matched += 1
                if national.get("flag") and not country.flag_url:
                    country.flag_url = national.get("flag")
                squad = af.get_squad(national["id"]) or []
                for member in squad:
                    api_id = member.get("id")
                    name = member.get("name") or ""
                    if not api_id:
                        continue
                    position = ApiFootballClient.map_position(member.get("position"))
                    photo = member.get("photo") or PHOTO_CDN.format(api_id)
                    player = _find_player_loose(api_id, name, country.id, position)
                    if not player:
                        continue
                    if not player.api_football_id:
                        player.api_football_id = api_id
                        linked += 1
                    if force or not _has_real_photo(player.photo_url):
                        player.photo_url = photo
                        updated += 1
                        af_hits += 1
                db.session.commit()

    stats = _photo_stats()
    return {
        "updated": updated,
        "thesportsdb": tsdb_hits,
        "api_football": af_hits,
        "linked": linked,
        "teams_matched": teams_matched,
        "remaining_untried": stats["untried"],
        "remaining": stats["untried"],
        "no_match": stats["no_match"],
        "exhausted": stats["exhausted"],
        "with_photo": stats["with_photo"],
        "remaining_before": remaining_before,
        "batch_size": batch_size,
        "retry_failed": retry_failed,
    }


def _normalize_name(name: str) -> str:
    n = (name or "").strip().lower()
    n = re.sub(r"\s+", " ", n)
    return NAME_ALIASES.get(n, n)


def _normalize_player_name(name: str) -> str:
    n = unicodedata.normalize("NFKD", name or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^\w\s]", " ", n.lower())
    return re.sub(r"\s+", " ", n).strip()


def _player_names_match(name_a: str, name_b: str) -> bool:
    a = _normalize_player_name(name_a)
    b = _normalize_player_name(name_b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    parts_a = a.split()
    parts_b = b.split()
    if parts_a and parts_b and parts_a[-1] == parts_b[-1]:
        return parts_a[0][0] == parts_b[0][0]
    return False


def _find_player_for_api_stat(
    api_player_id: int,
    player_name: str,
    country_id: int,
    position: str,
) -> Player | None:
    """Resolve football-data Player from API-Football player id/name."""
    player = Player.query.filter_by(api_football_id=api_player_id).first()
    if player:
        return player

    player = db.session.get(Player, api_player_id)
    if player:
        if not player.api_football_id:
            player.api_football_id = api_player_id
        return player

    for candidate in Player.query.filter_by(country_id=country_id).all():
        if _player_names_match(candidate.name, player_name):
            candidate.api_football_id = api_player_id
            return candidate

    return None


def _build_api_team_side_map(fixture: Fixture, players_data: list, lineups_data: list) -> dict:
    """Map API-Football team id -> 'home' or 'away'."""
    home_name = _normalize_name(fixture.home_team.name if fixture.home_team else "")
    away_name = _normalize_name(fixture.away_team.name if fixture.away_team else "")
    side_map: dict[int, str] = {}

    for block in (lineups_data or []) + (players_data or []):
        team = block.get("team") or {}
        tid = team.get("id")
        tname = _normalize_name(team.get("name", ""))
        if not tid or tid in side_map:
            continue
        if home_name and (home_name in tname or tname in home_name):
            side_map[tid] = "home"
        elif away_name and (away_name in tname or tname in away_name):
            side_map[tid] = "away"

    return side_map


def _parse_datetime(value) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(str(value).replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _find_country_by_name(name: str) -> Country | None:
    norm = _normalize_name(name)
    for country in wc26_countries_query().all():
        if _normalize_name(country.name) == norm:
            return country
        if country.code and _normalize_name(country.code) == norm:
            return country
    for country in Country.query.all():
        if _normalize_name(country.name) == norm:
            return country
        if country.code and _normalize_name(country.code) == norm:
            return country
    return None


def _upsert_country(
    name: str,
    *,
    country_id: int = None,
    code: str = None,
    flag_url: str = None,
    football_data_id: int = None,
    worldcup26_id: str = None,
) -> Country:
    country = None
    if football_data_id:
        country = Country.query.filter_by(football_data_id=football_data_id).first()
    if not country and worldcup26_id:
        country = Country.query.filter_by(worldcup26_id=str(worldcup26_id)).first()
    if not country and country_id:
        country = db.session.get(Country, country_id)
    if not country:
        country = _find_country_by_name(name)

    if not country:
        cid = country_id or OpenFootballSeeder.stable_country_id(name)
        country = Country(id=cid, name=name)
        db.session.add(country)

    country.name = name
    if code:
        country.code = code
    if flag_url:
        country.flag_url = flag_url
    if football_data_id:
        country.football_data_id = football_data_id
    if worldcup26_id:
        country.worldcup26_id = str(worldcup26_id)
    return country


def _estimate_price(position: str, player_data: dict) -> Decimal:
    base = DEFAULT_PRICES.get(position, Decimal("5.0"))
    display_name = (player_data.get("name") or player_data.get("display_name") or "").lower()
    if any(kw in display_name for kw in ("messi", "ronaldo", "mbapp", "neymar", "haaland")):
        return Decimal("12.0")
    return base + Decimal(str(round(random.uniform(-0.5, 1.5), 1)))


def _get_or_create_fixture(
    home_team_id: int,
    away_team_id: int,
    kickoff_utc: datetime,
    *,
    fixture_id: int = None,
    football_data_id: int = None,
    worldcup26_id: str = None,
) -> Fixture | None:
    if home_team_id == away_team_id:
        logger.warning("Skipping fixture with identical home/away team ids")
        return None

    fixture = None
    if football_data_id:
        fixture = Fixture.query.filter_by(football_data_id=football_data_id).first()
    if not fixture and worldcup26_id:
        fixture = Fixture.query.filter_by(worldcup26_id=str(worldcup26_id)).first()
    if not fixture and fixture_id:
        fixture = db.session.get(Fixture, fixture_id)
    if not fixture:
        fixture = Fixture.query.filter_by(
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            kickoff_utc=kickoff_utc,
        ).first()
    if not fixture:
        new_id = fixture_id or OpenFootballSeeder.stable_fixture_id(
            str(home_team_id), str(away_team_id), kickoff_utc.date().isoformat()
        )
        if db.session.get(Fixture, new_id):
            fixture = db.session.get(Fixture, new_id)
        else:
            fixture = Fixture(
                id=new_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                kickoff_utc=kickoff_utc,
                matchday=1,
                stage="group",
                status="NS",
            )
            db.session.add(fixture)
    if worldcup26_id:
        fixture.worldcup26_id = str(worldcup26_id)
    if football_data_id:
        fixture.football_data_id = football_data_id
    return fixture


def _apply_wc26_game(
    game: dict,
    team_map: dict[str, dict],
) -> Fixture | None:
    home_id = str(game.get("home_team_id") or "")
    away_id = str(game.get("away_team_id") or "")
    home_t = team_map.get(home_id, {})
    away_t = team_map.get(away_id, {})

    home_name = game.get("home_team_name_en") or home_t.get("name_en") or home_t.get("name", "Home")
    away_name = game.get("away_team_name_en") or away_t.get("name_en") or away_t.get("name", "Away")

    home_country = _upsert_country(
        home_name,
        worldcup26_id=home_id,
        code=home_t.get("fifa_code"),
        flag_url=home_t.get("flag"),
    )
    away_country = _upsert_country(
        away_name,
        worldcup26_id=away_id,
        code=away_t.get("fifa_code"),
        flag_url=away_t.get("flag"),
    )
    db.session.flush()

    kickoff = _parse_datetime(game.get("local_date"))
    fixture = _get_or_create_fixture(
        home_country.id,
        away_country.id,
        kickoff,
        worldcup26_id=game.get("id"),
    )
    if not fixture:
        return None

    fixture.home_team_id = home_country.id
    fixture.away_team_id = away_country.id
    fixture.kickoff_utc = kickoff
    fixture.status = WorldCup26Client.map_status(game)
    try:
        fixture.matchday = int(game.get("matchday") or fixture.matchday or 1)
    except (TypeError, ValueError):
        pass
    fixture.stage = WorldCup26Client.map_stage(game.get("type"))
    raw_group = game.get("group")
    if raw_group is not None:
        fixture.group_name = str(raw_group).strip()[:32] or None
    else:
        fixture.group_name = None
    try:
        fixture.home_score = int(game["home_score"]) if game.get("home_score") not in (None, "null", "") else None
        fixture.away_score = int(game["away_score"]) if game.get("away_score") not in (None, "null", "") else None
    except (TypeError, ValueError):
        pass
    return fixture


# ── Seed (worldcup26.ir, CLI only) ──────────────────────────────────────────

def seed_database() -> dict:
    wc26 = WorldCup26Client()
    teams = wc26.get_teams()
    if not teams:
        return {"error": "Could not fetch worldcup26.ir teams"}

    team_map = _sync_wc26_countries(teams)
    wc_team_ids = set(team_map.keys())
    raw_team_map = {str(t.get("id")): t for t in teams}

    games = wc26.get_games() or []
    fixtures = 0
    for game in games:
        if not _is_valid_wc26_game(game, wc_team_ids):
            continue
        if _apply_wc26_game(game, raw_team_map):
            fixtures += 1

    db.session.commit()
    return {"countries": len(team_map), "fixtures": fixtures, "source": "worldcup26.ir"}


# ── Teams & players (worldcup26.ir teams + football-data WC squads) ─────────

def sync_countries_and_players() -> dict:
    wc26 = WorldCup26Client()
    teams = wc26.get_teams()
    if not teams:
        set_data_delayed(True)
        return {"countries": 0, "players": 0, "warning": "No team data from worldcup26.ir"}

    clear_data_delayed()
    team_map = _sync_wc26_countries(teams)
    players_synced, player_source = _sync_wc26_players_from_football_data(team_map.values())
    db.session.commit()
    update_selected_by_percentages()

    photos = sync_player_photos()
    db.session.commit()

    result = {
        "countries": len(team_map),
        "players": wc26_players_query().count(),
        "players_synced": players_synced,
        "photos": photos,
        "source": "worldcup26.ir",
    }
    if player_source:
        result["player_source"] = player_source
    elif not FootballDataClient().token:
        result["warning"] = "Set FOOTBALL_DATA_TOKEN to load WC2026 squads"
    return result


# ── Fixtures (worldcup26.ir only) ───────────────────────────────────────────

def _sync_from_worldcup26() -> int:
    wc26 = WorldCup26Client()
    games = wc26.get_games()
    teams = wc26.get_teams() or []
    if not games:
        return 0

    team_map = _sync_wc26_countries(teams)
    wc_team_ids = set(team_map.keys())
    raw_team_map = {str(t.get("id")): t for t in teams}

    synced = 0
    for game in games:
        if not _is_valid_wc26_game(game, wc_team_ids):
            continue
        if _apply_wc26_game(game, raw_team_map):
            synced += 1

    db.session.commit()
    return synced


def sync_fixtures() -> dict:
    synced = _sync_from_worldcup26()
    source = "worldcup26.ir" if synced else "cached"

    if synced:
        clear_data_delayed()
    else:
        set_data_delayed(True)
        logger.warning("worldcup26.ir fixture sync failed — serving cached DB data")

    return {"fixtures": synced, "source": source, "data_delayed": is_data_delayed()}


# ── Live scores (worldcup26.ir only) ────────────────────────────────────────

def sync_live_scores() -> dict:
    updated = 0
    wc26 = WorldCup26Client()
    games = wc26.get_games()
    source = "worldcup26.ir"
    live_games = []

    if games:
        live_games = [g for g in games if WorldCup26Client.map_status(g) in ("LIVE", "HT")]
        for g in live_games:
            fixture = Fixture.query.filter_by(worldcup26_id=str(g.get("id"))).first()
            if not fixture:
                home = g.get("home_team_name_en")
                away = g.get("away_team_name_en")
                hc = _find_country_by_name(home) if home else None
                ac = _find_country_by_name(away) if away else None
                if hc and ac:
                    fixture = Fixture.query.filter_by(
                        home_team_id=hc.id, away_team_id=ac.id
                    ).order_by(Fixture.kickoff_utc.desc()).first()
            if not fixture:
                continue
            fixture.status = WorldCup26Client.map_status(g)
            try:
                if g.get("home_score") not in (None, "null", ""):
                    fixture.home_score = int(g["home_score"])
                if g.get("away_score") not in (None, "null", ""):
                    fixture.away_score = int(g["away_score"])
            except (TypeError, ValueError):
                pass
            updated += 1
        clear_data_delayed()
    else:
        set_data_delayed(True)
        logger.warning("worldcup26.ir live sync failed — serving cached DB data")

    db.session.commit()
    stats_result = sync_live_player_stats(live_games=live_games)
    return {
        "updated": updated,
        "source": source,
        "data_delayed": is_data_delayed(),
        "player_stats": stats_result,
    }


def sync_livescores() -> dict:
    """Alias for scheduler compatibility."""
    return sync_live_scores()


# ── Player stats (api-football; live + FT, quota-protected) ───────────────────

def _int_or_zero(value) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _parse_api_football_entry_stats(entry: dict) -> dict:
    """Parse player statistics from API-Football (nested or legacy flat format)."""
    raw_stats = entry.get("statistics") or []

    if raw_stats and isinstance(raw_stats[0], dict) and "games" in raw_stats[0]:
        block = raw_stats[0]
        games = block.get("games") or {}
        shots = block.get("shots") or {}
        goals_block = block.get("goals") or {}
        passes = block.get("passes") or {}
        tackles_block = block.get("tackles") or {}
        cards = block.get("cards") or {}
        penalty = block.get("penalty") or {}
        return {
            "minutes": _int_or_zero(games.get("minutes")),
            "goals": _int_or_zero(goals_block.get("total")),
            "assists": _int_or_zero(goals_block.get("assists")),
            "saves": _int_or_zero(goals_block.get("saves")),
            "shots_on_target": _int_or_zero(shots.get("on")),
            "tackles": _int_or_zero(tackles_block.get("total")),
            "chances_created": _int_or_zero(passes.get("key")),
            "yellow_cards": _int_or_zero(cards.get("yellow")),
            "red_cards": _int_or_zero(cards.get("red")),
            "penalty_missed": _int_or_zero(penalty.get("missed")),
            "penalty_saved": _int_or_zero(penalty.get("saved")),
        }

    flat = {
        s.get("type", "").lower(): s.get("value")
        for s in raw_stats
        if isinstance(s, dict) and s.get("type")
    }
    return {
        "minutes": _int_or_zero(flat.get("minutes played") or flat.get("minutes")),
        "goals": _int_or_zero(flat.get("goals")),
        "assists": _int_or_zero(flat.get("assists")),
        "saves": _int_or_zero(flat.get("saves")),
        "shots_on_target": _int_or_zero(flat.get("shots on goal") or flat.get("shots on target")),
        "tackles": _int_or_zero(flat.get("tackles")),
        "chances_created": _int_or_zero(flat.get("key passes")),
        "yellow_cards": 0,
        "red_cards": 0,
        "penalty_missed": 0,
        "penalty_saved": 0,
    }


def _parse_api_football_stats(
    fixture: Fixture,
    players_data: list,
    events_data: list,
    lineups_data: list,
) -> list[dict]:
    home_score = fixture.home_score or 0
    away_score = fixture.away_score or 0
    side_map = _build_api_team_side_map(fixture, players_data, lineups_data)

    event_goals = {}
    event_assists = {}
    event_cards = {"yellow": set(), "red": set()}
    event_own_goals = set()
    event_pen_missed = set()

    for ev in events_data or []:
        etype = (ev.get("type") or "").lower()
        detail = (ev.get("detail") or "").lower()
        player = ev.get("player") or {}
        pid = player.get("id")
        if not pid:
            continue
        if etype == "goal":
            if "own" in detail:
                event_own_goals.add(pid)
            else:
                event_goals[pid] = event_goals.get(pid, 0) + 1
            assist = ev.get("assist") or {}
            aid = assist.get("id")
            if aid:
                event_assists[aid] = event_assists.get(aid, 0) + 1
        elif etype == "card":
            if "red" in detail:
                event_cards["red"].add(pid)
            else:
                event_cards["yellow"].add(pid)
        elif etype == "var" and "penalty" in detail and "missed" in detail:
            event_pen_missed.add(pid)

    results = []
    for team_block in players_data or []:
        team_info = team_block.get("team") or {}
        team_id = team_info.get("id")
        side = side_map.get(team_id, "home")
        country_id = fixture.home_team_id if side == "home" else fixture.away_team_id
        goals_conceded = away_score if side == "home" else home_score

        for entry in team_block.get("players") or []:
            player_info = entry.get("player") or {}
            api_pid = player_info.get("id")
            if not api_pid:
                continue

            parsed = _parse_api_football_entry_stats(entry)
            minutes = parsed["minutes"]

            goals = int(event_goals.get(api_pid, parsed["goals"]))
            assists = int(event_assists.get(api_pid, parsed["assists"]))
            saves = parsed["saves"]
            shots_on_target = parsed["shots_on_target"]
            tackles = parsed["tackles"]
            yellow = max(parsed["yellow_cards"], 1 if api_pid in event_cards["yellow"] else 0)
            red = max(parsed["red_cards"], 1 if api_pid in event_cards["red"] else 0)
            own_goals = 1 if api_pid in event_own_goals else 0
            pen_missed = max(parsed["penalty_missed"], 1 if api_pid in event_pen_missed else 0)
            pen_saved = parsed["penalty_saved"]

            if minutes == 0 and (goals > 0 or assists > 0 or saves > 0 or yellow or red):
                minutes = 1

            pos_raw = player_info.get("pos") or player_info.get("position") or "MID"
            position = ApiFootballClient.map_position(pos_raw)

            clean_sheet = minutes >= 60 and goals_conceded == 0 and position in ("GK", "DEF", "MID")

            results.append({
                "api_player_id": api_pid,
                "player_name": player_info.get("name") or f"Player {api_pid}",
                "position": position,
                "country_id": country_id,
                "minutes_played": minutes,
                "goals": goals,
                "assists": assists,
                "clean_sheet": clean_sheet,
                "saves": saves,
                "yellow_cards": yellow,
                "red_cards": red,
                "own_goals": own_goals,
                "penalty_saved": pen_saved,
                "penalty_missed": pen_missed,
                "shots_on_target": shots_on_target,
                "chances_created": parsed["chances_created"],
                "tackles": tackles,
                "goals_conceded": goals_conceded if minutes >= 60 and position in ("GK", "DEF") else 0,
                "goals_outside_box": 0,
                "is_potm": False,
            })

    return results


def _apply_fixture_stats(fixture_id: int, stats_list: list[dict]) -> int:
    synced = 0
    for stat_data in stats_list:
        country = db.session.get(Country, stat_data["country_id"])
        if not country or not country.worldcup26_id:
            continue

        player = _find_player_for_api_stat(
            stat_data["api_player_id"],
            stat_data["player_name"],
            stat_data["country_id"],
            stat_data["position"],
        )
        if not player:
            continue

        stat = PlayerMatchStat.query.filter_by(
            player_id=player.id, fixture_id=fixture_id
        ).first()
        if not stat:
            stat = PlayerMatchStat(player_id=player.id, fixture_id=fixture_id)
            db.session.add(stat)

        for field in (
            "minutes_played", "goals", "assists", "saves", "yellow_cards",
            "red_cards", "own_goals", "penalty_saved", "penalty_missed",
            "shots_on_target", "chances_created", "tackles", "goals_conceded",
            "goals_outside_box",
        ):
            setattr(stat, field, stat_data.get(field, 0))
        stat.clean_sheet = stat_data.get("clean_sheet", False)
        stat.is_potm = stat_data.get("is_potm", False)
        synced += 1

    return synced


def _resolve_api_fixture_id(fixture: Fixture, af: ApiFootballClient) -> int | None:
    api_fixture_id = fixture.api_football_id
    if api_fixture_id:
        return api_fixture_id

    home_name = fixture.home_team.name if fixture.home_team else ""
    away_name = fixture.away_team.name if fixture.away_team else ""
    match_date = fixture.kickoff_utc.strftime("%Y-%m-%d")
    api_fixture_id = af.find_fixture_id(home_name, away_name, match_date)
    if api_fixture_id:
        fixture.api_football_id = api_fixture_id
        db.session.commit()
    return api_fixture_id


def sync_player_stats(fixture_id: int, *, allow_live: bool = False) -> dict:
    fixture = db.session.get(Fixture, fixture_id)
    if not fixture:
        return {"error": "Fixture not found"}
    if not fixture.worldcup26_id:
        return {"skipped": True, "reason": "not_wc26_fixture"}
    if fixture.stats_synced and fixture.status == "FT":
        return {"skipped": True, "reason": "already synced"}

    is_live = fixture.status in LIVE_STATUSES
    if fixture.status != "FT" and not allow_live:
        return {"skipped": True, "reason": "not finished"}
    if is_live and not allow_live:
        return {"skipped": True, "reason": "live_not_allowed"}

    af = ApiFootballClient()
    quota = ApiFootballClient.get_quota_usage()
    if quota["remaining"] <= 0:
        logger.warning("API-Football quota exhausted — skipping stats for fixture %s", fixture_id)
        return {"skipped": True, "reason": "quota_exhausted", "quota": quota}

    api_fixture_id = _resolve_api_fixture_id(fixture, af)
    if not api_fixture_id:
        logger.warning("Could not resolve api-football fixture id for %s", fixture_id)
        return {"skipped": True, "reason": "no_api_fixture_id"}

    use_live_cache = is_live
    players_data = af.get_fixture_players(api_fixture_id, live=use_live_cache)
    events_data = af.get_fixture_events(api_fixture_id, live=use_live_cache)
    lineups_data = af.get_fixture_lineups(api_fixture_id, live=use_live_cache) if not is_live else []

    if not players_data:
        logger.warning("No player stats from api-football for fixture %s", fixture_id)
        return {"skipped": True, "reason": "no_data"}

    stats_list = _parse_api_football_stats(
        fixture, players_data or [], events_data or [], lineups_data or []
    )
    synced = _apply_fixture_stats(fixture_id, stats_list)

    if fixture.status == "FT":
        fixture.stats_synced = True
    db.session.commit()

    from app.fantasy.scoring import recalculate_fixture_points
    recalculate_fixture_points(fixture_id)

    return {
        "stats": synced,
        "fixture_id": fixture_id,
        "live": is_live,
        "quota": ApiFootballClient.get_quota_usage(),
    }


# ── Live player stats (worldcup26.ir scorers + api-football when available) ─

SCORER_ENTRY_RE = re.compile(r"^(.+?)\s+(\d+)['\u2019]?\s*$")


def _parse_wc26_scorers(scorers_raw) -> list[tuple[str, int]]:
    """Parse worldcup26.ir scorer strings like {\"Cristiano Ronaldo 6'\",\"Player 17'\"}."""
    if not scorers_raw or str(scorers_raw).lower() in ("null", "none", ""):
        return []

    text = str(scorers_raw).strip()
    if text.startswith("{"):
        text = text[1:-1]
    text = text.replace('\\"', '"')
    parts = re.split(r'","|",\s*"', text)

    results = []
    for part in parts:
        part = part.strip().strip('"').strip()
        if not part:
            continue
        match = SCORER_ENTRY_RE.match(part)
        if match:
            results.append((match.group(1).strip(), int(match.group(2))))
        else:
            results.append((part, 0))
    return results


def _parse_wc26_elapsed_minutes(game: dict) -> int:
    elapsed = str(game.get("time_elapsed") or "").lower().strip()
    if not elapsed or elapsed in ("null", "live", "0"):
        return 0
    if "half" in elapsed or elapsed == "ht":
        return 45
    if elapsed == "finished":
        return 90
    digits = re.sub(r"[^\d]", "", elapsed)
    return int(digits) if digits else 0


def _find_player_by_name_in_country(player_name: str, country_id: int) -> Player | None:
    for candidate in Player.query.filter_by(country_id=country_id).all():
        if _player_names_match(candidate.name, player_name):
            return candidate
    return None


def _find_fixture_for_wc26_game(game: dict) -> Fixture | None:
    fixture = Fixture.query.filter_by(worldcup26_id=str(game.get("id"))).first()
    if fixture:
        return fixture

    home = game.get("home_team_name_en") or game.get("home_team_name")
    away = game.get("away_team_name_en") or game.get("away_team_name")
    hc = _find_country_by_name(home) if home else None
    ac = _find_country_by_name(away) if away else None
    if hc and ac:
        return Fixture.query.filter_by(
            home_team_id=hc.id, away_team_id=ac.id
        ).order_by(Fixture.kickoff_utc.desc()).first()
    return None


def _estimate_live_minutes(goal_minutes: list[int], game_minute: int) -> int:
    if game_minute > 0:
        return game_minute
    return max(goal_minutes) if goal_minutes else 0


def _sync_live_stats_from_worldcup26(fixture: Fixture, game: dict) -> dict:
    """Update goals/minutes from worldcup26.ir live scorer data."""
    all_goal_minutes: list[int] = []
    player_goals: dict[tuple[str, int], list[int]] = {}

    for key, country_id in (
        ("home_scorers", fixture.home_team_id),
        ("away_scorers", fixture.away_team_id),
    ):
        for name, minute in _parse_wc26_scorers(game.get(key)):
            all_goal_minutes.append(minute)
            player_goals.setdefault((name, country_id), []).append(minute)

    game_minute = _parse_wc26_elapsed_minutes(game)
    if not game_minute and all_goal_minutes:
        game_minute = max(all_goal_minutes)

    synced = 0
    for (raw_name, country_id), goal_mins in player_goals.items():
        player = _find_player_by_name_in_country(raw_name, country_id)
        if not player:
            continue

        stat = PlayerMatchStat.query.filter_by(
            player_id=player.id, fixture_id=fixture.id
        ).first()
        if not stat:
            stat = PlayerMatchStat(player_id=player.id, fixture_id=fixture.id)
            db.session.add(stat)

        stat.goals = len(goal_mins)
        stat.minutes_played = max(
            stat.minutes_played or 0,
            _estimate_live_minutes(goal_mins, game_minute),
        )
        synced += 1

    if synced:
        db.session.commit()
        from app.fantasy.scoring import recalculate_fixture_points
        recalculate_fixture_points(fixture.id)

    return {"stats": synced, "fixture_id": fixture.id, "source": "worldcup26.ir"}


def _sync_live_stats_from_api_football(fixture: Fixture) -> dict:
    return sync_player_stats(fixture.id, allow_live=True)


def sync_live_player_stats(live_games: list[dict] | None = None) -> dict:
    """Fetch and score player stats for all in-progress WC fixtures."""
    if live_games is None:
        games = WorldCup26Client().get_games() or []
        live_games = [
            g for g in games
            if WorldCup26Client.map_status(g) in ("LIVE", "HT")
        ]

    if not live_games:
        return {"processed": 0, "results": []}

    results = []
    quota = ApiFootballClient.get_quota_usage()
    use_api = quota["remaining"] > 5 and ApiFootballClient().api_key

    for game in live_games:
        fixture = _find_fixture_for_wc26_game(game)
        if not fixture:
            continue
        try:
            if use_api:
                api_result = sync_player_stats(fixture.id, allow_live=True)
                results.append(api_result)
                if api_result.get("stats", 0) > 0:
                    if api_result.get("skipped") and api_result.get("reason") == "quota_exhausted":
                        use_api = False
                    continue
                if api_result.get("skipped") and api_result.get("reason") == "quota_exhausted":
                    use_api = False

            result = _sync_live_stats_from_worldcup26(fixture, game)
            results.append(result)
        except Exception as exc:
            logger.error("Failed live stats sync for fixture %s: %s", fixture.id, exc)
            results.append({"fixture_id": fixture.id, "error": str(exc)})

    return {"processed": len(results), "results": results}


def sync_fixture_stats(fixture_id: int, *, allow_live: bool = False) -> dict:
    """Alias for admin routes."""
    return sync_player_stats(fixture_id, allow_live=allow_live)


def sync_finished_stats() -> dict:
    finished = wc26_fixtures_query().filter(
        Fixture.status == "FT",
        Fixture.stats_synced.is_(False),
    ).all()

    results = []
    for fixture in finished:
        try:
            result = sync_player_stats(fixture.id)
            results.append(result)
            if result.get("skipped") and result.get("reason") == "quota_exhausted":
                break
        except Exception as exc:
            logger.error("Failed to sync fixture %s: %s", fixture.id, exc)
            results.append({"fixture_id": fixture.id, "error": str(exc)})

    return {"processed": len(results), "results": results}


def update_selected_by_percentages():
    from app.models import FantasyTeam, FantasyTeamPlayer

    latest_md = db.session.query(db.func.max(FantasyTeam.matchday)).scalar() or 1
    total_teams = FantasyTeam.query.filter_by(matchday=latest_md).count() or 1

    player_counts = db.session.query(
        FantasyTeamPlayer.player_id,
        db.func.count(FantasyTeamPlayer.id),
    ).join(FantasyTeam).filter(
        FantasyTeam.matchday == latest_md
    ).group_by(FantasyTeamPlayer.player_id).all()

    count_map = {pid: cnt for pid, cnt in player_counts}
    for player in wc26_players_query().all():
        cnt = count_map.get(player.id, 0)
        player.selected_by_pct = Decimal(str(round((cnt / total_teams) * 100, 2)))
    db.session.commit()


def get_current_matchday() -> int:
    now = datetime.now(timezone.utc)
    upcoming = (
        wc26_fixtures_query()
        .filter(Fixture.kickoff_utc > now)
        .order_by(Fixture.kickoff_utc)
        .first()
    )
    if upcoming:
        return upcoming.matchday
    last = wc26_fixtures_query().order_by(Fixture.matchday.desc(), Fixture.kickoff_utc.desc()).first()
    return last.matchday if last else 1


def is_matchday_live(matchday: int = None) -> bool:
    matchday = matchday or get_current_matchday()
    live_statuses = ["LIVE", "HT", "1H", "2H", "ET"]
    return wc26_fixtures_query().filter(
        Fixture.matchday == matchday,
        Fixture.status.in_(live_statuses),
    ).first() is not None
