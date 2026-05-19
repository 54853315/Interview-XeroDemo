from __future__ import annotations

import hmac
import json
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from .models import db, User, Workspace, OAuthToken
from .oauth import XeroOAuth2
from .decorators import login_required

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
app_bp = Blueprint("app", __name__)


def _fetch_connections(access_token: str) -> list[dict]:
    """调用 Xero Connections API，失败时返回空列表不影响主流程。"""
    try:
        oauth = XeroOAuth2()
        return oauth.get_connections(access_token)
    except Exception as exc:
        import sys
        print(f"[WARN] Xero Connections API failed: {exc}", file=sys.stderr)
        return []


def _sync_workspaces(user_id: int, connections: list[dict]) -> None:
    """根据 Xero Connections API 返回的数据同步 Workspace 记录。"""
    existing = {ws.xero_tenant_id for ws in Workspace.query.filter_by(user_id=user_id).all()}

    for conn in connections:
        tid = conn.get("tenantId")
        if not tid or tid in existing:
            continue
        ws = Workspace(
            user_id=user_id,
            name=conn.get("tenantName", "Unknown"),
            xero_tenant_id=tid,
            trial_account=False,
        )
        db.session.add(ws)


@app_bp.route("/")
def index() -> str:
    """Home page."""
    return render_template("index.html")


@app_bp.route("/login", methods=["GET", "POST"])
def login() -> str:
    """User login."""
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["email"] = user.email

            # 登录成功后绑定 pending Xero token
            pending_key = session.pop("pending_token_key", None)
            if pending_key:
                OAuthToken.claim_by_user(pending_key, user.id)

            # 同步 pending Xero workspace 数据
            pending_json = session.pop("pending_connections", None)
            if pending_json:
                _sync_workspaces(user.id, json.loads(pending_json))
                db.session.commit()

            flash("Logged in successfully!", "success")
            return redirect(url_for("app.dashboard"))

        flash("Invalid email or password", "error")

    return render_template("login.html")


@app_bp.route("/signup", methods=["GET", "POST"])
def signup() -> str:
    """User registration with Xero data prefill."""
    prefill_data = {}

    # 如果从 Xero OAuth 回调跳转过来
    if "xero_prefill" in session:
        prefill_data = session["xero_prefill"]

    if request.method == "POST":
        email = request.form.get("email")
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        password = request.form.get("password")

        if not email or not password:
            flash("Email and password are required", "error")
            return render_template("signup.html", prefill=prefill_data)

        if len(password) < 8 or not re.search(r"[a-zA-Z]", password) or not re.search(r"\d", password):
            flash("Password must be at least 8 characters and contain both letters and numbers", "error")
            return render_template("signup.html", prefill=prefill_data)

        existing = User.query.filter_by(email=email).first()
        if existing:
            if "pending_token_key" in session:
                flash("该邮箱已注册，请先登录以绑定 Xero 账号", "error")
            else:
                flash("Email already registered", "error")
            return render_template("signup.html", prefill=prefill_data)

        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=generate_password_hash(password),
            xero_id=prefill_data.get("xero_id"),
            xero_tenant_id=prefill_data.get("xero_tenant_id"),
        )
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        session["email"] = user.email

        # 绑定 pending OAuth token
        pending_key = session.pop("pending_token_key", None)
        if pending_key:
            OAuthToken.claim_by_user(pending_key, user.id)

        # 同步 pending Xero workspace 数据
        pending_json = session.pop("pending_connections", None)
        if pending_json:
            _sync_workspaces(user.id, json.loads(pending_json))
            db.session.commit()

        # 清理 prefill 数据
        session.pop("xero_prefill", None)

        flash("Account created successfully!", "success")
        return redirect(url_for("app.dashboard"))

    return render_template("signup.html", prefill=prefill_data)


@app_bp.route("/logout")
def logout() -> str:
    """User logout — 清理 session 和 OAuth token。"""
    user_id = session.get("user_id")
    if user_id:
        OAuthToken.query.filter_by(user_id=user_id).delete()
        db.session.commit()
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("app.index"))


@app_bp.route("/dashboard")
@login_required
def dashboard() -> str:
    """User dashboard."""
    user = User.query.get(session.get("user_id"))
    return render_template("dashboard.html", user=user)


