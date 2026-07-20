import logging
from decimal import Decimal

from flask import current_app
from sqlalchemy import func

from app import db
from app.models import (
    BoosterUsage,
    FantasyTeam,
    FantasyTeamPlayer,
    Fixture,
    Player,
    PlayerMatchStat,
    User,
)

logger = logging.getLogger(__name__)


def calculate_player_points(stat: PlayerMatchStat, player: Player = None) -> int:
    player = player or stat.player
    if not player:
        player = db.session.get(Player, stat.player_id)
    if not player:
        return 0

    cfg = current_app.config
    position = player.position
    minutes = stat.minutes_played or 0
    goals = stat.goals or 0
    assists = stat.assists or 0
    shots_on_target = stat.shots_on_target or 0
    chances_created = stat.chances_created or 0
    tackles = stat.tackles or 0
    saves = stat.saves or 0
    goals_conceded = stat.goals_conceded or 0
    goals_outside_box = stat.goals_outside_box or 0
    penalty_saved = stat.penalty_saved or 0
    penalty_missed = stat.penalty_missed or 0
    own_goals = stat.own_goals or 0
    yellow_cards = stat.yellow_cards or 0
    red_cards = stat.red_cards or 0

    points = 0
    if minutes > 0:
        points += cfg.get("SCORING_APPEARANCE_POINTS", 1)
        if minutes >= 60:
            points += cfg.get("SCORING_60_MIN_BONUS", 1)

    if goals > 0:
        goal_pts = cfg.get("SCORING_GOAL_POINTS", {"GK": 9, "DEF": 7, "MID": 6, "FWD": 5})
        points += goals * goal_pts.get(position, 5)

    points += goals_outside_box * cfg.get("SCORING_FREE_KICK_GOAL", 1)

    points += assists * cfg.get("SCORING_ASSIST_POINTS", 3)

    if minutes >= 60 and stat.clean_sheet:
        cs_pts = cfg.get("SCORING_CLEAN_SHEET", {"GK": 5, "DEF": 5, "MID": 1, "FWD": 0})
        points += cs_pts.get(position, 0)

    if minutes >= 60 and position in ("GK", "DEF") and goals_conceded > 1:
        points -= goals_conceded - 1

    saves_step = cfg.get("SCORING_SAVES_PER_POINT", 3)
    if position == "GK" and saves > 0 and saves_step:
        points += saves // saves_step

    points += penalty_saved * cfg.get("SCORING_PENALTY_SAVED", 3)
    points += penalty_missed * cfg.get("SCORING_PENALTY_MISSED", -2)
    points += own_goals * cfg.get("SCORING_OWN_GOAL", -2)
    points += yellow_cards * cfg.get("SCORING_YELLOW_CARD", -1)
    points += red_cards * cfg.get("SCORING_RED_CARD", -2)

    shots_step = cfg.get("SCORING_SHOTS_ON_TARGET_PER_POINT", 2)
    if position == "FWD" and shots_on_target > 0 and shots_step:
        points += shots_on_target // shots_step

    chances_step = cfg.get("SCORING_CHANCES_CREATED_PER_POINT", 2)
    if position == "MID" and chances_created > 0 and chances_step:
        points += chances_created // chances_step

    tackles_step = cfg.get("SCORING_TACKLES_PER_POINT", 3)
    if position == "MID" and tackles > 0 and tackles_step:
        points += tackles // tackles_step

    scouting_bonus = 0
    if points > cfg.get("SCOUTING_BONUS_THRESHOLD", 4):
        ownership = float(player.selected_by_pct or 0)
        if ownership < cfg.get("SCOUTING_BONUS_OWNERSHIP_PCT", 5.0):
            scouting_bonus = cfg.get("SCOUTING_BONUS_POINTS", 2)
            points += scouting_bonus

    stat.scouting_bonus = scouting_bonus
    stat.fantasy_points = max(points, 0)
    return stat.fantasy_points


def _get_active_booster(user_id: int, matchday: int) -> BoosterUsage | None:
    return BoosterUsage.query.filter_by(user_id=user_id, matchday_used=matchday).first()


