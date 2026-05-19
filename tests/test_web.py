import json
from datetime import datetime, timedelta

from xerodemo.web.app import create_app, db
from xerodemo.web.models import OAuthToken, User, Workspace
from xerodemo.web.routes import _sync_workspaces, _fetch_connections


def test_web_app_creation() -> None:
    """Test Flask app creation."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    assert app is not None
    assert app.config["TESTING"] is True


def test_home_page() -> None:
    """Test home page loads."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_client() as client:
        response = client.get("/")
        assert response.status_code == 200
        assert b"Welcome" in response.data or b"XeroDemo" in response.data


def test_login_page() -> None:
    """Test login page loads."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_client() as client:
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Login" in response.data


def test_signup_page() -> None:
    """Test signup page loads."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_client() as client:
        response = client.get("/signup")
        assert response.status_code == 200
        assert b"Create Account" in response.data


def test_user_signup() -> None:
    """Test user registration."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    with app.app_context():
        db.create_all()

        with app.test_client() as client:
            response = client.post(
                "/signup",
                data={
                    "email": "test@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "password": "password123",
                },
                follow_redirects=True,
            )
            assert response.status_code == 200


def test_weak_password_rejected() -> None:
    """Test 弱密码注册被拒绝。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        with app.test_client() as client:
            # 太短
            response = client.post("/signup", data={"email": "weak1@example.com", "password": "ab1"}, follow_redirects=True)
            assert b"Password must be at least 8" in response.data

            # 只有字母
            response = client.post("/signup", data={"email": "weak2@example.com", "password": "abcdefgh"}, follow_redirects=True)
            assert b"Password must be at least 8" in response.data

            # 只有数字
            response = client.post("/signup", data={"email": "weak3@example.com", "password": "12345678"}, follow_redirects=True)
            assert b"Password must be at least 8" in response.data


def test_dashboard_requires_login() -> None:
    """Test dashboard is protected."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_client() as client:
        response = client.get("/dashboard")
        assert response.status_code == 302
        assert "login" in response.location.lower()


# --- 模型测试 ---

def test_oauth_token_creation() -> None:
    """Test OAuthToken 模型创建和查询。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        user = User(email="token@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        token = OAuthToken.from_token_response(
            user_id=user.id,
            token_data={
                "access_token": "test_access",
                "refresh_token": "test_refresh",
                "token_type": "Bearer",
                "expires_in": 1800,
                "scope": "openid profile email",
            },
            tenant_id="tenant_123",
        )
        db.session.add(token)
        db.session.commit()

        retrieved = OAuthToken.query.filter_by(user_id=user.id).first()
        assert retrieved is not None
        assert retrieved.access_token == "test_access"
        assert retrieved.refresh_token == "test_refresh"
        assert retrieved.token_type == "Bearer"
        assert retrieved.tenant_id == "tenant_123"
        assert retrieved.scope == "openid profile email"
        assert retrieved.expires_at is not None


def test_oauth_token_is_expired() -> None:
    """Test OAuthToken 过期判断。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()

        expired_token = OAuthToken(
            access_token="expired",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.session.add(expired_token)
        db.session.commit()
        assert expired_token.is_expired is True

        valid_token = OAuthToken(
            access_token="valid",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(valid_token)
        db.session.commit()
        assert valid_token.is_expired is False

        no_expiry = OAuthToken(access_token="no_expiry")
        assert no_expiry.is_expired is True


def test_pending_token_claim() -> None:
    """Test pending token 通过 session_key 绑定到用户。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        user = User(email="claim@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        pending = OAuthToken(
            access_token="pending_access",
            refresh_token="pending_refresh",
            session_key="test_session_key",
            user_id=None,
        )
        db.session.add(pending)
        db.session.commit()

        result = OAuthToken.claim_by_user("test_session_key", user.id)
        assert result is not None
        assert result.user_id == user.id
        assert result.session_key is None


# --- Workspace 同步测试 ---

MOCK_CONNECTIONS = [
    {"id": "conn1", "tenantId": "tenant_abc", "tenantName": "Demo Company", "tenantType": "ORGANISATION"},
    {"id": "conn2", "tenantId": "tenant_xyz", "tenantName": "Xero Practice", "tenantType": "ORGANISATION"},
]


