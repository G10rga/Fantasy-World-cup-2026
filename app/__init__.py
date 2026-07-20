import click
from flask import Flask, jsonify, render_template
from flask_caching import Cache
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
cache = Cache()


def create_app(config_name=None):
    import os
    from app.config import config_by_name

    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    if config_name not in config_by_name:
        config_name = "default"

    app = Flask(__name__, static_folder="../static", template_folder="templates")
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"

    cache_config = {
        "CACHE_TYPE": app.config.get("CACHE_TYPE", "SimpleCache"),
        "CACHE_DEFAULT_TIMEOUT": app.config.get("CACHE_DEFAULT_TIMEOUT", 300),
    }
    if app.config.get("CACHE_TYPE") == "RedisCache":
        cache_config["CACHE_REDIS_URL"] = app.config.get("CACHE_REDIS_URL")
    cache.init_app(app, config=cache_config)

    from app.auth.routes import auth_bp
    from app.fantasy.routes import fantasy_bp
    from app.leagues.routes import leagues_bp
    from app import models as _models  # noqa: F401 — register models with SQLAlchemy

    flask_app = app
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(fantasy_bp)
    flask_app.register_blueprint(leagues_bp)

    register_cli(flask_app)
    register_page_routes(flask_app)

    if not flask_app.config.get("TESTING"):
        from app.data.scheduler import init_scheduler
        init_scheduler(flask_app)

    @flask_app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify({"success": False, "error": "NOT_FOUND", "message": "Resource not found"}), 404
        return render_template("404.html"), 404

    @flask_app.errorhandler(500)
    def server_error(e):
        if _wants_json():
            return jsonify({"success": False, "error": "SERVER_ERROR", "message": "Internal server error"}), 500
        return render_template("500.html"), 500

    return flask_app


def _wants_json():
    from flask import request
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def register_page_routes(app):
    @app.route("/")
    def index():
        return render_template("fantasy/squad_builder.html")

    @app.route("/my-team")
    def my_team_page():
        return render_template("fantasy/my_team.html")

    @app.route("/transfers")
    def transfers_page():
        return render_template("fantasy/transfers.html")

    @app.route("/points")
    def points_page():
        return render_template("fantasy/points.html")

    @app.route("/fixtures")
    def fixtures_page():
        return render_template("fantasy/fixtures.html")

    @app.route("/leagues")
    def leagues_page():
        return render_template("leagues/leagues.html")

    @app.route("/leaderboard")
    def leaderboard_page():
        return render_template("fantasy/leaderboard.html")

    @app.route("/login")
    def login_page_redirect():
        return render_template("auth/login.html")

    @app.route("/register")
    def register_page_redirect():
        return render_template("auth/register.html")


def register_cli(app):
    @app.cli.command("seed-db")
    def seed_db_cmd():
        from app.data.sync import seed_database
        result = seed_database()
        click.echo(f"Seeded: {result}")

    @app.cli.command("sync-players")
    def sync_players_cmd():
        from app.data.sync import sync_countries_and_players
        result = sync_countries_and_players()
        click.echo(f"Synced: {result}")

    @app.cli.command("sync-fixtures")
    def sync_fixtures_cmd():
        from app.data.sync import sync_fixtures
        result = sync_fixtures()
        click.echo(f"Synced: {result}")

    @app.cli.command("sync-all")
    def sync_all_cmd():
        from app.data.sync import seed_database, sync_countries_and_players, sync_fixtures
        click.echo("Run seed-db separately for first-time setup.")
        click.echo(sync_countries_and_players())
        click.echo(sync_fixtures())
