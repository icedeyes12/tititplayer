"""
Core logic package for tititplayer.

Contains StateManager (MPV ↔ DB sync) and QueueEngine (playlist logic).
"""

from tititplayer.core.state import PlaybackState, RepeatMode, StateManager
from tititplayer.core.queue import QueueEngine, QueueEvent, QueueEventData, QueueState

__all__ = [
    "PlaybackState",
    "RepeatMode",
    "StateManager",
    "QueueEngine",
    "QueueEvent",
    "QueueEventData",
    "QueueState",
]
