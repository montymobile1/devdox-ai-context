"""
Test cases for custom exceptions
"""
import pytest
from app.core.exceptions.base import (
    DevDoxBaseException,
    DatabaseError,
    UserNotFoundError,
    RepoNotFoundError,
    ContextNotFoundError,
    APIKeyNotFoundError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    GitProviderError,
    ProcessingError,
    QueueError,
    ConfigurationError,
    RateLimitExceededError,
    TokenLimitExceededError,
    EmbeddingError,
    VectorStoreError
)


class TestDevDoxBaseException:
    """Test cases for DevDoxBaseException base class"""
    
    def test_base_exception_with_message_only(self):
        """Test base exception with message only"""
        exc = DevDoxBaseException("Test error message")
        
        assert str(exc) == "Test error message"
        assert exc.message == "Test error message"
        assert exc.error_code == "DevDoxBaseException"
    
    def test_base_exception_with_message_and_code(self):
        """Test base exception with message and custom error code"""
        exc = DevDoxBaseException("Test error", "CUSTOM_ERROR")
        
        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.error_code == "CUSTOM_ERROR"
    
    def test_base_exception_inheritance(self):
        """Test that base exception inherits from Exception"""
        exc = DevDoxBaseException("Test")
        assert isinstance(exc, Exception)
    
    def test_base_exception_equality(self):
        """Test exception equality comparison"""
        exc1 = DevDoxBaseException("Same message")
        exc2 = DevDoxBaseException("Same message")
        exc3 = DevDoxBaseException("Different message")
        
        # Note: Exception instances are not equal by default, even with same message
        assert str(exc1) == str(exc2)
        assert str(exc1) != str(exc3)
    
    def test_base_exception_with_empty_message(self):
        """Test base exception with empty message"""
        exc = DevDoxBaseException("")
        
        assert str(exc) == ""
        assert exc.message == ""
        assert exc.error_code == "DevDoxBaseException"
    
    def test_base_exception_with_none_error_code(self):
        """Test base exception with None error code"""
        exc = DevDoxBaseException("Test message", None)
        
        assert exc.error_code == "DevDoxBaseException"


class TestSpecificExceptions:
    """Test cases for specific exception classes"""
    
    def test_database_error(self):
        """Test DatabaseError exception"""
        exc = DatabaseError("Database connection failed")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Database connection failed"
        assert exc.error_code == "DatabaseError"
    
    def test_user_not_found_error(self):
        """Test UserNotFoundError exception"""
        exc = UserNotFoundError("User with ID 123 not found")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "User with ID 123 not found"
        assert exc.error_code == "UserNotFoundError"
    
    def test_repo_not_found_error(self):
        """Test RepoNotFoundError exception"""
        exc = RepoNotFoundError("Repository test/repo not found")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Repository test/repo not found"
        assert exc.error_code == "RepoNotFoundError"
    
    def test_context_not_found_error(self):
        """Test ContextNotFoundError exception"""
        exc = ContextNotFoundError("Context ctx123 not found")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Context ctx123 not found"
        assert exc.error_code == "ContextNotFoundError"
    
    def test_api_key_not_found_error(self):
        """Test APIKeyNotFoundError exception"""
        exc = APIKeyNotFoundError("Invalid API key")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Invalid API key"
        assert exc.error_code == "APIKeyNotFoundError"
    
    def test_authentication_error(self):
        """Test AuthenticationError exception"""
        exc = AuthenticationError("Authentication failed")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Authentication failed"
        assert exc.error_code == "AuthenticationError"
    
    def test_authorization_error(self):
        """Test AuthorizationError exception"""
        exc = AuthorizationError("User not authorized for this operation")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "User not authorized for this operation"
        assert exc.error_code == "AuthorizationError"
    
    def test_validation_error(self):
        """Test ValidationError exception"""
        exc = ValidationError("Data validation failed")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Data validation failed"
        assert exc.error_code == "ValidationError"
    
    def test_git_provider_error(self):
        """Test GitProviderError exception"""
        exc = GitProviderError("GitHub API rate limit exceeded")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "GitHub API rate limit exceeded"
        assert exc.error_code == "GitProviderError"
    
    def test_processing_error(self):
        """Test ProcessingError exception"""
        exc = ProcessingError("Repository processing failed")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Repository processing failed"
        assert exc.error_code == "ProcessingError"
    
    def test_queue_error(self):
        """Test QueueError exception"""
        exc = QueueError("Queue operation failed")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Queue operation failed"
        assert exc.error_code == "QueueError"
    
    def test_configuration_error(self):
        """Test ConfigurationError exception"""
        exc = ConfigurationError("Invalid configuration")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Invalid configuration"
        assert exc.error_code == "ConfigurationError"
    
    def test_rate_limit_exceeded_error(self):
        """Test RateLimitExceededError exception"""
        exc = RateLimitExceededError("Rate limit exceeded")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Rate limit exceeded"
        assert exc.error_code == "RateLimitExceededError"
    
    def test_token_limit_exceeded_error(self):
        """Test TokenLimitExceededError exception"""
        exc = TokenLimitExceededError("Token usage limit exceeded")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Token usage limit exceeded"
        assert exc.error_code == "TokenLimitExceededError"
    
    def test_embedding_error(self):
        """Test EmbeddingError exception"""
        exc = EmbeddingError("Error generating embeddings")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Error generating embeddings"
        assert exc.error_code == "EmbeddingError"
    
    def test_vector_store_error(self):
        """Test VectorStoreError exception"""
        exc = VectorStoreError("Vector store operation failed")
        
        assert isinstance(exc, DevDoxBaseException)
        assert str(exc) == "Vector store operation failed"
        assert exc.error_code == "VectorStoreError"