# --- OAuth2 routes ---

@auth_bp.route("/xero/start")
def xero_start() -> str:
    """Start Xero OAuth2 flow."""
    try:
        oauth = XeroOAuth2()
        state = secrets.token_urlsafe(32)
        session["oauth_state"] = state
        auth_url = oauth.get_authorization_url(state=state)
        return redirect(auth_url)
    except Exception as exc:
        flash(f"Failed to start authorization: {exc}", "error")
        return redirect(url_for("app.index"))


@auth_bp.route("/xero/callback")
def xero_callback() -> str:
    """Handle Xero OAuth2 callback."""
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        flash(f"Authorization failed: {error}", "error")
        return redirect(url_for("app.index"))

    # 时序安全的 state 校验，单次使用
    stored_state = session.pop("oauth_state", None)
    if not code or not stored_state or not hmac.compare_digest(state or "", stored_state):
        flash("Invalid authorization response. Please try again.", "error")
        return redirect(url_for("app.index"))

    try:
        oauth = XeroOAuth2()
        token_data = oauth.exchange_code_for_token(code)
        access_token = token_data.get("access_token", "")
        id_token = token_data.get("id_token")

        # 获取 Xero organization 列表（失败不影响登录）
        connections = _fetch_connections(access_token)
        tenant_id = connections[0]["tenantId"] if connections else None

        # 解析 ID token 获取用户信息
        id_token_data = oauth.decode_id_token(id_token)
        email = id_token_data.get("email")
        given_name = id_token_data.get("given_name", "")
        family_name = id_token_data.get("family_name", "")

        # 检查用户是否已存在
        user = User.query.filter_by(email=email).first()

        if user:
            # 更新已有用户的 Xero 信息
            user.xero_id = id_token_data.get("sub")
            user.xero_tenant_id = tenant_id

            # 删除旧 token，保存新 token 到数据库
            OAuthToken.query.filter_by(user_id=user.id).delete()
            oauth_token = OAuthToken.from_token_response(
                user_id=user.id,
                token_data=token_data,
                tenant_id=tenant_id,
            )
            db.session.add(oauth_token)

            # 同步 Workspace 记录
            _sync_workspaces(user.id, connections)

            session["user_id"] = user.id
            session["email"] = user.email
            session.pop("pending_token_key", None)
            session.pop("xero_prefill", None)
            session.pop("pending_connections", None)

            db.session.commit()
            flash("Successfully authenticated with Xero!", "success")
            return redirect(url_for("app.dashboard"))
        else:
            # 新用户：token 存为 pending 记录
            session_key = secrets.token_urlsafe(32)
            oauth_token = OAuthToken.from_token_response(
                user_id=None,
                token_data=token_data,
                tenant_id=tenant_id,
            )
            oauth_token.session_key = session_key
            db.session.add(oauth_token)
            db.session.commit()

            session["xero_prefill"] = {
                "email": email,
                "first_name": given_name,
                "last_name": family_name,
                "xero_id": id_token_data.get("sub"),
                "xero_tenant_id": tenant_id,
            }
            session["pending_token_key"] = session_key
            # connections 序列化为 JSON 存入 session
            if connections:
                session["pending_connections"] = json.dumps(connections)
            flash("Please complete your registration", "info")
            return redirect(url_for("app.signup"))

    except Exception as exc:
        flash(f"Authorization failed: {exc}", "error")
        return redirect(url_for("app.index"))


def get_valid_token(user_id: int) -> OAuthToken | None:
    """获取用户有效的 OAuth token，过期时自动 refresh。"""
    token = OAuthToken.query.filter_by(user_id=user_id).first()
    if not token:
        return None
    if token.is_expired and token.refresh_token:
        try:
            oauth = XeroOAuth2()
            new_data = oauth.refresh_access_token(token.refresh_token)
            token.access_token = new_data.get("access_token", "")
            token.refresh_token = new_data.get("refresh_token")
            token.expires_at = datetime.utcnow() + timedelta(seconds=new_data.get("expires_in", 0))
            token.scope = new_data.get("scope")
            db.session.commit()
        except Exception:
            db.session.delete(token)
            db.session.commit()
            return None
    return token