def _apply_qualification_bonus(team: FantasyTeam, matchday: int) -> int:
    booster = _get_active_booster(team.user_id, matchday)
    if not booster or booster.booster_type != "QUALIFICATION_BOOSTER":
        return 0

    bonus = 0
    fixture_ids = [f.id for f in Fixture.query.filter_by(matchday=matchday).all()]
    for ftp in team.squad_players:
        if not ftp.is_starting:
            continue
        player = ftp.player
        if not player:
            continue
        country = player.country
        if not country or country.eliminated_at_round:
            continue
        stat = PlayerMatchStat.query.filter(
            PlayerMatchStat.player_id == player.id,
            PlayerMatchStat.fixture_id.in_(fixture_ids),
        ).first()
        if stat and stat.minutes_played > 0:
            bonus += 2
            ftp.matchday_points += 2
    return bonus


def _resolve_captain_multiplier(
    team: FantasyTeam,
    ftp: FantasyTeamPlayer,
    captain_played: dict,
    booster: BoosterUsage | None,
) -> int:
    if booster and booster.booster_type == "MAX_CAPTAIN":
        return 1

    captain_id = team.captain_id
    vice_id = team.vice_captain_id

    if ftp.player_id == captain_id:
        if captain_played.get(captain_id, 0) > 0 or not team.user.manual_changes_matchday:
            return 2
    elif ftp.player_id == vice_id:
        if captain_played.get(captain_id, 0) == 0 and team.user.manual_changes_matchday != team.matchday:
            return 2

    return ftp.multiplier if ftp.multiplier > 1 else 1


def _get_max_captain_player_id(team: FantasyTeam, matchday: int) -> int | None:
    best_id = None
    best_pts = -1
    fixture_ids = [f.id for f in Fixture.query.filter_by(matchday=matchday).all()]
    for ftp in team.squad_players:
        if not ftp.is_starting:
            continue
        stat = PlayerMatchStat.query.filter(
            PlayerMatchStat.player_id == ftp.player_id,
            PlayerMatchStat.fixture_id.in_(fixture_ids),
        ).first()
        pts = stat.fantasy_points if stat else 0
        if pts > best_pts:
            best_pts = pts
            best_id = ftp.player_id
    return best_id


def apply_team_points(team: FantasyTeam, matchday: int):
    fixture_ids = [f.id for f in Fixture.query.filter_by(matchday=matchday).all()]
    if not fixture_ids:
        team.matchday_points = 0
        return 0

    booster = _get_active_booster(team.user_id, matchday)
    captain_played = {}
    for ftp in team.squad_players:
        stat = PlayerMatchStat.query.filter(
            PlayerMatchStat.player_id == ftp.player_id,
            PlayerMatchStat.fixture_id.in_(fixture_ids),
        ).first()
        captain_played[ftp.player_id] = stat.minutes_played if stat else 0

    max_captain_id = None
    if booster and booster.booster_type == "MAX_CAPTAIN":
        max_captain_id = _get_max_captain_player_id(team, matchday)

    total = 0
    for ftp in team.squad_players:
        stat = PlayerMatchStat.query.filter(
            PlayerMatchStat.player_id == ftp.player_id,
            PlayerMatchStat.fixture_id.in_(fixture_ids),
        ).first()
        base_pts = stat.fantasy_points if stat else 0

        if booster and booster.booster_type == "MAX_CAPTAIN" and ftp.player_id == max_captain_id and ftp.is_starting:
            mult = 2
        elif ftp.is_starting:
            mult = _resolve_captain_multiplier(team, ftp, captain_played, booster)
        else:
            mult = 0

        ftp.multiplier = mult if mult > 1 else 1
        ftp.matchday_points = base_pts * mult if ftp.is_starting else 0
        total += ftp.matchday_points

    if booster and booster.booster_type == "12TH_MAN" and team.twelfth_man_player_id:
        stat = PlayerMatchStat.query.filter(
            PlayerMatchStat.player_id == team.twelfth_man_player_id,
            PlayerMatchStat.fixture_id.in_(fixture_ids),
        ).first()
        if stat:
            total += stat.fantasy_points

    qual_bonus = _apply_qualification_bonus(team, matchday)
    total += qual_bonus
    team.matchday_points = total
    return total


