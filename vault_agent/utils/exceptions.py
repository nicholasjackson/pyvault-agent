"""Custom exceptions for PyVault Agent."""


class VaultAgentError(Exception):
    """Base exception for PyVault Agent errors."""
    pass


class AuthenticationError(VaultAgentError):
    """Raised when authentication fails."""
    pass


class CacheError(VaultAgentError):
    """Raised when cache operations fail."""
    pass


class SecretNotFoundError(VaultAgentError):
    """Raised when a secret is not found."""
    pass