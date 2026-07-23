from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import asc, desc, func

from app import db
from app.data.cache_utils import is_data_delayed
from app.data.sync import (
    get_current_matchday,
    is_matchday_live,
    seed_database,
    sync_countries_and_players,
    sync_fixture_stats,
    sync_fixtures,
    sync_live_player_stats,
    sync_live_scores,
    wc26_countries_query,
    wc26_fixtures_query,
    wc26_players_query,
)
from app.data.api_football import ApiFootballClient
from app.fantasy.boosters import BoosterError, activate_booster, get_booster_status
from app.fantasy.scoring import recalculate_matchday
from app.fantasy.transfers import (
    TransferError,
    get_or_create_team,
    get_transfer_budget_info,
    live_substitute,
    make_transfer,
    save_team,
)
from app.models import (
    Country,
    FantasyTeam,
    FantasyTeamPlayer,
    Fixture,
    Player,
    PlayerMatchStat,
    Transfer,
    User,
)

fantasy_bp = Blueprint("fantasy", __name__)


def _success(data=None, status=200):
    payload = {"success": True, "data_delayed": is_data_delayed()}
    if data:
        payload.update(data)
    return jsonify(payload), status


def _with_meta(data=None, status=200):
    return _success(data, status)


@fantasy_bp.route("/api/meta", methods=["GET"])
def api_meta():
    return _with_meta({
        "matchday": get_current_matchday(),
        "is_live": is_matchday_live(),
        "api_football_quota": ApiFootballClient.get_quota_usage(),
    })


def _error(code, message, details=None, status=400):
    payload = {"success": False, "error": code, "message": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status


def _admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        return _error("FORBIDDEN", "Admin access required", status=403)
    return None


# ── Players ──────────────────────────────────────────────────────────────────

@fantasy_bp.route("/api/players", methods=["GET"])
def list_players():
    position = request.args.get("position")
    country_id = request.args.get("country", type=int)
    max_price = request.args.get("max_price", type=float)
    sort_by = request.args.get("sort_by", "total_pts")
    matchday = request.args.get("matchday", type=int) or get_current_matchday()

    query = wc26_players_query()

    if position:
        query = query.filter(Player.position == position.upper())
    if country_id:
        query = query.filter(Player.country_id == country_id)
    if max_price is not None:
        query = query.filter(Player.price <= Decimal(str(max_price)))

    players = query.all()

    # Lazily backfill a handful of missing headshots on each browse
    try:
        from app.data.sync import ensure_player_photos
        ensure_player_photos([p for p in players if p.photo_url is None], limit=12)
    except Exception:
        current_app.logger.exception("ensure_player_photos failed for player list")

    fixture_ids = [
        f.id for f in wc26_fixtures_query().filter_by(matchday=matchday).all()
    ]

    results = []
    for player in players:
        if fixture_ids:
            this_md_pts = db.session.query(func.sum(PlayerMatchStat.fantasy_points)).filter(
                PlayerMatchStat.player_id == player.id,
                PlayerMatchStat.fixture_id.in_(fixture_ids),
            ).scalar() or 0
        else:
            this_md_pts = 0

        form_matchdays = _get_form_points(player.id, 3)
        form_avg = sum(form_matchdays) / len(form_matchdays) if form_matchdays else 0

        scouting_eligible = float(player.selected_by_pct) < current_app.config.get(
            "SCOUTING_BONUS_OWNERSHIP_PCT", 5.0
        )

        extra = {
            "total_pts": player.total_fantasy_points,
            "this_matchday_pts": int(this_md_pts),
            "form": form_matchdays,
            "form_avg": round(form_avg, 1),
            "scouting_bonus_eligible": scouting_eligible,
        }
        results.append(player.to_dict(extra))

    sort_key = {
        "pts": "total_pts",
        "total_pts": "total_pts",
        "price": "price",
        "name": "name",
        "form_avg": "form_avg",
        "selected_by_pct": "selected_by_pct",
        "this_matchday_pts": "this_matchday_pts",
    }.get(sort_by, "total_pts")

    reverse = sort_key not in ("name", "price")
    if sort_key == "name":
        results.sort(key=lambda x: x["name"].lower())
    else:
        results.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)

    return _success({"players": results, "matchday": matchday})


