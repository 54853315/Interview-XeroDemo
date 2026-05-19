from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import session, redirect, url_for


def login_required(f: Callable) -> Callable:
    """Decorator to require user login."""

    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session:
            return redirect(url_for("app.login"))
        return f(*args, **kwargs)

    return decorated_function
