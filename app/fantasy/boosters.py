from flask import current_app

from app import db
from app.data.sync import get_current_matchday
from app.fantasy.transfers import TransferError, get_stage_for_matchday
from app.models import BoosterUsage, FantasyTeam


class BoosterError(Exception):
    def __init__(self, code: str, message: str, details: dict = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


BOOSTER_DESCRIPTIONS = {
    "WILDCARD": "Unlimited free transfers for one matchday",
    "12TH_MAN": "Pick any player outside your squad to score bonus points for one round",
    "MAX_CAPTAIN": "Auto double points for highest-scoring starting XI player",
    "QUALIFICATION_BOOSTER": "Starting XI players who advance earn +2 bonus points",
    "MYSTERY": "Mystery booster revealed before Round of 32",
}


def get_booster_status(user_id: int) -> list[dict]:
    used = {
        b.booster_type: b
        for b in BoosterUsage.query.filter_by(user_id=user_id).all()
    }
    mystery_type = current_app.config.get("MYSTERY_BOOSTER_TYPE", "WILDCARD")
    boosters = []

    for btype in current_app.config.get("BOOSTER_TYPES", []):
        actual_type = mystery_type if btype == "MYSTERY" else btype
        usage = used.get(btype) or used.get(actual_type)
        boosters.append({
            "type": btype,
            "resolved_type": actual_type,
            "description": BOOSTER_DESCRIPTIONS.get(btype, ""),
            "used": usage is not None,
            "matchday_used": usage.matchday_used if usage else None,
            "available": usage is None,
        })
    return boosters


def get_active_booster(user_id: int, matchday: int = None) -> BoosterUsage | None:
    matchday = matchday or get_current_matchday()
    return BoosterUsage.query.filter_by(user_id=user_id, matchday_used=matchday).first()


def activate_booster(user_id: int, booster_type: str, matchday: int = None, extra_data: dict = None):
    matchday = matchday or get_current_matchday()
    stage = get_stage_for_matchday(matchday)

    if booster_type == "MYSTERY":
        booster_type = current_app.config.get("MYSTERY_BOOSTER_TYPE", "WILDCARD")

    valid_types = current_app.config.get("BOOSTER_TYPES", [])
    resolved_types = [t if t != "MYSTERY" else current_app.config.get("MYSTERY_BOOSTER_TYPE") for t in valid_types]
    if booster_type not in resolved_types:
        raise BoosterError("INVALID_BOOSTER", f"Unknown booster type: {booster_type}")

    if booster_type == "WILDCARD" and stage == "RO32":
        raise BoosterError(
            "WILDCARD_NOT_AVAILABLE",
            "Wildcard is not available during Round of 32 (transfers are already unlimited)",
        )

    if booster_type == "QUALIFICATION_BOOSTER" and stage in ("group",):
        raise BoosterError(
            "BOOSTER_NOT_AVAILABLE",
            "Qualification Booster is only available from Round of 32 onwards",
        )

    existing_matchday = get_active_booster(user_id, matchday)
    if existing_matchday:
        raise BoosterError(
            "BOOSTER_ALREADY_ACTIVE",
            f"Booster {existing_matchday.booster_type} is already active this matchday",
        )

    stored_type = booster_type
    for btype in valid_types:
        if btype == "MYSTERY" and booster_type == current_app.config.get("MYSTERY_BOOSTER_TYPE"):
            stored_type = "MYSTERY"
            break
        if btype == booster_type:
            stored_type = btype
            break

    used = BoosterUsage.query.filter_by(user_id=user_id, booster_type=stored_type).first()
    if used:
        raise BoosterError("BOOSTER_ALREADY_USED", f"{stored_type} has already been used this tournament")

    if booster_type == "12TH_MAN":
        if not extra_data or not extra_data.get("player_id"):
            raise BoosterError("MISSING_PLAYER", "12th Man requires a player_id in extra_data")
        team = FantasyTeam.query.filter_by(user_id=user_id, matchday=matchday).first()
        if team:
            team.twelfth_man_player_id = extra_data["player_id"]

    usage = BoosterUsage(
        user_id=user_id,
        booster_type=stored_type,
        matchday_used=matchday,
        extra_data=extra_data,
    )
    db.session.add(usage)
    db.session.commit()
    return usage
