from __future__ import annotations

import json
import os
from typing import Any

import click
from dotenv import load_dotenv

from .oauth2 import OAuth2Handler
from .token_store import TokenStore
from .xero_client import XeroClient

load_dotenv()


@click.group()
def main() -> None:
    """XeroDemo CLI entrypoint."""


@main.command("web")
@click.option("--port", type=int, default=5000, help="Port to run the web server on.")
@click.option("--host", type=str, default="localhost", help="Host to bind to.")
def web(port: int, host: str) -> None:
    """Run the Flask web application."""
    from .web.app import create_app
    app = create_app()
    click.echo(f"Starting web server at http://{host}:{port}")
    app.run(host=host, port=port, debug=True)


@main.command("auth")
def auth() -> None:
    """Authenticate with Xero and store token."""
    client_id = os.getenv("XERO_CLIENT_ID")
    client_secret = os.getenv("XERO_CLIENT_SECRET")
    redirect_uri = os.getenv("XERO_REDIRECT_URI", "http://localhost:8080/callback")

    if not client_id or not client_secret:
        raise click.ClickException(
            "Missing XERO_CLIENT_ID or XERO_CLIENT_SECRET. "
            "Create .env file using .env.example as template."
        )

    oauth = OAuth2Handler(client_id, client_secret, redirect_uri)

    try:
        callback = oauth.authorize()
        if "error" in callback:
            raise click.ClickException(f"Authorization failed: {callback.get('error')}")

        code = callback.get("code")
        token_data = oauth.exchange_code_for_token(code)
        store = TokenStore()
        store.save(token_data)
        click.echo("✓ Authorization successful! Token saved.")
    except Exception as exc:
        raise click.ClickException(f"Authorization failed: {exc}") from exc
