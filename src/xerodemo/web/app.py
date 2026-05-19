from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from .models import db, User, Workspace, OAuthToken


def _find_project_root() -> Path:
    """向上查找 pyproject.toml 定位项目根目录。"""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


_PROJECT_ROOT = _find_project_root()
_DB_DIR = _PROJECT_ROOT / "db"
_DB_DIR.mkdir(exist_ok=True)
_DEFAULT_DB_URI = f"sqlite:///{_DB_DIR / 'xerodemo.db'}"


def _resolve_sqlite_uri(db_uri: str) -> str:
    """解析 SQLite URI，确保目录存在，相对路径转为绝对路径。

    SQLite URI 格式：
      sqlite:///:memory:       — 内存数据库
      sqlite:///relative/db    — 相对路径（三斜杠）
      sqlite:////absolute/db   — 绝对路径（四斜杠）
    """
    if not db_uri.startswith("sqlite"):
        return db_uri

    # 内存数据库无需处理
    if ":memory:" in db_uri:
        return db_uri

    # 提取 sqlite:/// 之后的部分（去掉 scheme 和 netloc）
    # sqlite:///path → path 部分在三斜杠之后
    match = re.match(r"sqlite(?:\+\w+)?:///(.*)", db_uri)
    if not match:
        return db_uri

    db_path_str = match.group(1)

    # 绝对路径（原 URI 是四斜杠 sqlite:////，提取后以 / 开头）
    if db_path_str.startswith("/"):
        db_file = Path(db_path_str)
    else:
        # 相对路径，基于项目根目录解析
        db_file = _PROJECT_ROOT / db_path_str

    # 确保目录存在
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # 返回绝对路径 URI
    return f"sqlite:///{db_file}"


def create_app(config: Optional[dict] = None) -> Flask:
    """Create and configure Flask app."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Configuration
    db_uri = os.getenv("DATABASE_URL", _DEFAULT_DB_URI)
    db_uri = _resolve_sqlite_uri(db_uri)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")

    if config:
        app.config.update(config)

    # Initialize extensions
    db.init_app(app)

    # Create tables
    with app.app_context():
        db.create_all()

    # Register blueprints
    from .routes import auth_bp, app_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(app_bp)

    return app
