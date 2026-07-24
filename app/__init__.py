import click
import threading
import time
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_caching import Cache
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

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

    # Heroku / Render style postgres URLs
    db_url = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url

    engine_opts = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {})
    if db_url.startswith("sqlite"):
        engine_opts["connect_args"] = {"timeout": 30}
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_opts

    if app.config.get("TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"

    @login_manager.unauthorized_handler
    def unauthorized():
        # API clients must get JSON 401 — HTML redirects break fetch().json()
        if request.path.startswith("/api/") or _wants_json():
            return jsonify({
                "success": False,
                "error": "NOT_AUTHENTICATED",
                "message": "Login required",
            }), 401
        return redirect(url_for(login_manager.login_view, next=request.path))

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

    # Create/upgrade schema without needing Render Shell
    should_migrate = (
        not flask_app.config.get("TESTING")
        and (
            flask_app.config.get("AUTO_MIGRATE")
            or (db_url.startswith("postgres://") or db_url.startswith("postgresql://"))
        )
    )
    if should_migrate:
        with flask_app.app_context():
            try:
                from flask_migrate import upgrade
                print("AUTO_MIGRATE: running flask db upgrade…", flush=True)
                upgrade()
                print("AUTO_MIGRATE: migrations applied", flush=True)
                flask_app.logger.info("Database migrations applied")
            except Exception as exc:
                print(f"AUTO_MIGRATE: upgrade failed ({exc}); falling back to create_all", flush=True)
                flask_app.logger.exception("AUTO_MIGRATE failed")
                try:
                    db.create_all()
                    print("AUTO_MIGRATE: create_all completed", flush=True)
                except Exception:
                    print("AUTO_MIGRATE: create_all also failed", flush=True)
                    flask_app.logger.exception("create_all failed")

            should_seed = flask_app.config.get("AUTO_SEED") or db_url.startswith(
                ("postgres://", "postgresql://")
            )
            if should_seed:
                try:
                    from app.models import Country, Player
                    from app.data.sync import (
                        seed_database,
                        sync_countries_and_players,
                        sync_fixtures,
                    )

                    if Country.query.count() == 0:
                        print("AUTO_SEED: seeding empty database…", flush=True)
                        result = seed_database()
                        print(f"AUTO_SEED: completed {result}", flush=True)
                        flask_app.logger.info("AUTO_SEED completed: %s", result)
                    else:
                        print("AUTO_SEED: skipped (countries already present)", flush=True)

                    if Player.query.count() == 0:
                        print("AUTO_SYNC: loading players…", flush=True)
                        players_result = sync_countries_and_players()
                        print(f"AUTO_SYNC: players {players_result}", flush=True)
                        fixtures_result = sync_fixtures()
                        print(f"AUTO_SYNC: fixtures {fixtures_result}", flush=True)
                    else:
                        print("AUTO_SYNC: skipped (players already present)", flush=True)

                    # Manual URI map from app/data/player_photos.py (instant, persisted)
                    try:
                        from app.data.player_photos import apply_manual_player_photos
                        manual = apply_manual_player_photos(only_missing=False)
                        print(f"AUTO_SYNC: manual photos {manual}", flush=True)
                    except Exception as manual_exc:
                        print(f"AUTO_SYNC: manual photos failed: {manual_exc}", flush=True)

                    # Always (re)scan for better coverage: untried first, then one retry of empties
                    from app.data.sync import _photo_stats

                    stats = _photo_stats()
                    if stats["untried"] > 0 or stats["no_match"] > 0:
                        print(
                            f"AUTO_SYNC: starting photo sync "
                            f"(have={stats['with_photo']}, untried={stats['untried']}, "
                            f"no_match={stats['no_match']}, exhausted={stats['exhausted']})…",
                            flush=True,
                        )

                        def _photo_worker(app):
                            with app.app_context():
                                from app.data.sync import _photo_stats, sync_player_photos
                                from app import db as _db

                                # Pass 1: never-tried (NULL)
                                for _ in range(80):
                                    left = _photo_stats()["untried"]
                                    if left == 0:
                                        break
                                    try:
                                        result = sync_player_photos(batch_size=40)
                                        print(f"AUTO_SYNC: photos {result}", flush=True)
                                    except Exception as photo_exc:
                                        print(f"AUTO_SYNC: photo batch failed: {photo_exc}", flush=True)
                                        _db.session.rollback()
                                        break
                                    time.sleep(1)

                                # Pass 2: retry "" once; failures become "-" and drop out of the queue
                                for _ in range(80):
                                    left = _photo_stats()["no_match"]
                                    if left == 0:
                                        break
                                    try:
                                        result = sync_player_photos(batch_size=40, retry_failed=True)
                                        print(f"AUTO_SYNC: photos retry {result}", flush=True)
                                    except Exception as photo_exc:
                                        print(f"AUTO_SYNC: photo retry failed: {photo_exc}", flush=True)
                                        _db.session.rollback()
                                        break
                                    time.sleep(1)

                                final = _photo_stats()
                                print(
                                    f"AUTO_SYNC: photo scan finished — {final['with_photo']} with photos, "
                                    f"{final['exhausted']} no match, {final['untried']} untried",
                                    flush=True,
                                )

                        threading.Thread(
                            target=_photo_worker,
                            args=(flask_app,),
                            daemon=True,
                            name="photo-sync",
                        ).start()
                except Exception as exc:
                    db.session.rollback()
                    print(f"AUTO_SEED/SYNC failed: {exc}", flush=True)
                    flask_app.logger.exception("AUTO_SEED failed")

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
    def _user_has_squad(user) -> bool:
        from app.models import FantasyTeam, FantasyTeamPlayer

        team = (
            FantasyTeam.query.filter_by(user_id=user.id)
            .order_by(FantasyTeam.matchday.desc())
            .first()
        )
        if not team:
            return False
        return FantasyTeamPlayer.query.filter_by(fantasy_team_id=team.id).count() > 0

    @app.route("/")
    def index():
        from flask_login import current_user

        if current_user.is_authenticated and _user_has_squad(current_user):
            return render_template("fantasy/dashboard.html")
        mode = "onboard" if current_user.is_authenticated else "guest"
        return render_template("welcome.html", mode=mode)

    @app.route("/dashboard")
    def dashboard_page():
        return render_template("fantasy/dashboard.html")

    @app.route("/squad")
    def squad_page():
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

    @app.route("/account")
    def account_page():
        return render_template("fantasy/account.html")

    @app.route("/admin")
    def admin_page():
        from flask import abort, redirect, url_for
        from flask_login import current_user

        if not current_user.is_authenticated:
            return redirect(url_for("login_page_redirect"))
        # Refresh flag from ADMIN_EMAILS in case env changed after register
        from app.auth.routes import _sync_admin_flag

        _sync_admin_flag(current_user)
        if not current_user.is_admin:
            abort(403)
        return render_template("fantasy/admin.html")

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

    @app.cli.command("sync-photos")
    def sync_photos_cmd():
        from app.data.sync import sync_player_photos
        result = sync_player_photos(force=True)
        click.echo(f"Photos: {result}")

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
