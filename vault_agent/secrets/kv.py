"""Key-Value secrets engine with caching."""

from typing import Any, Dict, Optional
import logging

from ..cache import MemoryCache
from ..utils.exceptions import SecretNotFoundError

logger = logging.getLogger(__name__)


class KVSecrets:
    """Manages Key-Value secrets with caching support."""

    def __init__(self, client, cache: MemoryCache, mount_point: str = "secret"):
        """
        Initialize KV secrets manager.

        Args:
            client: The Vault client instance.
            cache: The cache instance to use.
            mount_point: The KV engine mount point.
        """
        self.client = client
        self.cache = cache
        self.mount_point = mount_point

    def read(self, path: str, version: Optional[int] = None) -> Dict[str, Any]:
        """
        Read a secret from KV engine.

        Args:
            path: The secret path.
            version: Optional version for KV v2.

        Returns:
            The secret data.

        Raises:
            SecretNotFoundError: If the secret is not found.
        """
        cache_key = f"kv:{self.mount_point}:{path}"
        if version:
            cache_key = f"{cache_key}:v{version}"

        cached_value = self.cache.get(cache_key)
        if cached_value is not None:
            logger.debug(f"Cache hit for key: {cache_key}")
            return cached_value

        logger.debug(f"Cache miss for key: {cache_key}, fetching from Vault")

        try:
            if self._is_kv_v2():
                response = self.client.secrets.kv.v2.read_secret_version(
                    path=path,
                    mount_point=self.mount_point,
                    version=version
                )
                data = response.get("data", {}).get("data", {})
            else:
                response = self.client.secrets.kv.v1.read_secret(
                    path=path,
                    mount_point=self.mount_point
                )
                data = response.get("data", {})

            self.cache.set(cache_key, data)
            return data

        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise SecretNotFoundError(f"Secret not found at path: {path}")
            raise



    def list_secrets(self, path: str = "") -> list:
        """
        List secrets at a given path.

        Args:
            path: The path to list secrets from.

        Returns:
            List of secret keys at the path.
        """
        cache_key = f"kv:list:{self.mount_point}:{path}"

        cached_value = self.cache.get(cache_key)
        if cached_value is not None:
            return cached_value

        if self._is_kv_v2():
            response = self.client.secrets.kv.v2.list_secrets(
                path=path,
                mount_point=self.mount_point
            )
        else:
            response = self.client.secrets.kv.v1.list_secrets(
                path=path,
                mount_point=self.mount_point
            )

        keys = response.get("data", {}).get("keys", [])
        self.cache.set(cache_key, keys, ttl=60)
        return keys

    def _is_kv_v2(self) -> bool:
        """Check if the mount point is KV v2."""
        try:
            mount_info = self.client.sys.read_mount_configuration(
                path=self.mount_point
            )
            options = mount_info.get("options", {})
            return options.get("version", "1") == "2"
        except Exception:
            return False
