"""
Daemon entry point for tititplayer.

Starts the MPV connection and HTTP API server.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys

import click

from tititplayer.api.app import run_server
from tititplayer.config import API_HOST, API_PORT, MPV_SOCKET_PATH


def check_mpv_binary() -> bool:
    """Check if MPV binary is installed."""
    return shutil.which("mpv") is not None


def is_mpv_running() -> bool:
    """Check if MPV is already running with IPC socket."""
    return MPV_SOCKET_PATH.exists()


async def start_mpv() -> subprocess.Popen | None:
    """
    Start MPV daemon with IPC socket.

    Returns the process handle if started, None if already running.
    """
    # Pre-check: MPV binary exists?
    if not check_mpv_binary():
        click.echo("[MPV] Error: 'mpv' binary not found", err=True)
        click.echo("Install with: pkg install mpv (Termux) or apt install mpv", err=True)
        sys.exit(1)

    # Check if already running
    if is_mpv_running():
        click.echo(f"[MPV] Already running (socket exists at {MPV_SOCKET_PATH})")
        return None

    # Ensure parent directory exists
    MPV_SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Start MPV with idle mode and IPC socket
    mpv_cmd = [
        "mpv",
        "--idle",  # Stay idle when no file
        f"--input-ipc-server={MPV_SOCKET_PATH}",
        "--no-video",  # Audio only
        "--really-quiet",  # Minimal output
    ]

    click.echo(f"[MPV] Starting: {' '.join(mpv_cmd)}")

    try:
        process = subprocess.Popen(
            mpv_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # Detach from current process group
        )
        click.echo(f"[MPV] Started daemon (PID: {process.pid})")

        # Wait for socket to appear
        for i in range(100):  # 10 seconds timeout
            if MPV_SOCKET_PATH.exists():
                click.echo(f"[MPV] Socket ready at {MPV_SOCKET_PATH}")
                return process
            if process.poll() is not None:
                # MPV exited - capture stderr
                _, stderr = process.communicate()
                click.echo(f"[MPV] Error: MPV exited with code {process.returncode}", err=True)
                if stderr:
                    click.echo(f"[MPV] stderr: {stderr.decode()}", err=True)
                sys.exit(1)
            await asyncio.sleep(0.1)
            if i == 50:
                click.echo("[MPV] Still waiting for socket...")

        click.echo("[MPV] Warning: Socket not created after 10s", err=True)
        # Check if process is still alive
        if process.poll() is not None:
            _, stderr = process.communicate()
            click.echo(f"[MPV] Error: MPV exited with code {process.returncode}", err=True)
            if stderr:
                click.echo(f"[MPV] stderr: {stderr.decode()}", err=True)
            sys.exit(1)
        return process

    except FileNotFoundError:
        click.echo("[MPV] Error: 'mpv' binary not found", err=True)
        click.echo("Install with: pkg install mpv (Termux) or apt install mpv", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"[MPV] Error starting MPV: {e}", err=True)
        sys.exit(1)


@click.command()
@click.option("--port", default=API_PORT, help="API server port")
@click.option("--host", default=API_HOST, help="API server host")
@click.option("--no-mpv", is_flag=True, help="Don't auto-start MPV daemon")
def main(host: str, port: int, no_mpv: bool) -> None:
    """
    Start the tititplayer daemon.

    Automatically starts MPV if not already running.
    """
    mpv_process = None

    if not no_mpv:
        # Start MPV if not running
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mpv_process = loop.run_until_complete(start_mpv())
        finally:
            loop.close()

    click.echo(f"Starting tititplayer daemon on {host}:{port}")

    try:
        run_server(host=host, port=port)
    finally:
        # Cleanup: stop MPV if we started it
        if mpv_process and mpv_process.poll() is None:
            click.echo("\n[MPV] Stopping daemon...")
            mpv_process.terminate()
            try:
                mpv_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                mpv_process.kill()


if __name__ == "__main__":
    main()
