"""
Test cases for schema models
"""
import pytest
import uuid
from types import SimpleNamespace
from datetime import datetime
from unittest.mock import MagicMock
from github.Repository import Repository
from pydantic import ValidationError
from app.schemas.processing_result import ProcessingResult
from app.schemas.repo import (
    GitHostingProvider, 
    RepoBase, 
    RepoResponse, 
    GitRepoResponse,
    GitLabRepoResponseTransformer,
    GitHubRepoResponseTransformer
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
            metadata={"files_processed": 25, "language": "python"}
        )
        
        assert result.success is True
        assert result.context_id == "ctx123"
        assert result.processing_time == 15.5
        assert result.chunks_created == 100
        assert result.embeddings_created == 95
        assert result.metadata["files_processed"] == 25
        assert result.metadata["language"] == "python"
        assert result.error_message is None
    
    def test_processing_result_failure_minimal(self):
        """Test ProcessingResult with minimal failure data"""
        result = ProcessingResult(
            success=False,
            error_message="Processing failed"
        )
        
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
            metadata={"attempted_repo": "test/repo"}
        )
        
        assert result.success is False
        assert result.context_id == "ctx456"
        assert result.error_message == "Repository not found"
        assert result.processing_time == 2.1
        assert result.metadata["attempted_repo"] == "test/repo"
    
    def test_processing_result_dict_conversion(self):
        """Test ProcessingResult to dict conversion"""
        result = ProcessingResult(
            success=True,
            context_id="ctx789",
            chunks_created=50
        )
        
        result_dict = result.dict()
        
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
            metadata={"test": "data"}
        )
        json_data= result.model_dump()

        assert json_data['success']
        assert json_data['context_id'] == "ctx999"
        assert json_data['processing_time'] == 8.7
        assert json_data['metadata'] == {"test": "data"}



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
            repo_name="test-repo",
            html_url="https://github.com/test/test-repo"
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
            repo_updated_at=updated_at
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
                repo_name="a" * 256,  # Too long
                html_url="https://github.com/test/test"
            )
    
    def test_repo_base_validation_negative_counts(self):
        """Test RepoBase validation for negative counts"""
        with pytest.raises(ValidationError):
            RepoBase(
                repo_name="test-repo",
                html_url="https://github.com/test/test",
                forks_count=-1  # Negative not allowed
            )
        
        with pytest.raises(ValidationError):
            RepoBase(
                repo_name="test-repo",
                html_url="https://github.com/test/test",
                stargazers_count=-5  # Negative not allowed
            )
        
        with pytest.raises(ValidationError):
            RepoBase(
                repo_name="test-repo",
                html_url="https://github.com/test/test",
                size=-100  # Negative not allowed
            )


class TestRepoResponse:
    """Test cases for RepoResponse schema"""
    
    def test_repo_response_complete(self):
        """Test RepoResponse with all fields"""
        repo_id = uuid.uuid4()
        created_at = datetime.now()
        updated_at = datetime.now()
        
        repo = RepoResponse(
            id=repo_id,
            user_id="user123",
            repo_id="repo456",
            repo_name="response-repo",
            html_url="https://github.com/test/response-repo",
            token_id="token789",
            created_at=created_at,
            updated_at=updated_at,
            description="Test repository response"
        )
        
        assert repo.id == repo_id
        assert repo.user_id == "user123"
        assert repo.repo_id == "repo456"
        assert repo.repo_name == "response-repo"
        assert repo.html_url == "https://github.com/test/response-repo"
        assert repo.token_id == "token789"
        assert repo.created_at == created_at
        assert repo.updated_at == updated_at
        assert repo.description == "Test repository response"
    
    def test_repo_response_from_attributes(self):
        """Test RepoResponse from_attributes configuration"""
        # This tests that the model config allows creation from ORM objects
        mock_orm_object = MagicMock()
        mock_orm_object.id = uuid.uuid4()
        mock_orm_object.user_id = "user123"
        mock_orm_object.repo_id = "repo456"
        mock_orm_object.repo_name = "orm-repo"
        mock_orm_object.html_url = "https://github.com/test/orm-repo"
        mock_orm_object.created_at = datetime.now()
        mock_orm_object.updated_at = datetime.now()
        mock_orm_object.token_id = None
        mock_orm_object.description = None
        mock_orm_object.default_branch = "main"
        mock_orm_object.forks_count = 0
        mock_orm_object.stargazers_count = 0
        mock_orm_object.is_private = False
        mock_orm_object.visibility = None
        mock_orm_object.git_hosting = None
        mock_orm_object.language = None
        mock_orm_object.size = None
        mock_orm_object.repo_created_at = None
        mock_orm_object.repo_updated_at = None
        
        # This would work with actual ORM objects due to from_attributes=True
        # For testing, we'll just verify the configuration exists
        assert RepoResponse.model_config["from_attributes"] is True


