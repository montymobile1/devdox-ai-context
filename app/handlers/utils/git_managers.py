from abc import abstractmethod
from typing import Any, Optional, Protocol
import gitlab
import requests
from github import Github, GithubException
from github.AuthenticatedUser import AuthenticatedUser
from github.Repository import Repository
from gitlab import Gitlab, GitlabError
from gitlab.v4.objects import Project

from app.core.config import GitHosting
from app.core.exceptions.custom_exceptions import DevDoxAPIException
from app.core.exceptions.exception_constants import SERVICE_UNAVAILABLE


class IManager(Protocol):
    @abstractmethod
    def authenticate(self, access_token):
        ...


class AuthenticatedGitHubManager:
    def __init__(self, base_url, git_client):
        self.base_url = base_url
        self._git_client: Github = git_client

    def get_project(self, full_name_or_id: str | int):
        try:
            return self._git_client.get_repo(full_name_or_id)
        except GithubException as e:
            raise DevDoxAPIException(
                user_message="Unable to fetch GithHub project",
                log_message="GitHub project fetch failed",
                root_exception=e,
            ) from e

    def get_project_languages(
        self, full_name_or_id_or_repository: str | int | Repository
    ):
        try:
            if isinstance(full_name_or_id_or_repository, Repository):
                return full_name_or_id_or_repository.get_languages()
            else:
                return self._git_client.get_repo(
                    full_name_or_id_or_repository
                ).get_languages()
        except GithubException as e:
            raise DevDoxAPIException(
                user_message="Unable to fetch GitHub project languages",
                log_message="GitHub project languages fetch failed",
                root_exception=e,
            ) from e

    def get_user(self) -> AuthenticatedUser:
        """Get the authenticated user information using PyGithub."""
        try:
            user = self._git_client.get_user()
            return user
        except GithubException as e:
            raise DevDoxAPIException(
                user_message="Unable to fetch GitHub user.",
                log_message="GitHub user fetch failed",
                root_exception=e,
            )

    def get_user_repositories(
        self,
        page=1,
        per_page=20,
        visibility="all",
        affiliation="owner,collaborator,organization_member",
        sort="updated",
        direction="desc",
    ):
        """
        Get list of repositories that the authenticated user has access to with pagination.
        """
        try:
            per_page = GitHubManager.validate_per_page(per_page)
            page = GitHubManager.validate_page(page)

            user = self._git_client.get_user()

            repos_paginated = user.get_repos(
                visibility=visibility,
                affiliation=affiliation,
                sort=sort,
                direction=direction,
            )
            repos_paginated.per_page = per_page

            repos_page = repos_paginated.get_page(page - 1)

            pagination_info = GitHubManager.get_pagination_info(
                total_count=repos_paginated.totalCount,
                page=page,
                per_page=per_page,
            )

            return {
                "repositories": repos_page,
                "pagination_info": pagination_info,
            }

        except GithubException as e:
            raise DevDoxAPIException(
                user_message="Unable to fetch GitHub repositories.",
                log_message="GitHub repository list fetch failed",
                root_exception=e,
            )

    def _is_supported_file(self, filename: str) -> bool:
        """Check if file type is supported"""
        extensions = {
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".cpp",
            ".c",
            ".hpp",
            ".h",
            ".rb",
            ".php",
            ".cs",
            ".jsx",
            ".tsx",
            ".vue",
            ".swift",
            ".kt",
            ".scala",
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
        }
        return any(filename.endswith(ext) for ext in extensions)


class GitHubManager(IManager):
    default_base_url = "https://api.github.com"

    def __init__(self, base_url=default_base_url):
        self.base_url = base_url

    def authenticate(self, access_token: str) -> AuthenticatedGitHubManager:
        try:
            if self.base_url == self.default_base_url:
                github_client = Github(access_token)
            else:
                github_client = Github(
                    base_url=self.base_url, login_or_token=access_token
                )

            return AuthenticatedGitHubManager(
                base_url=self.base_url, git_client=github_client
            )

        except GithubException as e:
            raise DevDoxAPIException(
                user_message="GitHub authentication failed",
                log_message="Failed to authenticate GitHubManager",
                root_exception=e,
            ) from e

    @staticmethod
    def validate_per_page(per_page):
        return per_page if 1 <= per_page <= 100 else 30

    @staticmethod
    def validate_page(page):
        return page if page >= 1 else 1

    @staticmethod
    def extract_repo_info(repo):
        return {
            "id": repo.id,
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "private": repo.private,
            "html_url": repo.html_url,
            "clone_url": repo.clone_url,
            "ssh_url": repo.ssh_url,
            "default_branch": repo.default_branch,
            "language": repo.language,
            "size": repo.size,
            "stargazers_count": repo.stargazers_count,
            "watchers_count": repo.watchers_count,
            "forks_count": repo.forks_count,
            "open_issues_count": repo.open_issues_count,
            "created_at": repo.created_at.isoformat() if repo.created_at else None,
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
            "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
            "owner": {
                "login": repo.owner.login,
                "id": repo.owner.id,
                "type": repo.owner.type,
            },
            "permissions": GitHubManager._get_repo_permissions(repo),
        }

    @staticmethod
    def _get_repo_permissions(repo):
        permissions = getattr(repo, "permissions", None)
        return {
            "admin": getattr(permissions, "admin", False),
            "push": getattr(permissions, "push", False),
            "pull": getattr(permissions, "pull", False),
        }

    @staticmethod
    def get_pagination_info(total_count, page, per_page):
        total_pages = (total_count + per_page - 1) // per_page
        has_next_page = page < total_pages
        has_prev_page = page > 1

        return {
            "current_page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next_page": has_next_page,
            "has_prev_page": has_prev_page,
            "next_page": page + 1 if has_next_page else None,
            "prev_page": page - 1 if has_prev_page else None,
        }


