from xerodemo.web.app import create_app


def test_web_app_creation() -> None:
    """Test Flask app creation."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    assert app is not None
    assert app.config["TESTING"] is True