class TestGitRepoResponse:
    """Test cases for GitRepoResponse schema"""
    
    def test_git_repo_response_minimal(self):
        """Test GitRepoResponse with minimal fields"""
        repo = GitRepoResponse(
            id="123",
            repo_name="git-repo",
            html_url="https://github.com/test/git-repo",
            relative_path="test/git-repo",
            default_branch="main",
            forks_count=0,
            stargazers_count=0
        )
        
        assert repo.id == "123"
        assert repo.repo_name == "git-repo"
        assert repo.html_url == "https://github.com/test/git-repo"
        assert repo.relative_path == "test/git-repo"
        assert repo.default_branch == "main"
        assert repo.forks_count == 0
        assert repo.stargazers_count == 0
        assert repo.description is None
        assert repo.size is None
        assert repo.private is None
        assert repo.visibility is None
    
    def test_git_repo_response_complete(self):
        """Test GitRepoResponse with all fields"""
        created_at = datetime.now()
        
        repo = GitRepoResponse(
            id="456",
            repo_name="complete-git-repo",
            description="Complete git repository",
            html_url="https://gitlab.com/test/complete-git-repo",
            relative_path="test/complete-git-repo",
            default_branch="develop",
            forks_count=10,
            stargazers_count=50,
            size=1024,
            repo_created_at=created_at,
            private=True,
            visibility="private"
        )
        
        assert repo.id == "456"
        assert repo.repo_name == "complete-git-repo"
        assert repo.description == "Complete git repository"
        assert repo.default_branch == "develop"
        assert repo.forks_count == 10
        assert repo.stargazers_count == 50
        assert repo.size == 1024
        assert repo.repo_created_at == created_at
        assert repo.private is True
        assert repo.visibility == "private"


