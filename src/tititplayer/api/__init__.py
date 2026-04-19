"""
API package for tititplayer.

Provides FastAPI server and Pydantic schemas.
"""

from tititplayer.api.app import app, run_server

__all__ = ["app", "run_server"]
