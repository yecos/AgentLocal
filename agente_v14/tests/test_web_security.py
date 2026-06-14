"""
Tests for tools/web.py security features:
- _validate_web_url() blocks private IPs (10.x, 172.16.x, 192.168.x, 127.x, 169.254.x)
- _validate_web_url() blocks dangerous schemes (file://, ftp://, data://, javascript://)
- _validate_web_url() allows valid http:// and https:// URLs
- _is_private_ip() for IPv4 and IPv6
- Response size limiting
"""

import ipaddress
import socket
import pytest
from unittest.mock import patch, MagicMock

from tools.web import (
    _validate_web_url,
    _is_private_ip,
    _safe_urlopen,
    BLOCKED_SCHEMES,
    PRIVATE_NETWORKS,
    WEB_RESPONSE_MAX_SIZE,
    WEB_USER_AGENT,
    WebSearchCache,
)


class TestValidateWebUrlAllowsValid:
    """Test that _validate_web_url() allows valid http:// and https:// URLs."""

    def test_valid_https_url(self):
        is_valid, error = _validate_web_url("https://www.google.com/search?q=test")
        assert is_valid is True
        assert error == ""

    def test_valid_http_url(self):
        is_valid, error = _validate_web_url("http://example.com/page")
        assert is_valid is True
        assert error == ""

    def test_valid_url_with_port(self):
        is_valid, error = _validate_web_url("http://example.com:8080/api")
        assert is_valid is True
        assert error == ""

    def test_valid_url_with_path_and_query(self):
        is_valid, error = _validate_web_url("https://api.example.com/v1/data?key=val&foo=bar")
        assert is_valid is True
        assert error == ""

    def test_valid_url_simple_domain(self):
        is_valid, error = _validate_web_url("https://github.com")
        assert is_valid is True
        assert error == ""


class TestValidateWebUrlBlocksEmpty:
    """Test that _validate_web_url() blocks empty/invalid URLs."""

    def test_empty_url(self):
        is_valid, error = _validate_web_url("")
        assert is_valid is False
        assert "vacia" in error.lower() or "invalido" in error.lower()

    def test_whitespace_url(self):
        is_valid, error = _validate_web_url("   ")
        assert is_valid is False

    def test_none_url(self):
        is_valid, error = _validate_web_url(None)
        assert is_valid is False


class TestValidateWebUrlBlocksDangerousSchemes:
    """Test that _validate_web_url() blocks dangerous URL schemes."""

    def test_file_scheme_blocked(self):
        is_valid, error = _validate_web_url("file:///etc/passwd")
        assert is_valid is False
        assert "bloqueado" in error.lower() or "esquema" in error.lower()

    def test_ftp_scheme_blocked(self):
        is_valid, error = _validate_web_url("ftp://ftp.example.com/file")
        assert is_valid is False

    def test_data_scheme_blocked(self):
        is_valid, error = _validate_web_url("data:text/html,<script>alert(1)</script>")
        assert is_valid is False

    def test_javascript_scheme_blocked(self):
        is_valid, error = _validate_web_url("javascript:alert(1)")
        assert is_valid is False

    def test_vbscript_scheme_blocked(self):
        is_valid, error = _validate_web_url("vbscript:MsgBox('x')")
        assert is_valid is False

    def test_blob_scheme_blocked(self):
        is_valid, error = _validate_web_url("blob:https://example.com/uuid")
        assert is_valid is False

    def test_no_scheme_blocked(self):
        is_valid, error = _validate_web_url("www.example.com")
        assert is_valid is False
        assert "esquema" in error.lower() or "sin" in error.lower()

    def test_unknown_scheme_blocked(self):
        is_valid, error = _validate_web_url("gopher://example.com")
        assert is_valid is False


class TestValidateWebUrlBlocksEmbeddedDangerous:
    """Test that _validate_web_url() blocks URLs with embedded dangerous schemes."""

    def test_embedded_javascript(self):
        is_valid, error = _validate_web_url("https://example.com/page?url=javascript:alert(1)")
        assert is_valid is False

    def test_embedded_data(self):
        is_valid, error = _validate_web_url("https://example.com/redirect?to=data:text/html,payload")
        assert is_valid is False

    def test_embedded_file(self):
        is_valid, error = _validate_web_url("https://example.com/?ref=file:///etc/passwd")
        assert is_valid is False


