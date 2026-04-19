"""
Tests for the MPV IPC client.

Note: These tests require a running MPV instance with IPC enabled.
Run MPV with: mpv --idle --input-ipc-server=~/.mpvsocket
"""

from unittest.mock import MagicMock

import pytest

from tititplayer.mpv.client import MPVClient, MPVEvent


@pytest.fixture
def mpv_client():
    """Create an MPV client instance."""
    return MPVClient()


class TestMPVClient:
    """Tests for MPVClient without requiring actual MPV instance."""

    def test_initial_state(self, mpv_client: MPVClient):
        """Test initial state is correct."""
        assert mpv_client.state.filename == ""
        assert mpv_client.state.pause is True
        assert mpv_client.state.volume == 100

    def test_is_connected_false_initially(self, mpv_client: MPVClient):
        """Test that is_connected is False initially."""
        assert mpv_client.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_fails_without_socket(self, mpv_client: MPVClient):
        """Test that connect raises error when socket doesn't exist."""
        with pytest.raises(ConnectionError):
            await mpv_client.connect()

    @pytest.mark.asyncio
    async def test_disconnect_safe_when_not_connected(self, mpv_client: MPVClient):
        """Test that disconnect is safe when not connected."""
        await mpv_client.disconnect()  # Should not raise

    def test_add_remove_event_callback(self, mpv_client: MPVClient):
        """Test adding and removing event callbacks."""
        callback = MagicMock()
        mpv_client.add_event_callback(callback)
        assert callback in mpv_client._event_callbacks

        mpv_client.remove_event_callback(callback)
        assert callback not in mpv_client._event_callbacks

    def test_state_property(self, mpv_client: MPVClient):
        """Test state property returns current state."""
        state = mpv_client.state
        assert state.pause is True
        assert state.volume == 100


class TestMPVEvent:
    """Tests for MPVEvent dataclass."""

    def test_from_dict_property_change(self):
        """Test creating MPVEvent from a property-change dict."""
        data = {
            "event": "property-change",
            "name": "pause",
            "data": True,
            "id": 1,
        }
        event = MPVEvent.from_dict(data)
        assert event.event == "property-change"
        assert event.name == "pause"
        assert event.data is True
        assert event.id == 1

    def test_from_dict_seek(self):
        """Test creating MPVEvent from a seek event."""
        data = {"event": "seek"}
        event = MPVEvent.from_dict(data)
        assert event.event == "seek"
        assert event.name is None
        assert event.data is None


class TestMPVIntegration:
    """
    Integration tests that require a running MPV instance.

    Run these tests manually with MPV running:
    mpv --idle --input-ipc-server=~/.mpvsocket
    """

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration tests require running MPV instance")
    async def test_connect_and_disconnect(self, mpv_client: MPVClient):
        """Test connecting to and disconnecting from MPV."""
        try:
            await mpv_client.connect()
            assert mpv_client.is_connected
        finally:
            await mpv_client.disconnect()
            assert not mpv_client.is_connected

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration tests require running MPV instance")
    async def test_set_volume(self, mpv_client: MPVClient):
        """Test setting volume via MPV."""
        try:
            await mpv_client.connect()
            await mpv_client.set_volume(50)
            # Should not raise
        finally:
            await mpv_client.disconnect()
