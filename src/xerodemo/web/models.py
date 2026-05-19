from __future__ import annotations

from datetime import datetime, timedelta

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    """User model for account management."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    xero_id = db.Column(db.String(255), unique=True, nullable=True)
    xero_tenant_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workspaces = db.relationship("Workspace", back_populates="owner", cascade="all, delete-orphan")
    oauth_tokens = db.relationship("OAuthToken", backref="owner", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class Workspace(db.Model):
    """Workspace/Trial Account model."""

    __tablename__ = "workspaces"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    xero_tenant_id = db.Column(db.String(255), nullable=True, unique=True)
    trial_account = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("User", back_populates="workspaces")

    def __repr__(self) -> str:
        return f"<Workspace {self.name}>"


class OAuthToken(db.Model):
    """OAuth2 token 持久化存储。

    user_id 为 NULL 时表示 pending token（OAuth 回调时新用户尚未注册），
    通过 session_key 关联，注册后绑定用户并清空 session_key。
    """

    __tablename__ = "oauth_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    session_key = db.Column(db.String(64), nullable=True, index=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.String(512), nullable=True)
    token_type = db.Column(db.String(32), nullable=True, default="Bearer")
    expires_at = db.Column(db.DateTime, nullable=True)
    scope = db.Column(db.Text, nullable=True)
    tenant_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<OAuthToken user={self.user_id}>"

    @property
    def is_expired(self) -> bool:
        """判断 access_token 是否过期（预留 60 秒缓冲）。"""
        if self.expires_at is None:
            return True
        return datetime.utcnow() >= (self.expires_at - timedelta(seconds=60))

    @classmethod
    def from_token_response(
        cls,
        user_id: int | None,
        token_data: dict,
        tenant_id: str | None = None,
    ) -> OAuthToken:
        """从 Xero token 响应构建 OAuthToken 实例。"""
        expires_in = token_data.get("expires_in", 0)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        return cls(
            user_id=user_id,
            access_token=token_data.get("access_token", ""),
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scope=token_data.get("scope"),
            tenant_id=tenant_id,
        )

    @classmethod
    def claim_by_user(cls, session_key: str, user_id: int) -> OAuthToken | None:
        """将 pending token 绑定到用户，返回 token 或 None。"""
        token = cls.query.filter_by(session_key=session_key, user_id=None).first()
        if token:
            # 删除该用户已有的旧 token
            cls.query.filter_by(user_id=user_id).delete()
            token.user_id = user_id
            token.session_key = None
            db.session.commit()
        return token
