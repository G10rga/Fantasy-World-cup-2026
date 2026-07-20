from decimal import Decimal

from flask import current_app

from app import db
from app.data.sync import get_current_matchday, is_matchday_live
from app.models import BoosterUsage, FantasyTeam, FantasyTeamPlayer, Fixture, Player, Transfer, User


class TransferError(Exception):
    def __init__(self, code: str, message: str, details: dict = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def get_stage_for_matchday(matchday: int) -> str:
    fixture = Fixture.query.filter_by(matchday=matchday).first()
    if fixture:
        return fixture.stage
    return "group"


def get_budget_limit(stage: str) -> Decimal:
    if stage in ("RO32", "QF", "SF", "F"):
        return Decimal(str(current_app.config.get("BUDGET_KNOCKOUT", 105.0)))
    return Decimal(str(current_app.config.get("BUDGET_GROUP_STAGE", 100.0)))


def get_country_limit(stage: str) -> int:
    limits = current_app.config.get("COUNTRY_LIMITS", {})
    return limits.get(stage, limits.get("group", 3))


def validate_formation(position_counts: dict) -> tuple[bool, str]:
    valid_formations = current_app.config.get("VALID_FORMATIONS", [])
    defs = position_counts.get("DEF", 0)
    mids = position_counts.get("MID", 0)
    fwds = position_counts.get("FWD", 0)
    gks = position_counts.get("GK", 0)

    if gks < 1:
        return False, "Starting XI must include 1 goalkeeper"
    if defs < 3:
        return False, "Starting XI must have at least 3 defenders"
    if fwds < 2:
        return False, "Starting XI must have at least 2 forwards"

    if (defs, mids, fwds) in valid_formations:
        return True, ""

    return False, f"Invalid formation {defs}-{mids}-{fwds}. Valid: 3-4-3, 3-5-2, 4-3-3, etc."


def validate_squad_composition(player_ids: list[int]) -> tuple[bool, str]:
    limits = current_app.config.get("POSITION_LIMITS", {})
    players = Player.query.filter(Player.id.in_(player_ids)).all()
    if len(players) != len(player_ids):
        return False, "One or more players not found"

    counts = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
    for p in players:
        counts[p.position] = counts.get(p.position, 0) + 1

    for pos, limit in limits.items():
        if counts.get(pos, 0) != limit:
            return False, f"Squad must have exactly {limit} {pos} players (has {counts.get(pos, 0)})"

    return True, ""


def validate_country_limits(player_ids: list[int], stage: str) -> tuple[bool, str]:
    limit = get_country_limit(stage)
    players = Player.query.filter(Player.id.in_(player_ids)).all()
    country_counts = {}
    for p in players:
        country_counts[p.country_id] = country_counts.get(p.country_id, 0) + 1

    for country_id, count in country_counts.items():
        if count > limit:
            from app.models import Country
            country = db.session.get(Country, country_id)
            name = country.name if country else str(country_id)
            return False, f"Maximum {limit} players from {name} at this stage (have {count})"

    return True, ""


def validate_budget(player_ids: list[int], stage: str) -> tuple[bool, str, dict]:
    budget = get_budget_limit(stage)
    players = Player.query.filter(Player.id.in_(player_ids)).all()
    total = sum(Decimal(str(p.price)) for p in players)
    remaining = budget - total
    if total > budget:
        over = float(total - budget)
        return False, f"Transfer would exceed your ${float(budget)}m budget. You are ${over:.1f}m over budget.", {
            "budget": float(budget),
            "spent": float(total),
            "over_by": over,
        }
    return True, "", {"budget": float(budget), "spent": float(total), "remaining": float(remaining)}


def get_free_transfers(user: User, matchday: int) -> int:
    stage = get_stage_for_matchday(matchday)

    if matchday <= 1:
        return 999

    if stage == "RO32" and _is_first_knockout_matchday(matchday):
        return 999

    wildcard = BoosterUsage.query.filter_by(
        user_id=user.id, booster_type="WILDCARD", matchday_used=matchday
    ).first()
    if wildcard:
        return 999

    if stage in ("RO32", "QF", "SF", "F"):
        base = current_app.config.get("FREE_TRANSFERS_KNOCKOUT", 1)
    else:
        base = current_app.config.get("FREE_TRANSFERS_GROUP", 2)

    bank = user.free_transfers_bank or 0
    return base + min(bank, current_app.config.get("MAX_ROLLOVER_TRANSFERS", 1))


def _is_first_knockout_matchday(matchday: int) -> bool:
    fixture = Fixture.query.filter_by(matchday=matchday).first()
    if not fixture:
        return False
    if fixture.stage != "RO32":
        return False
    earlier_ko = Fixture.query.filter(
        Fixture.stage == "RO32",
        Fixture.matchday < matchday,
    ).first()
    return earlier_ko is None


def count_transfers_this_matchday(user_id: int, matchday: int) -> int:
    return Transfer.query.filter_by(
        user_id=user_id, matchday=matchday, applied=True
    ).count()


def get_transfer_budget_info(user: User, matchday: int = None) -> dict:
    matchday = matchday or get_current_matchday()
    stage = get_stage_for_matchday(matchday)
    team = get_or_create_team(user, matchday)
    free = get_free_transfers(user, matchday)
    used = count_transfers_this_matchday(user.id, matchday)
    remaining_free = max(0, free - used) if free < 999 else 999

    return {
        "matchday": matchday,
        "stage": stage,
        "budget_limit": float(get_budget_limit(stage)),
        "budget_remaining": float(team.budget_remaining),
        "free_transfers": free,
        "transfers_used": used,
        "free_transfers_remaining": remaining_free,
        "transfer_penalty": current_app.config.get("TRANSFER_PENALTY", 3),
        "is_live_matchday": is_matchday_live(matchday),
    }


def get_or_create_team(user: User, matchday: int) -> FantasyTeam:
    team = FantasyTeam.query.filter_by(user_id=user.id, matchday=matchday).first()
    if team:
        return team

    prev = FantasyTeam.query.filter(
        FantasyTeam.user_id == user.id,
        FantasyTeam.matchday < matchday,
    ).order_by(FantasyTeam.matchday.desc()).first()

    stage = get_stage_for_matchday(matchday)
    budget = get_budget_limit(stage)

    team = FantasyTeam(
        user_id=user.id,
        matchday=matchday,
        budget_remaining=budget,
    )
    db.session.add(team)

    if prev:
        for ftp in prev.squad_players:
            db.session.add(FantasyTeamPlayer(
                fantasy_team_id=team.id,
                player_id=ftp.player_id,
                is_starting=ftp.is_starting,
                bench_order=ftp.bench_order,
            ))
        team.captain_id = prev.captain_id
        team.vice_captain_id = prev.vice_captain_id
        team.formation = prev.formation
        _recalc_budget(team)

    db.session.commit()
    return team


def _recalc_budget(team: FantasyTeam):
    stage = get_stage_for_matchday(team.matchday)
    budget = get_budget_limit(stage)
    player_ids = [ftp.player_id for ftp in team.squad_players]
    players = Player.query.filter(Player.id.in_(player_ids)).all() if player_ids else []
    spent = sum(Decimal(str(p.price)) for p in players)
    team.budget_remaining = budget - spent


def validate_team_save(user: User, squad_data: list[dict], matchday: int = None) -> tuple[bool, dict]:
    matchday = matchday or get_current_matchday()
    stage = get_stage_for_matchday(matchday)

    if len(squad_data) != current_app.config.get("SQUAD_SIZE", 15):
        return False, {
            "error": "INVALID_SQUAD_SIZE",
            "message": f"Squad must have exactly {current_app.config.get('SQUAD_SIZE', 15)} players",
        }

    player_ids = [s["player_id"] for s in squad_data]
    ok, msg = validate_squad_composition(player_ids)
    if not ok:
        return False, {"error": "INVALID_COMPOSITION", "message": msg}

    ok, msg = validate_country_limits(player_ids, stage)
    if not ok:
        return False, {"error": "COUNTRY_LIMIT_EXCEEDED", "message": msg}

    ok, msg, details = validate_budget(player_ids, stage)
    if not ok:
        return False, {"error": "BUDGET_EXCEEDED", "message": msg, "details": details}

    starters = [s for s in squad_data if s.get("is_starting")]
    if len(starters) != current_app.config.get("STARTING_XI_SIZE", 11):
        return False, {
            "error": "INVALID_STARTING_XI",
            "message": "Starting XI must have exactly 11 players",
        }

    position_counts = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
    players_map = {p.id: p for p in Player.query.filter(Player.id.in_(player_ids)).all()}
    for s in starters:
        p = players_map.get(s["player_id"])
        if p:
            position_counts[p.position] = position_counts.get(p.position, 0) + 1

    ok, msg = validate_formation(position_counts)
    if not ok:
        return False, {"error": "INVALID_FORMATION", "message": msg}

    return True, {"details": details}


def save_team(user: User, squad_data: list[dict], captain_id: int, vice_captain_id: int, matchday: int = None):
    matchday = matchday or get_current_matchday()
    ok, result = validate_team_save(user, squad_data, matchday)
    if not ok:
        raise TransferError(result["error"], result["message"], result.get("details"))

    team = get_or_create_team(user, matchday)
    FantasyTeamPlayer.query.filter_by(fantasy_team_id=team.id).delete()

    for entry in squad_data:
        db.session.add(FantasyTeamPlayer(
            fantasy_team_id=team.id,
            player_id=entry["player_id"],
            is_starting=entry.get("is_starting", False),
            bench_order=entry.get("bench_order"),
        ))

    team.captain_id = captain_id
    team.vice_captain_id = vice_captain_id
    team.formation = _detect_formation_from_data(squad_data)
    _recalc_budget(team)
    db.session.commit()
    return team


def _detect_formation_from_data(squad_data: list[dict]) -> str:
    player_ids = [s["player_id"] for s in squad_data if s.get("is_starting")]
    players = Player.query.filter(Player.id.in_(player_ids)).all()
    counts = {"DEF": 0, "MID": 0, "FWD": 0}
    for p in players:
        if p.position in counts:
            counts[p.position] += 1
    return f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}"


