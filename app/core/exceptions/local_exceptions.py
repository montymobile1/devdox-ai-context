"""
Custom exception classes for the DevDox AI Context service.
"""
from typing import Optional

from app.core.exceptions.custom_exceptions import DevDoxAPIException


class DatabaseError(DevDoxAPIException):
    """Database operation errors"""
    
    def __init__(self, user_message=None, log_level="exception", internal_context: Optional[dict] = None):
        log_message = user_message
        
        super().__init__(
            user_message=user_message, log_message=log_message, log_level=log_level, internal_context=internal_context
        )


class UserNotFoundError(DevDoxAPIException):
    """User not found in database"""
    pass


class RepoNotFoundError(DevDoxAPIException):
    """Repository not found"""
    
    def __init__(self, user_message=None, log_level="error", internal_context: Optional[dict] = None):
        log_message = user_message
        
        super().__init__(
            user_message=user_message, log_message=log_message, log_level=log_level, internal_context=internal_context
        )


class ContextNotFoundError(DevDoxAPIException):
    """Context not found"""
    
    def __init__(self, user_message=None, log_level="error", internal_context: Optional[dict] = None):
        log_message = user_message
        
        super().__init__(
            user_message=user_message, log_message=log_message, log_level=log_level, internal_context=internal_context
        )


class APIKeyNotFoundError(DevDoxAPIException):
    """API key not found or invalid"""
    pass


class AuthenticationError(DevDoxAPIException):
    """Authentication failed"""
    
    def __init__(self, user_message=None, log_level="error", internal_context: Optional[dict] = None):
        log_message = user_message
        
        super().__init__(
            user_message=user_message, log_message=log_message, log_level=log_level, internal_context=internal_context
        )


class AuthorizationError(DevDoxAPIException):
    """User not authorized for this operation"""
    pass


class ValidationError(DevDoxAPIException):
    """Data validation failed"""
    pass


class GitProviderError(DevDoxAPIException):
    """Git provider API error"""
    pass


class ProcessingError(DevDoxAPIException):
    """Repository processing error"""
    
    def __init__(self, user_message=None):
        
        super().__init__(
            user_message=user_message
        )


class QueueError(DevDoxAPIException):
    """Queue operation error"""
    pass


class ConfigurationError(DevDoxAPIException):
    """Configuration error"""
    pass


class RateLimitExceededError(DevDoxAPIException):
    """Rate limit exceeded"""
    pass


class TokenLimitExceededError(DevDoxAPIException):
    """Token usage limit exceeded"""
    
    def __init__(self, user_message=None, log_level="error", internal_context: Optional[dict] = None):
        log_message = user_message
        
        super().__init__(
            user_message=user_message, log_message=log_message, log_level=log_level, internal_context=internal_context
        )


class EmbeddingError(DevDoxAPIException):
    """Error generating embeddings"""
    pass


class VectorStoreError(DevDoxAPIException):
    """Vector store operation error"""
    pass