@fantasy_bp.route("/api/photos/sync", methods=["POST"])
def sync_photos_now():
    """Kick a photo backfill batch (used after deploy / debugging)."""
    from app.data.sync import ensure_player_photos, sync_player_photos

    batch = sync_player_photos(batch_size=30)
    raw_ids = (request.get_json(silent=True) or {}).get("player_ids") or []
    ensured = 0
    if raw_ids:
        players = Player.query.filter(Player.id.in_(raw_ids)).all()
        ensured = ensure_player_photos(players, limit=len(players))
    missing = Player.query.filter(
        (Player.photo_url.is_(None)) | (Player.photo_url == "") | (Player.photo_url == "-")
    ).count()
    with_photo = Player.query.filter(
        Player.photo_url.isnot(None),
        Player.photo_url != "",
        Player.photo_url != "-",
    ).count()
    return _success({
        "batch": batch,
        "ensured": ensured,
        "with_photo": with_photo,
        "missing": missing,
    })


def _get_form_points(player_id: int, n: int) -> list[int]:
    stats = (
        db.session.query(
            Fixture.matchday,
            func.sum(PlayerMatchStat.fantasy_points).label("pts"),
        )
        .join(Fixture, PlayerMatchStat.fixture_id == Fixture.id)
        .filter(PlayerMatchStat.player_id == player_id)
        .group_by(Fixture.matchday)
        .order_by(Fixture.matchday.desc())
        .limit(n)
        .all()
    )
    return [int(s.pts) for s in reversed(stats)]


@fantasy_bp.route("/api/players/<int:player_id>", methods=["GET"])
def get_player(player_id):
    player = db.session.get(Player, player_id)
    if not player:
        return _error("NOT_FOUND", "Player not found", status=404)
    return _success({"player": player.to_dict()})


@fantasy_bp.route("/api/players/<int:player_id>/history", methods=["GET"])
def player_history(player_id):
    player = db.session.get(Player, player_id)
    if not player:
        return _error("NOT_FOUND", "Player not found", status=404)

    stats = (
        PlayerMatchStat.query.filter_by(player_id=player_id)
        .join(Fixture)
        .order_by(Fixture.matchday.asc())
        .all()
    )
    history = []
    for stat in stats:
        history.append({
            "matchday": stat.fixture.matchday if stat.fixture else None,
            "fixture": stat.fixture.to_dict() if stat.fixture else None,
            "stats": stat.to_dict(),
        })
    return _success({"player": player.to_dict(), "history": history})


# ── Squad Management ───────────────────────────────────────────────────────

@fantasy_bp.route("/api/team", methods=["GET"])
@login_required
def get_team():
    matchday = request.args.get("matchday", type=int) or get_current_matchday()
    team = get_or_create_team(current_user, matchday)
    # Pull headshots for this squad immediately so the pitch isn't initials-only
    try:
        from app.data.sync import ensure_player_photos
        roster = [ftp.player for ftp in team.squad_players if ftp.player]
        ensure_player_photos(roster, limit=15, retry_failed=True)
        db.session.refresh(team)
    except Exception:
        current_app.logger.exception("ensure_player_photos failed for team")
    return _success({"team": team.to_dict(), "matchday": matchday})


@fantasy_bp.route("/api/team/save", methods=["POST"])
@login_required
def save_team_route():
    data = request.get_json(silent=True) or {}
    squad = data.get("squad", [])
    captain_id = data.get("captain_id")
    vice_captain_id = data.get("vice_captain_id")
    matchday = data.get("matchday") or get_current_matchday()

    starter_ids = {s["player_id"] for s in squad if s.get("is_starting")}
    if captain_id not in starter_ids:
        return _error("INVALID_CAPTAIN", "Captain must be in starting XI")
    if vice_captain_id not in starter_ids:
        return _error("INVALID_VICE_CAPTAIN", "Vice-captain must be in starting XI")

    try:
        team = save_team(current_user, squad, captain_id, vice_captain_id, matchday)
        from app.data.sync import update_selected_by_percentages
        update_selected_by_percentages()
        return _success({"team": team.to_dict()})
    except TransferError as exc:
        return _error(exc.code, exc.message, exc.details)


