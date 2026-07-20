from datetime import datetime, timezone
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    supported_nation_id = db.Column(db.Integer, db.ForeignKey("countries.id"), nullable=True)
    total_points = db.Column(db.Integer, default=0, nullable=False)
    overall_rank = db.Column(db.Integer, nullable=True)
    country_rank = db.Column(db.Integer, nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    free_transfers_bank = db.Column(db.Integer, default=0, nullable=False)
    manual_changes_matchday = db.Column(db.Integer, nullable=True)

    supported_nation = db.relationship("Country", foreign_keys=[supported_nation_id])
    fantasy_teams = db.relationship("FantasyTeam", back_populates="user", lazy="dynamic")
    transfers = db.relationship("Transfer", back_populates="user", lazy="dynamic")
    booster_usages = db.relationship("BoosterUsage", back_populates="user", lazy="dynamic")
    mini_league_memberships = db.relationship(
        "MiniLeagueStanding", back_populates="user", lazy="dynamic"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "supported_nation_id": self.supported_nation_id,
            "supported_nation": self.supported_nation.to_dict() if self.supported_nation else None,
            "total_points": self.total_points,
            "overall_rank": self.overall_rank,
            "country_rank": self.country_rank,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Country(db.Model):
    __tablename__ = "countries"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    confederation = db.Column(db.String(20), nullable=True)
    flag_url = db.Column(db.String(512), nullable=True)
    eliminated_at_round = db.Column(db.String(20), nullable=True)
    code = db.Column(db.String(8), nullable=True)
    football_data_id = db.Column(db.Integer, unique=True, nullable=True, index=True)
    worldcup26_id = db.Column(db.String(20), unique=True, nullable=True, index=True)

    players = db.relationship("Player", back_populates="country", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "confederation": self.confederation,
            "flag_url": self.flag_url,
            "eliminated_at_round": self.eliminated_at_round,
            "code": self.code,
            "football_data_id": self.football_data_id,
            "worldcup26_id": self.worldcup26_id,
        }


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    position = db.Column(db.String(3), nullable=False, index=True)
    country_id = db.Column(db.Integer, db.ForeignKey("countries.id"), nullable=False, index=True)
    price = db.Column(db.Numeric(5, 1), nullable=False, default=Decimal("5.0"))
    photo_url = db.Column(db.String(512), nullable=True)
    total_fantasy_points = db.Column(db.Integer, default=0, nullable=False)
    selected_by_pct = db.Column(db.Numeric(5, 2), default=Decimal("0.0"), nullable=False)
    is_available = db.Column(db.Boolean, default=True, nullable=False)
    availability_status = db.Column(db.String(20), default="available", nullable=False)
    football_data_team_id = db.Column(db.Integer, nullable=True)
    api_football_id = db.Column(db.Integer, unique=True, nullable=True, index=True)

    country = db.relationship("Country", back_populates="players")
    match_stats = db.relationship("PlayerMatchStat", back_populates="player", lazy="dynamic")

    def to_dict(self, extra=None):
        data = {
            "id": self.id,
            "name": self.name,
            "position": self.position,
            "country_id": self.country_id,
            "country": self.country.to_dict() if self.country else None,
            "price": float(self.price),
            "photo_url": self.photo_url,
            "total_fantasy_points": self.total_fantasy_points,
            "selected_by_pct": float(self.selected_by_pct),
            "is_available": self.is_available,
            "availability_status": self.availability_status,
        }
        if extra:
            data.update(extra)
        return data


class Fixture(db.Model):
    __tablename__ = "fixtures"

    id = db.Column(db.Integer, primary_key=True)
    home_team_id = db.Column(db.Integer, db.ForeignKey("countries.id"), nullable=False)
    away_team_id = db.Column(db.Integer, db.ForeignKey("countries.id"), nullable=False)
    kickoff_utc = db.Column(db.DateTime, nullable=False, index=True)
    matchday = db.Column(db.Integer, nullable=False, index=True)
    stage = db.Column(db.String(20), nullable=False, default="group", index=True)
    status = db.Column(db.String(10), nullable=False, default="NS", index=True)
    home_score = db.Column(db.Integer, nullable=True)
    away_score = db.Column(db.Integer, nullable=True)
    stats_synced = db.Column(db.Boolean, default=False, nullable=False)
    football_data_id = db.Column(db.Integer, unique=True, nullable=True, index=True)
    worldcup26_id = db.Column(db.String(20), unique=True, nullable=True, index=True)
    api_football_id = db.Column(db.Integer, unique=True, nullable=True, index=True)
    group_name = db.Column(db.String(4), nullable=True)

    home_team = db.relationship("Country", foreign_keys=[home_team_id])
    away_team = db.relationship("Country", foreign_keys=[away_team_id])
    player_stats = db.relationship("PlayerMatchStat", back_populates="fixture", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "home_team": self.home_team.to_dict() if self.home_team else None,
            "away_team": self.away_team.to_dict() if self.away_team else None,
            "kickoff_utc": self.kickoff_utc.isoformat() if self.kickoff_utc else None,
            "matchday": self.matchday,
            "stage": self.stage,
            "status": self.status,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "stats_synced": self.stats_synced,
            "group_name": self.group_name,
        }

    @property
    def is_live(self):
        return self.status in ("LIVE", "HT", "1H", "2H", "ET", "BT", "PEN_LIVE")


class ApiQuotaLog(db.Model):
    __tablename__ = "api_quota_logs"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    source = db.Column(db.String(30), nullable=False, index=True)
    calls_made = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("date", "source", name="uq_quota_date_source"),
    )


class PlayerMatchStat(db.Model):
    __tablename__ = "player_match_stats"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False, index=True)
    fixture_id = db.Column(db.Integer, db.ForeignKey("fixtures.id"), nullable=False, index=True)
    minutes_played = db.Column(db.Integer, default=0, nullable=False)
    goals = db.Column(db.Integer, default=0, nullable=False)
    assists = db.Column(db.Integer, default=0, nullable=False)
    clean_sheet = db.Column(db.Boolean, default=False, nullable=False)
    saves = db.Column(db.Integer, default=0, nullable=False)
    yellow_cards = db.Column(db.Integer, default=0, nullable=False)
    red_cards = db.Column(db.Integer, default=0, nullable=False)
    own_goals = db.Column(db.Integer, default=0, nullable=False)
    penalty_saved = db.Column(db.Integer, default=0, nullable=False)
    penalty_missed = db.Column(db.Integer, default=0, nullable=False)
    shots_on_target = db.Column(db.Integer, default=0, nullable=False)
    chances_created = db.Column(db.Integer, default=0, nullable=False)
    tackles = db.Column(db.Integer, default=0, nullable=False)
    goals_conceded = db.Column(db.Integer, default=0, nullable=False)
    goals_outside_box = db.Column(db.Integer, default=0, nullable=False)
    is_potm = db.Column(db.Boolean, default=False, nullable=False)
    fantasy_points = db.Column(db.Integer, default=0, nullable=False)
    scouting_bonus = db.Column(db.Integer, default=0, nullable=False)

    player = db.relationship("Player", back_populates="match_stats")
    fixture = db.relationship("Fixture", back_populates="player_stats")

    __table_args__ = (
        db.UniqueConstraint("player_id", "fixture_id", name="uq_player_fixture"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "player_id": self.player_id,
            "fixture_id": self.fixture_id,
            "minutes_played": self.minutes_played,
            "goals": self.goals,
            "assists": self.assists,
            "clean_sheet": self.clean_sheet,
            "saves": self.saves,
            "yellow_cards": self.yellow_cards,
            "red_cards": self.red_cards,
            "own_goals": self.own_goals,
            "penalty_saved": self.penalty_saved,
            "penalty_missed": self.penalty_missed,
            "shots_on_target": self.shots_on_target,
            "chances_created": self.chances_created,
            "tackles": self.tackles,
            "goals_conceded": self.goals_conceded,
            "goals_outside_box": self.goals_outside_box,
            "is_potm": self.is_potm,
            "fantasy_points": self.fantasy_points,
            "scouting_bonus": self.scouting_bonus,
            "fixture": self.fixture.to_dict() if self.fixture else None,
        }


class FantasyTeam(db.Model):
    __tablename__ = "fantasy_teams"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    matchday = db.Column(db.Integer, nullable=False, default=1, index=True)
    budget_remaining = db.Column(db.Numeric(6, 1), nullable=False, default=Decimal("100.0"))
    formation = db.Column(db.String(10), nullable=True)
    total_points = db.Column(db.Integer, default=0, nullable=False)
    captain_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=True)
    vice_captain_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=True)
    matchday_points = db.Column(db.Integer, default=0, nullable=False)
    twelfth_man_player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=True)

    user = db.relationship("User", back_populates="fantasy_teams")
    captain = db.relationship("Player", foreign_keys=[captain_id])
    vice_captain = db.relationship("Player", foreign_keys=[vice_captain_id])
    twelfth_man = db.relationship("Player", foreign_keys=[twelfth_man_player_id])
    squad_players = db.relationship(
        "FantasyTeamPlayer",
        back_populates="fantasy_team",
        lazy="joined",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "matchday", name="uq_user_matchday_team"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "matchday": self.matchday,
            "budget_remaining": float(self.budget_remaining),
            "formation": self.formation,
            "total_points": self.total_points,
            "matchday_points": self.matchday_points,
            "captain_id": self.captain_id,
            "vice_captain_id": self.vice_captain_id,
            "twelfth_man_player_id": self.twelfth_man_player_id,
            "players": [p.to_dict() for p in self.squad_players],
        }


