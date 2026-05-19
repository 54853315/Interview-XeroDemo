from __future__ import annotations

import click
from dotenv import load_dotenv

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
