#!/usr/bin/env python3
"""Example usage of PyVault Agent with database connection pools."""

import os

from vault_agent import VaultAgentClient
from vault_agent.database_pool import (
    DatabaseConnectionManager,
    BackgroundRefreshManager,
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

vault_addr = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
vault_namespace = os.getenv("VAULT_NAMESPACE", None)

db_host = os.getenv("DB_HOST", "db.example.com")

role_id = os.getenv("VAULT_ROLE_ID", None)
secret_id = os.getenv("VAULT_SECRET_ID", None)


def example_psycopg2_pool():
    """Example using psycopg2 connection pool."""
    try:
        import psycopg2.pool
    except ImportError:
        print("psycopg2 not installed. Install with: pip install psycopg2-binary")
        return

    if not role_id or not secret_id:
        print("VAULT_ROLE_ID and VAULT_SECRET_ID must be set in environment")
        return

    client = VaultAgentClient(
        url=vault_addr,
        role_id=role_id,
        secret_id=secret_id,
        cache_ttl=300,
        max_cache_size=1000,
        namespace=vault_namespace,
    )

    print("\n=== PostgreSQL Connection Pool Example ===")

    manager = DatabaseConnectionManager(
        vault_client=client,
        role="sales-readonly",
        pool_class=psycopg2.pool.SimpleConnectionPool,
        pool_kwargs={
            "minconn": 1,
            "maxconn": 10,
            "host": db_host,
            "port": 5432,
            "database": "sales",
        },
        refresh_buffer=0.8,
        on_refresh=lambda creds: logger.info(f"Credentials refreshed: {creds['user']}"),
    )

    try:
        with manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_user, now()")
            result = cursor.fetchone()
            print(f"Connected as: {result[0]} at {result[1]}")
            cursor.close()

        with manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"PostgreSQL version: {version[:30]}...")
            cursor.close()

    finally:
        manager.close()


def example_background_refresh():
    """Example with background credential refresh."""
    try:
        import psycopg2.pool
    except ImportError:
        print("psycopg2 not installed. Install with: pip install psycopg2-binary")
        return

    if not role_id or not secret_id:
        print("VAULT_ROLE_ID and VAULT_SECRET_ID must be set in environment")
        return

    client = VaultAgentClient(
        url=vault_addr,
        role_id=role_id,
        secret_id=secret_id,
        cache_ttl=300,
        max_cache_size=1000,
        namespace=vault_namespace,
    )

    print("\n=== Background Refresh Example ===")

    with BackgroundRefreshManager(
        vault_client=client,
        role="sales-readonly",
        pool_class=psycopg2.pool.ThreadedConnectionPool,
        pool_kwargs={
            "minconn": 2,
            "maxconn": 10,
            "host": db_host,
            "port": 5432,
            "database": "sales",
        },
        refresh_buffer=0.8,
        check_interval=30,
    ) as manager:
        print("Background refresh manager started")

        for i in range(3):
            with manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
                print(f"Query {i + 1} executed on connection PID: {pid}")
                cursor.close()

            import time

            time.sleep(2)

        print("✓ Manager will close and stop background thread")


def example_error_handling():
    """Example showing error handling and retry logic."""

    if not role_id or not secret_id:
        print("VAULT_ROLE_ID and VAULT_SECRET_ID must be set in environment")
        return

    client = VaultAgentClient(
        url=vault_addr,
        role_id=role_id,
        secret_id=secret_id,
        cache_ttl=300,
        max_cache_size=1000,
        namespace=vault_namespace,
    )

    print("\n=== Error Handling Example ===")

    try:
        import psycopg2.pool

        manager = DatabaseConnectionManager(
            vault_client=client,
            role="sales-readonly",
            pool_class=psycopg2.pool.SimpleConnectionPool,
            pool_kwargs={
                "minconn": 1,
                "maxconn": 5,
                "host": db_host,
                "database": "sales",
            },
        )

        try:
            with manager.get_connection(retry=True) as conn:
                print("Connection obtained with retry enabled")

        except Exception as e:
            print(f"Connection failed even after retry: {e}")

        manager.refresh_now()
        print("Forced credential refresh completed")

        manager.close()

    except ImportError:
        print("psycopg2 not installed")
    except Exception as e:
        print(f"Error: {e}")


def main():
    """Run all examples."""
    print("=" * 60)
    print("PyVault Agent - Database Connection Pool Examples")
    print("=" * 60)

    example_psycopg2_pool()
    example_background_refresh()
    example_error_handling()

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
