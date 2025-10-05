# PyVault Agent

A Python implementation of Vault Agent providing client-side caching and automatic authentication for HashiCorp Vault. PyVault Agent brings the core functionality of HashiCorp's Vault Agent directly into your Python applications as a library, eliminating the need for external processes while providing the same benefits of credential caching and automatic token management.

## Why PyVault Agent?

Traditional HashiCorp Vault Agent runs as a separate daemon process that manages authentication and caching. PyVault Agent provides the same functionality as an embedded Python library, offering several advantages:

- **Simplified deployment**: No need to manage separate agent processes
- **Direct integration**: Native Python API for your applications
- **Reduced complexity**: Single process architecture eliminates IPC overhead
- **Fine-grained control**: Programmatic access to cache management and configuration
- **Development friendly**: Easy to use in development environments and testing

## Key Problems Solved

1. **Credential Management**: Automatically handles AppRole authentication and token renewal
2. **Performance Optimization**: Caches secrets to reduce Vault API calls and improve response times
3. **Connection Pool Issues**: Manages database connection pools with expiring credentials
4. **Token Expiration**: Seamlessly re-authenticates when tokens expire
5. **Thread Safety**: Safe for use in multi-threaded applications

## Features

- **Client-side caching**: Reduces API calls to Vault with configurable TTL
- **Automatic re-authentication**: Seamlessly handles token expiration
- **AppRole authentication**: Secure authentication using role ID and secret ID
- **KV secrets engine support**: Read-only secret access with version support (v1 & v2)
- **Database secrets engine**: Manage dynamic database credentials
- **Connection pool management**: Automatic credential refresh for database pools
- **Thread-safe caching**: Safe for concurrent usage

## Installation

```bash
pip install pyvault-agent
```

## Quick Start

### Environment Setup

```bash
export VAULT_ADDR="https://vault.example.com"
export VAULT_ROLE_ID="your-role-id"
export VAULT_SECRET_ID="your-secret-id"
```

### Basic Usage

```python
import os
from vault_agent import VaultAgentClient

# Initialize the client with AppRole credentials
client = VaultAgentClient(
    url=os.getenv("VAULT_ADDR"),
    role_id=os.getenv("VAULT_ROLE_ID"),
    secret_id=os.getenv("VAULT_SECRET_ID"),
    cache_ttl=300,  # Cache for 5 minutes
    max_cache_size=1000
)

# KV Secrets - Read application configuration
try:
    config = client.kv.read("myapp/config")
    api_key = config["api_key"]
    db_password = config["db_password"]
    print("Configuration loaded from Vault")
except Exception as e:
    print(f"Failed to load config: {e}")

# Database Credentials - Get dynamic database credentials
try:
    creds = client.database.get_credentials("myapp-db-role")
    print(f"Database user: {creds['username']}")

    # Create connection string
    conn_str = client.database.get_connection_string(
        role="myapp-db-role",
        template="postgresql://{username}:{password}@{host}:{port}/{database}",
        host="db.example.com",
        port=5432,
        database="myapp"
    )
except Exception as e:
    print(f"Failed to get database credentials: {e}")

# Cache Management - Monitor cache performance
stats = client.get_cache_stats()
print(f"Cache efficiency: {stats['hits']}/{stats['hits'] + stats['misses']} hits")
```

## Advanced Usage

### Configuration Options

```python
client = VaultAgentClient(
    url="https://vault.example.com",
    role_id="role-id",
    secret_id="secret-id",
    cache_ttl=300,           # Default cache TTL in seconds
    max_cache_size=1000,     # Maximum number of cached entries
    namespace="team-a",      # Vault namespace (Enterprise)
    verify=True              # SSL certificate verification
)
```

### Working with Different Secret Engines

```python
# KV v1 secrets (using default "secret" mount point)
config = client.kv.read("app/config")

# KV v2 secrets with versioning (using default "secret" mount point)
config = client.kv.read("app/config")
old_config = client.kv.read("app/config", version=1)

# Using custom mount points
client_custom = VaultAgentClient(
    url="https://vault.example.com",
    role_id="role-id",
    secret_id="secret-id",
    kv_mount_point="kv-v2",  # Custom KV mount point
    database_mount_point="db"  # Custom database mount point
)

# Database dynamic credentials
creds = client.database.get_credentials("postgres-readonly")

# Database static credentials
static_creds = client.database.get_static_credentials("app-service-account")
```

### Database Connection Pools

One of the key challenges with dynamic database credentials is managing connection pools when credentials expire. PyVault Agent provides a `DatabaseConnectionManager` that automatically handles credential refresh and pool recreation:

```python
from vault_agent import VaultAgentClient, DatabaseConnectionManager
import psycopg2.pool

client = VaultAgentClient(...)

# Managed connection pool with auto-refresh
with DatabaseConnectionManager(
    vault_client=client,
    role="postgres-role",
    pool_class=psycopg2.pool.SimpleConnectionPool,
    pool_kwargs={
        "minconn": 1,
        "maxconn": 10,
        "host": "db.example.com",
        "database": "myapp"
    },
    refresh_buffer=0.8,  # Refresh at 80% of credential TTL
    validation_query="SELECT 1",  # Query to validate connections
) as manager:

    # Get connections that are automatically managed
    with manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        results = cursor.fetchall()
```

#### Background Refresh

For high-performance applications, use `BackgroundRefreshManager` to refresh credentials proactively:

```python
from vault_agent import BackgroundRefreshManager

with BackgroundRefreshManager(
    vault_client=client,
    role="postgres-role",
    pool_class=psycopg2.pool.ThreadedConnectionPool,
    pool_kwargs={"minconn": 2, "maxconn": 10, "host": "db.example.com"},
    check_interval=30,  # Check every 30 seconds
) as manager:
    # Credentials refresh in background, zero-latency for requests
    with manager.get_connection() as conn:
        # Your database operations
        pass
```

### Error Handling and Resilience

```python
from vault_agent.utils import SecretNotFoundError, AuthenticationError

try:
    # Attempt to read secret with automatic retry
    config = client.kv.read("secret/data/app/config")
except SecretNotFoundError:
    print("Secret not found - using defaults")
    config = {"api_key": "default"}
except AuthenticationError:
    print("Failed to authenticate with Vault")
    # Handle authentication failure
except Exception as e:
    print(f"Unexpected error: {e}")
    # Handle other errors

# Cache management
if client.get_cache_stats()["size"] > 500:
    client.clear_cache()  # Clear cache if getting too large
```

### Integration with Existing Applications

#### Django Integration

```python
# settings.py
import os
from vault_agent import VaultAgentClient

vault_client = VaultAgentClient(
    url=os.getenv("VAULT_ADDR"),
    role_id=os.getenv("VAULT_ROLE_ID"),
    secret_id=os.getenv("VAULT_SECRET_ID"),
)

# Get database credentials
db_creds = vault_client.database.get_credentials("django-db-role")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'myapp',
        'USER': db_creds['username'],
        'PASSWORD': db_creds['password'],
        'HOST': 'db.example.com',
        'PORT': '5432',
    }
}
```

#### Flask Integration

```python
from flask import Flask
from vault_agent import VaultAgentClient

app = Flask(__name__)

# Initialize Vault client
vault_client = VaultAgentClient(
    url=os.getenv("VAULT_ADDR"),
    role_id=os.getenv("VAULT_ROLE_ID"),
    secret_id=os.getenv("VAULT_SECRET_ID"),
)

@app.before_first_request
def setup():
    # Load configuration from Vault
    config = vault_client.kv.read("secret/data/flask/config")
    app.config.update(config)
```

## Development and Testing

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run unit tests
pytest tests/

# Run functional tests (requires Vault dev server)
vault server -dev -dev-root-token-id="root"
VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root pytest tests/functional/

# Run with coverage
pytest --cov=vault_agent tests/
```

### Development Setup

```bash
# Clone the repository
git clone https://github.com/your-username/pyvault-agent.git
cd pyvault-agent

# Install in development mode
pip install -e ".[dev]"

# Run linting and formatting
black vault_agent/ tests/
ruff vault_agent/ tests/
mypy vault_agent/
```

### Running Examples

```bash
# Set environment variables
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_ROLE_ID="your-role-id"
export VAULT_SECRET_ID="your-secret-id"

# Run basic example
python example.py

# Run connection pool example
python example_pool.py
```

## Performance Considerations

### Cache Tuning

- **TTL**: Set appropriate cache TTL based on secret sensitivity and change frequency
- **Size**: Limit cache size to prevent memory growth in long-running applications
- **Hit Rate**: Monitor cache hit rates to optimize TTL settings

```python
# Monitor cache performance
stats = client.get_cache_stats()
hit_rate = stats['hits'] / (stats['hits'] + stats['misses'])
print(f"Cache hit rate: {hit_rate:.2%}")

# Adjust TTL based on performance needs
if hit_rate < 0.8:  # Less than 80% hit rate
    client.set_cache_ttl(600)  # Increase TTL
```

### Connection Pool Best Practices

- **Buffer**: Set refresh_buffer to 0.7-0.8 to refresh before expiry
- **Validation**: Use connection validation to catch stale connections
- **Pool Size**: Size pools appropriately for your application load
- **Monitoring**: Monitor credential refresh frequency

## Security Considerations

1. **Secure Storage**: Store role_id and secret_id securely (environment variables, not in code)
2. **Network Security**: Use HTTPS for Vault connections in production
3. **Credential Rotation**: Regularly rotate AppRole credentials
4. **Audit Logging**: Enable Vault audit logging to track secret access
5. **Least Privilege**: Configure Vault policies with minimal required permissions

## Troubleshooting

### Common Issues

**Authentication Failures**
```python
# Check Vault connectivity
try:
    client = VaultAgentClient(url="https://vault.example.com", ...)
except AuthenticationError as e:
    print(f"Auth failed: {e}")
    # Check role_id and secret_id
```

**Cache Issues**
```python
# Clear cache if data seems stale
client.clear_cache()

# Check cache statistics
stats = client.get_cache_stats()
print(f"Cache size: {stats['size']}")
```

**Connection Pool Problems**
```python
# Force credential refresh
manager.refresh_now()

# Check credential expiry
print(f"Credentials expire at: {manager.credentials_expire_at}")
```

### Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# This will show cache hits/misses and authentication events
client = VaultAgentClient(...)
```

## Roadmap

### Current Version (0.1.0)
- [x] AppRole authentication with automatic re-auth
- [x] KV secrets engine (v1 & v2) read-only access with caching
- [x] Database secrets engine read-only access with caching
- [x] Connection pool management
- [x] Thread-safe operations

### Planned Features

- [ ] **Token renewal**: Proactive token refresh before expiry
- [ ] **Lease renewal**: Automatic secret lease renewal
- [ ] **Additional auth methods**: JWT, Kubernetes, AWS IAM
- [ ] **More secret engines**: PKI, Transit, SSH
- [ ] **Metrics integration**: Prometheus metrics export
- [ ] **Configuration files**: YAML/TOML configuration support
- [ ] **Async support**: AsyncIO-compatible client

## Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests to our GitHub repository.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.