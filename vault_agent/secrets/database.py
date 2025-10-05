"""Database secrets engine with caching."""

from typing import Any, Dict, Optional
import logging

import hvac

from ..cache import MemoryCache
from ..utils.exceptions import SecretNotFoundError

logger = logging.getLogger(__name__)


class DatabaseSecrets:
    """Manages Database secrets with caching support."""

    def __init__(
        self, client: hvac.Client, cache: MemoryCache, mount_point: str = "database"
    ):
        """
        Initialize Database secrets manager.

        Args:
            client: The Vault client instance.
            cache: The cache instance to use.
            mount_point: The database engine mount point.
        """
        self.client = client
        self.cache = cache
        self.mount_point = mount_point

    def get_credentials(self, role: str, ttl: Optional[int] = None) -> Dict[str, Any]:
        """
        Get database credentials for a role.

        Args:
            role: The database role name.
            ttl: Optional cache TTL for these credentials.

        Returns:
            Dictionary containing username and password.

        Raises:
            SecretNotFoundError: If the role is not found.
        """
        cache_key = f"db:{self.mount_point}:{role}"

        cached_creds = self.cache.get(cache_key)
        if cached_creds is not None:
            logger.debug(f"Cache hit for database role: {role}")
            return cached_creds

        logger.debug(f"Cache miss for database role: {role}, fetching from Vault")

        try:
            response = self.client.secrets.database.generate_credentials(
                name=role, mount_point=self.mount_point
            )

            credentials = {
                "username": response["data"]["username"],
                "password": response["data"]["password"],
            }

            lease_duration = response.get("lease_duration", 3600)
            cache_ttl = min(ttl or lease_duration, lease_duration)

            self.cache.set(cache_key, credentials, ttl=cache_ttl)

            return credentials

        except Exception as e:
            if "400" in str(e) or "role" in str(e).lower():
                raise SecretNotFoundError(f"Database role not found: {role}")
            raise

    def get_static_credentials(
        self, role: str, ttl: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get static database credentials for a role.

        Args:
            role: The static database role name.
            ttl: Optional cache TTL for these credentials.

        Returns:
            Dictionary containing username and password.

        Raises:
            SecretNotFoundError: If the role is not found.
        """
        cache_key = f"db:static:{self.mount_point}:{role}"

        cached_creds = self.cache.get(cache_key)
        if cached_creds is not None:
            logger.debug(f"Cache hit for static database role: {role}")
            return cached_creds

        logger.debug(
            f"Cache miss for static database role: {role}, fetching from Vault"
        )

        try:
            response = self.client.secrets.database.get_static_credentials(
                name=role, mount_point=self.mount_point
            )

            credentials = {
                "username": response["data"]["username"],
                "password": response["data"]["password"],
                "last_vault_rotation": response["data"].get("last_vault_rotation"),
                "rotation_period": response["data"].get("rotation_period"),
            }

            cache_ttl = ttl or 300

            self.cache.set(cache_key, credentials, ttl=cache_ttl)

            return credentials

        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise SecretNotFoundError(f"Static database role not found: {role}")
            raise


    def get_connection_string(
        self,
        role: str,
        template: str = "postgresql://{username}:{password}@{host}/{database}",
        host: str = "localhost",
        database: str = "postgres",
        **kwargs,
    ) -> str:
        """
        Get a formatted connection string with credentials.

        Args:
            role: The database role name.
            template: Connection string template with {username} and {password} placeholders.
            host: Database host.
            database: Database name.
            **kwargs: Additional template parameters.

        Returns:
            Formatted connection string.
        """
        credentials = self.get_credentials(role)

        return template.format(
            username=credentials["username"],
            password=credentials["password"],
            host=host,
            database=database,
            **kwargs,
        )

    def clear_cache(self, role: Optional[str] = None) -> None:
        """
        Clear cached credentials.

        Args:
            role: Optional specific role to clear, otherwise clears all database cache.
        """
        if role:
            self.cache.delete(f"db:{self.mount_point}:{role}")
            self.cache.delete(f"db:static:{self.mount_point}:{role}")
        else:
            import re

            pattern = f"^db:.*:{self.mount_point}:"
            with self.cache._lock:
                keys_to_delete = [
                    key for key in self.cache._cache.keys() if re.match(pattern, key)
                ]
                for key in keys_to_delete:
                    del self.cache._cache[key]
