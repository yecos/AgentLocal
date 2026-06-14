"""
Tests for bridge_api.py new features:
- Request validation middleware (content-type, size limits)
- CORS configuration
- /api/config endpoint
- /api/sessions endpoint
- Request ID tracking
- Structured error responses
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

import sys
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)


# Import the app and helper functions directly
# bridge_api may have import errors for agent modules but the app still loads
from bridge_api import (
    app,
    _error_body,
    _MAX_BODY_SIZE,
    _DEFAULT_CORS_ORIGINS,
    _MULTIPART_PATHS,
    _PRODUCTION,
)
from fastapi.testclient import TestClient


client = TestClient(app, raise_server_exceptions=False)


class TestRequestIdMiddleware:
    """Test request ID tracking middleware."""

    def test_request_id_header_present(self):
        """Every response should have X-Request-ID header."""
        response = client.get("/api/health")
        assert "X-Request-ID" in response.headers

    def test_request_id_is_uuid_format(self):
        """X-Request-ID should be a UUID."""
        response = client.get("/api/health")
        request_id = response.headers["X-Request-ID"]
        # UUID format: 8-4-4-4-12 hex chars
        parts = request_id.split("-")
        assert len(parts) == 5

    def test_different_requests_different_ids(self):
        """Different requests should get different IDs."""
        resp1 = client.get("/api/health")
        resp2 = client.get("/api/health")
        id1 = resp1.headers["X-Request-ID"]
        id2 = resp2.headers["X-Request-ID"]
        assert id1 != id2


class TestRequestValidationMiddleware:
    """Test request validation middleware (content-type, size limits)."""

    def test_post_wrong_content_type_rejected(self):
        """POST with non-JSON content type should be rejected with 415."""
        response = client.post(
            "/api/chat/simple",
            content="message=hello",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 415

    def test_post_oversized_body_constant(self):
        """Verify the max body size constant."""
        assert _MAX_BODY_SIZE == 10 * 1024 * 1024  # 10MB

    def test_multipart_upload_path_exempt(self):
        """Upload path should be exempt from JSON content-type check."""
        assert "/api/upload" in _MULTIPART_PATHS

    def test_get_requests_no_content_type_check(self):
        """GET requests should not be subject to content-type validation."""
        response = client.get("/api/health")
        assert response.status_code == 200


class TestCORSConfiguration:
    """Test CORS configuration."""

    def test_cors_default_origins(self):
        """Default CORS origins should include localhost:3000 and 3001."""
        assert "http://localhost:3000" in _DEFAULT_CORS_ORIGINS
        assert "http://localhost:3001" in _DEFAULT_CORS_ORIGINS

    def test_cors_preflight_allowed(self):
        """OPTIONS preflight requests should be allowed."""
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        # Should get 200 or 204
        assert response.status_code in (200, 204)

    def test_cors_origin_header(self):
        """Responses should include access-control-allow-origin for allowed origins."""
        response = client.get(
            "/api/health",
            headers={"Origin": "http://localhost:3000"}
        )
        # Should have CORS header
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestHealthEndpoint:
    """Test /api/health endpoint."""

    def test_health_returns_200(self):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_json(self):
        response = client.get("/api/health")
        data = response.json()
        assert isinstance(data, dict)

    def test_health_has_status_field(self):
        response = client.get("/api/health")
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_health_has_version(self):
        response = client.get("/api/health")
        data = response.json()
        assert "version" in data

    def test_health_has_uptime(self):
        response = client.get("/api/health")
        data = response.json()
        assert "uptime" in data
        assert isinstance(data["uptime"], int)

    def test_health_has_agent_available(self):
        response = client.get("/api/health")
        data = response.json()
        assert "agent" in data

    def test_health_has_auth_enabled(self):
        response = client.get("/api/health")
        data = response.json()
        assert "auth_enabled" in data

    def test_health_has_ollama_status(self):
        response = client.get("/api/health")
        data = response.json()
        assert "ollama" in data
        # Without Ollama running, should be "unreachable" or "unknown"
        assert data["ollama"] in ("ok", "unreachable", "unknown")


class TestConfigEndpoint:
    """Test /api/config endpoint."""

    def test_config_returns_200(self):
        response = client.get("/api/config")
        assert response.status_code == 200

    def test_config_returns_json(self):
        response = client.get("/api/config")
        data = response.json()
        assert isinstance(data, dict)

    def test_config_has_deep_thinking_mode(self):
        response = client.get("/api/config")
        data = response.json()
        assert "deep_thinking_mode" in data

    def test_config_has_max_react_iterations(self):
        response = client.get("/api/config")
        data = response.json()
        assert "max_react_iterations" in data

    def test_config_has_timeout_settings(self):
        response = client.get("/api/config")
        data = response.json()
        assert "default_timeout" in data

    def test_config_has_streaming(self):
        response = client.get("/api/config")
        data = response.json()
        assert "use_streaming" in data

    def test_config_values_not_sensitive(self):
        """Config should not expose sensitive data like passwords or tokens."""
        response = client.get("/api/config")
        data = response.json()
        data_str = json.dumps(data).lower()
        assert "password" not in data_str
        assert "secret_key" not in data_str


class TestSessionsEndpoint:
    """Test /api/sessions endpoint."""

    def test_sessions_returns_200(self):
        response = client.get("/api/sessions")
        assert response.status_code == 200

    def test_sessions_returns_json(self):
        response = client.get("/api/sessions")
        data = response.json()
        assert isinstance(data, dict)

    def test_sessions_has_sessions_list(self):
        response = client.get("/api/sessions")
        data = response.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_sessions_has_count(self):
        response = client.get("/api/sessions")
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)

    def test_sessions_count_matches_list(self):
        response = client.get("/api/sessions")
        data = response.json()
        assert data["count"] == len(data["sessions"])


class TestStructuredErrorResponses:
    """Test structured error response format."""

    def test_error_body_has_required_fields(self):
        body = _error_body(detail="Test error", request_id="test-123")
        assert "detail" in body
        assert "request_id" in body
        assert "timestamp" in body

    def test_error_body_detail_matches(self):
        body = _error_body(detail="Something went wrong", request_id="id-1")
        assert body["detail"] == "Something went wrong"

    def test_error_body_request_id_matches(self):
        body = _error_body(detail="Error", request_id="unique-id")
        assert body["request_id"] == "unique-id"

    def test_error_body_timestamp_is_iso_format(self):
        body = _error_body(detail="Error", request_id="id")
        try:
            datetime.fromisoformat(body["timestamp"])
        except ValueError:
            pytest.fail("Timestamp is not in ISO format")

    def test_error_body_internal_detail_hidden_in_production(self):
        """In production mode, internal_detail should not be exposed."""
        with patch("bridge_api._PRODUCTION", True):
            body = _error_body(
                detail="Error", request_id="id",
                internal_detail="stack trace info"
            )
            assert "internal_detail" not in body

    def test_error_body_internal_detail_shown_in_dev(self):
        """In development mode, internal_detail should be included."""
        with patch("bridge_api._PRODUCTION", False):
            body = _error_body(
                detail="Error", request_id="id",
                internal_detail="debug info"
            )
            assert "internal_detail" in body
            assert body["internal_detail"] == "debug info"

    def test_error_body_default_request_id(self):
        """Default request_id should be 'unknown'."""
        body = _error_body(detail="Error")
        assert body["request_id"] == "unknown"

    def test_http_error_includes_request_id(self):
        """HTTP errors should include X-Request-ID in response."""
        response = client.get("/api/nonexistent")
        assert "X-Request-ID" in response.headers

    def test_415_error_has_structured_body(self):
        """415 errors should have structured error body."""
        response = client.post(
            "/api/chat/simple",
            content="test",
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 415
        data = response.json()
        assert "detail" in data
        assert "request_id" in data


class TestMaxBodySize:
    """Test body size limit constants."""

    def test_max_body_size_is_10mb(self):
        assert _MAX_BODY_SIZE == 10 * 1024 * 1024

    def test_multipart_paths_defined(self):
        assert isinstance(_MULTIPART_PATHS, set)
        assert len(_MULTIPART_PATHS) > 0


class TestAuthConfiguration:
    """Test authentication configuration."""

    def test_health_no_auth_required(self):
        """Health endpoint should always be accessible."""
        response = client.get("/api/health")
        assert response.status_code != 401
        assert response.status_code != 403
