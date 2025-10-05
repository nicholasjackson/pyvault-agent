"""Tests for database connection pool manager."""

import time
import unittest
from unittest.mock import Mock, MagicMock, patch, call
from vault_agent.database_pool import DatabaseConnectionManager, BackgroundRefreshManager


class MockPool:
    """Mock connection pool for testing."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connections = []
        self.closed = False

    def getconn(self):
        """Get a mock connection."""
        conn = Mock()
        conn.cursor.return_value.execute = Mock()
        conn.cursor.return_value.close = Mock()
        self.connections.append(conn)
        return conn

    def putconn(self, conn):
        """Return a connection to the pool."""
        pass

    def closeall(self):
        """Close all connections."""
        self.closed = True


class TestDatabaseConnectionManager(unittest.TestCase):
    """Test cases for DatabaseConnectionManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_vault_client = Mock()
        self.mock_vault_client.database.client.secrets.database.generate_credentials.return_value = {
            "data": {
                "username": "test_user",
                "password": "test_pass",
            },
            "lease_duration": 3600,
        }
        self.mock_vault_client.database.mount_point = "database"

    def test_initialization(self):
        """Test manager initialization."""
        manager = DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
            pool_kwargs={"host": "localhost"},
        )

        self.assertEqual(manager.role, "test-role")
        self.assertIsNotNone(manager.pool)
        self.assertIsNotNone(manager.credentials)
        self.assertEqual(manager.credentials["user"], "test_user")
        self.assertEqual(manager.credentials["password"], "test_pass")

    def test_get_connection(self):
        """Test getting a connection from the pool."""
        manager = DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
        )

        with manager.get_connection() as conn:
            self.assertIsNotNone(conn)
            conn.cursor.assert_called()

    def test_credential_refresh_on_expiry(self):
        """Test credentials are refreshed when expired."""
        manager = DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
            refresh_buffer=0.0001,
        )

        initial_expire_time = manager.credentials_expire_at

        time.sleep(0.001)

        with manager.get_connection() as conn:
            pass

        self.assertGreater(manager.credentials_expire_at, initial_expire_time)
        self.assertEqual(
            self.mock_vault_client.database.client.secrets.database.generate_credentials.call_count,
            2,
        )

    def test_connection_validation(self):
        """Test connection validation logic."""
        manager = DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
            validation_query="SELECT 1",
        )

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor

        result = manager._validate_connection(mock_conn)
        self.assertTrue(result)
        mock_cursor.execute.assert_called_with("SELECT 1")

        mock_cursor.execute.side_effect = Exception("Connection error")
        result = manager._validate_connection(mock_conn)
        self.assertFalse(result)

    def test_refresh_callback(self):
        """Test refresh callback is called."""
        callback = Mock()

        manager = DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
            on_refresh=callback,
        )

        callback.assert_called_once()
        self.assertEqual(callback.call_args[0][0]["user"], "test_user")

    def test_force_refresh(self):
        """Test forcing credential refresh."""
        manager = DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
        )

        initial_pool = manager.pool
        manager.refresh_now()

        self.assertNotEqual(manager.pool, initial_pool)
        self.assertEqual(
            self.mock_vault_client.database.client.secrets.database.generate_credentials.call_count,
            2,
        )

    def test_pool_graceful_close(self):
        """Test pools are closed gracefully when refreshed."""
        manager = DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
        )

        old_pool = manager.pool
        manager.refresh_now()

        self.assertTrue(old_pool.closed)

    def test_context_manager(self):
        """Test using manager as context manager."""
        with DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
        ) as manager:
            self.assertIsNotNone(manager.pool)

        self.assertIsNone(manager.pool)

    def test_retry_on_validation_failure(self):
        """Test retry logic when connection validation fails."""
        manager = DatabaseConnectionManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
        )

        with patch.object(manager, "_validate_connection") as mock_validate:
            mock_validate.side_effect = [False, True]

            with manager.get_connection(retry=True) as conn:
                self.assertIsNotNone(conn)

            self.assertEqual(
                self.mock_vault_client.database.client.secrets.database.generate_credentials.call_count,
                2,
            )


class TestBackgroundRefreshManager(unittest.TestCase):
    """Test cases for BackgroundRefreshManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_vault_client = Mock()
        self.mock_vault_client.database.client.secrets.database.generate_credentials.return_value = {
            "data": {
                "username": "test_user",
                "password": "test_pass",
            },
            "lease_duration": 3600,
        }
        self.mock_vault_client.database.mount_point = "database"

    def test_background_thread_starts(self):
        """Test background refresh thread starts."""
        manager = BackgroundRefreshManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
            check_interval=1,
        )

        self.assertIsNotNone(manager._refresh_thread)
        self.assertTrue(manager._refresh_thread.is_alive())

        manager.close()

    @patch("time.sleep")
    def test_background_refresh_loop(self, mock_sleep):
        """Test background refresh loop logic."""
        manager = BackgroundRefreshManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
            check_interval=1,
            refresh_buffer=0.0001,
        )

        time.sleep(0.001)
        manager._background_refresh_loop()

        self.assertGreater(
            self.mock_vault_client.database.client.secrets.database.generate_credentials.call_count,
            1,
        )

        manager.close()

    def test_background_thread_stops_on_close(self):
        """Test background thread stops when manager closes."""
        manager = BackgroundRefreshManager(
            vault_client=self.mock_vault_client,
            role="test-role",
            pool_class=MockPool,
            check_interval=1,
        )

        thread = manager._refresh_thread
        self.assertTrue(thread.is_alive())

        manager.close()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()