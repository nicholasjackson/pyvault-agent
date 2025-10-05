"""Functional tests with real Vault server.

These tests require a running Vault dev server:
    vault server -dev -dev-root-token-id="root"

Set environment variable to run these tests:
    VAULT_ADDR=http://127.0.0.1:8200
    VAULT_TOKEN=root
"""

import os
import pytest
import hvac
from vault_agent import VaultAgentClient


VAULT_URL = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "root")


def vault_available():
    """Check if Vault server is available."""
    try:
        client = hvac.Client(url=VAULT_URL, token=VAULT_TOKEN)
        return client.sys.is_initialized()
    except Exception:
        return False


@pytest.mark.skipif(not vault_available(), reason="Vault server not available")
class TestVaultIntegration:
    """Integration tests with real Vault."""

    @pytest.fixture
    def setup_vault(self):
        """Setup Vault for testing."""
        client = hvac.Client(url=VAULT_URL, token=VAULT_TOKEN)

        client.sys.enable_auth_method(
            method_type="approle",
            path="approle",
        )

        client.auth.approle.create_or_update_approle(
            "test-role",
            token_policies=["default"],
            token_ttl="1h",
        )

        role_id = client.auth.approle.read_role_id("test-role")["data"]["role_id"]

        secret_id_response = client.auth.approle.generate_secret_id("test-role")
        secret_id = secret_id_response["data"]["secret_id"]

        client.sys.enable_secrets_engine(
            backend_type="kv",
            path="secret",
            options={"version": "2"},
        )

        # Pre-populate test secrets for read-only tests
        client.secrets.kv.v2.create_or_update_secret(
            path="test-secret",
            secret={"username": "testuser", "password": "testpass123"},
            mount_point="secret"
        )

        client.secrets.kv.v2.create_or_update_secret(
            path="expiry-test",
            secret={"key": "value1"},
            mount_point="secret"
        )

        client.secrets.kv.v2.create_or_update_secret(
            path="reauth-test",
            secret={"key": "value"},
            mount_point="secret"
        )

        yield {
            "role_id": role_id,
            "secret_id": secret_id,
            "admin_client": client,
        }

        try:
            client.sys.disable_auth_method("approle")
            client.sys.disable_secrets_engine("secret")
        except Exception:
            pass

    def test_approle_authentication(self, setup_vault):
        """Test AppRole authentication."""
        client = VaultAgentClient(
            url=VAULT_URL,
            role_id=setup_vault["role_id"],
            secret_id=setup_vault["secret_id"],
        )

        assert client._is_authenticated()

    def test_kv_read_operations(self, setup_vault):
        """Test KV secret read operations and caching."""
        client = VaultAgentClient(
            url=VAULT_URL,
            role_id=setup_vault["role_id"],
            secret_id=setup_vault["secret_id"],
            cache_ttl=5,
        )

        # Read pre-populated secret
        retrieved = client.kv.read("test-secret")
        assert retrieved["username"] == "testuser"
        assert retrieved["password"] == "testpass123"

        stats = client.get_cache_stats()
        assert stats["misses"] == 1

        retrieved_cached = client.kv.read("test-secret")
        assert retrieved_cached["username"] == "testuser"

        stats = client.get_cache_stats()
        assert stats["hits"] == 1


    def test_cache_expiration_and_refetch(self, setup_vault):
        """Test that cache expires and refetches."""
        client = VaultAgentClient(
            url=VAULT_URL,
            role_id=setup_vault["role_id"],
            secret_id=setup_vault["secret_id"],
            cache_ttl=1,
        )

        # Read pre-populated secret
        first_read = client.kv.read("expiry-test")
        assert first_read["key"] == "value1"
        assert client.get_cache_stats()["hits"] == 0
        assert client.get_cache_stats()["misses"] == 1

        # Read from cache
        cached_read = client.kv.read("expiry-test")
        assert cached_read["key"] == "value1"
        assert client.get_cache_stats()["hits"] == 1

        import time
        time.sleep(2)

        # After cache expires, should fetch from Vault again
        second_read = client.kv.read("expiry-test")
        assert second_read["key"] == "value1"
        assert client.get_cache_stats()["misses"] == 2

    def test_token_reauth(self, setup_vault):
        """Test automatic re-authentication when token expires."""
        client = VaultAgentClient(
            url=VAULT_URL,
            role_id=setup_vault["role_id"],
            secret_id=setup_vault["secret_id"],
        )

        # Get valid token first
        old_token = client._client.token

        # Invalidate token to force re-authentication
        client._client.token = "invalid-token"

        # Read pre-populated secret (should trigger re-auth)
        retrieved = client.kv.read("reauth-test")
        assert retrieved["key"] == "value"

        # Verify re-authentication occurred
        assert client._client.token != "invalid-token"
        assert client._client.token != old_token