class FantasyTeamPlayer(db.Model):
    __tablename__ = "fantasy_team_players"

    id = db.Column(db.Integer, primary_key=True)
    fantasy_team_id = db.Column(
        db.Integer, db.ForeignKey("fantasy_teams.id"), nullable=False, index=True
    )
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False, index=True)
    is_starting = db.Column(db.Boolean, default=True, nullable=False)
    bench_order = db.Column(db.Integer, nullable=True)
    multiplier = db.Column(db.Integer, default=1, nullable=False)
    matchday_points = db.Column(db.Integer, default=0, nullable=False)
    removed_from_xi_matchday = db.Column(db.Boolean, default=False, nullable=False)

    fantasy_team = db.relationship("FantasyTeam", back_populates="squad_players")
    player = db.relationship("Player")

    def to_dict(self):
        return {
            "id": self.id,
            "player_id": self.player_id,
            "player": self.player.to_dict() if self.player else None,
            "is_starting": self.is_starting,
            "bench_order": self.bench_order,
            "multiplier": self.multiplier,
            "matchday_points": self.matchday_points,
            "removed_from_xi_matchday": self.removed_from_xi_matchday,
        }


class Transfer(db.Model):
    __tablename__ = "transfers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    player_out_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=True)
    player_in_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    matchday = db.Column(db.Integer, nullable=False, index=True)
    cost_in_points = db.Column(db.Integer, default=0, nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)
    applied = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", back_populates="transfers")
    player_out = db.relationship("Player", foreign_keys=[player_out_id])
    player_in = db.relationship("Player", foreign_keys=[player_in_id])

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "player_out_id": self.player_out_id,
            "player_in_id": self.player_in_id,
            "player_out": self.player_out.to_dict() if self.player_out else None,
            "player_in": self.player_in.to_dict() if self.player_in else None,
            "matchday": self.matchday,
            "cost_in_points": self.cost_in_points,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "applied": self.applied,
        }


