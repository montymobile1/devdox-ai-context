from typing import Any

from app.core.exceptions import exception_constants

from app.core.exceptions.base_exceptions import DevDoxAPIException

from app.core.config import GitHosting


def retrieve_git_fetcher_or_die(
    store, provider: GitHosting | str, include_data_mapper: bool = True
) -> tuple[Any, Any]:
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