@fantasy_bp.route("/api/team/captain", methods=["PUT"])
@login_required
def set_captain():
    data = request.get_json(silent=True) or {}
    matchday = data.get("matchday") or get_current_matchday()
    team = get_or_create_team(current_user, matchday)

    captain_id = data.get("captain_id")
    vice_captain_id = data.get("vice_captain_id")

    starter_ids = {ftp.player_id for ftp in team.squad_players if ftp.is_starting}
    if captain_id and captain_id not in starter_ids:
        return _error("INVALID_CAPTAIN", "Captain must be in starting XI")
    if vice_captain_id and vice_captain_id not in starter_ids:
        return _error("INVALID_VICE_CAPTAIN", "Vice-captain must be in starting XI")

    if captain_id:
        team.captain_id = captain_id
    if vice_captain_id:
        team.vice_captain_id = vice_captain_id

    if is_matchday_live(matchday):
        current_user.manual_changes_matchday = matchday

    db.session.commit()
    return _success({"team": team.to_dict()})


@fantasy_bp.route("/api/team/substitute", methods=["POST"])
@login_required
def substitute():
    data = request.get_json(silent=True) or {}
    try:
        team = live_substitute(
            current_user,
            data.get("player_out_id"),
            data.get("player_in_id"),
            data.get("matchday"),
        )
        return _success({"team": team.to_dict()})
    except TransferError as exc:
        return _error(exc.code, exc.message, exc.details)


@fantasy_bp.route("/api/team/points", methods=["GET"])
@login_required
def team_points():
    matchday = request.args.get("matchday", type=int)
    query = FantasyTeam.query.filter_by(user_id=current_user.id)
    if matchday:
        query = query.filter_by(matchday=matchday)
    teams = query.order_by(FantasyTeam.matchday.asc()).all()

    breakdown = []
    for team in teams:
        players_pts = []
        for ftp in team.squad_players:
            players_pts.append({
                "player": ftp.player.to_dict() if ftp.player else None,
                "matchday_points": ftp.matchday_points,
                "multiplier": ftp.multiplier,
                "is_starting": ftp.is_starting,
            })
        breakdown.append({
            "matchday": team.matchday,
            "total_points": team.matchday_points,
            "players": players_pts,
        })
    return _success({"breakdown": breakdown})


# ── Transfers ──────────────────────────────────────────────────────────────

@fantasy_bp.route("/api/transfers", methods=["GET"])
@login_required
def list_transfers():
    transfers = Transfer.query.filter_by(user_id=current_user.id).order_by(
        Transfer.timestamp.desc()
    ).all()
    return _success({"transfers": [t.to_dict() for t in transfers]})


@fantasy_bp.route("/api/transfers", methods=["POST"])
@login_required
def create_transfer():
    data = request.get_json(silent=True) or {}
    try:
        transfer = make_transfer(
            current_user,
            data.get("player_out_id"),
            data.get("player_in_id"),
            data.get("matchday"),
        )
        return _success({"transfer": transfer.to_dict()})
    except TransferError as exc:
        return _error(exc.code, exc.message, exc.details)


@fantasy_bp.route("/api/transfers/budget", methods=["GET"])
@login_required
def transfer_budget():
    matchday = request.args.get("matchday", type=int)
    info = get_transfer_budget_info(current_user, matchday)
    return _success(info)


# ── Boosters ───────────────────────────────────────────────────────────────

@fantasy_bp.route("/api/boosters", methods=["GET"])
@login_required
def boosters_status():
    return _success({"boosters": get_booster_status(current_user.id)})


@fantasy_bp.route("/api/boosters/activate", methods=["POST"])
@login_required
def activate_booster_route():
    data = request.get_json(silent=True) or {}
    try:
        usage = activate_booster(
            current_user.id,
            data.get("type"),
            data.get("matchday"),
            data.get("extra_data"),
        )
        return _success({"booster": usage.to_dict()})
    except BoosterError as exc:
        return _error(exc.code, exc.message, exc.details)


# ── Fixtures & Live ────────────────────────────────────────────────────────

@fantasy_bp.route("/api/fixtures", methods=["GET"])
def list_fixtures():
    matchday = request.args.get("matchday", type=int)
    stage = request.args.get("stage")

    query = wc26_fixtures_query()
    if matchday:
        query = query.filter_by(matchday=matchday)
    if stage:
        query = query.filter_by(stage=stage)

    fixtures = query.order_by(Fixture.kickoff_utc.asc()).all()
    return _success({"fixtures": [f.to_dict() for f in fixtures]})


