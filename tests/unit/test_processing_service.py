"""
Test cases for processing service
"""
import pytest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document
from app.services.processing_service import ProcessingService
import tempfile


class TestProcessingService:
    """Test cases for ProcessingService class"""

    @pytest.fixture
    def mock_repositories(self):
        """Create mock repositories"""
        context_repo = MagicMock()
        context_repo.update_status = AsyncMock()

        user_repo = MagicMock()
        user_repo.find_by_user_id = AsyncMock()

        repo_repo = MagicMock()
        repo_repo.find_by_repo_id = AsyncMock()

        git_label_repo = MagicMock()
        git_label_repo.find_by_user_and_hosting = AsyncMock()

        code_chunks_repo = MagicMock()
        code_chunks_repo.store_emebeddings = AsyncMock()

        return {
            "context": context_repo,
            "user": user_repo,
            "repo": repo_repo,
            "git_label": git_label_repo,
            "code_chunks": code_chunks_repo,
        }

    @pytest.fixture
    def mock_encryption_service(self):
        """Mock encryption service"""
        encryption = MagicMock()
        encryption.decrypt_for_user = MagicMock(return_value="decrypted_token")
        return encryption

    @pytest.fixture
    def mock_repo_fetcher(self):
        """Mock repository fetcher"""
        fetcher = MagicMock()
        return fetcher

    @pytest.fixture
    def processing_service(
        self, mock_repositories, mock_encryption_service, mock_repo_fetcher
    ):
        """Create ProcessingService instance for testing"""
        return ProcessingService(
            context_repository=mock_repositories["context"],
            user_info=mock_repositories["user"],
            repo_repository=mock_repositories["repo"],
            git_label_repository=mock_repositories["git_label"],
            encryption_service=mock_encryption_service,
            code_chunks_repository=mock_repositories["code_chunks"],
            repo_fetcher_store=mock_repo_fetcher,
        )

    @pytest.fixture
    def sample_repo(self):
        """Sample repository data"""
        repo = MagicMock()
        repo.id = str(uuid.uuid4())
        repo.repo_name = "test-repo"
        repo.html_url = "https://github.com/test/test-repo"
        repo.user_id = "user123"
        return repo

    @pytest.fixture
    def sample_user(self):
        """Sample user data"""
        user = MagicMock()
        user.id = "user123"
        user.encryption_salt = "test_salt"
        return user

    @pytest.fixture
    def sample_git_config(self):
        """Sample git configuration"""
        git_config = MagicMock()
        git_config.token_value = "encrypted_token"
        return git_config

    def test_init(self, processing_service, mock_repositories, mock_encryption_service):
        """Test ProcessingService initialization"""
        assert processing_service.context_repository == mock_repositories["context"]
        assert processing_service.user_info == mock_repositories["user"]
        assert processing_service.repo_repository == mock_repositories["repo"]
        assert processing_service.git_label_repository == mock_repositories["git_label"]
        assert processing_service.encryption_service == mock_encryption_service
        assert (
            processing_service.code_chunks_repository
            == mock_repositories["code_chunks"]
        )
        assert processing_service.base_dir == Path("app/repos")

    @pytest.mark.asyncio
    @patch("shutil.rmtree")
    async def test_prepare_repository_existing_path(
        self, mock_rmtree, processing_service
    ):
        """Test repository preparation when path exists"""
        repo_name = "test-repo"

        with patch("pathlib.Path.exists", return_value=True):
            repo_path = await processing_service.prepare_repository(repo_name)

            expected_path = processing_service.base_dir / repo_name
            assert repo_path == expected_path
            mock_rmtree.assert_called_once_with(expected_path)

    @pytest.mark.asyncio
    @patch("shutil.rmtree")
    async def test_prepare_repository_new_path(self, mock_rmtree, processing_service):
        """Test repository preparation when path doesn't exist"""
        repo_name = "new-repo"

        with patch("pathlib.Path.exists", return_value=False):
            repo_path = await processing_service.prepare_repository(repo_name)

            expected_path = processing_service.base_dir / repo_name
            assert repo_path == expected_path
            mock_rmtree.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.processing_service.GitLoader")
    async def test_clone_and_process_repository_success(
        self, mock_git_loader, processing_service
    ):
        """Test successful repository cloning and processing"""
        repo_url = "https://github.com/test/test-repo"
        branch = "main"

        # Mock documents
        mock_documents = [
            Document(page_content="print('hello')", metadata={"source": "main.py"}),
            Document(page_content="def test(): pass", metadata={"source": "test.py"}),
        ]

        mock_loader_instance = MagicMock()
        mock_loader_instance.load.return_value = mock_documents
        mock_git_loader.return_value = mock_loader_instance

        with tempfile.TemporaryDirectory() as tmp_dir:
            processing_service.prepare_repository = AsyncMock(return_value=tmp_dir)

            result = await processing_service.clone_and_process_repository(
                repo_url, tmp_dir, branch  # Use tmp_dir instead of hardcoded path
            )

            assert result == mock_documents
            mock_git_loader.assert_called_once()
            mock_loader_instance.load.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.processing_service.GitLoader")
    async def test_clone_and_process_repository_failure(
        self, mock_git_loader, processing_service
    ):
        """Test repository cloning failure"""
        repo_url = "https://github.com/test/test-repo"

        mock_git_loader.side_effect = Exception("Clone failed")
        with tempfile.TemporaryDirectory() as tmp_dir:
            processing_service.prepare_repository = AsyncMock(return_value=tmp_dir)

            result = await processing_service.clone_and_process_repository(
                repo_url, tmp_dir
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_get_authenticated_git_client(
        self,
        processing_service,
        mock_repositories,
        mock_encryption_service,
        sample_user,
        sample_git_config,
    ):
        """Test getting authenticated git client"""
        user_id = "user123"
        git_provider = "github"
        git_token = "token123"

        # Setup mocks
        mock_repositories[
            "git_label"
        ].find_by_user_and_hosting.return_value = sample_git_config
        mock_repositories["user"].find_by_user_id.return_value = sample_user

        with patch.object(
            processing_service.git_client_factory, "create_client"
        ) as mock_create_client:
            mock_client = MagicMock()
            mock_create_client.return_value = mock_client

            result = await processing_service._get_authenticated_git_client(
                user_id, git_provider, git_token
            )

            assert result == mock_client
            mock_repositories[
                "git_label"
            ].find_by_user_and_hosting.assert_called_once_with(
                user_id, git_token, git_provider
            )
            mock_repositories["user"].find_by_user_id.assert_called_once_with(user_id)
            mock_encryption_service.decrypt_for_user.assert_called_once_with(
                sample_git_config.token_value, sample_user.encryption_salt
            )
            mock_create_client.assert_called_once_with(git_provider, "decrypted_token")

    @pytest.mark.asyncio
    @patch("app.services.processing_service.RecursiveCharacterTextSplitter")
    async def test_process_files_to_chunks(
        self, mock_text_splitter, processing_service
    ):
        """Test processing files to chunks"""
        files = [
            Document(
                page_content="def hello(): print('hello')",
                metadata={"source": "hello.py"},
            ),
            Document(
                page_content="def world(): print('world')",
                metadata={"source": "world.py"},
            ),
        ]
        context_id = "ctx123"
        repo_id = "repo456"
        user_id = "user789"

        mock_chunks = [
            Document(page_content="def hello():", metadata={"source": "hello.py"}),
            Document(page_content="print('hello')", metadata={"source": "hello.py"}),
            Document(page_content="def world():", metadata={"source": "world.py"}),
            Document(page_content="print('world')", metadata={"source": "world.py"}),
        ]

        mock_splitter_instance = MagicMock()
        mock_splitter_instance.split_documents.return_value = mock_chunks
        mock_text_splitter.return_value = mock_splitter_instance

        result = await processing_service._process_files_to_chunks(
            files, context_id, repo_id, user_id
        )

        assert result == mock_chunks
        mock_text_splitter.assert_called_once_with(chunk_size=700, chunk_overlap=200)
        mock_splitter_instance.split_documents.assert_called_once_with(files)

    def test_detect_language(self, processing_service):
        """Test programming language detection"""
        test_cases = [
            ("main.py", "python"),
            ("script.js", "javascript"),
            ("app.ts", "typescript"),
            ("Main.java", "java"),
            ("main.go", "go"),
            ("lib.rs", "rust"),
            ("program.cpp", "cpp"),
            ("header.h", "cpp"),
            ("program.c", "cpp"),
            ("header.hpp", "cpp"),
            ("readme.txt", "text"),
            ("unknown.xyz", "text"),
        ]

        for file_path, expected_lang in test_cases:
            result = processing_service._detect_language(file_path)
            assert result == expected_lang, f"Failed for {file_path}"

    @pytest.mark.asyncio
    @patch("app.services.processing_service.Together")
    @patch("app.services.processing_service.settings")
    async def test_create_embeddings_success(
        self, mock_settings, mock_together_class, processing_service
    ):
        """Test successful embedding creation"""
        chunks = [
            Document(
                page_content="def hello(): pass",
                metadata={"file_name": "test.py", "source": "test.py"},
            )
        ]

        # Mock Together client response
        mock_embedding_data = MagicMock()
        mock_embedding_data.embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        mock_response = MagicMock()
        mock_response.data = [mock_embedding_data]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response
        mock_together_class.return_value = mock_client

        mock_settings.TOGETHER_API_KEY = "test_key"

        result = await processing_service._create_embeddings(chunks)
        assert len(result) == 1
        embedding = result[0]
        assert "chunk_id" in embedding
        assert embedding["embedding"] == [0.1, 0.2, 0.3, 0.4, 0.5]
        assert embedding["model_name"] == "togethercomputer/m2-bert-80M-32k-retrieval"
        assert embedding["vector_dimension"] == 5
        assert embedding["content"] == "def hello(): pass"
        assert embedding["metadata"] == {"file_name": "test.py", "source": "test.py"}

    @pytest.mark.asyncio
    @patch("app.services.processing_service.Together")
    async def test_create_embeddings_empty_chunks(
        self, mock_together_class, processing_service
    ):
        """Test embedding creation with empty chunks"""
        chunks = []

        result = await processing_service._create_embeddings(chunks)

        assert result == []
        mock_together_class.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.processing_service.Together")
    @patch("app.services.processing_service.settings")
    async def test_create_embeddings_api_failure(
        self, mock_settings, mock_together_class, processing_service
    ):
        """Test embedding creation with API failure"""
        chunks = [
            Document(page_content="def test(): pass", metadata={"file_name": "test.py"})
        ]

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API Error")
        mock_together_class.return_value = mock_client

        mock_settings.TOGETHER_API_KEY = "test_key"
        result = await processing_service._create_embeddings(chunks)

        assert result == []

    @pytest.mark.asyncio
    @patch("app.services.processing_service.Repo")
    async def test_process_repository_success(
        self, mock_repo_class, processing_service, mock_repositories, sample_repo
    ):
        """Test successful repository processing"""
        job_payload = {
            "context_id": "ctx123",
            "repo_id": "repo456",
            "user_id": "user789",
            "git_provider": "github",
            "git_token": "token123",
            "branch": "main",
        }

        # Setup mocks
        mock_repositories["repo"].find_by_repo_id.return_value = sample_repo

        mock_repo_instance = MagicMock()
        mock_repo_instance.head.commit.hexsha = "abc123"
        mock_repo_class.return_value = mock_repo_instance

        # Mock all the processing steps
        processing_service._get_authenticated_git_client = AsyncMock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            processing_service.prepare_repository = AsyncMock(return_value=tmp_dir)

        processing_service.clone_and_process_repository = AsyncMock(
            return_value=[
                Document(page_content="test content", metadata={"source": "test.py"})
            ]
        )
        processing_service._process_files_to_chunks = AsyncMock(
            return_value=[
                Document(page_content="chunk1", metadata={"source": "test.py"})
            ]
        )
        processing_service._create_embeddings = AsyncMock(
            return_value=[
                {"chunk_id": "chunk1", "embedding": [0.1, 0.2], "content": "chunk1"}
            ]
        )

        result = await processing_service.process_repository(job_payload)

        assert result.success is True
        assert result.context_id == "ctx123"
        assert result.chunks_created == 1
        assert result.embeddings_created == 1
        assert result.processing_time is not None

        # Verify all steps were called
        mock_repositories["repo"].find_by_repo_id.assert_called_once_with("repo456")
        processing_service._get_authenticated_git_client.assert_called_once()
        processing_service.prepare_repository.assert_called_once()
        processing_service.clone_and_process_repository.assert_called_once()
        processing_service._process_files_to_chunks.assert_called_once()
        processing_service._create_embeddings.assert_called_once()
        mock_repositories["code_chunks"].store_emebeddings.assert_called_once()
        mock_repositories["context"].update_status.assert_called()

    @pytest.mark.asyncio
    async def test_process_repository_repo_not_found(
        self, processing_service, mock_repositories
    ):
        """Test repository processing when repo not found"""
        job_payload = {
            "context_id": "ctx123",
            "repo_id": "nonexistent",
            "user_id": "user789",
            "git_provider": "github",
            "git_token": "token123",
        }

        mock_repositories["repo"].find_by_repo_id.return_value = None

        result = await processing_service.process_repository(job_payload)

        assert result.success is False
        assert result.context_id == "ctx123"
        assert "Repository not found" in result.error_message

        # Verify context status was updated to failed
        mock_repositories["context"].update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_repository_git_client_failure(
        self, processing_service, mock_repositories, sample_repo
    ):
        """Test repository processing when git client creation fails"""
        job_payload = {
            "context_id": "ctx123",
            "repo_id": "repo456",
            "user_id": "user789",
            "git_provider": "github",
            "git_token": "token123",
        }

        mock_repositories["repo"].find_by_repo_id.return_value = sample_repo
        processing_service._get_authenticated_git_client = AsyncMock(
            side_effect=Exception("Git auth failed")
        )

        result = await processing_service.process_repository(job_payload)

        assert result.success is False
        assert "Git auth failed" in result.error_message

    @pytest.mark.asyncio
    async def test_process_repository_cloning_failure(
        self, processing_service, mock_repositories, sample_repo
    ):
        """Test repository processing when cloning fails"""
        job_payload = {
            "context_id": "ctx123",
            "repo_id": "repo456",
            "user_id": "user789",
            "git_provider": "github",
            "git_token": "token123",
        }

        mock_repositories["repo"].find_by_repo_id.return_value = sample_repo
        processing_service._get_authenticated_git_client = AsyncMock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            processing_service.prepare_repository = AsyncMock(return_value=tmp_dir)

        processing_service.clone_and_process_repository = AsyncMock(
            side_effect=Exception("Clone failed")
        )

        result = await processing_service.process_repository(job_payload)

        assert result.success is False
        assert "Clone failed" in result.error_message

    @pytest.mark.asyncio
    async def test_chunk_file_content(self, processing_service):
        """Test file content chunking"""
        file_data = {
            "content": "\n".join([f"line {i}" for i in range(1, 201)]),  # 200 lines
            "path": "test.py",
        }
        context_id = "ctx123"

        chunks = await processing_service._chunk_file_content(file_data, context_id)

        assert len(chunks) > 0

        # Check first chunk
        first_chunk = chunks[0]
        assert first_chunk["context_id"] == context_id
        assert first_chunk["file_path"] == "test.py"
        assert first_chunk["start_line"] == 1
        assert first_chunk["language"] == "python"
        assert first_chunk["chunk_type"] == "code_block"
        assert "line 1" in first_chunk["content"]

    @pytest.mark.asyncio
    async def test_chunk_file_content_empty_content(self, processing_service):
        """Test file content chunking with empty content"""
        file_data = {"content": "", "path": "empty.py"}
        context_id = "ctx123"

        chunks = await processing_service._chunk_file_content(file_data, context_id)

        assert chunks == []

    @pytest.mark.asyncio
    async def test_chunk_file_content_whitespace_only(self, processing_service):
        """Test file content chunking with whitespace-only content"""
        file_data = {"content": "\n\n   \n\n", "path": "whitespace.py"}
        context_id = "ctx123"

        chunks = await processing_service._chunk_file_content(file_data, context_id)

        assert chunks == []


class TestProcessingServiceIntegration:
    """Integration tests for ProcessingService"""

    @pytest.mark.asyncio
    @patch("app.services.processing_service.Repo")
    async def test_full_processing_workflow_minimal(self, mock_repo):
        """Test minimal processing workflow with mocked dependencies"""
        # Set up the Repo mock
        mock_repo_instance = MagicMock()
        mock_repo_instance.head.commit.hexsha = "abc123"
        mock_repo.return_value = mock_repo_instance
        # Create all mocks
        context_repo = MagicMock()
        context_repo.update_status = AsyncMock()

        user_repo = MagicMock()
        user_repo.find_by_user_id = AsyncMock(
            return_value=MagicMock(encryption_salt="salt")
        )

        repo_repo = MagicMock()
        sample_repo = MagicMock()
        sample_repo.id = "repo123"
        sample_repo.repo_name = "test-repo"
        sample_repo.html_url = "https://github.com/test/test-repo"
        sample_repo.user_id = "user123"
        repo_repo.find_by_repo_id = AsyncMock(return_value=sample_repo)

        git_label_repo = MagicMock()
        git_label_repo.find_by_user_and_hosting = AsyncMock(
            return_value=MagicMock(token_value="token")
        )

        code_chunks_repo = MagicMock()
        code_chunks_repo.store_emebeddings = AsyncMock()

        encryption_service = MagicMock()
        encryption_service.decrypt_for_user = MagicMock(return_value="decrypted_token")

        # Create service
        service = ProcessingService(
            context_repository=context_repo,
            user_info=user_repo,
            repo_repository=repo_repo,
            git_label_repository=git_label_repo,
            encryption_service=encryption_service,
            code_chunks_repository=code_chunks_repo,
        )

        # Mock all processing steps
        service._get_authenticated_git_client = AsyncMock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            service.prepare_repository = AsyncMock(return_value=tmp_dir)

        service.clone_and_process_repository = AsyncMock(return_value=[])

        service._process_files_to_chunks = AsyncMock(return_value=[])
        service._create_embeddings = AsyncMock(return_value=[])

        # Test payload
        payload = {
            "context_id": "ctx123",
            "repo_id": "repo123",
            "user_id": "user123",
            "git_provider": "github",
            "git_token": "token123",
        }

        # Process
        result = await service.process_repository(payload)
        print("result line 529 ", result)
        # Verify success with empty results
        assert result.success is True
        assert result.context_id == "ctx123"
        assert result.chunks_created == 0
        assert result.embeddings_created == 0
