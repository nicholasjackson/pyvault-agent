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

"""Database connection pool manager with automatic credential refresh."""

import time
import logging
from typing import Any, Dict, Optional, Type, Callable
from contextlib import contextmanager
from threading import Lock, Thread
import warnings

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    """Manages database connection pools with automatic credential refresh from Vault."""

    def __init__(
        self,
        vault_client,
        role: str,
        pool_class: Type,
        pool_kwargs: Optional[Dict[str, Any]] = None,
        refresh_buffer: float = 0.8,
        validation_query: str = "SELECT 1",
        on_refresh: Optional[Callable] = None,
    ):
        """
        Initialize the connection manager.

        Args:
            vault_client: VaultAgentClient instance.
            role: Database role name in Vault.
            pool_class: Connection pool class (e.g., psycopg2.pool.SimpleConnectionPool).
            pool_kwargs: Additional kwargs for pool initialization.
            refresh_buffer: Refresh credentials when this percentage of TTL remains (0.8 = 80%).
            validation_query: Query to validate connections.
            on_refresh: Optional callback when credentials are refreshed.
        """
        self.vault_client = vault_client
        self.role = role
        self.pool_class = pool_class
        self.pool_kwargs = pool_kwargs or {}
        self.refresh_buffer = refresh_buffer
        self.validation_query = validation_query
        self.on_refresh = on_refresh

        self.pool = None
        self.credentials = None
        self.credentials_expire_at = None
        self._lock = Lock()
        self._closing = False

        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """Initialize the connection pool with fresh credentials."""
        self._refresh_credentials()
        self._create_pool()

    def _refresh_credentials(self) -> None:
        """Fetch fresh credentials from Vault."""
        logger.info(f"Refreshing database credentials for role: {self.role}")

        response = self.vault_client.database.client.secrets.database.generate_credentials(
            name=self.role,
            mount_point=self.vault_client.database.mount_point
        )

        self.credentials = {
            "user": response["data"]["username"],
            "password": response["data"]["password"],
        }

        lease_duration = response.get("lease_duration", 3600)
        effective_ttl = lease_duration * self.refresh_buffer
        self.credentials_expire_at = time.time() + effective_ttl

        logger.info(f"Credentials refreshed, will refresh again in {effective_ttl} seconds")

        if self.on_refresh:
            self.on_refresh(self.credentials)

    def _create_pool(self) -> None:
        """Create a new connection pool with current credentials."""
        with self._lock:
            old_pool = self.pool

            pool_config = {**self.pool_kwargs, **self.credentials}
            self.pool = self.pool_class(**pool_config)

            if old_pool:
                self._close_pool_gracefully(old_pool)

            logger.info("Connection pool created with fresh credentials")

    def _close_pool_gracefully(self, pool: Any) -> None:
        """Close a connection pool gracefully."""
        try:
            if hasattr(pool, "closeall"):
                pool.closeall()
            elif hasattr(pool, "dispose"):
                pool.dispose()
            elif hasattr(pool, "close"):
                pool.close()
            logger.info("Old connection pool closed gracefully")
        except Exception as e:
            logger.warning(f"Error closing old pool: {e}")

    def _should_refresh_credentials(self) -> bool:
        """Check if credentials should be refreshed."""
        if not self.credentials_expire_at:
            return True
        return time.time() >= self.credentials_expire_at

    def _validate_connection(self, conn: Any) -> bool:
        """Validate a database connection."""
        try:
            cursor = conn.cursor()
            cursor.execute(self.validation_query)
            cursor.close()
            return True
        except Exception as e:
            logger.debug(f"Connection validation failed: {e}")
            return False

    @contextmanager
    def get_connection(self, retry: bool = True):
        """
        Get a database connection from the pool.

        Args:
            retry: Whether to retry with fresh credentials on failure.

        Yields:
            Database connection.

        Raises:
            Exception: If unable to get a valid connection.
        """
        if self._closing:
            raise RuntimeError("Connection manager is closing")

        if self._should_refresh_credentials():
            self._refresh_credentials()
            self._create_pool()

        conn = None
        try:
            conn = self._get_connection_from_pool()

            if not self._validate_connection(conn):
                if retry:
                    logger.info("Connection validation failed, refreshing credentials")
                    self._return_connection_to_pool(conn)
                    conn = None
                    self._refresh_credentials()
                    self._create_pool()
                    conn = self._get_connection_from_pool()
                else:
                    raise Exception("Connection validation failed")

            yield conn

        finally:
            if conn:
                self._return_connection_to_pool(conn)

    def _get_connection_from_pool(self) -> Any:
        """Get a connection from the pool (implementation depends on pool type)."""
        with self._lock:
            if hasattr(self.pool, "getconn"):
                return self.pool.getconn()
            elif hasattr(self.pool, "connection"):
                return self.pool.connection()
            elif hasattr(self.pool, "get"):
                return self.pool.get()
            else:
                raise NotImplementedError(f"Unsupported pool type: {type(self.pool)}")

    def _return_connection_to_pool(self, conn: Any) -> None:
        """Return a connection to the pool (implementation depends on pool type)."""
        try:
            with self._lock:
                if hasattr(self.pool, "putconn"):
                    self.pool.putconn(conn)
                elif hasattr(conn, "close"):
                    pass
                else:
                    warnings.warn("Unable to return connection to pool properly")
        except Exception as e:
            logger.debug(f"Error returning connection to pool: {e}")

    def refresh_now(self) -> None:
        """Force immediate credential refresh and pool recreation."""
        logger.info("Forcing credential refresh")
        self._refresh_credentials()
        self._create_pool()

    def close(self) -> None:
        """Close the connection manager and all connections."""
        self._closing = True
        with self._lock:
            if self.pool:
                self._close_pool_gracefully(self.pool)
                self.pool = None
        logger.info("Connection manager closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class BackgroundRefreshManager(DatabaseConnectionManager):
    """Connection manager with background credential refresh thread."""

    def __init__(self, *args, check_interval: int = 60, **kwargs):
        """
        Initialize with background refresh capability.

        Args:
            check_interval: How often to check for credential expiry (seconds).
            *args, **kwargs: Arguments for DatabaseConnectionManager.
        """
        super().__init__(*args, **kwargs)
        self.check_interval = check_interval
        self._refresh_thread = None
        self._stop_refresh = False
        self._start_background_refresh()

    def _start_background_refresh(self) -> None:
        """Start the background refresh thread."""
        self._refresh_thread = Thread(target=self._background_refresh_loop, daemon=True)
        self._refresh_thread.start()
        logger.info("Background credential refresh thread started")

    def _background_refresh_loop(self) -> None:
        """Background thread loop to refresh credentials proactively."""
        while not self._stop_refresh:
            try:
                if self._should_refresh_credentials():
                    logger.info("Background thread refreshing credentials")
                    self._refresh_credentials()
                    self._create_pool()
            except Exception as e:
                logger.error(f"Background refresh failed: {e}")

            time.sleep(self.check_interval)

    def close(self) -> None:
        """Close the manager and stop background thread."""
        self._stop_refresh = True
        if self._refresh_thread:
            self._refresh_thread.join(timeout=5)
        super().close()