def make_transfer(user: User, player_out_id: int, player_in_id: int, matchday: int = None) -> Transfer:
    matchday = matchday or get_current_matchday()
    current_md = get_current_matchday()

    if is_matchday_live(current_md):
        matchday = current_md + 1

    stage = get_stage_for_matchday(matchday)
    team = get_or_create_team(user, matchday)
    squad_ids = [ftp.player_id for ftp in team.squad_players]

    if player_out_id and player_out_id not in squad_ids:
        raise TransferError("PLAYER_NOT_IN_SQUAD", "Player to transfer out is not in your squad")
    if player_in_id in squad_ids:
        raise TransferError("PLAYER_ALREADY_OWNED", "Player is already in your squad")

    player_in = db.session.get(Player, player_in_id)
    if not player_in:
        raise TransferError("PLAYER_NOT_FOUND", "Player not found")
    if not player_in.is_available:
        raise TransferError("PLAYER_UNAVAILABLE", f"Player is {player_in.availability_status}")

    new_squad_ids = [pid for pid in squad_ids if pid != player_out_id] + [player_in_id]
    ok, msg = validate_squad_composition(new_squad_ids)
    if not ok:
        raise TransferError("INVALID_COMPOSITION", msg)

    ok, msg = validate_country_limits(new_squad_ids, stage)
    if not ok:
        raise TransferError("COUNTRY_LIMIT_EXCEEDED", msg)

    ok, msg, details = validate_budget(new_squad_ids, stage)
    if not ok:
        raise TransferError("BUDGET_EXCEEDED", msg, details)

    free = get_free_transfers(user, matchday)
    used = count_transfers_this_matchday(user.id, matchday)
    cost = 0
    if free < 999 and used >= free:
        cost = current_app.config.get("TRANSFER_PENALTY", 3)

    transfer = Transfer(
        user_id=user.id,
        player_out_id=player_out_id,
        player_in_id=player_in_id,
        matchday=matchday,
        cost_in_points=cost,
        applied=True,
    )
    db.session.add(transfer)

    if player_out_id:
        ftp_out = FantasyTeamPlayer.query.filter_by(
            fantasy_team_id=team.id, player_id=player_out_id
        ).first()
        if ftp_out:
            was_starting = ftp_out.is_starting
            bench_order = ftp_out.bench_order
            db.session.delete(ftp_out)
        else:
            was_starting = False
            bench_order = 4
    else:
        was_starting = False
        bench_order = 4

    ftp_in = FantasyTeamPlayer(
        fantasy_team_id=team.id,
        player_id=player_in_id,
        is_starting=was_starting,
        bench_order=bench_order if not was_starting else None,
    )
    db.session.add(ftp_in)
    _recalc_budget(team)
    db.session.commit()
    return transfer


