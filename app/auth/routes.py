from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.auth.forms import LoginForm, RegisterForm
from app.models import (
    BoosterUsage,
    Country,
    FantasyTeam,
    MiniLeague,
    MiniLeagueStanding,
    Transfer,
    User,
)

auth_bp = Blueprint("auth", __name__)


def _json_success(data=None, status=200):
    payload = {"success": True}
    if data:
        payload.update(data)
    return jsonify(payload), status


def _json_error(code, message, details=None, status=400):
    payload = {"success": False, "error": code, "message": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status


def _admin_emails() -> list[str]:
    return [e.lower() for e in current_app.config.get("ADMIN_EMAILS", [])]


def _sync_admin_flag(user: User) -> bool:
    """Keep is_admin aligned with ADMIN_EMAILS (promote or demote on login/me)."""
    should = user.email.lower() in _admin_emails()
    if bool(user.is_admin) != should:
        user.is_admin = should
        db.session.commit()
        return True
    return False


def _delete_user_account(user: User) -> None:
    """Remove a user and all owned fantasy data. Does not touch players/fixtures."""
    uid = user.id

    created_leagues = MiniLeague.query.filter_by(creator_id=uid).all()
    for league in created_leagues:
        MiniLeagueStanding.query.filter_by(league_id=league.id).delete(synchronize_session=False)
        db.session.delete(league)

    MiniLeagueStanding.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Transfer.query.filter_by(user_id=uid).delete(synchronize_session=False)
    BoosterUsage.query.filter_by(user_id=uid).delete(synchronize_session=False)

    for team in FantasyTeam.query.filter_by(user_id=uid).all():
        db.session.delete(team)  # cascades FantasyTeamPlayer via delete-orphan

    db.session.delete(user)
    db.session.commit()


@auth_bp.route("/login", methods=["GET"])
def login_page():
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET"])
def register_page():
    return render_template("auth/register.html")


@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    # JSON null for optional int must not reach IntegerField raw processing.
    if data.get("supported_nation_id") in (None, "", "null", "undefined"):
        data.pop("supported_nation_id", None)

    form = RegisterForm(data=data, meta={"csrf": False})

    if not form.validate():
        errors = {k: (v[0] if isinstance(v, (list, tuple)) else v) for k, v in form.errors.items()}
        message = next(iter(errors.values()), "Invalid registration data")
        return _json_error("VALIDATION_ERROR", message, errors)

    if User.query.filter_by(email=form.email.data.lower()).first():
        return _json_error("EMAIL_EXISTS", "Email already registered")

    if User.query.filter_by(username=form.username.data).first():
        return _json_error("USERNAME_EXISTS", "Username already taken")

    nation_id = form.supported_nation_id.data
    if nation_id and not db.session.get(Country, nation_id):
        return _json_error("INVALID_NATION", "Selected nation not found")

    user = User(
        email=form.email.data.lower(),
        username=form.username.data,
        supported_nation_id=nation_id,
    )
    user.set_password(form.password.data)
    user.is_admin = user.email in _admin_emails()

    db.session.add(user)
    db.session.commit()
    login_user(user)

    return _json_success({"user": user.to_dict()}, 201)


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    form = LoginForm(data=data, meta={"csrf": False})

    if not form.validate():
        errors = {k: (v[0] if isinstance(v, (list, tuple)) else v) for k, v in form.errors.items()}
        message = next(iter(errors.values()), "Invalid login data")
        return _json_error("VALIDATION_ERROR", message, errors)

    user = User.query.filter_by(email=form.email.data.lower()).first()
    if not user or not user.check_password(form.password.data):
        return _json_error("INVALID_CREDENTIALS", "Invalid email or password", status=401)

    _sync_admin_flag(user)
    login_user(user, remember=True)
    return _json_success({"user": user.to_dict()})


@auth_bp.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return _json_success()


@auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    if not current_user.is_authenticated:
        return _json_error("NOT_AUTHENTICATED", "Not logged in", status=401)
    _sync_admin_flag(current_user)
    return _json_success({"user": current_user.to_dict()})


@auth_bp.route("/api/auth/account", methods=["DELETE"])
@login_required
def delete_account():
    """Permanently delete the signed-in account and all fantasy data."""
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    confirm = (data.get("confirm") or "").strip().upper()

    if confirm != "DELETE":
        return _json_error(
            "CONFIRMATION_REQUIRED",
            'Type DELETE in the confirm field to permanently remove your account',
        )
    if not current_user.check_password(password):
        return _json_error("INVALID_CREDENTIALS", "Password is incorrect", status=401)

    user = db.session.get(User, current_user.id)
    logout_user()
    _delete_user_account(user)
    return _json_success({"deleted": True})
