"""Unit tests for HMAC-signed callback URL authentication."""

import time
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.network.utils.callback_auth import (
    CALLBACK_EXPIRY_SECONDS,
    sign_callback_url,
    verify_callback_signature,
)


@pytest.fixture
def network_id():
    return uuid4()


@pytest.fixture
def participant_id():
    return uuid4()


SECRET = "test-secret-key-for-unit-tests"


class TestSignCallbackUrl:
    def test_appends_sig_and_exp(self, network_id, participant_id):
        url = f"https://api.intuno.ai/networks/{network_id}/participants/{participant_id}/callback"
        signed = sign_callback_url(url, network_id, participant_id, secret=SECRET)
        assert "sig=" in signed
        assert "exp=" in signed

    def test_preserves_base_url(self, network_id, participant_id):
        base = "https://api.intuno.ai/networks/test/callback"
        signed = sign_callback_url(base, network_id, participant_id, secret=SECRET)
        assert signed.startswith("https://api.intuno.ai/networks/test/callback?")


class TestVerifyCallbackSignature:
    def test_valid_signature(self, network_id, participant_id):
        url = "https://example.com/callback"
        signed = sign_callback_url(url, network_id, participant_id, secret=SECRET)
        # Extract sig and exp from the signed URL
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(signed)
        params = parse_qs(parsed.query)
        sig = params["sig"][0]
        exp = params["exp"][0]

        assert verify_callback_signature(
            network_id, participant_id, sig, exp, secret=SECRET
        )

    def test_wrong_network_id(self, network_id, participant_id):
        url = "https://example.com/callback"
        signed = sign_callback_url(url, network_id, participant_id, secret=SECRET)
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(signed)
        params = parse_qs(parsed.query)

        wrong_network = uuid4()
        assert not verify_callback_signature(
            wrong_network, participant_id,
            params["sig"][0], params["exp"][0],
            secret=SECRET,
        )

    def test_wrong_participant_id(self, network_id, participant_id):
        url = "https://example.com/callback"
        signed = sign_callback_url(url, network_id, participant_id, secret=SECRET)
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(signed)
        params = parse_qs(parsed.query)

        wrong_participant = uuid4()
        assert not verify_callback_signature(
            network_id, wrong_participant,
            params["sig"][0], params["exp"][0],
            secret=SECRET,
        )

    def test_expired_signature(self, network_id, participant_id):
        url = "https://example.com/callback"
        # Sign with 0 expiry (already expired)
        signed = sign_callback_url(
            url, network_id, participant_id, secret=SECRET, expiry_seconds=-1
        )
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(signed)
        params = parse_qs(parsed.query)

        assert not verify_callback_signature(
            network_id, participant_id,
            params["sig"][0], params["exp"][0],
            secret=SECRET,
        )

    def test_tampered_signature(self, network_id, participant_id):
        assert not verify_callback_signature(
            network_id, participant_id,
            "tampered_signature", str(int(time.time()) + 3600),
            secret=SECRET,
        )

    def test_invalid_exp_format(self, network_id, participant_id):
        assert not verify_callback_signature(
            network_id, participant_id, "some_sig", "not_a_number", secret=SECRET
        )

    def test_wrong_secret(self, network_id, participant_id):
        url = "https://example.com/callback"
        signed = sign_callback_url(url, network_id, participant_id, secret=SECRET)
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(signed)
        params = parse_qs(parsed.query)

        assert not verify_callback_signature(
            network_id, participant_id,
            params["sig"][0], params["exp"][0],
            secret="wrong-secret",
        )