class AuthenticatedGitLabManager:
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        base_url,
        git_client,
        access_token,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url
        self._header = {"PRIVATE-TOKEN": access_token}
        self._git_client: Gitlab = git_client
        self._rq = session or requests.Session()

    def get_project(self, project_id, timeout: int = DEFAULT_TIMEOUT) -> Project:
        try:
            return self._git_client.projects.get(
                project_id, statistics=True, timeout=timeout
            )
        except GitlabError as e:
            raise DevDoxAPIException(
                user_message="Unable to fetch GitLab project",
                log_message="GitLab project fetch failed",
                root_exception=e,
            ) from e

    def get_project_languages(
        self, project_or_id: int | Project, timeout: int = DEFAULT_TIMEOUT
    ):
        try:
            if isinstance(project_or_id, Project):
                return project_or_id.languages()
            else:
                return self._git_client.projects.get(
                    project_or_id, timeout=timeout
                ).languages()
        except GitlabError as e:
            raise DevDoxAPIException(
                user_message="Unable to fetch GitLab project languages",
                log_message="GitLab project languages fetch failed",
                root_exception=e,
            ) from e

    def get_user(self, timeout: int = DEFAULT_TIMEOUT):
        try:
            url = f"{self.base_url}/api/v4/user"
            response = self._rq.get(url, headers=self._header, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise DevDoxAPIException(
                user_message="Unable to fetch GitLab user.",
                log_message="GitLab user fetch failed",
                root_exception=e,
            ) from e

    def get_user_repositories(
        self, page=1, per_page=20, timeout: int = DEFAULT_TIMEOUT
    ):
        try:
            per_page = max(1, min(per_page, 100))
            page = max(1, page)

            url = (
                f"{self.base_url}/api/v4/projects"
                f"?membership=true&min_access_level=30&per_page={per_page}&page={page}"
            )
            response = self._rq.get(url, headers=self._header, timeout=timeout)
            response.raise_for_status()

            repos = response.json()
            pagination = {
                "current_page": page,
                "per_page": per_page,
                "total_count": int(response.headers.get("X-Total") or 0) or 0,
                "total_pages": int(response.headers.get("X-Total-Pages", 1)),
                "next_page": int(response.headers.get("X-Next-Page") or 0) or None,
                "prev_page": int(response.headers.get("X-Prev-Page") or 0) or None,
            }
            return {"repositories": repos, "pagination_info": pagination}
        except requests.exceptions.RequestException as e:
            raise DevDoxAPIException(
                user_message="Unable to fetch GitLab repositories.",
                log_message="GitLab repository list fetch failed",
                root_exception=e,
            ) from e

    def _is_supported_file(self, filename: str) -> bool:
        """Check if file type is supported"""
        extensions = {
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".cpp",
            ".c",
            ".hpp",
            ".h",
            ".rb",
            ".php",
            ".cs",
            ".jsx",
            ".tsx",
            ".vue",
            ".swift",
            ".kt",
            ".scala",
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
        }
        return any(filename.endswith(ext) for ext in extensions)


class GitLabManager(IManager):
    default_base_url = "https://gitlab.com"

    def __init__(self, base_url=default_base_url):
        self.base_url = base_url.rstrip("/")

    def authenticate(self, access_token):
        try:
            gl = gitlab.Gitlab(url=self.base_url, private_token=access_token)
            gl.auth()
            return AuthenticatedGitLabManager(
                base_url=self.base_url, git_client=gl, access_token=access_token
            )

        except GitlabError as e:
            raise DevDoxAPIException(
                user_message="GitLab authentication failed",
                log_message="Failed to authenticate GitLabManager",
                root_exception=e,
            ) from e


def retrieve_git_fetcher_or_die(
    store, provider: GitHosting | str, include_data_mapper: bool = True
) -> tuple[Any, Any]:
    fetcher, fetcher_data_mapper = store.get_components(provider)
    if not fetcher:
        raise DevDoxAPIException(
            user_message=SERVICE_UNAVAILABLE,
            log_message=f"Unsupported Git hosting: {provider}",
            log_level="exception",
        )

    if include_data_mapper and not fetcher_data_mapper:
        raise DevDoxAPIException(
            user_message=SERVICE_UNAVAILABLE,
            log_message=f"Unable to find mapper for Git hosting: {provider}",
            log_level="exception",
        )

    return fetcher, fetcher_data_mapper
