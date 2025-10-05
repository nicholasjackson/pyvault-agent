#!/usr/bin/env python3
"""Example usage of WatsonX Vault Client."""

import os
from vault_agent import VaultAgentClient
from vault_agent.utils import SecretNotFoundError

vault_addr = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
vault_namespace = os.getenv("VAULT_NAMESPACE", None)

db_host = os.getenv("DB_HOST", "db.example.com")

role_id = os.getenv("VAULT_ROLE_ID", None)
secret_id = os.getenv("VAULT_SECRET_ID", None)


def main():
    """Demonstrate WatsonX Vault Client usage."""

    if not role_id or not secret_id:
        print("VAULT_ROLE_ID and VAULT_SECRET_ID must be set in environment")
        return

    client = VaultAgentClient(
        url=vault_addr,
        role_id=role_id,
        secret_id=secret_id,
        cache_ttl=300,
        max_cache_size=1000,
        kv_mount_point="kv",
        namespace=vault_namespace,
    )

    print("\n=== KV Secrets Example ===")

    try:
        retrieved_config = client.kv.read("api")
        print(f"Retrieved config: {retrieved_config}")

        cached_config = client.kv.read("api")
        print(f"Retrieved from cache (second call) {cached_config}")

    except SecretNotFoundError as e:
        print(f"Secret not found: {e}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n=== Database Credentials Example ===")

    try:
        db_creds = client.database.get_credentials("sales-readonly")
        print("Database credentials:")
        print(f"  Username: {db_creds['username']}")
        print(f"  Password: {db_creds['password'][:8]}...")

        conn_string = client.database.get_connection_string(
            role="sales-readonly",
            template="postgresql://{username}:{password}@{host}:{port}/{database}",
            host="db.example.com",
            port=5432,
            database="myapp",
        )
        print(f"Connection string: {conn_string[:50]}...")

        cached_creds = client.database.get_credentials("sales-readonly")
        print("Credentials retrieved from cache")

    except SecretNotFoundError as e:
        print(f"Database role not found: {e}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n=== Cache Statistics ===")

    stats = client.get_cache_stats()
    print(f"Cache hits: {stats['hits']}")
    print(f"Cache misses: {stats['misses']}")
    print(f"Cache size: {stats['size']}/{stats['max_size']}")

    print("\n=== Cache Management ===")

    client.set_cache_ttl(600)
    print("Updated cache TTL to 600 seconds")

    client.clear_cache()
    print("Cache cleared")


if __name__ == "__main__":
    main()