def recalculate_fixture_points(fixture_id: int):
    fixture = db.session.get(Fixture, fixture_id)
    if not fixture:
        return

    stats = PlayerMatchStat.query.filter_by(fixture_id=fixture_id).all()
    for stat in stats:
        calculate_player_points(stat)

    player_ids = {s.player_id for s in stats}
    for pid in player_ids:
        total = db.session.query(func.sum(PlayerMatchStat.fantasy_points)).filter(
            PlayerMatchStat.player_id == pid
        ).scalar() or 0
        player = db.session.get(Player, pid)
        if player:
            player.total_fantasy_points = int(total)

    db.session.commit()

    matchday = fixture.matchday
    teams = FantasyTeam.query.filter_by(matchday=matchday).all()
    for team in teams:
        apply_team_points(team, matchday)
        team.total_points = _calculate_user_total(team.user_id)

    db.session.commit()
    update_rankings()


def recalculate_matchday(matchday: int):
    fixtures = Fixture.query.filter_by(matchday=matchday).all()
    for fixture in fixtures:
        stats = PlayerMatchStat.query.filter_by(fixture_id=fixture.id).all()
        for stat in stats:
            calculate_player_points(stat)

    for player in Player.query.all():
        total = db.session.query(func.sum(PlayerMatchStat.fantasy_points)).filter(
            PlayerMatchStat.player_id == player.id
        ).scalar() or 0
        player.total_fantasy_points = int(total)

    teams = FantasyTeam.query.filter_by(matchday=matchday).all()
    for team in teams:
        apply_team_points(team, matchday)
        team.user.total_points = _calculate_user_total(team.user_id)

    db.session.commit()
    update_rankings()
    return {"matchday": matchday, "teams_processed": len(teams)}


def _calculate_user_total(user_id: int) -> int:
    return int(
        db.session.query(func.sum(FantasyTeam.matchday_points)).filter(
            FantasyTeam.user_id == user_id
        ).scalar() or 0
    )


def update_rankings():
    users = User.query.order_by(User.total_points.desc(), User.id.asc()).all()
    for rank, user in enumerate(users, start=1):
        user.overall_rank = rank

    countries = db.session.query(User.supported_nation_id).distinct().all()
    for (country_id,) in countries:
        if not country_id:
            continue
        country_users = User.query.filter_by(
            supported_nation_id=country_id
        ).order_by(User.total_points.desc(), User.id.asc()).all()
        for rank, user in enumerate(country_users, start=1):
            user.country_rank = rank

    db.session.commit()


def apply_auto_substitutions(team: FantasyTeam, matchday: int):
    user = team.user
    if user.manual_changes_matchday == matchday:
        return

    fixture_ids = [f.id for f in Fixture.query.filter_by(matchday=matchday).all()]

    def minutes_for(player_id):
        stat = PlayerMatchStat.query.filter(
            PlayerMatchStat.player_id == player_id,
            PlayerMatchStat.fixture_id.in_(fixture_ids),
        ).first()
        return stat.minutes_played if stat else 0

    starters = [p for p in team.squad_players if p.is_starting]
    bench = sorted(
        [p for p in team.squad_players if not p.is_starting],
        key=lambda x: x.bench_order or 99,
    )

    for starter in starters:
        if minutes_for(starter.player_id) > 0:
            continue
        for bench_player in bench:
            if minutes_for(bench_player.player_id) > 0:
                continue
            if _can_swap_positions(team, starter, bench_player):
                starter.is_starting = False
                starter.bench_order = bench_player.bench_order
                bench_player.is_starting = True
                bench_player.bench_order = None
                break

    team.formation = detect_formation(team)
    apply_team_points(team, matchday)


def _can_swap_positions(team: FantasyTeam, out_player: FantasyTeamPlayer, in_player: FantasyTeamPlayer) -> bool:
    from app.fantasy.transfers import validate_formation

    positions = {}
    for ftp in team.squad_players:
        if not ftp.is_starting and ftp.id != in_player.id:
            continue
        if ftp.id == out_player.id:
            if in_player.player:
                pos = in_player.player.position
                positions[pos] = positions.get(pos, 0) + 1
            continue
        if ftp.id == in_player.id:
            continue
        if ftp.player:
            pos = ftp.player.position
            positions[pos] = positions.get(pos, 0) + 1

    if in_player.player:
        pos = in_player.player.position
        positions[pos] = positions.get(pos, 0) + 1

    return validate_formation(positions)[0]


def detect_formation(team: FantasyTeam) -> str:
    counts = {"DEF": 0, "MID": 0, "FWD": 0}
    for ftp in team.squad_players:
        if ftp.is_starting and ftp.player and ftp.player.position in counts:
            counts[ftp.player.position] += 1
    return f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}"
