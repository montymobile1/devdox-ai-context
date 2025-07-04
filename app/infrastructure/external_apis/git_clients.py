# src/infrastructure/external_apis/git_clients.py
from abc import ABC, abstractmethod
from typing import Dict, Any
from github import Github
import gitlab

# Import the retrieve_git_fetcher_or_die function

from app.core.config import GitHosting

from app.core.exceptions.custom_exceptions import DevDoxAPIException
from app.handlers.utils.constants import SERVICE_UNAVAILABLE


class GitClient(ABC):
    @abstractmethod
    async def get_repository_info(self, repo_url: str) -> Dict[str, Any]:
        pass


class GitHubClient(GitClient):
    def __init__(self, token: str):
        self.client = Github(token)

    async def get_repository_info(self, repo_url: str) -> Dict[str, Any]:
        """Get repository metadata"""
        parts = repo_url.replace("https://github.com/", "").split("/")
        owner, repo_name = parts[0], parts[1]

        repo = self.client.get_repo(f"{owner}/{repo_name}")
        return {
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "language": repo.language,
            "default_branch": repo.default_branch,
            "size": repo.size,
            "created_at": repo.created_at,
            "updated_at": repo.updated_at,
        }

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
        }
        return any(filename.endswith(ext) for ext in extensions)


class GitLabClient(GitClient):
    def __init__(self, token: str):
        self.client = gitlab.Gitlab("https://gitlab.com", private_token=token)

    async def get_repository_info(self, repo_url: str) -> Dict[str, Any]:
        """Get repository metadata"""
        project_path = repo_url.replace("https://gitlab.com/", "")
        project = self.client.projects.get(project_path)

        return {
            "name": project.name,
            "full_name": project.path_with_namespace,
            "description": project.description,
            "default_branch": project.default_branch,
            "created_at": project.created_at,
            "updated_at": project.last_activity_at,
        }

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
        }
        return any(filename.endswith(ext) for ext in extensions)


def retrieve_git_fetcher_or_die(
    store, provider: GitHosting | str, include_data_mapper: bool = True
) -> tuple[Any, Any]:
    """

    Retrieve git fetcher and data mapper from store or raise exception.

    This function is imported from the main application.

    """

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


class GitClientFactory:
    """Factory for creating git clients using retrieve_git_fetcher_or_die"""

    def __init__(self, store):
        """

        Initialize factory with a store that contains git fetchers.



        Args:

            store: Store containing git fetchers and data mappers (e.g., RepoFetcher instance)

        """

        self.store = store

    def create_client(self, provider: GitHosting | str, token: str) -> GitClient:
        """

        Create a git client using the retrieve_git_fetcher_or_die function.



        Args:

            provider: Git provider (GitHosting enum or string like "github", "gitlab")

            token: Authentication token



        Returns:

            GitClient: Configured git client instance



        Raises:

            DevDoxAPIException: If provider is unsupported or unavailable

        """

        try:
            # Use retrieve_git_fetcher_or_die to validate provider availability

            fetcher, fetcher_data_mapper = retrieve_git_fetcher_or_die(
                self.store,
                provider,
                include_data_mapper=False,  # We only need validation, not the mapper
            )
            # Normalize provider to GitHosting enum

            if isinstance(provider, str):
                provider_str = provider.upper()

                if provider_str == "GITHUB":
                    provider_enum = GitHosting.GITHUB

                elif provider_str == "GITLAB":
                    provider_enum = GitHosting.GITLAB

                else:
                    raise DevDoxAPIException(
                        user_message=SERVICE_UNAVAILABLE,
                        log_message=f"Unsupported git provider: {provider}",
                        log_level="exception",
                    )

            else:
                provider_enum = provider
            # Create the appropriate client based on provider

            if provider_enum == GitHosting.GITHUB:
                return GitHubClient(token)

            elif provider_enum == GitHosting.GITLAB:
                return GitLabClient(token)

            else:
                # This should be caught by retrieve_git_fetcher_or_die, but as a fallback

                raise DevDoxAPIException(
                    user_message=SERVICE_UNAVAILABLE,
                    log_message=f"Unsupported git provider: {provider}",
                    log_level="exception",
                )

        except DevDoxAPIException:
            # Re-raise DevDoxAPIException as-is
            raise

        except Exception as e:
            # Wrap any other exceptions

            raise DevDoxAPIException(
                user_message="Failed to create git client",
                log_message=f"Error creating git client for provider {provider}: {str(e)}",
                log_level="exception",
                root_exception=e,
            ) from e