class TestGitLabRepoResponseTransformer:
    """Test cases for GitLabRepoResponseTransformer"""
    
    def test_derive_storage_size_with_statistics(self):
        """Test storage size derivation with statistics"""
        statistics = {"storage_size": 2048, "other_stat": 100}
        
        size = GitLabRepoResponseTransformer.derive_storage_size(statistics)
        
        assert size == 2048
    
    def test_derive_storage_size_no_statistics(self):
        """Test storage size derivation without statistics"""
        size = GitLabRepoResponseTransformer.derive_storage_size(None)
        
        assert size is None
    
    def test_derive_storage_size_missing_storage_size(self):
        """Test storage size derivation with statistics but no storage_size"""
        statistics = {"other_stat": 100}
        
        size = GitLabRepoResponseTransformer.derive_storage_size(statistics)
        
        assert size == 0
    
    def test_derived_private_field_private(self):
        """Test private field derivation for private visibility"""
        private = GitLabRepoResponseTransformer.derived_private_field("private")
        assert private is True
        
        private = GitLabRepoResponseTransformer.derived_private_field("PRIVATE")
        assert private is True
    
    def test_derived_private_field_internal(self):
        """Test private field derivation for internal visibility"""
        private = GitLabRepoResponseTransformer.derived_private_field("internal")
        assert private is True
        
        private = GitLabRepoResponseTransformer.derived_private_field("INTERNAL")
        assert private is True
    
    def test_derived_private_field_public(self):
        """Test private field derivation for public visibility"""
        private = GitLabRepoResponseTransformer.derived_private_field("public")
        assert private is False
        
        private = GitLabRepoResponseTransformer.derived_private_field("PUBLIC")
        assert private is False
    
    def test_derived_private_field_none(self):
        """Test private field derivation for None visibility"""
        private = GitLabRepoResponseTransformer.derived_private_field(None)
        assert private is None
    
    def test_transform_project_to_dict(self):
        """Test project transformation to dict"""
        mock_project = MagicMock()
        mock_project.id = 123
        mock_project.name = "test-project"
        mock_project.description = "Test description"
        mock_project.default_branch = "main"
        mock_project.forks_count = 5
        mock_project.visibility = "public"
        mock_project.created_at = "2023-01-01"
        mock_project.star_count = 25
        mock_project.http_url_to_repo = "https://gitlab.com/test/project"
        mock_project.path_with_namespace = "test/project"
        mock_project.statistics = {"storage_size": 1024}
        
        result = GitLabRepoResponseTransformer.transform_project_to_dict(mock_project)
        
        assert result["id"] == "123"
        assert result["name"] == "test-project"
        assert result["description"] == "Test description"
        assert result["default_branch"] == "main"
        assert result["forks_count"] == 5
        assert result["visibility"] == "public"
        assert result["created_at"] == "2023-01-01"
        assert result["star_count"] == 25
        assert result["http_url_to_repo"] == "https://gitlab.com/test/project"
        assert result["path_with_namespace"] == "test/project"
        assert result["statistics"] == {"storage_size": 1024}
    
    def test_from_git_with_project_object(self):
        """Test GitRepoResponse creation from GitLab project object"""
        mock_project = MagicMock(spec=SimpleNamespace)
        mock_project.id = 456
        mock_project.name = "gitlab-repo"
        mock_project.description = "GitLab repository"
        mock_project.default_branch = "develop"
        mock_project.forks_count = 3
        mock_project.visibility = "private"
        mock_project.created_at = "2023-06-01"
        mock_project.star_count = 15
        mock_project.http_url_to_repo = "https://gitlab.com/test/gitlab-repo"
        mock_project.path_with_namespace = "test/gitlab-repo"
        mock_project.statistics = {"storage_size": 512}
        
        result = GitLabRepoResponseTransformer.from_git(mock_project)
        assert result.id == "456"
        assert result.repo_name == "gitlab-repo"
        assert result.description == "GitLab repository"
        assert result.default_branch == "develop"
        assert result.forks_count == 3
        assert result.stargazers_count == 15
        assert result.html_url == "https://gitlab.com/test/gitlab-repo"
        assert result.relative_path == "test/gitlab-repo"
        assert result.visibility == "private"
        assert result.size == 512
        assert result.private is True
    
    def test_from_git_with_dict(self):
        """Test GitRepoResponse creation from dict"""
        data = {
            "id": 789,
            "name": "dict-repo",
            "description": "Dictionary repository",
            "default_branch": "master",
            "forks_count": 8,
            "visibility": "public",
            "created_at": "2023-03-15",
            "star_count": 40,
            "http_url_to_repo": "https://gitlab.com/test/dict-repo",
            "path_with_namespace": "test/dict-repo",
            "statistics": {"storage_size": 2048}
        }
        
        result = GitLabRepoResponseTransformer.from_git(data)
        
        assert result.id == "789"
        assert result.repo_name == "dict-repo"
        assert result.private is False  # public visibility
        assert result.size == 2048
    
    def test_from_git_with_none(self):
        """Test GitRepoResponse creation with None data"""
        result = GitLabRepoResponseTransformer.from_git(None)
        assert result is None
    
    def test_from_git_with_invalid_type(self):
        """Test GitRepoResponse creation with invalid type"""
        with pytest.raises(TypeError):
            GitLabRepoResponseTransformer.from_git("invalid_type")


