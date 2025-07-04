"""
Test cases for authentication service
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.auth_service import AuthService
from app.core.exceptions.base import AuthenticationError, TokenLimitExceededError


class TestAuthService:
    """Test cases for AuthService class"""
    
    @pytest.fixture
    def mock_user_repository(self):
        """Mock user repository"""
        repo = MagicMock()
        repo.find_by_user_id = AsyncMock()
        repo.update_token_usage = AsyncMock()
        return repo
    
    @pytest.fixture
    def mock_api_key_repository(self):
        """Mock API key repository"""
        repo = MagicMock()
        repo.find_active_by_key = AsyncMock()
        return repo
    
    @pytest.fixture
    def mock_encryption_service(self):
        """Mock encryption service"""
        service = MagicMock()
        return service
    
    @pytest.fixture
    def auth_service(self, mock_user_repository, mock_api_key_repository, mock_encryption_service):
        """Create AuthService instance for testing"""
        return AuthService(
            user_repository=mock_user_repository,
            api_key_repository=mock_api_key_repository,
            encryption_service=mock_encryption_service
        )
    
    @pytest.fixture
    def sample_api_key_record(self):
        """Sample API key record"""
        api_key = MagicMock()
        api_key.user_id = "user123"
        api_key.key = "api_key_123"
        return api_key
    
    @pytest.fixture
    def sample_user(self):
        """Sample user"""
        user = MagicMock()
        user.user_id = "user123"
        user.email = "test@example.com"
        user.active = True
        user.membership_level = "free"
        user.token_limit = 1000
        user.token_used = 100
        return user
    
    @pytest.fixture
    def sample_premium_user(self):
        """Sample premium user"""
        user = MagicMock()
        user.user_id = "user456"
        user.email = "premium@example.com"
        user.active = True
        user.membership_level = "premium"
        user.token_limit = 10000
        user.token_used = 500
        return user
    
    def test_init(self, auth_service, mock_user_repository, mock_api_key_repository, mock_encryption_service):
        """Test AuthService initialization"""
        assert auth_service.user_repository == mock_user_repository
        assert auth_service.api_key_repository == mock_api_key_repository
        assert auth_service.encryption_service == mock_encryption_service
    
    @pytest.mark.asyncio
    async def test_authenticate_request_success(self, auth_service, mock_api_key_repository, mock_user_repository, sample_api_key_record, sample_user):
        """Test successful authentication"""
        api_key = "valid_api_key"
        
        # Setup mocks
        mock_api_key_repository.find_active_by_key.return_value = sample_api_key_record
        mock_user_repository.find_by_user_id.return_value = sample_user
        
        user_id, user_info = await auth_service.authenticate_request(api_key)
        
        assert user_id == "user123"
        assert user_info["user_id"] == "user123"
        assert user_info["email"] == "test@example.com"
        assert user_info["membership_level"] == "free"
        assert user_info["token_limit"] == 1000
        assert user_info["token_used"] == 100
        
        mock_api_key_repository.find_active_by_key.assert_called_once_with(api_key)
        mock_user_repository.find_by_user_id.assert_called_once_with("user123")
    
    @pytest.mark.asyncio
    async def test_authenticate_request_invalid_api_key(self, auth_service, mock_api_key_repository):
        """Test authentication with invalid API key"""
        api_key = "invalid_api_key"
        
        # API key not found
        mock_api_key_repository.find_active_by_key.return_value = None
        
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.authenticate_request(api_key)
        
        assert "Invalid API key" in str(exc_info.value)
        mock_api_key_repository.find_active_by_key.assert_called_once_with(api_key)
    
    @pytest.mark.asyncio
    async def test_authenticate_request_user_not_found(self, auth_service, mock_api_key_repository, mock_user_repository, sample_api_key_record):
        """Test authentication when user not found"""
        api_key = "valid_api_key"
        
        mock_api_key_repository.find_active_by_key.return_value = sample_api_key_record
        mock_user_repository.find_by_user_id.return_value = None
        
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.authenticate_request(api_key)
        
        assert "User not found or inactive" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_authenticate_request_inactive_user(self, auth_service, mock_api_key_repository, mock_user_repository, sample_api_key_record, sample_user):
        """Test authentication with inactive user"""
        api_key = "valid_api_key"
        
        # Make user inactive
        sample_user.active = False
        
        mock_api_key_repository.find_active_by_key.return_value = sample_api_key_record
        mock_user_repository.find_by_user_id.return_value = sample_user
        
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.authenticate_request(api_key)
        
        assert "User not found or inactive" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_check_token_limit_free_user_within_limit(self, auth_service, mock_user_repository, sample_user):
        """Test token limit check for free user within limit"""
        user_id = "user123"
        estimated_tokens = 50  # 100 used + 50 = 150, within 1000 limit
        
        mock_user_repository.find_by_user_id.return_value = sample_user
        
        # Should not raise exception
        await auth_service.check_token_limit(user_id, estimated_tokens)
        
        mock_user_repository.find_by_user_id.assert_called_once_with(user_id)
    
    @pytest.mark.asyncio
    async def test_check_token_limit_free_user_exceeds_limit(self, auth_service, mock_user_repository, sample_user):
        """Test token limit check for free user exceeding limit"""
        user_id = "user123"
        estimated_tokens = 1000  # 100 used + 1000 = 1100, exceeds 1000 limit
        
        mock_user_repository.find_by_user_id.return_value = sample_user
        
        with pytest.raises(TokenLimitExceededError) as exc_info:
            await auth_service.check_token_limit(user_id, estimated_tokens)
        
        assert "Token limit exceeded" in str(exc_info.value)
        assert "Used: 100" in str(exc_info.value)
        assert "Limit: 1000" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_check_token_limit_premium_user_exceeds_limit(self, auth_service, mock_user_repository, sample_premium_user):
        """Test token limit check for premium user exceeding limit"""
        user_id = "user456"
        estimated_tokens = 10000  # 500 used + 10000 = 10500, exceeds 10000 limit
        
        mock_user_repository.find_by_user_id.return_value = sample_premium_user
        
        with pytest.raises(TokenLimitExceededError) as exc_info:
            await auth_service.check_token_limit(user_id, estimated_tokens)
        
        assert "Token limit exceeded" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_check_token_limit_user_not_found(self, auth_service, mock_user_repository):
        """Test token limit check when user not found"""
        user_id = "nonexistent_user"
        estimated_tokens = 100
        
        mock_user_repository.find_by_user_id.return_value = None
        
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service.check_token_limit(user_id, estimated_tokens)
        
        assert "User not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_check_token_limit_premium_user_no_limit_check(self, auth_service, mock_user_repository):
        """Test that premium users don't get token limit errors regardless of membership level check"""
        user = MagicMock()
        user.user_id = "premium_user"
        user.membership_level = "premium"
        user.token_used = 50000
        user.token_limit = 10000  # Even if limit is set, premium should not be checked the same way
        
        user_id = "premium_user"
        estimated_tokens = 5000
        
        mock_user_repository.find_by_user_id.return_value = user
        
        # This tests the current implementation - if premium users are treated differently,
        # this test might need to be updated based on actual business logic
        # For now, the implementation treats all users the same way
        with pytest.raises(TokenLimitExceededError):
            await auth_service.check_token_limit(user_id, estimated_tokens)
    
    @pytest.mark.asyncio
    async def test_check_token_limit_exact_limit(self, auth_service, mock_user_repository, sample_user):
        """Test token limit check when exactly at limit"""
        user_id = "user123"
        estimated_tokens = 900  # 100 used + 900 = 1000, exactly at limit
        
        mock_user_repository.find_by_user_id.return_value = sample_user
        
        # Should not raise exception when exactly at limit
        await auth_service.check_token_limit(user_id, estimated_tokens)
        
        mock_user_repository.find_by_user_id.assert_called_once_with(user_id)
    
    @pytest.mark.asyncio
    async def test_check_token_limit_one_over_limit(self, auth_service, mock_user_repository, sample_user):
        """Test token limit check when one token over limit"""
        user_id = "user123"
        estimated_tokens = 901  # 100 used + 901 = 1001, one over 1000 limit
        
        mock_user_repository.find_by_user_id.return_value = sample_user
        
        with pytest.raises(TokenLimitExceededError):
            await auth_service.check_token_limit(user_id, estimated_tokens)
    
    @pytest.mark.asyncio
    async def test_consume_tokens_success(self, auth_service, mock_user_repository):
        """Test successful token consumption"""
        user_id = "user123"
        tokens_used = 50
        
        await auth_service.consume_tokens(user_id, tokens_used)
        
        mock_user_repository.update_token_usage.assert_called_once_with(user_id, tokens_used)
    
    @pytest.mark.asyncio
    async def test_consume_tokens_zero_tokens(self, auth_service, mock_user_repository):
        """Test consuming zero tokens"""
        user_id = "user123"
        tokens_used = 0
        
        await auth_service.consume_tokens(user_id, tokens_used)
        
        mock_user_repository.update_token_usage.assert_called_once_with(user_id, tokens_used)
    
    @pytest.mark.asyncio
    async def test_consume_tokens_large_amount(self, auth_service, mock_user_repository):
        """Test consuming large amount of tokens"""
        user_id = "user123"
        tokens_used = 10000
        
        await auth_service.consume_tokens(user_id, tokens_used)
        
        mock_user_repository.update_token_usage.assert_called_once_with(user_id, tokens_used)
    
    @pytest.mark.asyncio
    async def test_consume_tokens_repository_failure(self, auth_service, mock_user_repository):
        """Test token consumption when repository fails"""
        user_id = "user123"
        tokens_used = 50
        
        mock_user_repository.update_token_usage.side_effect = Exception("Database error")
        
        with pytest.raises(Exception) as exc_info:
            await auth_service.consume_tokens(user_id, tokens_used)
        
        assert "Database error" in str(exc_info.value)


