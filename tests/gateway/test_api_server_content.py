"""Tests for content normalization with attachments.

Tests cover:
- image_url content block extraction
- file attachment content block handling
- Mixed text and image content
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.api_server import APIServerAdapter, _normalize_chat_content


class TestNormalizeChatContent:
    """Test _normalize_chat_content with attachments."""

    def test_normalize_plain_text(self):
        """Test normalizing plain text content."""
        content = "Hello world"
        result = _normalize_chat_content(content)
        assert result == "Hello world"

    def test_normalize_text_array(self):
        """Test normalizing array of text blocks."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        result = _normalize_chat_content(content)
        assert result == "Hello\nWorld"

    def test_normalize_with_image_url(self):
        """Test normalizing content with image_url block."""
        content = [
            {"type": "text", "text": "Check this image:"},
            {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
        ]
        # Currently image_url is skipped - for Task 1.4 this should be handled
        result = _normalize_chat_content(content)
        assert "Check this image:" in result

    def test_normalize_with_file_attachment(self):
        """Test normalizing content with file attachment."""
        content = [
            {"type": "text", "text": "See attached file:"},
            {"type": "file", "file": {"file_id": "file_123", "filename": "doc.pdf"}},
        ]
        # Currently file blocks are skipped - for Task 1.4 this should be handled
        result = _normalize_chat_content(content)
        assert "See attached file:" in result

    def test_normalize_mixed_content(self):
        """Test normalizing mixed text, image and file content."""
        content = [
            {"type": "text", "text": "Here is an image:"},
            {"type": "image_url", "image_url": {"url": "https://example.com/image.png", "detail": "high"}},
            {"type": "text", "text": "And a file:"},
            {"type": "file", "file": {"file_id": "file_456", "filename": "report.pdf"}},
        ]
        result = _normalize_chat_content(content)
        assert "Here is an image:" in result
        assert "And a file:" in result


