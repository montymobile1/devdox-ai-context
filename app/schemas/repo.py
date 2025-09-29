import uuid
from types import SimpleNamespace

from github.Repository import Repository
from gitlab.v4.objects import Project
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from enum import Enum


class GitHostingProvider(str, Enum):
    """Supported Git hosting providers"""

    GITHUB = "github"
    GITLAB = "gitlab"


class RepoBase(BaseModel):
    """Base repository schema with common fields"""

    repo_name: str = Field(..., description="Repository name", max_length=255)
    description: Optional[str] = Field(None, description="Repository description")
    html_url: str = Field(..., description="Repository URL", max_length=500)
    default_branch: str = Field(
        default="main", description="Default branch name", max_length=100
    )
    forks_count: int = Field(default=0, description="Number of forks", ge=0)
    stargazers_count: int = Field(default=0, description="Number of stars", ge=0)
    is_private: bool = Field(default=False, description="Whether repository is private")
    visibility: Optional[str] = Field(
        None, description="Repository visibility (GitLab)", max_length=50
    )
    git_hosting: Optional[GitHostingProvider] = Field(
        None, description="Git hosting provider"
    )
    language: Optional[str] = Field(
        None, description="Primary programming language", max_length=100
    )
    size: Optional[int] = Field(None, description="Repository size in KB", ge=0)
    repo_created_at: Optional[datetime] = Field(
        None, description="Repository creation date from provider"
    )
    repo_updated_at: Optional[datetime] = Field(
        None, description="Repository last update from provider"
    )


class RepoResponse(RepoBase):
    """Schema for repository response"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Primary key")
    user_id: str = Field(..., description="User ID who owns this repository")
    repo_id: str = Field(..., description="Repository ID from the Git provider")
    token_id: Optional[str] = Field(None, description="Associated token ID")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record update timestamp")


class GitRepoResponse(BaseModel):
    """Schema for Git provider repository response (unified format)"""

    id: str = Field(..., description="Repository ID from provider")
    repo_name: str = Field(..., description="Repository name")
    description: Optional[str] = Field(None, description="Repository description")
    html_url: str = Field(..., description="Repository URL")
    relative_path: str = Field(
        ..., description="The part of the repository's url excluding the domain"
    )

    default_branch: str = Field(..., description="Default branch name")
    forks_count: int = Field(..., description="Number of forks")
    stargazers_count: int = Field(..., description="Number of stars")
    size: Optional[int] = Field(None, description="Repository size in KB")
    repo_created_at: Optional[datetime] = Field(
        None, description="Repository creation date from provider"
    )
    # Platform-specific fields (one will be None depending on provider)
    private: Optional[bool] = Field(None, description="Private flag (GitHub)")
    visibility: Optional[str] = Field(None, description="Visibility setting (GitLab)")


class GitLabRepoResponseTransformer:
    @classmethod
    def derive_storage_size(cls, statistics: dict):
        if not statistics:
            return None

        return statistics.get("storage_size", 0)

    @classmethod
    def derived_private_field(cls, visibility: str):
        if not visibility:
            return None

        if visibility.lower() in ("private", "internal"):
            derived_private = True
        else:
            derived_private = False

        return derived_private

    @classmethod
    def transform_project_to_dict(cls, project: Project | SimpleNamespace) -> dict:
        extracted_visibility = getattr(project, "visibility", None)
        extracted_statistics = getattr(project, "statistics", None)

        return {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "default_branch": project.default_branch,
            "forks_count": project.forks_count,
            "visibility": extracted_visibility,
            "created_at": project.created_at,
            "star_count": project.star_count,
            "http_url_to_repo": project.http_url_to_repo,
            "path_with_namespace": project.path_with_namespace,
            "statistics": extracted_statistics,
        }

    @classmethod
    def from_git(cls, data: Project | SimpleNamespace | dict) -> GitRepoResponse | None:
        if not data:
            return None
        elif isinstance(data, Project) or isinstance(data, SimpleNamespace):
            dict_data = cls.transform_project_to_dict(data)
        elif isinstance(data, dict):
            dict_data = data
        else:
            raise TypeError(
                f"Unsupported type for `data`: {type(data)}. Expected Project, SimpleNamespace, or dict."
            )

        return GitRepoResponse(
            id=str(dict_data.get("id", "")),
            repo_name=dict_data.get("name"),
            description=dict_data.get("description"),
            default_branch=dict_data.get("default_branch", "main"),
            forks_count=dict_data.get("forks_count", 0),
            stargazers_count=dict_data.get("star_count", 0),
            html_url=dict_data.get("http_url_to_repo"),
            relative_path=dict_data.get("path_with_namespace"),
            visibility=dict_data.get("visibility"),
            repo_created_at=dict_data.get("created_at"),
            size=cls.derive_storage_size(dict_data.get("statistics")) or 0,
            private=cls.derived_private_field(dict_data.get("visibility")),
        )


class GitHubRepoResponseTransformer:
    @classmethod
    def transform_repository_to_dict(
        cls, repository: Repository | SimpleNamespace
    ) -> dict:
        return {
            "id": str(repository.id),
            "name": repository.name,
            "description": repository.description,
            "default_branch": repository.default_branch or "main",
            "forks_count": repository.forks_count or 0,
            "size": repository.size or 0,
            "stargazers_count": repository.stargazers_count or 0,
            "full_name": repository.full_name,
            "html_url": repository.html_url,
            "private": repository.private,
            "visibility": getattr(repository, "visibility", None),
            "repo_created_at": repository.created_at,
        }

    @classmethod
    def from_git(
        cls, data: Repository | SimpleNamespace | dict
    ) -> GitRepoResponse | None:
        if not data:
            return None
        elif isinstance(data, Repository) or isinstance(data, SimpleNamespace):
            dict_data = cls.transform_repository_to_dict(data)
        elif isinstance(data, dict):
            dict_data = data
        else:
            raise TypeError(
                f"Unsupported type for `data`: {type(data)}. Expected Repository, SimpleNamespace, or dict."
            )

        return GitRepoResponse(
            id=str(dict_data.get("id", "")),
            repo_name=dict_data.get("name"),
            description=dict_data.get("description"),
            default_branch=dict_data.get("default_branch", "main"),
            forks_count=dict_data.get("forks_count", 0),
            stargazers_count=dict_data.get("stargazers_count", 0),
            relative_path=dict_data.get("full_name"),
            html_url=dict_data.get("html_url"),
            private=dict_data.get("private"),
            visibility=dict_data.get("visibility"),
            size=dict_data.get("size", 0),
            repo_created_at=dict_data.get("repo_created_at"),
        )