"""Tests for API server exec approval functionality.

Tests cover:
- send_exec_approval method
- GET /v1/approvals/pending endpoint
- POST /v1/approvals/{id}/resolve endpoint
- Approval timeout and expiration
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


class TestExecApprovalAPI(AioHTTPTestCase):
    """Test exec approval endpoints."""

    async def get_application(self):
        """Create test app with approval routes."""
        config = GatewayConfig({})
        platform_config = PlatformConfig(
            enabled=True,
            extra={"host": "127.0.0.1", "port": 8642}
        )
        self.adapter = APIServerAdapter(platform_config)
        self.adapter.config = config

        app = web.Application()
        app.router.add_get("/v1/approvals/pending", self.adapter._handle_approvals_list)
        app.router.add_post("/v1/approvals/{approval_id}/resolve", self.adapter._handle_approval_resolve)
        return app

    async def setUpAsync(self):
        await super().setUpAsync()
        # Clear pending approvals before each test
        if hasattr(self.adapter, '_pending_approvals'):
            self.adapter._pending_approvals.clear()

    async def test_list_pending_approvals_empty(self):
        """Test listing approvals when none pending."""
        resp = await self.client.get("/v1/approvals/pending")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"approvals": []}

    async def test_send_exec_approval_creates_pending(self):
        """Test send_exec_approval creates a pending approval."""
        result = await self.adapter.send_exec_approval(
            chat_id="test_chat",
            command="rm -rf /important",
            session_key="test_session",
            description="dangerous delete"
        )
        assert result.success is True
        assert result.message_id is not None

        # Verify it's in pending list
        resp = await self.client.get("/v1/approvals/pending")
        data = await resp.json()
        assert len(data["approvals"]) == 1
        assert data["approvals"][0]["command"] == "rm -rf /important"
        assert data["approvals"][0]["status"] == "pending"

    async def test_resolve_approval_allow_once(self):
        """Test resolving approval with allow-once."""
        # Create an approval first
        result = await self.adapter.send_exec_approval(
            chat_id="test_chat",
            command="rm -rf /",
            session_key="test_session"
        )
        approval_id = result.message_id

        # Resolve it
        resp = await self.client.post(
            f"/v1/approvals/{approval_id}/resolve",
            json={"decision": "allow-once"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True

        # Verify it's no longer pending
        resp = await self.client.get("/v1/approvals/pending")
        data = await resp.json()
        assert len(data["approvals"]) == 0

    async def test_resolve_approval_deny(self):
        """Test resolving approval with deny."""
        result = await self.adapter.send_exec_approval(
            chat_id="test_chat",
            command="rm -rf /",
            session_key="test_session"
        )
        approval_id = result.message_id

        resp = await self.client.post(
            f"/v1/approvals/{approval_id}/resolve",
            json={"decision": "deny"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True

    async def test_resolve_nonexistent_approval(self):
        """Test resolving non-existent approval returns 404."""
        resp = await self.client.post(
            "/v1/approvals/nonexistent/resolve",
            json={"decision": "allow-once"}
        )
        assert resp.status == 404

    async def test_approval_contains_required_fields(self):
        """Test approval object contains all required fields."""
        await self.adapter.send_exec_approval(
            chat_id="test_chat",
            command="rm -rf /important",
            session_key="test_session_123",
            description="test description"
        )

        resp = await self.client.get("/v1/approvals/pending")
        data = await resp.json()
        approval = data["approvals"][0]

        assert "id" in approval
        assert "command" in approval
        assert "session_key" in approval
        assert "description" in approval
        assert "created_at" in approval
        assert "status" in approval
        assert approval["command"] == "rm -rf /important"
        assert approval["session_key"] == "test_session_123"
        assert approval["description"] == "test description"

    async def test_multiple_approvals_pending(self):
        """Test multiple approvals can be pending simultaneously."""
        for i in range(3):
            await self.adapter.send_exec_approval(
                chat_id=f"chat_{i}",
                command=f"command_{i}",
                session_key=f"session_{i}"
            )

        resp = await self.client.get("/v1/approvals/pending")
        data = await resp.json()
        assert len(data["approvals"]) == 3


class TestSendExecApprovalMethod:
    """Test send_exec_approval method directly."""

    @pytest.fixture
    def adapter(self):
        platform_config = PlatformConfig(
            enabled=True,
            extra={}
        )
        return APIServerAdapter(platform_config)

    @pytest.mark.asyncio
    async def test_returns_success_with_id(self, adapter):
        """Test send_exec_approval returns success result with ID."""
        result = await adapter.send_exec_approval(
            chat_id="test_chat",
            command="rm -rf /",
            session_key="test_session"
        )
        assert result.success is True
        assert result.message_id.startswith("api_")

    @pytest.mark.asyncio
    async def test_stores_approval_in_pending(self, adapter):
        """Test approval is stored in pending dict."""
        await adapter.send_exec_approval(
            chat_id="test_chat",
            command="rm -rf /",
            session_key="test_session"
        )
        assert len(adapter._pending_approvals) == 1

    @pytest.mark.asyncio
    async def test_approval_has_unique_id(self, adapter):
        """Test each approval gets unique ID."""
        result1 = await adapter.send_exec_approval(
            chat_id="chat1",
            command="cmd1",
            session_key="session1"
        )
        result2 = await adapter.send_exec_approval(
            chat_id="chat2",
            command="cmd2",
            session_key="session2"
        )
        assert result1.message_id != result2.message_id
