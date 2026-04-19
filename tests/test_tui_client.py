"""
Tests for the TUI HTTP client.

These tests mock HTTP responses to verify client behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tititplayer.tui.client import APIClient, APIClientError, close_client, get_client


@pytest.fixture
def api_client():
    """Create an API client instance."""
    return APIClient(base_url="http://localhost:8765")


class TestAPIClient:
    """Tests for APIClient."""

    @pytest.mark.asyncio
    async def test_connect_creates_client(self, api_client: APIClient):
        """Test connect creates HTTP client."""
        await api_client.connect()
        assert api_client._client is not None
        assert isinstance(api_client._client, httpx.AsyncClient)
        await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self, api_client: APIClient):
        """Test disconnect closes HTTP client."""
        await api_client.connect()
        assert api_client._client is not None
        await api_client.disconnect()
        assert api_client._client is None

    @pytest.mark.asyncio
    async def test_request_without_connect_raises(self, api_client: APIClient):
        """Test request without connecting raises error."""
        with pytest.raises(APIClientError, match="Client not connected"):
            await api_client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_get_status(self, api_client: APIClient):
        """Test get_status request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "ok"}

            await api_client.connect()
            result = await api_client.get_status()

            mock_request.assert_called_once_with("GET", "/api/v1/status")
            assert result["status"] == "ok"
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_play(self, api_client: APIClient):
        """Test play request with track_id."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "playing"}

            await api_client.connect()
            result = await api_client.play(track_id=1)

            mock_request.assert_called_once_with(
                "POST", "/api/v1/playback/play", json={"track_id": 1}
            )
            assert result["status"] == "playing"
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_play_without_track(self, api_client: APIClient):
        """Test play request without track_id."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "playing"}

            await api_client.connect()
            await api_client.play()

            mock_request.assert_called_once_with("POST", "/api/v1/playback/play", json={})
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_toggle_pause(self, api_client: APIClient):
        """Test toggle_pause request."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "paused"}

            await api_client.connect()
            await api_client.toggle_pause()

            mock_request.assert_called_once_with("POST", "/api/v1/playback/toggle")
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_set_volume(self, api_client: APIClient):
        """Test set_volume request."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"volume": 50}

            await api_client.connect()
            await api_client.set_volume(50)

            mock_request.assert_called_once_with(
                "POST", "/api/v1/playback/volume", json={"volume": 50}
            )
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_next_track(self, api_client: APIClient):
        """Test next_track request."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "playing"}

            await api_client.connect()
            await api_client.next_track()

            mock_request.assert_called_once_with("POST", "/api/v1/playback/next")
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_add_to_queue(self, api_client: APIClient):
        """Test add_to_queue request."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"items": []}

            await api_client.connect()
            await api_client.add_to_queue([1, 2, 3], position=0)

            mock_request.assert_called_once_with(
                "POST", "/api/v1/queue/add",
                json={"track_ids": [1, 2, 3], "position": 0}
            )
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_toggle_shuffle(self, api_client: APIClient):
        """Test toggle_shuffle request."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"shuffle_mode": True}

            await api_client.connect()
            await api_client.toggle_shuffle()

            mock_request.assert_called_once_with("POST", "/api/v1/queue/shuffle")
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_health_check_success(self, api_client: APIClient):
        """Test health_check returns True on success."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "healthy"}

            await api_client.connect()
            result = await api_client.health_check()

            assert result is True
            await api_client.disconnect()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, api_client: APIClient):
        """Test health_check returns False on error."""
        with patch.object(api_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = APIClientError("Connection failed")

            await api_client.connect()
            result = await api_client.health_check()

            assert result is False
            await api_client.disconnect()


class TestSingletonClient:
    """Tests for singleton client management."""

    @pytest.mark.asyncio
    async def test_get_client_creates_singleton(self):
        """Test get_client creates client."""
        client = await get_client()
        assert client is not None
        assert isinstance(client, APIClient)
        await close_client()

    @pytest.mark.asyncio
    async def test_close_client_clears_singleton(self):
        """Test close_client clears singleton."""
        await get_client()
        await close_client()

        # Global should be None
        from tititplayer.tui import client as client_module
        assert client_module._client is None