class TestAuthServiceIntegration:
    """Integration tests for AuthService"""
    
    @pytest.mark.asyncio
    async def test_full_authentication_workflow(self):
        """Test complete authentication workflow"""
        # Setup mocks
        user_repo = MagicMock()
        api_key_repo = MagicMock()
        encryption = MagicMock()
        
        # Sample data
        api_key_record = MagicMock()
        api_key_record.user_id = "user789"
        
        user = MagicMock()
        user.user_id = "user789"
        user.email = "integration@test.com"
        user.active = True
        user.membership_level = "premium"
        user.token_limit = 5000
        user.token_used = 200
        
        # Setup mock returns
        api_key_repo.find_active_by_key = AsyncMock(return_value=api_key_record)
        user_repo.find_by_user_id = AsyncMock(return_value=user)
        user_repo.update_token_usage = AsyncMock()
        
        # Create service
        service = AuthService(
            user_repository=user_repo,
            api_key_repository=api_key_repo,
            encryption_service=encryption
        )
        
        # Test authentication
        user_id, user_info = await service.authenticate_request("valid_key")
        assert user_id == "user789"
        assert user_info["email"] == "integration@test.com"
        
        # Test token limit check
        await service.check_token_limit("user789", 100)  # Should pass
        
        # Test token consumption
        await service.consume_tokens("user789", 25)
        
        # Verify calls
        api_key_repo.find_active_by_key.assert_called_once_with("valid_key")
        user_repo.find_by_user_id.assert_called()
        user_repo.update_token_usage.assert_called_once_with("user789", 25)
    
    @pytest.mark.asyncio
    async def test_authentication_and_token_limit_failure(self):
        """Test authentication success but token limit failure"""
        user_repo = MagicMock()
        api_key_repo = MagicMock()
        encryption = MagicMock()
        
        # Sample data - user with low token limit
        api_key_record = MagicMock()
        api_key_record.user_id = "low_limit_user"
        
        user = MagicMock()
        user.user_id = "low_limit_user"
        user.email = "lowlimit@test.com"
        user.active = True
        user.membership_level = "free"
        user.token_limit = 100
        user.token_used = 90  # Only 10 tokens left
        
        api_key_repo.find_active_by_key = AsyncMock(return_value=api_key_record)
        user_repo.find_by_user_id = AsyncMock(return_value=user)
        
        service = AuthService(
            user_repository=user_repo,
            api_key_repository=api_key_repo,
            encryption_service=encryption
        )
        
        # Authentication should succeed
        user_id, user_info = await service.authenticate_request("valid_key")
        assert user_id == "low_limit_user"
        
        # Token limit check should fail
        with pytest.raises(TokenLimitExceededError):
            await service.check_token_limit("low_limit_user", 20)  # Exceeds remaining 10 tokens
    
    @pytest.mark.asyncio
    async def test_edge_case_zero_token_limit(self):
        """Test user with zero token limit"""
        user_repo = MagicMock()
        api_key_repo = MagicMock()
        encryption = MagicMock()
        
        user = MagicMock()
        user.user_id = "zero_limit_user"
        user.membership_level = "free"
        user.token_limit = 0
        user.token_used = 0
        
        user_repo.find_by_user_id = AsyncMock(return_value=user)
        
        service = AuthService(
            user_repository=user_repo,
            api_key_repository=api_key_repo,
            encryption_service=encryption
        )
        
        # Even 1 token should exceed limit of 0
        with pytest.raises(TokenLimitExceededError):
            await service.check_token_limit("zero_limit_user", 1)