class TestIsPrivateIpIPv4:
    """Test _is_private_ip() for IPv4 addresses."""

    def test_10_network_private(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_10_any_private(self):
        assert _is_private_ip("10.255.255.255") is True

    def test_172_16_network_private(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_172_31_network_private(self):
        assert _is_private_ip("172.31.255.255") is True

    def test_192_168_network_private(self):
        assert _is_private_ip("192.168.1.1") is True

    def test_192_168_any_private(self):
        assert _is_private_ip("192.168.0.100") is True

    def test_127_loopback_private(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_127_any_loopback_private(self):
        assert _is_private_ip("127.0.0.99") is True

    def test_169_254_link_local_private(self):
        assert _is_private_ip("169.254.1.1") is True

    def test_169_254_any_link_local_private(self):
        assert _is_private_ip("169.254.255.255") is True

    def test_public_ip_not_private(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_another_public_ip_not_private(self):
        assert _is_private_ip("1.1.1.1") is False

    def test_172_15_not_private(self):
        """172.15.x.x is NOT in the 172.16.0.0/12 range."""
        assert _is_private_ip("172.15.0.1") is False

    def test_172_32_not_private(self):
        """172.32.x.x is NOT in the 172.16.0.0/12 range."""
        assert _is_private_ip("172.32.0.1") is False


class TestIsPrivateIpIPv6:
    """Test _is_private_ip() for IPv6 addresses."""

    def test_ipv6_loopback_private(self):
        assert _is_private_ip("::1") is True

    def test_ipv6_unique_local_private(self):
        # fc00::/7 range
        assert _is_private_ip("fc00::1") is True

    def test_ipv6_link_local_private(self):
        # fe80::/10 range
        assert _is_private_ip("fe80::1") is True

    def test_ipv6_public_not_private(self):
        # A public IPv6 address
        assert _is_private_ip("2001:4860:4860::8888") is False


class TestIsPrivateIpDNSResolution:
    """Test _is_private_ip() with DNS resolution (hostnames)."""

    @patch('tools.web.socket.getaddrinfo')
    def test_hostname_resolving_to_private_blocked(self, mock_getaddr):
        """Hostname resolving to 127.0.0.1 should be blocked."""
        mock_getaddr.return_value = [
            (2, 1, 6, '', ('127.0.0.1', 0))
        ]
        assert _is_private_ip("localhost") is True

    @patch('tools.web.socket.getaddrinfo')
    def test_hostname_resolving_to_public_allowed(self, mock_getaddr):
        """Hostname resolving to public IP should be allowed."""
        mock_getaddr.return_value = [
            (2, 1, 6, '', ('93.184.216.34', 0))
        ]
        assert _is_private_ip("example.com") is False

    @patch('tools.web.socket.getaddrinfo', side_effect=socket.gaierror("DNS failure"))
    def test_unresolvable_hostname_returns_false(self, mock_getaddr):
        """If DNS resolution fails, allow through (will fail at connection)."""
        assert _is_private_ip("nonexistent.invalid") is False


class TestValidateWebUrlBlocksPrivateIPs:
    """Test _validate_web_url() blocks URLs pointing to private IPs."""

    @patch('tools.web._is_private_ip', return_value=True)
    def test_private_ip_url_blocked(self, mock_private):
        is_valid, error = _validate_web_url("http://10.0.0.1/admin")
        assert is_valid is False
        assert "privada" in error.lower() or "interna" in error.lower()

    @patch('tools.web._is_private_ip', return_value=False)
    def test_public_ip_url_allowed(self, mock_private):
        is_valid, error = _validate_web_url("http://93.184.216.34/page")
        assert is_valid is True

    def test_localhost_url_blocked(self):
        """URL pointing to localhost should be blocked."""
        is_valid, error = _validate_web_url("http://127.0.0.1:11434/api/tags")
        assert is_valid is False

    def test_internal_aws_metadata_blocked(self):
        """AWS metadata endpoint (169.254.169.254) should be blocked (SSRF)."""
        is_valid, error = _validate_web_url("http://169.254.169.254/latest/meta-data/")
        assert is_valid is False


class TestBlockedSchemesConstant:
    """Test BLOCKED_SCHEMES constant is properly configured."""

    def test_file_in_blocked_schemes(self):
        assert "file" in BLOCKED_SCHEMES

    def test_ftp_in_blocked_schemes(self):
        assert "ftp" in BLOCKED_SCHEMES

    def test_data_in_blocked_schemes(self):
        assert "data" in BLOCKED_SCHEMES

    def test_javascript_in_blocked_schemes(self):
        assert "javascript" in BLOCKED_SCHEMES

    def test_vbscript_in_blocked_schemes(self):
        assert "vbscript" in BLOCKED_SCHEMES

    def test_blob_in_blocked_schemes(self):
        assert "blob" in BLOCKED_SCHEMES


class TestPrivateNetworksConstant:
    """Test PRIVATE_NETWORKS constant covers all required ranges."""

    def test_has_10_network(self):
        assert ipaddress.ip_network("10.0.0.0/8") in PRIVATE_NETWORKS

    def test_has_172_16_network(self):
        assert ipaddress.ip_network("172.16.0.0/12") in PRIVATE_NETWORKS

    def test_has_192_168_network(self):
        assert ipaddress.ip_network("192.168.0.0/16") in PRIVATE_NETWORKS

    def test_has_127_network(self):
        assert ipaddress.ip_network("127.0.0.0/8") in PRIVATE_NETWORKS

    def test_has_169_254_network(self):
        assert ipaddress.ip_network("169.254.0.0/16") in PRIVATE_NETWORKS

    def test_has_ipv6_loopback(self):
        assert ipaddress.ip_network("::1/128") in PRIVATE_NETWORKS

    def test_has_ipv6_unique_local(self):
        assert ipaddress.ip_network("fc00::/7") in PRIVATE_NETWORKS

    def test_has_ipv6_link_local(self):
        assert ipaddress.ip_network("fe80::/10") in PRIVATE_NETWORKS


class TestResponseSizeLimiting:
    """Test response size limiting via _safe_urlopen."""

    def test_max_size_constant(self):
        assert WEB_RESPONSE_MAX_SIZE == 5 * 1024 * 1024  # 5MB

    def test_user_agent_constant(self):
        assert "AgentLocal" in WEB_USER_AGENT

    @patch('tools.web._validate_web_url', return_value=(True, ""))
    @patch('urllib.request.urlopen')
    def test_safe_urlopen_valid_url(self, mock_urlopen, mock_validate):
        """Normal response should be returned as-is."""
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [b"Hello World", b""]
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _safe_urlopen("https://example.com")
        assert result == b"Hello World"

    @patch('tools.web._validate_web_url', return_value=(True, ""))
    @patch('urllib.request.urlopen')
    def test_safe_urlopen_oversized_response(self, mock_urlopen, mock_validate):
        """Response exceeding 5MB should raise RuntimeError."""
        # Create a mock that returns more than 5MB of data
        mock_resp = MagicMock()

        # First chunk is large (> 5MB)
        large_chunk = b"x" * (5 * 1024 * 1024 + 1)
        mock_resp.read.side_effect = [large_chunk]
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with pytest.raises(RuntimeError, match="limite|excede|5MB"):
            _safe_urlopen("https://example.com/large")

    @patch('tools.web._validate_web_url', return_value=(False, "URL bloqueada"))
    def test_safe_urlopen_invalid_url_raises_valueerror(self, mock_validate):
        """Invalid URL should raise ValueError."""
        with pytest.raises(ValueError, match="bloqueada"):
            _safe_urlopen("file:///etc/passwd")


class TestWebSearchCache:
    """Test WebSearchCache behavior."""

    def test_cache_miss(self):
        cache = WebSearchCache()
        result = cache.get("nonexistent query")
        assert result is None

    def test_cache_put_and_get(self):
        cache = WebSearchCache()
        cache.put("test query", "test results")
        result = cache.get("test query")
        assert result == "test results"

    def test_cache_case_insensitive(self):
        cache = WebSearchCache()
        cache.put("Test Query", "results")
        result = cache.get("test query")
        assert result == "results"

    def test_cache_ttl_expired(self):
        cache = WebSearchCache(default_ttl=0)  # Immediate expiry
        cache.put("test", "results")
        # TTL of 0 means it expires immediately
        import time
        time.sleep(0.01)
        result = cache.get("test")
        assert result is None

    def test_cache_custom_ttl(self):
        cache = WebSearchCache(default_ttl=0)
        cache.put("test", "results", ttl=3600)  # 1 hour TTL
        result = cache.get("test")
        assert result == "results"

    def test_cache_max_size_eviction(self):
        cache = WebSearchCache(max_size=2)
        cache.put("query1", "result1")
        cache.put("query2", "result2")
        cache.put("query3", "result3")  # Should evict oldest
        # At least one should be evicted
        results = [cache.get("query1"), cache.get("query2"), cache.get("query3")]
        assert None in results  # At least one was evicted

    def test_cache_clear(self):
        cache = WebSearchCache()
        cache.put("test", "results")
        cache.clear()
        assert cache.get("test") is None

    def test_cache_stats(self):
        cache = WebSearchCache(max_size=10)
        cache.put("test", "results")
        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["max_size"] == 10
