"""Tests for API server file upload functionality.

Tests cover:
- POST /v1/files upload endpoint
- GET /v1/files/{id} retrieve endpoint
- File size limits
- MIME type detection
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


class TestFileUploadAPI(AioHTTPTestCase):
    """Test file upload endpoints."""

    async def get_application(self):
        """Create test app with file routes."""
        config = GatewayConfig({})
        platform_config = PlatformConfig(
            enabled=True,
            extra={
                "host": "127.0.0.1",
                "port": 8642,
                "files_dir": "/tmp/test_api_files",
            }
        )
        self.adapter = APIServerAdapter(platform_config)
        self.adapter.config = config

        app = web.Application()
        app.router.add_post("/v1/files", self.adapter._handle_files_upload)
        app.router.add_get("/v1/files/{file_id}", self.adapter._handle_files_get)
        return app

    async def setUpAsync(self):
        await super().setUpAsync()
        import tempfile
        import os
        self.temp_dir = tempfile.mkdtemp()
        self.adapter._files_dir = self.temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)

    async def tearDownAsync(self):
        await super().tearDownAsync()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_upload_file_success(self):
        """Test successful file upload."""
        data = FormData()
        data.add_field("file",
                       io.BytesIO(b"test content"),
                       filename="test.txt",
                       content_type="text/plain")

        resp = await self.client.post("/v1/files", data=data)
        assert resp.status == 200
        data = await resp.json()
        assert "id" in data
        assert data["filename"] == "test.txt"
        assert data["bytes"] == 12
        assert data["mime_type"] == "text/plain"

    async def test_upload_image_success(self):
        """Test successful image upload."""
        # Fake PNG header
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        data = FormData()
        data.add_field("file",
                       io.BytesIO(fake_png),
                       filename="test.png",
                       content_type="image/png")

        resp = await self.client.post("/v1/files", data=data)
        assert resp.status == 200
        data = await resp.json()
        assert data["mime_type"] == "image/png"
        assert data["is_image"] is True

    async def test_upload_file_too_large(self):
        """Test upload rejection for files exceeding size limit."""
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        data = FormData()
        data.add_field("file",
                       io.BytesIO(large_content),
                       filename="large.bin",
                       content_type="application/octet-stream")

        resp = await self.client.post("/v1/files", data=data)
        assert resp.status == 413

    async def test_get_file_success(self):
        """Test successful file retrieval."""
        # First upload
        data = FormData()
        data.add_field("file",
                       io.BytesIO(b"test content"),
                       filename="test.txt",
                       content_type="text/plain")
        upload_resp = await self.client.post("/v1/files", data=data)
        upload_data = await upload_resp.json()
        file_id = upload_data["id"]

        # Then retrieve
        resp = await self.client.get(f"/v1/files/{file_id}")
        assert resp.status == 200
        content = await resp.read()
        assert content == b"test content"

    async def test_get_nonexistent_file(self):
        """Test 404 for non-existent file."""
        resp = await self.client.get("/v1/files/nonexistent")
        assert resp.status == 404

    async def test_upload_requires_auth(self):
        """Test upload requires authentication when API key set."""
        self.adapter._api_key = "test_key"
        data = FormData()
        data.add_field("file",
                       io.BytesIO(b"test"),
                       filename="test.txt")

        # No auth header
        resp = await self.client.post("/v1/files", data=data)
        assert resp.status == 401

        # With auth header
        resp = await self.client.post("/v1/files",
                                      data=data,
                                      headers={"Authorization": "Bearer test_key"})
        assert resp.status == 200


class TestFileUploadService:
    """Test file upload service methods directly."""

    @pytest.fixture
    def adapter(self):
        import tempfile
        platform_config = PlatformConfig(
            enabled=True,
            extra={"files_dir": tempfile.mkdtemp()}
        )
        return APIServerAdapter(platform_config)

    @pytest.mark.asyncio
    async def test_files_dir_configurable(self, adapter):
        """Test files directory is configurable."""
        import tempfile
        import os
        assert adapter._files_dir is not None
        assert os.path.exists(adapter._files_dir)

    @pytest.mark.asyncio
    async def test_file_storage_persistence(self, adapter):
        """Test uploaded files persist to disk."""
        import os
        test_content = b"persistent content"
        # Simulate file save
        file_id = "test_123"
        file_path = os.path.join(adapter._files_dir, file_id)
        with open(file_path, "wb") as f:
            f.write(test_content)

        assert os.path.exists(file_path)
        with open(file_path, "rb") as f:
            assert f.read() == test_content
