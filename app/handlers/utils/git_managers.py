from typing import Any

from devdox_ai_git.repo_fetcher import RepoFetcher
from models_src.dto.repo import GitHosting

from app.core.exceptions.base_exceptions import DevDoxAPIException
from app.core.exceptions.exception_constants import (
    PROVIDER_NOT_SUPPORTED_MESSAGE,
    SERVICE_UNAVAILABLE,
)

def retrieve_git_fetcher_or_die(
    store:RepoFetcher, provider: GitHosting | str, include_data_mapper: bool = True
) -> tuple[Any, Any]:
    fetcher, fetcher_data_mapper = store.get_components(provider)
    if not fetcher:
        raise DevDoxAPIException(
            user_message=SERVICE_UNAVAILABLE,
            log_message=PROVIDER_NOT_SUPPORTED_MESSAGE.format(provider=provider),
            log_level="exception",
        )

    if include_data_mapper and not fetcher_data_mapper:
        raise DevDoxAPIException(
            user_message=SERVICE_UNAVAILABLE,
            log_message=PROVIDER_NOT_SUPPORTED_MESSAGE.format(provider=provider),
            log_level="exception",
        )

    return fetcher, fetcher_data_mapper
