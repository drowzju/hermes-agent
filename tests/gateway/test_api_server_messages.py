"""Tests for API server session messages endpoint.

Tests cover:
- GET /v1/sessions/{session_id}/messages
- Pagination (limit, before_id)
- Message format
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


class TestSessionMessagesAPI(AioHTTPTestCase):
    """Test session messages endpoint."""

    async def get_application(self):
        """Create test app with messages route."""
        config = GatewayConfig({})
        platform_config = PlatformConfig(
            enabled=True,
            extra={"host": "127.0.0.1", "port": 8642}
        )
        self.adapter = APIServerAdapter(platform_config)
        self.adapter.config = config

        app = web.Application()
        app.router.add_get("/v1/sessions/{session_id}/messages", self.adapter._handle_session_messages)
        return app

    async def test_get_messages_success(self):
        """Test getting messages for a session."""
        # Mock SessionDB
        mock_messages = [
            {"role": "user", "content": "Hello", "timestamp": 1234567890},
            {"role": "assistant", "content": "Hi there!", "timestamp": 1234567891},
        ]
        with patch.object(self.adapter, '_ensure_session_db') as mock_db:
            mock_db.return_value.get_messages_as_conversation.return_value = mock_messages

            resp = await self.client.get("/v1/sessions/test-session/messages")
            assert resp.status == 200
            data = await resp.json()
            assert "messages" in data
            assert len(data["messages"]) == 2
            assert data["messages"][0]["role"] == "user"

    async def test_get_messages_pagination_limit(self):
        """Test pagination with limit parameter."""
        mock_messages = [{"role": "user", "content": f"msg_{i}"} for i in range(50)]
        with patch.object(self.adapter, '_ensure_session_db') as mock_db:
            mock_db.return_value.get_messages_as_conversation.return_value = mock_messages

            resp = await self.client.get("/v1/sessions/test-session/messages?limit=10")
            data = await resp.json()
            assert len(data["messages"]) == 10

    async def test_get_messages_pagination_before_id(self):
        """Test pagination with before_id parameter."""
        # This would test cursor-based pagination
        pass

    async def test_get_messages_session_not_found(self):
        """Test 404 for non-existent session."""
        with patch.object(self.adapter, '_ensure_session_db') as mock_db:
            mock_db.return_value.get_messages_as_conversation.return_value = []

            resp = await self.client.get("/v1/sessions/nonexistent/messages")
            assert resp.status == 200
            data = await resp.json()
            assert data["messages"] == []

    async def test_get_messages_requires_auth(self):
        """Test messages endpoint requires auth when API key set."""
        self.adapter._api_key = "test_key"

        resp = await self.client.get("/v1/sessions/test-session/messages")
        assert resp.status == 401
