"""
Test cases for schema models
"""
import pytest
from datetime import datetime
from pydantic import ValidationError
from app.schemas.processing_result import ProcessingResult
from app.schemas.repo import (
    GitHostingProvider,
    RepoBase
)


class TestProcessingResult:
    """Test cases for ProcessingResult schema"""

    def test_processing_result_success_minimal(self):
        """Test ProcessingResult with minimal success data"""
        result = ProcessingResult(success=True)

        assert result.success is True
        assert result.context_id is None
        assert result.error_message is None
        assert result.processing_time is None
        assert result.chunks_created is None
        assert result.embeddings_created is None
        assert result.metadata == {}

    def test_processing_result_success_complete(self):
        """Test ProcessingResult with complete success data"""
        result = ProcessingResult(
            success=True,
            context_id="ctx123",
            processing_time=15.5,
            chunks_created=100,
            embeddings_created=95,
            metadata={"files_processed": 25, "language": "python"},
        )

        assert result.success is True
        assert result.context_id == "ctx123"
        assert result.processing_time == pytest.approx(15.5)
        assert result.chunks_created == 100
        assert result.embeddings_created == 95
        assert result.metadata["files_processed"] == 25
        assert result.metadata["language"] == "python"
        assert result.error_message is None

    def test_processing_result_failure_minimal(self):
        """Test ProcessingResult with minimal failure data"""
        result = ProcessingResult(success=False, error_message="Processing failed")

        assert result.success is False
        assert result.error_message == "Processing failed"
        assert result.context_id is None
        assert result.processing_time is None
        assert result.chunks_created is None
        assert result.embeddings_created is None

    def test_processing_result_failure_with_context(self):
        """Test ProcessingResult with failure and context info"""
        result = ProcessingResult(
            success=False,
            context_id="ctx456",
            error_message="Repository not found",
            processing_time=2.1,
            metadata={"attempted_repo": "test/repo"},
        )

        assert result.success is False
        assert result.context_id == "ctx456"
        assert result.error_message == "Repository not found"
        assert result.processing_time == pytest.approx(2.1)
        assert result.metadata["attempted_repo"] == "test/repo"

    def test_processing_result_dict_conversion(self):
        """Test ProcessingResult to dict conversion"""
        result = ProcessingResult(success=True, context_id="ctx789", chunks_created=50)

        result_dict = result.model_dump()

        assert result_dict["success"] is True
        assert result_dict["context_id"] == "ctx789"
        assert result_dict["chunks_created"] == 50
        assert "error_message" in result_dict
        assert "processing_time" in result_dict
        assert "embeddings_created" in result_dict
        assert "metadata" in result_dict

    def test_processing_result_json_serialization(self):
        """Test ProcessingResult JSON serialization"""
        result = ProcessingResult(
            success=True,
            context_id="ctx999",
            processing_time=8.7,
            metadata={"test": "data"},
        )
        json_data = result.model_dump()

        assert json_data["success"]
        assert json_data["context_id"] == "ctx999"
        assert json_data["processing_time"] == pytest.approx(8.7)
        assert json_data["metadata"] == {"test": "data"}


class TestGitHostingProvider:
    """Test cases for GitHostingProvider enum"""

    def test_git_hosting_provider_values(self):
        """Test GitHostingProvider enum values"""
        assert GitHostingProvider.GITHUB == "github"
        assert GitHostingProvider.GITLAB == "gitlab"

    def test_git_hosting_provider_membership(self):
        """Test GitHostingProvider enum membership"""
        assert "github" in GitHostingProvider
        assert "gitlab" in GitHostingProvider
        assert "bitbucket" not in GitHostingProvider


class TestRepoBase:
    """Test cases for RepoBase schema"""

    def test_repo_base_minimal(self):
        """Test RepoBase with minimal required fields"""
        repo = RepoBase(
            repo_name="test-repo", html_url="https://github.com/test/test-repo"
        )

        assert repo.repo_name == "test-repo"
        assert repo.html_url == "https://github.com/test/test-repo"
        assert repo.default_branch == "main"  # Default value
        assert repo.forks_count == 0  # Default value
        assert repo.stargazers_count == 0  # Default value
        assert repo.is_private is False  # Default value
        assert repo.description is None
        assert repo.visibility is None
        assert repo.git_hosting is None

    def test_repo_base_complete(self):
        """Test RepoBase with all fields"""
        created_at = datetime.now()
        updated_at = datetime.now()

        repo = RepoBase(
            repo_name="complete-repo",
            description="A complete repository for testing",
            html_url="https://gitlab.com/test/complete-repo",
            default_branch="develop",
            forks_count=25,
            stargazers_count=150,
            is_private=True,
            visibility="private",
            git_hosting=GitHostingProvider.GITLAB,
            language="Python",
            size=2048,
            repo_created_at=created_at,
            repo_updated_at=updated_at,
        )

        assert repo.repo_name == "complete-repo"
        assert repo.description == "A complete repository for testing"
        assert repo.html_url == "https://gitlab.com/test/complete-repo"
        assert repo.default_branch == "develop"
        assert repo.forks_count == 25
        assert repo.stargazers_count == 150
        assert repo.is_private is True
        assert repo.visibility == "private"
        assert repo.git_hosting == GitHostingProvider.GITLAB
        assert repo.language == "Python"
        assert repo.size == 2048
        assert repo.repo_created_at == created_at
        assert repo.repo_updated_at == updated_at

    def test_repo_base_validation_repo_name_too_long(self):
        """Test RepoBase validation for repo_name length"""
        with pytest.raises(ValidationError):
            RepoBase(
                repo_name="a" * 256, html_url="https://github.com/test/test"  # Too long
            )

    def test_repo_base_validation_negative_counts(self):
        """Test RepoBase validation for negative counts"""
        with pytest.raises(ValidationError):
            RepoBase(
                repo_name="test-repo",
                html_url="https://github.com/test/test",
                forks_count=-1,  # Negative not allowed
            )

        with pytest.raises(ValidationError):
            RepoBase(
                repo_name="test-repo",
                html_url="https://github.com/test/test",
                stargazers_count=-5,  # Negative not allowed
            )

        with pytest.raises(ValidationError):
            RepoBase(
                repo_name="test-repo",
                html_url="https://github.com/test/test",
                size=-100,  # Negative not allowed
            )
