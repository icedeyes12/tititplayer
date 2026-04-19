"""
Daemon entry point for tititplayer.

Starts the MPV connection and HTTP API server.
"""

import click

from tititplayer.api.app import run_server
from tititplayer.config import API_HOST, API_PORT


@click.command()
@click.option("--port", default=API_PORT, help="API server port")
@click.option("--host", default=API_HOST, help="API server host")
def main(host: str, port: int) -> None:
    """Start the tititplayer daemon."""
    click.echo(f"Starting tititplayer daemon on {host}:{port}")
    run_server(host=host, port=port)


if __name__ == "__main__":
    main()