def test_sync_workspaces_creates_records() -> None:
    """Test _sync_workspaces 根据 Connections API 数据创建 Workspace。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        user = User(email="ws@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        _sync_workspaces(user.id, MOCK_CONNECTIONS)
        db.session.commit()

        workspaces = Workspace.query.filter_by(user_id=user.id).all()
        assert len(workspaces) == 2
        names = {ws.name for ws in workspaces}
        assert "Demo Company" in names
        assert "Xero Practice" in names
        tenant_ids = {ws.xero_tenant_id for ws in workspaces}
        assert "tenant_abc" in tenant_ids
        assert "tenant_xyz" in tenant_ids


def test_sync_workspaces_no_duplicates() -> None:
    """Test _sync_workspaces 不创建重复 workspace。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        user = User(email="nodup@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        # 第一次同步
        _sync_workspaces(user.id, MOCK_CONNECTIONS)
        db.session.commit()

        # 第二次同步相同数据 — 不应产生重复
        _sync_workspaces(user.id, MOCK_CONNECTIONS)
        db.session.commit()

        assert Workspace.query.filter_by(user_id=user.id).count() == 2


def test_sync_workspaces_empty_connections() -> None:
    """Test _sync_workspaces 空 connections 不创建记录。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        user = User(email="empty@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        _sync_workspaces(user.id, [])
        db.session.commit()

        assert Workspace.query.filter_by(user_id=user.id).count() == 0


def test_fetch_connections_returns_empty_on_failure() -> None:
    """Test _fetch_connections API 失败时返回空列表。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        # 无效 token，API 调用必然失败
        result = _fetch_connections("invalid_token")
        assert result == []


# --- 路由集成测试 ---

def test_logout_clears_tokens() -> None:
    """Test 登出后 OAuth token 被删除。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        user = User(email="logout@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        token = OAuthToken(user_id=user.id, access_token="to_be_deleted")
        db.session.add(token)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = user.id

            response = client.get("/logout", follow_redirects=True)
            assert response.status_code == 200
            assert OAuthToken.query.filter_by(user_id=user.id).first() is None


def test_oauth_callback_rejects_invalid_state() -> None:
    """Test OAuth 回调拒绝不匹配的 state。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["oauth_state"] = "correct_state"

        response = client.get("/auth/xero/callback?code=test&state=wrong_state")
        assert response.status_code == 302


def test_duplicate_signup_shows_error() -> None:
    """Test 重复 email 注册显示错误。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        user = User(email="dup@example.com", password_hash="hash")
        db.session.add(user)
        db.session.commit()

        with app.test_client() as client:
            response = client.post(
                "/signup",
                data={
                    "email": "dup@example.com",
                    "first_name": "Dup",
                    "last_name": "User",
                    "password": "password123",
                },
                follow_redirects=True,
            )
            assert response.status_code == 200
            assert b"already registered" in response.data or "已注册" in response.data.decode("utf-8")


def test_login_binds_pending_token() -> None:
    """Test 登录后绑定 pending Xero token。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()

        from werkzeug.security import generate_password_hash
        user = User(email="bind@example.com", password_hash=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        pending = OAuthToken(
            access_token="pending_token",
            session_key="login_bind_key",
            user_id=None,
        )
        db.session.add(pending)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["pending_token_key"] = "login_bind_key"

            response = client.post(
                "/login",
                data={"email": "bind@example.com", "password": "pass123"},
                follow_redirects=True,
            )
            assert response.status_code == 200

            token = OAuthToken.query.filter_by(user_id=user.id).first()
            assert token is not None
            assert token.access_token == "pending_token"
            assert token.session_key is None


def test_signup_with_pending_connections() -> None:
    """Test 注册时 pending_connections 同步 Workspace。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["pending_token_key"] = "signup_ws_key"
                sess["pending_connections"] = json.dumps(MOCK_CONNECTIONS)
                sess["xero_prefill"] = {"email": "wssignup@example.com"}

            response = client.post(
                "/signup",
                data={
                    "email": "wssignup@example.com",
                    "first_name": "WS",
                    "last_name": "Test",
                    "password": "password123",
                },
                follow_redirects=True,
            )
            assert response.status_code == 200

            # 验证 workspace 已创建
            user = User.query.filter_by(email="wssignup@example.com").first()
            assert user is not None
            workspaces = Workspace.query.filter_by(user_id=user.id).all()
            assert len(workspaces) == 2


def test_login_with_pending_connections() -> None:
    """Test 登录时 pending_connections 同步 Workspace。"""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()

        from werkzeug.security import generate_password_hash
        user = User(email="wslogin@example.com", password_hash=generate_password_hash("pass123"))
        db.session.add(user)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["pending_token_key"] = "login_ws_key"
                sess["pending_connections"] = json.dumps(MOCK_CONNECTIONS)

            response = client.post(
                "/login",
                data={"email": "wslogin@example.com", "password": "pass123"},
                follow_redirects=True,
            )
            assert response.status_code == 200

            workspaces = Workspace.query.filter_by(user_id=user.id).all()
            assert len(workspaces) == 2