class TestExceptionWithCustomErrorCodes:
    """Test exceptions with custom error codes"""
    
    def test_database_error_with_custom_code(self):
        """Test DatabaseError with custom error code"""
        exc = DatabaseError("Connection timeout", "DB_TIMEOUT")
        
        assert str(exc) == "Connection timeout"
        assert exc.error_code == "DB_TIMEOUT"
    
    def test_authentication_error_with_custom_code(self):
        """Test AuthenticationError with custom error code"""
        exc = AuthenticationError("Invalid credentials", "INVALID_CREDS")
        
        assert str(exc) == "Invalid credentials"
        assert exc.error_code == "INVALID_CREDS"
    
    def test_processing_error_with_custom_code(self):
        """Test ProcessingError with custom error code"""
        exc = ProcessingError("Embedding generation failed", "EMBEDDING_FAILED")
        
        assert str(exc) == "Embedding generation failed"
        assert exc.error_code == "EMBEDDING_FAILED"


class TestExceptionRaising:
    """Test exception raising behavior"""
    
    def test_raise_database_error(self):
        """Test raising DatabaseError"""
        with pytest.raises(DatabaseError) as exc_info:
            raise DatabaseError("Database error occurred")
        
        assert "Database error occurred" in str(exc_info.value)
        assert exc_info.value.error_code == "DatabaseError"
    
    def test_raise_authentication_error(self):
        """Test raising AuthenticationError"""
        with pytest.raises(AuthenticationError) as exc_info:
            raise AuthenticationError("Authentication failed")
        
        assert "Authentication failed" in str(exc_info.value)
        assert exc_info.value.error_code == "AuthenticationError"
    
    def test_catch_as_base_exception(self):
        """Test catching specific exception as base exception"""
        with pytest.raises(DevDoxBaseException) as exc_info:
            raise UserNotFoundError("User not found")
        
        assert isinstance(exc_info.value, UserNotFoundError)
        assert isinstance(exc_info.value, DevDoxBaseException)
    
    def test_catch_as_standard_exception(self):
        """Test catching custom exception as standard Exception"""
        with pytest.raises(Exception) as exc_info:
            raise ValidationError("Validation failed")
        
        assert isinstance(exc_info.value, ValidationError)
        assert isinstance(exc_info.value, Exception)


class TestExceptionChaining:
    """Test exception chaining and context"""
    
    def test_exception_chaining_from_other_exception(self):
        """Test raising custom exception from another exception"""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise DatabaseError("Database operation failed") from e
        except DatabaseError as exc:
            assert str(exc) == "Database operation failed"
            assert exc.__cause__ is not None
            assert isinstance(exc.__cause__, ValueError)
            assert str(exc.__cause__) == "Original error"
    
    def test_exception_context_preservation(self):
        """Test exception context preservation"""
        try:
            try:
                raise KeyError("Missing key")
            except KeyError:
                raise ProcessingError("Processing failed")
        except ProcessingError as exc:
            assert str(exc) == "Processing failed"
            assert exc.__context__ is not None
            assert isinstance(exc.__context__, KeyError)


class TestExceptionAttributes:
    """Test exception attribute access and modification"""
    
    def test_modify_exception_attributes(self):
        """Test modifying exception attributes after creation"""
        exc = GitProviderError("Initial message")
        
        # Attributes can be modified
        exc.message = "Modified message"
        exc.error_code = "MODIFIED_CODE"
        
        # But str() still returns the original message passed to Exception
        assert str(exc) == "Initial message"
        assert exc.message == "Modified message"
        assert exc.error_code == "MODIFIED_CODE"
    
    def test_exception_with_additional_attributes(self):
        """Test adding additional attributes to exceptions"""
        exc = TokenLimitExceededError("Token limit exceeded")
        
        # Add custom attributes
        exc.user_id = "user123"
        exc.tokens_used = 1500
        exc.tokens_limit = 1000
        
        assert exc.user_id == "user123"
        assert exc.tokens_used == 1500
        assert exc.tokens_limit == 1000
        assert str(exc) == "Token limit exceeded"
    
    def test_exception_serialization_properties(self):
        """Test exception properties for serialization"""
        exc = AuthenticationError("Auth failed", "AUTH_FAILED")
        
        # Test that we can access all properties needed for serialization
        assert hasattr(exc, 'message')
        assert hasattr(exc, 'error_code')
        assert exc.message == "Auth failed"
        assert exc.error_code == "AUTH_FAILED"
        
        # Test dict-like access for serialization
        error_dict = {
            'message': exc.message,
            'error_code': exc.error_code,
            'exception_type': exc.__class__.__name__
        }
        
        assert error_dict['message'] == "Auth failed"
        assert error_dict['error_code'] == "AUTH_FAILED"
        assert error_dict['exception_type'] == "AuthenticationError"
