"""
CLI entry point for tititplayer.

This launches the Textual TUI client.
"""

import click

from tititplayer.tui.app import run_tui


@click.command()
@click.version_option()
def main() -> None:
    """Tititplayer - Modern async terminal music player TUI."""
    click.echo("Starting tititplayer TUI...")
    run_tui()


if __name__ == "__main__":
    main()
