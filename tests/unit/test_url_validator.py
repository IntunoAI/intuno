"""Unit tests for SSRF-safe URL validation."""

from unittest.mock import patch

import pytest

from src.exceptions import BadRequestException
from src.network.utils.url_validator import validate_callback_url


class TestValidateCallbackUrl:
    def test_valid_https_url(self):
        """Uses a public IP to avoid DNS resolution issues in CI."""
        with patch("src.network.utils.url_validator._is_private_ip", return_value=False):
            url = "https://example.com/callback"
            assert validate_callback_url(url) == url

    def test_valid_http_in_development(self):
        with patch("src.network.utils.url_validator.settings") as mock_settings, \
             patch("src.network.utils.url_validator._is_private_ip", return_value=False):
            mock_settings.ENVIRONMENT = "development"
            url = "http://example.com/callback"
            assert validate_callback_url(url) == url

    def test_rejects_http_in_production(self):
        with patch("src.network.utils.url_validator.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            with pytest.raises(BadRequestException, match="HTTPS"):
                validate_callback_url("http://example.com/callback")

    def test_rejects_empty_url(self):
        with pytest.raises(BadRequestException, match="empty"):
            validate_callback_url("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(BadRequestException, match="empty"):
            validate_callback_url("   ")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(BadRequestException, match="http or https"):
            validate_callback_url("ftp://example.com/file")

    def test_rejects_javascript_scheme(self):
        with pytest.raises(BadRequestException, match="http or https"):
            validate_callback_url("javascript:alert(1)")

    def test_rejects_no_hostname(self):
        with pytest.raises(BadRequestException, match="hostname"):
            validate_callback_url("https:///path")

    def test_rejects_localhost(self):
        with pytest.raises(BadRequestException, match="private"):
            validate_callback_url("https://127.0.0.1/callback")

    def test_rejects_private_10_range(self):
        with pytest.raises(BadRequestException, match="private"):
            validate_callback_url("https://10.0.0.1/callback")

    def test_rejects_private_172_range(self):
        with pytest.raises(BadRequestException, match="private"):
            validate_callback_url("https://172.16.0.1/callback")

    def test_rejects_private_192_range(self):
        with pytest.raises(BadRequestException, match="private"):
            validate_callback_url("https://192.168.1.1/callback")

    def test_rejects_link_local(self):
        with pytest.raises(BadRequestException, match="private"):
            validate_callback_url("https://169.254.169.254/latest/meta-data/")

    def test_rejects_ipv6_loopback(self):
        with pytest.raises(BadRequestException, match="private"):
            validate_callback_url("https://[::1]/callback")
