import uuid
from types import SimpleNamespace

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


