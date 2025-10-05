# Copyright 2024 Nicholas Jackson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Vault Agent Client with AppRole authentication and caching."""

import logging
from typing import Optional
import hvac
from hvac.exceptions import InvalidRequest, Forbidden

from .cache import MemoryCache
from .secrets import KVSecrets, DatabaseSecrets
from .utils.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


class VaultAgentClient:
    """Extended Vault client with caching and automatic re-authentication."""

    def __init__(
        self,
        url: str,
        role_id: str,
        secret_id: str,
        cache_ttl: int = 300,
        max_cache_size: int = 1000,
        namespace: Optional[str] = None,
        verify: bool = True,
        kv_mount_point: str = "secret",
        database_mount_point: str = "database",
    ):
        """
        Initialize the Vault Agent client.

        Args:
            url: Vault server URL.
            role_id: AppRole role ID.
            secret_id: AppRole secret ID.
            cache_ttl: Default cache TTL in seconds.
            max_cache_size: Maximum number of cache entries.
            namespace: Optional Vault namespace.
            verify: Whether to verify SSL certificates.
            kv_mount_point: KV secrets engine mount point.
            database_mount_point: Database secrets engine mount point.
        """
        self.url = url
        self.role_id = role_id
        self.secret_id = secret_id
        self.namespace = namespace
        self.verify = verify

        self.cache = MemoryCache(default_ttl=cache_ttl, max_size=max_cache_size)

        self._client = None
        self._authenticate()

        self.kv = KVSecrets(self._get_client(), self.cache, kv_mount_point)
        self.database = DatabaseSecrets(self._get_client(), self.cache, database_mount_point)

    def _authenticate(self) -> None:
        """Authenticate with Vault using AppRole."""
        try:
            self._client = hvac.Client(
                url=self.url, namespace=self.namespace, verify=self.verify
            )

            response = self._client.auth.approle.login(
                role_id=self.role_id, secret_id=self.secret_id
            )

            self._client.token = response["auth"]["client_token"]

            logger.info("Successfully authenticated with Vault")

        except Exception as e:
            logger.error(f"Failed to authenticate with Vault: {e}")
            raise AuthenticationError(f"Failed to authenticate: {e}")

    def _get_client(self) -> hvac.Client:
        """
        Get the Vault client, re-authenticating if needed.

        Returns:
            The authenticated Vault client.
        """
        if not self._is_authenticated():
            logger.info("Token expired or invalid, re-authenticating")
            self._authenticate()

        return self._client  # type: ignore

    def _is_authenticated(self) -> bool:
        """Check if the client is authenticated."""
        if not self._client:
            return False

        try:
            self._client.sys.read_health_status()
            return self._client.is_authenticated()
        except (InvalidRequest, Forbidden):
            return False
        except Exception:
            return False

    def __getattr__(self, name):
        """
        Proxy attribute access to the underlying hvac client.

        This allows direct access to hvac client methods when needed.
        """
        client = self._get_client()
        return getattr(client, name)

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return self.cache.get_stats()

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.cache.clear()
        logger.info("Cache cleared")

    def set_cache_ttl(self, ttl: int) -> None:
        """
        Update the default cache TTL.

        Args:
            ttl: New default TTL in seconds.
        """
        self.cache.default_ttl = ttl
        logger.info(f"Cache TTL updated to {ttl} seconds")
