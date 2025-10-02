# src/infrastructure/external_apis/git_clients.py
from abc import ABC, abstractmethod
from typing import Any

from devdox_ai_git.git_managers import GitHubManager, GitLabManager

from app.core.exceptions import exception_constants


from app.core.config import GitHosting

from app.core.exceptions.base_exceptions import DevDoxAPIException

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
            user_message=exception_constants.SERVICE_UNAVAILABLE,
            log_message=exception_constants.PROVIDER_NOT_SUPPORTED_MESSAGE.format(provider=provider),
            log_level="exception",
        )

    if include_data_mapper and not fetcher_data_mapper:
        raise DevDoxAPIException(
            user_message=exception_constants.SERVICE_UNAVAILABLE,
            log_message=exception_constants.PROVIDER_NOT_SUPPORTED_MESSAGE.format(provider=provider),
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

    def create_client(self, provider: GitHosting | str, token: str):
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

            _, _ = retrieve_git_fetcher_or_die(
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
                        user_message=exception_constants.SERVICE_UNAVAILABLE,
                        log_message=exception_constants.PROVIDER_NOT_SUPPORTED_MESSAGE.format(provider=provider),
                        log_level="exception",
                    )

            else:
                provider_enum = provider
            # Create the appropriate client based on provider

            if provider_enum == GitHosting.GITHUB:
                return GitHubManager().authenticate(access_token=token)

            elif provider_enum == GitHosting.GITLAB:
                return GitLabManager().authenticate(access_token=token)

            else:
                # This should be caught by retrieve_git_fetcher_or_die, but as a fallback
                
                raise DevDoxAPIException(
                    user_message=exception_constants.SERVICE_UNAVAILABLE,
                    log_message=exception_constants.PROVIDER_NOT_SUPPORTED_MESSAGE.format(provider=provider),
                    log_level="exception",
                )

        except DevDoxAPIException:
            # Re-raise DevDoxAPIException as-is
            raise

        except Exception as e:
            # Wrap any other exceptions

            raise DevDoxAPIException(
                user_message=exception_constants.SERVICE_UNAVAILABLE,
                log_message=exception_constants.GIT_CLIENT_CREATION_FAILED,
                internal_context={
                    "provider": provider
                },
                log_level="exception",
            ) from e