class TestGitHubRepoResponseTransformer:
    """Test cases for GitHubRepoResponseTransformer"""
    
    def test_transform_repository_to_dict(self):
        """Test repository transformation to dict"""
        mock_repo = MagicMock()
        mock_repo.id = 123
        mock_repo.name = "github-repo"
        mock_repo.description = "GitHub repository"
        mock_repo.default_branch = "main"
        mock_repo.forks_count = 10
        mock_repo.size = 1024
        mock_repo.stargazers_count = 50
        mock_repo.full_name = "test/github-repo"
        mock_repo.html_url = "https://github.com/test/github-repo"
        mock_repo.private = False
        mock_repo.visibility = "public"
        mock_repo.created_at = "2023-01-01"
        
        result = GitHubRepoResponseTransformer.transform_repository_to_dict(mock_repo)
        
        assert result["id"] == "123"
        assert result["name"] == "github-repo"
        assert result["description"] == "GitHub repository"
        assert result["default_branch"] == "main"
        assert result["forks_count"] == 10
        assert result["size"] == 1024
        assert result["stargazers_count"] == 50
        assert result["full_name"] == "test/github-repo"
        assert result["html_url"] == "https://github.com/test/github-repo"
        assert result["private"] is False
        assert result["visibility"] == "public"
        assert result["repo_created_at"] == "2023-01-01"
    
    def test_transform_repository_with_none_values(self):
        """Test repository transformation with None values"""
        mock_repo = MagicMock()
        mock_repo.id = 456
        mock_repo.name = "minimal-repo"
        mock_repo.description = None
        mock_repo.default_branch = None  # Will default to "main"
        mock_repo.forks_count = None  # Will default to 0
        mock_repo.size = None  # Will default to 0
        mock_repo.stargazers_count = None  # Will default to 0
        mock_repo.full_name = "test/minimal-repo"
        mock_repo.html_url = "https://github.com/test/minimal-repo"
        mock_repo.private = True
        mock_repo.visibility = None
        mock_repo.created_at = "2023-02-01"
        
        result = GitHubRepoResponseTransformer.transform_repository_to_dict(mock_repo)
        
        assert result["default_branch"] == "main"
        assert result["forks_count"] == 0
        assert result["size"] == 0
        assert result["stargazers_count"] == 0
        assert result["description"] is None
        assert result["visibility"] is None
    
    def test_from_git_with_repository_object(self):
        """Test GitRepoResponse creation from GitHub repository object"""
        mock_repo = MagicMock(spec=Repository)
        mock_repo.id = 789
        mock_repo.name = "test-github-repo"
        mock_repo.description = "Test GitHub repository"
        mock_repo.default_branch = "develop"
        mock_repo.forks_count = 5
        mock_repo.size = 2048
        mock_repo.stargazers_count = 100
        mock_repo.full_name = "test/test-github-repo"
        mock_repo.html_url = "https://github.com/test/test-github-repo"
        mock_repo.private = True
        mock_repo.visibility = "private"
        mock_repo.created_at = "2023-05-01"
        
        result = GitHubRepoResponseTransformer.from_git(mock_repo)
        assert result.id == "789"
        assert result.repo_name == "test-github-repo"
        assert result.description == "Test GitHub repository"
        assert result.default_branch == "develop"
        assert result.forks_count == 5
        assert result.stargazers_count == 100
        assert result.relative_path == "test/test-github-repo"
        assert result.html_url == "https://github.com/test/test-github-repo"
        assert result.private is True
        assert result.visibility == "private"
        assert result.size == 2048
    
    def test_from_git_with_dict(self):
        """Test GitRepoResponse creation from dict"""
        data = {
            "id": 999,
            "name": "dict-github-repo",
            "description": "Dictionary GitHub repository",
            "default_branch": "master",
            "forks_count": 15,
            "size": 4096,
            "stargazers_count": 200,
            "full_name": "test/dict-github-repo",
            "html_url": "https://github.com/test/dict-github-repo",
            "private": False,
            "visibility": "public",
            "repo_created_at": "2023-07-01"
        }
        
        result = GitHubRepoResponseTransformer.from_git(data)
        
        assert result.id == "999"
        assert result.repo_name == "dict-github-repo"
        assert result.private is False
        assert result.size == 4096
    
    def test_from_git_with_none(self):
        """Test GitRepoResponse creation with None data"""
        result = GitHubRepoResponseTransformer.from_git(None)
        assert result is None
    
    def test_from_git_with_invalid_type(self):
        """Test GitRepoResponse creation with invalid type"""
        with pytest.raises(TypeError):
            GitHubRepoResponseTransformer.from_git(123)