def live_substitute(user: User, player_out_id: int, player_in_id: int, matchday: int = None):
    matchday = matchday or get_current_matchday()
    team = get_or_create_team(user, matchday)

    from app.models import PlayerMatchStat, Fixture
    fixture_ids = [f.id for f in Fixture.query.filter_by(matchday=matchday).all()]

    stat_in = PlayerMatchStat.query.filter(
        PlayerMatchStat.player_id == player_in_id,
        PlayerMatchStat.fixture_id.in_(fixture_ids),
    ).first()
    if stat_in and stat_in.minutes_played > 0:
        raise TransferError(
            "BENCH_PLAYER_PLAYED",
            "Bench player has already played and cannot be substituted in",
        )

    ftp_out = FantasyTeamPlayer.query.filter_by(
        fantasy_team_id=team.id, player_id=player_out_id, is_starting=True
    ).first()
    ftp_in = FantasyTeamPlayer.query.filter_by(
        fantasy_team_id=team.id, player_id=player_in_id, is_starting=False
    ).first()

    if not ftp_out or not ftp_in:
        raise TransferError("INVALID_SUBSTITUTION", "Invalid substitution players")

    if ftp_out.removed_from_xi_matchday:
        raise TransferError("PLAYER_CANNOT_RETURN", "Player removed from XI cannot return this round")

    positions = {}
    for ftp in team.squad_players:
        if ftp.id == ftp_out.id:
            if ftp_in.player:
                pos = ftp_in.player.position
                positions[pos] = positions.get(pos, 0) + 1
        elif ftp.id == ftp_in.id:
            continue
        elif ftp.is_starting and ftp.player:
            pos = ftp.player.position
            positions[pos] = positions.get(pos, 0) + 1

    ok, msg = validate_formation(positions)
    if not ok:
        raise TransferError("INVALID_FORMATION", msg)

    bench_order = ftp_out.bench_order
    ftp_out.is_starting = False
    ftp_out.bench_order = ftp_in.bench_order
    ftp_out.removed_from_xi_matchday = True
    ftp_in.is_starting = True
    ftp_in.bench_order = None

    user.manual_changes_matchday = matchday
    team.formation = _detect_formation_from_squad(team)
    db.session.commit()
    return team


def _detect_formation_from_squad(team: FantasyTeam) -> str:
    counts = {"DEF": 0, "MID": 0, "FWD": 0}
    for ftp in team.squad_players:
        if ftp.is_starting and ftp.player and ftp.player.position in counts:
            counts[ftp.player.position] += 1
    return f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}"
