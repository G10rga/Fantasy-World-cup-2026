import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///wc2026_fantasy.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite needs connect timeout; Postgres pool options differ — applied in create_app if needed
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }
    TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") in ("1", "true", "True", "yes")
    WTF_CSRF_ENABLED = False  # API uses JSON + session cookies; forms validate via WTForms without CSRF tokens
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # On hosts without Shell (e.g. some Render plans), apply migrations at boot
    AUTO_MIGRATE = os.environ.get("AUTO_MIGRATE", "0") in ("1", "true", "True", "yes")
    AUTO_SEED = os.environ.get("AUTO_SEED", "0") in ("1", "true", "True", "yes")

    FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
    API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "")
    FOOTBALL_DATA_COMPETITION = "WC"
    FOOTBALL_DATA_SEASON = 2026
    API_FOOTBALL_LEAGUE_ID = 1
    API_FOOTBALL_SEASON = 2026
    API_FOOTBALL_DAILY_QUOTA = 90

    ADMIN_EMAILS = [
        e.strip().lower()
        for e in os.environ.get("ADMIN_EMAILS", "").split(",")
        if e.strip()
    ]

    CACHE_TYPE = os.environ.get("CACHE_TYPE", "SimpleCache")
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_REDIS_URL = os.environ.get("CACHE_REDIS_URL", "redis://localhost:6379/0")

    # Fantasy game constants
    SQUAD_SIZE = 15
    STARTING_XI_SIZE = 11
    BENCH_SIZE = 4
    POSITION_LIMITS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
    VALID_FORMATIONS = [
        (3, 4, 3),
        (3, 5, 2),
        (4, 3, 3),
        (4, 4, 2),
        (4, 5, 1),
        (5, 2, 3),
        (5, 3, 2),
        (5, 4, 1),
    ]
    BUDGET_GROUP_STAGE = 100.0
    BUDGET_KNOCKOUT = 105.0
    TRANSFER_PENALTY = 3
    FREE_TRANSFERS_GROUP = 2
    FREE_TRANSFERS_KNOCKOUT = 1
    MAX_ROLLOVER_TRANSFERS = 1
    SCOUTING_BONUS_THRESHOLD = 4
    SCOUTING_BONUS_OWNERSHIP_PCT = 5.0
    SCOUTING_BONUS_POINTS = 2

    # Fantasy scoring rules (official FIFA WC 2026)
    SCORING_GOAL_POINTS = {"GK": 9, "DEF": 7, "MID": 6, "FWD": 5}
    SCORING_APPEARANCE_POINTS = 1          # any minutes played (> 0)
    SCORING_60_MIN_BONUS = 1               # extra point for 60+ minutes
    SCORING_ASSIST_POINTS = 3
    SCORING_SHOTS_ON_TARGET_PER_POINT = 2  # FWD only: 1 point per N shots on target
    SCORING_CHANCES_CREATED_PER_POINT = 2  # MID only: 1 point per N chances created
    SCORING_CLEAN_SHEET = {"GK": 5, "DEF": 5, "MID": 1, "FWD": 0}
    SCORING_SAVES_PER_POINT = 3            # GK only
    SCORING_PENALTY_SAVED = 3
    SCORING_PENALTY_MISSED = -2
    SCORING_OWN_GOAL = -2
    SCORING_YELLOW_CARD = -1
    SCORING_RED_CARD = -2
    SCORING_TACKLES_PER_POINT = 3          # MID only
    SCORING_FREE_KICK_GOAL = 1

    COUNTRY_LIMITS = {
        "group": 3,
        "RO32": 3,
        "QF": 4,
        "SF": 5,
        "F": 6,
    }

    BOOSTER_TYPES = [
        "WILDCARD",
        "12TH_MAN",
        "MAX_CAPTAIN",
        "QUALIFICATION_BOOSTER",
        "MYSTERY",
    ]
    MYSTERY_BOOSTER_TYPE = os.environ.get("MYSTERY_BOOSTER_TYPE", "WILDCARD")

    # Cache TTLs (seconds)
    CACHE_TTL_PLAYERS = 3600
    CACHE_TTL_FIXTURES = 600
    CACHE_TTL_LIVE = 60
    CACHE_TTL_LIVE_IDLE = 600
    CACHE_TTL_STATS_FT = 86400

    # Scheduler intervals (seconds)
    SCHEDULER_LIVESCORES_INTERVAL = 60
    SCHEDULER_LIVESCORES_IDLE_INTERVAL = 600
    SCHEDULER_FIXTURES_INTERVAL = 600
    SCHEDULER_STATS_INTERVAL = 600

    PERMANENT_SESSION_LIFETIME = timedelta(days=30)


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    # Behind HTTPS reverse proxies (Render, Railway, Heroku, etc.)
    TRUST_PROXY = os.environ.get("TRUST_PROXY", "1") in ("1", "true", "True", "yes")
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "1") in ("1", "true", "True", "yes")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE
    # Default on in production so empty Postgres gets tables without Shell access
    AUTO_MIGRATE = os.environ.get("AUTO_MIGRATE", "1") in ("1", "true", "True", "yes")
    AUTO_SEED = os.environ.get("AUTO_SEED", "1") in ("1", "true", "True", "yes")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    CACHE_TYPE = "NullCache"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
