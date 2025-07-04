"""
Custom exception classes for the DevDox AI Context service.
"""

class DevDoxBaseException(Exception):
    """Base exception for all DevDox exceptions"""
    
    def __init__(self, message: str, error_code: str = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__


class DatabaseError(DevDoxBaseException):
    """Database operation errors"""
    pass


class UserNotFoundError(DevDoxBaseException):
    """User not found in database"""
    pass


class RepoNotFoundError(DevDoxBaseException):
    """Repository not found"""
    pass


class ContextNotFoundError(DevDoxBaseException):
    """Context not found"""
    pass


class APIKeyNotFoundError(DevDoxBaseException):
    """API key not found or invalid"""
    pass


class AuthenticationError(DevDoxBaseException):
    """Authentication failed"""
    pass


class AuthorizationError(DevDoxBaseException):
    """User not authorized for this operation"""
    pass


class ValidationError(DevDoxBaseException):
    """Data validation failed"""
    pass


class GitProviderError(DevDoxBaseException):
    """Git provider API error"""
    pass


class ProcessingError(DevDoxBaseException):
    """Repository processing error"""
    pass


class QueueError(DevDoxBaseException):
    """Queue operation error"""
    pass


class ConfigurationError(DevDoxBaseException):
    """Configuration error"""
    pass


class RateLimitExceededError(DevDoxBaseException):
    """Rate limit exceeded"""
    pass


class TokenLimitExceededError(DevDoxBaseException):
    """Token usage limit exceeded"""
    pass


class EmbeddingError(DevDoxBaseException):
    """Error generating embeddings"""
    pass


class VectorStoreError(DevDoxBaseException):
    """Vector store operation error"""
    pass