@fantasy_bp.route("/api/fixtures/<int:fixture_id>/live", methods=["GET"])
def fixture_live(fixture_id):
    fixture = db.session.get(Fixture, fixture_id)
    if not fixture:
        return _error("NOT_FOUND", "Fixture not found", status=404)

    stats = PlayerMatchStat.query.filter_by(fixture_id=fixture_id).all()
    return _success({
        "fixture": fixture.to_dict(),
        "player_stats": [s.to_dict() for s in stats],
    })


@fantasy_bp.route("/api/live/points", methods=["GET"])
@login_required
def live_points():
    matchday = request.args.get("matchday", type=int) or get_current_matchday()
    live = is_matchday_live(matchday)

    if live:
        sync_live_player_stats()

    team = get_or_create_team(current_user, matchday)

    from app.fantasy.scoring import apply_team_points
    apply_team_points(team, matchday)
    db.session.commit()

    fixture_ids = [f.id for f in Fixture.query.filter_by(matchday=matchday).all()]

    players = []
    for ftp in team.squad_players:
        stat = PlayerMatchStat.query.filter(
            PlayerMatchStat.player_id == ftp.player_id,
            PlayerMatchStat.fixture_id.in_(fixture_ids),
        ).first() if fixture_ids else None
        players.append({
            "player_id": ftp.player_id,
            "name": ftp.player.name if ftp.player else None,
            "matchday_points": ftp.matchday_points,
            "multiplier": ftp.multiplier,
            "is_starting": ftp.is_starting,
            "position": ftp.player.position if ftp.player else None,
            "minutes_played": stat.minutes_played if stat else 0,
            "goals": stat.goals if stat else 0,
            "assists": stat.assists if stat else 0,
        })

    return _success({
        "matchday": matchday,
        "total_points": team.matchday_points,
        "players": players,
        "is_live": live,
    })


# ── Leaderboards ───────────────────────────────────────────────────────────

@fantasy_bp.route("/api/leaderboard/overall", methods=["GET"])
def leaderboard_overall():
    page = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 50, type=int), 100)
    offset = (page - 1) * limit

    total = User.query.count()
    users = (
        User.query.order_by(desc(User.total_points), asc(User.id))
        .offset(offset).limit(limit).all()
    )

    return _success({
        "leaderboard": [
            {
                "rank": u.overall_rank,
                "user_id": u.id,
                "username": u.username,
                "total_points": u.total_points,
                "supported_nation": u.supported_nation.to_dict() if u.supported_nation else None,
            }
            for u in users
        ],
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit,
    })


@fantasy_bp.route("/api/leaderboard/country/<int:country_id>", methods=["GET"])
def leaderboard_country(country_id):
    users = (
        User.query.filter_by(supported_nation_id=country_id)
        .order_by(desc(User.total_points), asc(User.id))
        .all()
    )
    country = db.session.get(Country, country_id)
    return _success({
        "country": country.to_dict() if country else None,
        "leaderboard": [
            {
                "rank": u.country_rank,
                "user_id": u.id,
                "username": u.username,
                "total_points": u.total_points,
            }
            for u in users
        ],
    })


@fantasy_bp.route("/api/leaderboard/matchday/<int:matchday>", methods=["GET"])
def leaderboard_matchday(matchday):
    teams = (
        FantasyTeam.query.filter_by(matchday=matchday)
        .join(User)
        .order_by(desc(FantasyTeam.matchday_points), asc(User.id))
        .all()
    )
    return _success({
        "matchday": matchday,
        "leaderboard": [
            {
                "rank": i + 1,
                "user_id": t.user_id,
                "username": t.user.username if t.user else None,
                "matchday_points": t.matchday_points,
            }
            for i, t in enumerate(teams)
        ],
    })


@fantasy_bp.route("/api/countries", methods=["GET"])
def list_countries():
    countries = wc26_countries_query().order_by(Country.name.asc()).all()
    return _success({"countries": [c.to_dict() for c in countries]})


# ── Admin / Sync ───────────────────────────────────────────────────────────

@fantasy_bp.route("/api/admin/players/missing-photos", methods=["GET"])
@login_required
def admin_missing_photos():
    """List players that still need a headshot (for manual URI filling)."""
    err = _admin_required()
    if err:
        return err
    limit = request.args.get("limit", 200, type=int)
    players = (
        Player.query.filter(
            (Player.photo_url.is_(None))
            | (Player.photo_url == "")
            | (Player.photo_url == "-")
        )
        .order_by(Player.name.asc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    return _success({
        "count": len(players),
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "position": p.position,
                "country": p.country.name if p.country else None,
                "photo_url": None,
            }
            for p in players
        ],
    })


