import secrets
import string

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import desc

from app import db
from app.models import MiniLeague, MiniLeagueStanding, User

leagues_bp = Blueprint("leagues", __name__)


def _success(data=None, status=200):
    payload = {"success": True}
    if data:
        payload.update(data)
    return jsonify(payload), status


def _error(code, message, status=400):
    return jsonify({"success": False, "error": code, "message": message}), status


def _generate_code(length=6) -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(chars) for _ in range(length))
        if not MiniLeague.query.filter_by(code=code).first():
            return code


def _update_league_standings(league_id: int, matchday: int = None):
    standings = MiniLeagueStanding.query.filter_by(league_id=league_id).all()
    for standing in standings:
        user = db.session.get(User, standing.user_id)
        if matchday:
            from app.models import FantasyTeam
            team = FantasyTeam.query.filter_by(user_id=user.id, matchday=matchday).first()
            standing.points = team.matchday_points if team else 0
        else:
            standing.points = user.total_points if user else 0
        standing.last_week_rank = standing.rank

    standings.sort(key=lambda s: (-s.points, s.user_id))
    for rank, standing in enumerate(standings, start=1):
        standing.rank = rank
    db.session.commit()


@leagues_bp.route("/api/leagues", methods=["GET"])
@login_required
def list_leagues():
    memberships = MiniLeagueStanding.query.filter_by(user_id=current_user.id).all()
    league_ids = [m.league_id for m in memberships]
    public_leagues = MiniLeague.query.filter_by(is_public=True).all()

    all_league_ids = set(league_ids) | {l.id for l in public_leagues}
    leagues = MiniLeague.query.filter(MiniLeague.id.in_(all_league_ids)).all() if all_league_ids else []

    result = []
    for league in leagues:
        member_count = MiniLeagueStanding.query.filter_by(league_id=league.id).count()
        standing = MiniLeagueStanding.query.filter_by(
            league_id=league.id, user_id=current_user.id
        ).first()
        result.append({
            **league.to_dict(),
            "member_count": member_count,
            "my_rank": standing.rank if standing else None,
            "my_points": standing.points if standing else None,
            "is_member": standing is not None,
        })

    return _success({"leagues": result})


@leagues_bp.route("/api/leagues", methods=["POST"])
@login_required
def create_league():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) < 3:
        return _error("INVALID_NAME", "League name must be at least 3 characters")

    is_public = bool(data.get("is_public", False))
    code = _generate_code()

    league = MiniLeague(
        name=name,
        code=code,
        creator_id=current_user.id,
        is_public=is_public,
    )
    db.session.add(league)
    db.session.flush()

    standing = MiniLeagueStanding(
        league_id=league.id,
        user_id=current_user.id,
        points=current_user.total_points,
        rank=1,
    )
    db.session.add(standing)
    db.session.commit()

    return _success({"league": league.to_dict()}, 201)


@leagues_bp.route("/api/leagues/join", methods=["POST"])
@login_required
def join_league():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return _error("INVALID_CODE", "Invite code is required")

    league = MiniLeague.query.filter_by(code=code).first()
    if not league:
        return _error("LEAGUE_NOT_FOUND", "League not found", status=404)

    existing = MiniLeagueStanding.query.filter_by(
        league_id=league.id, user_id=current_user.id
    ).first()
    if existing:
        return _error("ALREADY_MEMBER", "You are already in this league")

    standing = MiniLeagueStanding(
        league_id=league.id,
        user_id=current_user.id,
        points=current_user.total_points,
    )
    db.session.add(standing)
    db.session.commit()
    _update_league_standings(league.id)

    return _success({"league": league.to_dict()})


@leagues_bp.route("/api/leagues/<int:league_id>/standings", methods=["GET"])
@login_required
def league_standings(league_id):
    league = db.session.get(MiniLeague, league_id)
    if not league:
        return _error("LEAGUE_NOT_FOUND", "League not found", status=404)

    matchday = request.args.get("matchday", type=int)
    if matchday:
        _update_league_standings(league_id, matchday)

    standings = (
        MiniLeagueStanding.query.filter_by(league_id=league_id)
        .join(User)
        .order_by(desc(MiniLeagueStanding.points), User.id.asc())
        .all()
    )

    return _success({
        "league": league.to_dict(),
        "matchday": matchday,
        "standings": [s.to_dict() for s in standings],
    })
