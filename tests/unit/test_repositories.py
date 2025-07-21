"""
Test cases for database repositories
"""
import pytest
from datetime import datetime, timezone
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.infrastructure.database.repositories import (
    BaseRepository,
    UserRepositoryInterface,
    TortoiseUserRepository,
    APIKeyRepositoryInterface,
    TortoiseAPIKeyRepository,
    RepoRepositoryInterface,
    TortoiseRepoRepository,
    ContextRepositoryInterface,
    TortoiseContextRepository,
    ContextCodeChunkInterface,
    TortoiseCodeChunks
)
from app.core.exceptions.local_exceptions import (
    RepoNotFoundError,
    ContextNotFoundError,
    DatabaseError
)


class TestBaseRepository:
    """Test cases for BaseRepository abstract class"""
    
    def test_base_repository_is_abstract(self):
        """Test that BaseRepository cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BaseRepository()
    
    def test_base_repository_methods_are_abstract(self):
        """Test that BaseRepository methods are abstract"""
        from abc import ABC
        assert issubclass(BaseRepository, ABC)
        
        # Check that abstract methods exist
        abstract_methods = BaseRepository.__abstractmethods__
        expected_methods = {'find_by_id', 'create', 'update', 'delete'}
        assert expected_methods.issubset(abstract_methods)


class TestUserRepositoryInterface:
    """Test cases for UserRepositoryInterface"""
    
    def test_user_repository_interface_is_abstract(self):
        """Test that UserRepositoryInterface cannot be instantiated directly"""
        with pytest.raises(TypeError):
            UserRepositoryInterface()
    
    def test_user_repository_interface_methods(self):
        """Test that UserRepositoryInterface has expected abstract methods"""
        abstract_methods = UserRepositoryInterface.__abstractmethods__
        expected_methods = {'find_by_user_id', 'update_token_usage', 'create_user'}
        assert expected_methods.issubset(abstract_methods)


class TestTortoiseUserRepository:
    """Test cases for TortoiseUserRepository"""
    
    @pytest.fixture
    def user_repository(self):
        """Create TortoiseUserRepository instance for testing"""
        return TortoiseUserRepository()
    
    @pytest.fixture
    def sample_user(self):
        """Sample user object"""
        user = MagicMock()
        user.user_id = "user123"
        user.email = "test@example.com"
        user.token_used = 100
        user.save = AsyncMock()
        return user
    
    def test_user_repository_implements_interface(self, user_repository):
        """Test that TortoiseUserRepository implements UserRepositoryInterface"""
        assert isinstance(user_repository, UserRepositoryInterface)
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.User')
    async def test_find_by_user_id_success(self, mock_user_model, user_repository, sample_user):
        """Test successful user lookup by user_id"""
        mock_user_model.filter.return_value.first = AsyncMock(return_value=sample_user)
        
        result = await user_repository.find_by_user_id("user123")
        
        assert result == sample_user
        mock_user_model.filter.assert_called_once_with(user_id="user123")
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.User')
    async def test_find_by_user_id_not_found(self, mock_user_model, user_repository):
        """Test user lookup when user not found"""
        mock_user_model.filter.return_value.first = AsyncMock(return_value=None)
        
        result = await user_repository.find_by_user_id("nonexistent")
        
        assert result is None
        mock_user_model.filter.assert_called_once_with(user_id="nonexistent")
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.User')
    async def test_find_by_user_id_exception(self, mock_user_model, user_repository):
        """Test user lookup with database exception"""
        mock_user_model.filter.side_effect = Exception("Database error")
        
        result = await user_repository.find_by_user_id("user123")
        
        assert result is None
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.User')
    async def test_update_token_usage_success(self, mock_user_model, user_repository, sample_user):
        """Test successful token usage update"""
        mock_user_model.get = AsyncMock(return_value=sample_user)
        
        await user_repository.update_token_usage("user123", 50)
        
        assert sample_user.token_used == 150  # 100 + 50
        sample_user.save.assert_called_once()
        mock_user_model.get.assert_called_once_with(user_id="user123")
    

    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.User')
    async def test_update_token_usage_database_error(self, mock_user_model, user_repository, sample_user):
        """Test token usage update with database error"""
        mock_user_model.get = AsyncMock(return_value=sample_user)
        sample_user.save = AsyncMock(side_effect=Exception("Save failed"))
        
        with pytest.raises(DatabaseError) as exc_info:
            await user_repository.update_token_usage("user123", 50)
        
        assert "Failed to update token usage" in str(exc_info.value)
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.User')
    async def test_create_user_success(self, mock_user_model, user_repository, sample_user):
        """Test successful user creation"""
        user_data = {
            "user_id": "new_user",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User"
        }
        mock_user_model.create = AsyncMock(return_value=sample_user)
        
        result = await user_repository.create_user(user_data)
        
        assert result == sample_user
        mock_user_model.create.assert_called_once_with(**user_data)
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.User')
    async def test_create_user_database_error(self, mock_user_model, user_repository):
        """Test user creation with database error"""
        user_data = {"user_id": "new_user"}
        mock_user_model.create = AsyncMock(side_effect=Exception("Creation failed"))
        
        with pytest.raises(DatabaseError) as exc_info:
            await user_repository.create_user(user_data)
        
        assert "Failed to create user" in str(exc_info.value)


class TestTortoiseAPIKeyRepository:
    """Test cases for TortoiseAPIKeyRepository"""
    
    @pytest.fixture
    def api_key_repository(self):
        """Create TortoiseAPIKeyRepository instance for testing"""
        return TortoiseAPIKeyRepository()
    
    @pytest.fixture
    def sample_api_key(self):
        """Sample API key object"""
        api_key = MagicMock()
        api_key.id = str(uuid.uuid4())
        api_key.api_key = "test_key_123"
        api_key.is_active = True
        api_key.save = AsyncMock()
        return api_key
    
    def test_api_key_repository_implements_interface(self, api_key_repository):
        """Test that TortoiseAPIKeyRepository implements APIKeyRepositoryInterface"""
        assert isinstance(api_key_repository, APIKeyRepositoryInterface)
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.APIKEY')
    async def test_find_active_by_key_success(self, mock_apikey_model, api_key_repository, sample_api_key):
        """Test successful API key lookup"""
        mock_apikey_model.filter.return_value.first = AsyncMock(return_value=sample_api_key)
        
        result = await api_key_repository.find_active_by_key("test_key_123")
        
        assert result == sample_api_key
        mock_apikey_model.filter.assert_called_once_with(api_key="test_key_123", is_active=True)
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.APIKEY')
    async def test_find_active_by_key_not_found(self, mock_apikey_model, api_key_repository):
        """Test API key lookup when key not found"""
        mock_apikey_model.filter.return_value.first = AsyncMock(return_value=None)
        
        result = await api_key_repository.find_active_by_key("nonexistent_key")
        
        assert result is None
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.APIKEY')
    async def test_find_active_by_key_exception(self, mock_apikey_model, api_key_repository):
        """Test API key lookup with exception"""
        mock_apikey_model.filter.side_effect = Exception("Database error")
        
        result = await api_key_repository.find_active_by_key("test_key")
        
        assert result is None

    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.APIKEY')
    @patch('app.infrastructure.database.repositories.datetime')
    async def test_update_last_used_success(self, mock_datetime, mock_apikey_model, api_key_repository, sample_api_key):
        """Test successful last used update"""



        mock_datetime.now.return_value= datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_apikey_model.get = AsyncMock(return_value=sample_api_key)

        await api_key_repository.update_last_used(sample_api_key.id)

        assert sample_api_key.last_used_at ==  datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        sample_api_key.save.assert_called_once()


    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.APIKEY')
    async def test_update_last_used_database_error(self, mock_apikey_model, api_key_repository, sample_api_key):
        """Test last used update with database error"""
        mock_apikey_model.get = AsyncMock(return_value=sample_api_key)
        sample_api_key.save = AsyncMock(side_effect=Exception("Save failed"))
        
        with pytest.raises(DatabaseError):
            await api_key_repository.update_last_used(sample_api_key.id)


class TestTortoiseRepoRepository:
    """Test cases for TortoiseRepoRepository"""
    
    @pytest.fixture
    def repo_repository(self):
        """Create TortoiseRepoRepository instance for testing"""
        return TortoiseRepoRepository()
    
    @pytest.fixture
    def sample_repo(self):
        """Sample repository object"""
        repo = MagicMock()
        repo.id = str(uuid.uuid4())
        repo.repo_id = "repo123"
        repo.user_id = "user456"
        repo.html_url = "https://github.com/test/repo"
        repo.status = "active"
        repo.save = AsyncMock()
        return repo
    
    def test_repo_repository_implements_interface(self, repo_repository):
        """Test that TortoiseRepoRepository implements RepoRepositoryInterface"""
        assert isinstance(repo_repository, RepoRepositoryInterface)
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_find_by_repo_id_success(self, mock_repo_model, repo_repository, sample_repo):
        """Test successful repository lookup by repo_id"""
        mock_repo_model.filter.return_value.first = AsyncMock(return_value=sample_repo)
        
        result = await repo_repository.find_by_repo_id("repo123")
        
        assert result == sample_repo
        mock_repo_model.filter.assert_called_once_with(repo_id="repo123")
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_find_by_repo_id_not_found(self, mock_repo_model, repo_repository):
        """Test repository lookup when not found"""
        mock_repo_model.filter.return_value.first = AsyncMock(return_value=None)
        
        result = await repo_repository.find_by_repo_id("nonexistent")
        
        assert result is None
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_find_by_user_and_url_success(self, mock_repo_model, repo_repository, sample_repo):
        """Test successful repository lookup by user and URL"""
        mock_repo_model.filter.return_value.first = AsyncMock(return_value=sample_repo)
        
        result = await repo_repository.find_by_user_and_url("user456", "https://github.com/test/repo")
        
        assert result == sample_repo
        mock_repo_model.filter.assert_called_once_with(user_id="user456", html_url="https://github.com/test/repo")
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_update_processing_status_success(self, mock_repo_model, repo_repository, sample_repo):
        """Test successful processing status update"""
        mock_repo_model.filter.return_value.first = AsyncMock(return_value=sample_repo)
        
        await repo_repository.update_processing_status("repo123", "processing", priority=5)
        
        assert sample_repo.status == "processing"
        assert sample_repo.priority == 5
        sample_repo.save.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_update_processing_status_repo_not_found(self, mock_repo_model, repo_repository):
        """Test processing status update when repo not found"""
        mock_repo_model.filter.return_value.first = AsyncMock(return_value=None)
        
        with pytest.raises(RepoNotFoundError):
            await repo_repository.update_processing_status("nonexistent", "processing")
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_update_processing_status_database_error(self, mock_repo_model, repo_repository, sample_repo):
        """Test processing status update with database error"""
        mock_repo_model.filter.return_value.first = AsyncMock(return_value=sample_repo)
        sample_repo.save = AsyncMock(side_effect=Exception("Save failed"))
        
        with pytest.raises(DatabaseError):
            await repo_repository.update_processing_status("repo123", "processing")


class TestTortoiseContextRepository:
    """Test cases for TortoiseContextRepository"""
    
    @pytest.fixture
    def context_repository(self):
        """Create TortoiseContextRepository instance for testing"""
        return TortoiseContextRepository()
    
    @pytest.fixture
    def sample_context(self):
        """Sample context object"""
        context = MagicMock()
        context.id = str(uuid.uuid4())
        context.repo_id = "repo123"
        context.user_id = "user456"
        context.status = "pending"
        context.save = AsyncMock()
        return context
    
    def test_context_repository_implements_interface(self, context_repository):
        """Test that TortoiseContextRepository implements ContextRepositoryInterface"""
        assert isinstance(context_repository, ContextRepositoryInterface)
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_create_context_success(self, mock_repo_model, context_repository, sample_context):
        """Test successful context creation"""
        config = {"language": "python", "max_chunks": 100}
        mock_repo_model.create = AsyncMock(return_value=sample_context)
        
        result = await context_repository.create_context("repo123", "user456", config)
        
        assert result == sample_context
        mock_repo_model.create.assert_called_once_with(
            repo_id="repo123",
            user_id="user456",
            config=config,
            status="pending"
        )
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_create_context_database_error(self, mock_repo_model, context_repository):
        """Test context creation with database error"""
        mock_repo_model.create = AsyncMock(side_effect=Exception("Creation failed"))
        
        with pytest.raises(DatabaseError):
            await context_repository.create_context("repo123", "user456", {})
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_update_status_success(self, mock_repo_model, context_repository, sample_context):
        """Test successful status update"""
        mock_repo_model.filter.return_value.first = AsyncMock(return_value=sample_context)
        
        await context_repository.update_status("ctx123", "completed", chunks=50)
        
        assert sample_context.status == "completed"
        assert sample_context.chunks == 50
        sample_context.save.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.Repo')
    async def test_update_status_context_not_found(self, mock_repo_model, context_repository):
        """Test status update when context not found"""
        mock_repo_model.filter.return_value.first = AsyncMock(return_value=None)
        
        with pytest.raises(ContextNotFoundError):
            await context_repository.update_status("nonexistent", "completed")


class TestTortoiseCodeChunks:
    """Test cases for TortoiseCodeChunks"""
    
    @pytest.fixture
    def code_chunks_repository(self):
        """Create TortoiseCodeChunks instance for testing"""
        return TortoiseCodeChunks()
    
    @pytest.fixture
    def sample_code_chunk(self):
        """Sample code chunk object"""
        chunk = MagicMock()
        chunk.id = str(uuid.uuid4())
        chunk.repo_id = "repo123"
        chunk.content = "def hello(): pass"
        chunk.embedding = [0.1, 0.2, 0.3]
        return chunk
    
    @pytest.fixture
    def sample_embeddings_data(self):
        """Sample embeddings data for storage"""
        return [
            {
                "content": "def hello(): pass",
                "embedding": [0.1, 0.2, 0.3],
                "metadata": {"language": "python"},
                "file_name": "hello.py",
                "file_path": "/src/hello.py",
                "file_size": 100
            },
            {
                "content": "def world(): pass",
                "embedding": [0.4, 0.5, 0.6],
                "metadata": {"language": "python"},
                "file_name": "world.py",
                "file_path": "/src/world.py",
                "file_size": 120
            }
        ]
    
    def test_code_chunks_repository_implements_interface(self, code_chunks_repository):
        """Test that TortoiseCodeChunks implements ContextCodeChunkInterface"""
        assert isinstance(code_chunks_repository, ContextCodeChunkInterface)
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.CodeChunks')
    async def test_store_embeddings_success(self, mock_codechunks_model, code_chunks_repository, sample_embeddings_data, sample_code_chunk):
        """Test successful embeddings storage"""
        mock_codechunks_model.create = AsyncMock(return_value=sample_code_chunk)
        
        result = await code_chunks_repository.store_emebeddings(
            "repo123", "user456", sample_embeddings_data, "abc123"
        )
        
        assert result == sample_code_chunk
        assert mock_codechunks_model.create.call_count == 2  # Two embeddings
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.CodeChunks')
    async def test_store_embeddings_empty_data(self, mock_codechunks_model, code_chunks_repository):
        """Test embeddings storage with empty data"""
        result = await code_chunks_repository.store_emebeddings("repo123", "user456", [], "abc123")
        
        assert result is None
        mock_codechunks_model.create.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.CodeChunks')
    async def test_store_embeddings_database_error(self, mock_codechunks_model, code_chunks_repository, sample_embeddings_data):
        """Test embeddings storage with database error"""
        mock_codechunks_model.create = AsyncMock(side_effect=Exception("Creation failed"))
        
        with pytest.raises(DatabaseError):
            await code_chunks_repository.store_emebeddings(
                "repo123", "user456", sample_embeddings_data, "abc123"
            )
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.CodeChunks')
    async def test_find_by_repo_success(self, mock_codechunks_model, code_chunks_repository, sample_code_chunk):
        """Test successful code chunks retrieval by repo"""
        chunks = [sample_code_chunk]
        mock_codechunks_model.filter.return_value.limit.return_value.all = AsyncMock(return_value=chunks)
        
        result = await code_chunks_repository.find_by_repo("repo123", limit=50)
        
        assert result == chunks
        mock_codechunks_model.filter.assert_called_once_with(repo_id="repo123")
    
    @pytest.mark.asyncio
    @patch('app.infrastructure.database.repositories.CodeChunks')
    async def test_find_by_repo_exception(self, mock_codechunks_model, code_chunks_repository):
        """Test code chunks retrieval with exception"""
        mock_codechunks_model.filter.side_effect = Exception("Database error")
        
        result = await code_chunks_repository.find_by_repo("repo123")
        
        assert result == []


class TestRepositoryIntegration:
    """Integration tests for repositories"""
    
    @pytest.mark.asyncio
    async def test_repository_workflow(self):
        """Test typical repository workflow"""
        # This would be an integration test with actual database
        # For now, we'll test the interface compliance
        
        user_repo = TortoiseUserRepository()
        api_key_repo = TortoiseAPIKeyRepository()
        repo_repo = TortoiseRepoRepository()
        context_repo = TortoiseContextRepository()
        chunks_repo = TortoiseCodeChunks()
        
        # Test that all repositories implement their interfaces
        assert isinstance(user_repo, UserRepositoryInterface)
        assert isinstance(api_key_repo, APIKeyRepositoryInterface)
        assert isinstance(repo_repo, RepoRepositoryInterface)
        assert isinstance(context_repo, ContextRepositoryInterface)
        assert isinstance(chunks_repo, ContextCodeChunkInterface)
        
        # Test that all repositories have expected methods
        assert hasattr(user_repo, 'find_by_user_id')
        assert hasattr(api_key_repo, 'find_active_by_key')
        assert hasattr(repo_repo, 'find_by_repo_id')
        assert hasattr(context_repo, 'create_context')
        assert hasattr(chunks_repo, 'store_emebeddings')