@fantasy_bp.route("/api/admin/players/<int:player_id>/photo", methods=["PUT"])
@login_required
def admin_set_player_photo(player_id):
    """Set a manual photo URL for one player.

    Body: { "photo_url": "https://..." }  (empty string clears / marks none)
    """
    err = _admin_required()
    if err:
        return err
    player = db.session.get(Player, player_id)
    if not player:
        return _error("NOT_FOUND", "Player not found", status=404)
    data = request.get_json(silent=True) or {}
    url = data.get("photo_url")
    if url is None:
        return _error("VALIDATION_ERROR", "photo_url is required")
    url = str(url).strip()
    player.photo_url = url or "-"
    db.session.commit()
    return _success({"player": player.to_dict()})


@fantasy_bp.route("/api/admin/players/photos", methods=["POST"])
@login_required
def admin_bulk_set_photos():
    """Bulk-set manual photo URLs.

    Body: {
      "photos": [
        { "player_id": 123, "photo_url": "https://..." },
        { "name": "Fernando Muslera", "photo_url": "https://..." }
      ]
    }
    """
    err = _admin_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    rows = data.get("photos") or []
    if not isinstance(rows, list) or not rows:
        return _error("VALIDATION_ERROR", "photos must be a non-empty list")

    updated = 0
    skipped = []
    for row in rows:
        if not isinstance(row, dict):
            skipped.append({"row": row, "reason": "invalid row"})
            continue
        url = str(row.get("photo_url") or "").strip()
        if not url:
            skipped.append({"row": row, "reason": "missing photo_url"})
            continue

        player = None
        pid = row.get("player_id")
        if pid is not None:
            player = db.session.get(Player, int(pid))
        elif row.get("name"):
            name = str(row["name"]).strip()
            matches = Player.query.filter(Player.name.ilike(name)).all()
            if len(matches) == 1:
                player = matches[0]
            elif len(matches) > 1:
                skipped.append({"row": row, "reason": f"ambiguous name ({len(matches)} matches)"})
                continue
        if not player:
            skipped.append({"row": row, "reason": "player not found"})
            continue

        player.photo_url = url
        updated += 1

    db.session.commit()
    return _success({"updated": updated, "skipped": skipped})


@fantasy_bp.route("/api/admin/players/photos/apply-manual", methods=["POST"])
@login_required
def admin_apply_manual_photos():
    """Re-apply ``app/data/player_photos.py`` overrides into the DB."""
    err = _admin_required()
    if err:
        return err
    from app.data.player_photos import apply_manual_player_photos
    only_missing = bool((request.get_json(silent=True) or {}).get("only_missing"))
    return _success(apply_manual_player_photos(only_missing=only_missing))


@fantasy_bp.route("/api/admin/sync/players", methods=["POST"])
@login_required
def admin_sync_players():
    err = _admin_required()
    if err:
        return err
    result = sync_countries_and_players()
    return _success(result)


@fantasy_bp.route("/api/admin/sync/fixtures", methods=["POST"])
@login_required
def admin_sync_fixtures():
    err = _admin_required()
    if err:
        return err
    result = sync_fixtures()
    return _success(result)


@fantasy_bp.route("/api/admin/sync/livescores", methods=["POST"])
@login_required
def admin_sync_livescores():
    err = _admin_required()
    if err:
        return err
    result = sync_live_scores()
    return _success(result)


@fantasy_bp.route("/api/admin/seed-db", methods=["POST"])
@login_required
def admin_seed_db():
    err = _admin_required()
    if err:
        return err
    result = seed_database()
    return _success(result)


@fantasy_bp.route("/api/admin/sync/stats/<int:fixture_id>", methods=["POST"])
@login_required
def admin_sync_stats(fixture_id):
    err = _admin_required()
    if err:
        return err
    allow_live = request.args.get("live", "false").lower() in ("1", "true", "yes")
    result = sync_fixture_stats(fixture_id, allow_live=allow_live)
    return _success(result)


@fantasy_bp.route("/api/admin/recalculate/<int:matchday>", methods=["POST"])
@login_required
def admin_recalculate(matchday):
    err = _admin_required()
    if err:
        return err
    result = recalculate_matchday(matchday)
    return _success(result)