class BoosterUsage(db.Model):
    __tablename__ = "booster_usages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    booster_type = db.Column(db.String(30), nullable=False)
    matchday_used = db.Column(db.Integer, nullable=False)
    extra_data = db.Column(db.JSON, nullable=True)

    user = db.relationship("User", back_populates="booster_usages")

    __table_args__ = (
        db.UniqueConstraint("user_id", "booster_type", name="uq_user_booster"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "booster_type": self.booster_type,
            "matchday_used": self.matchday_used,
            "extra_data": self.extra_data,
        }


class MiniLeague(db.Model):
    __tablename__ = "mini_leagues"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(6), unique=True, nullable=False, index=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    creator = db.relationship("User", foreign_keys=[creator_id])
    standings = db.relationship(
        "MiniLeagueStanding", back_populates="league", lazy="dynamic"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "creator_id": self.creator_id,
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MiniLeagueStanding(db.Model):
    __tablename__ = "mini_league_standings"

    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey("mini_leagues.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    points = db.Column(db.Integer, default=0, nullable=False)
    rank = db.Column(db.Integer, nullable=True)
    last_week_rank = db.Column(db.Integer, nullable=True)

    league = db.relationship("MiniLeague", back_populates="standings")
    user = db.relationship("User", back_populates="mini_league_memberships")

    __table_args__ = (
        db.UniqueConstraint("league_id", "user_id", name="uq_league_user"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "league_id": self.league_id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "points": self.points,
            "rank": self.rank,
            "last_week_rank": self.last_week_rank,
        }
