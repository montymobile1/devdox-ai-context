import datetime
import logging
from typing import List, Optional

from app.core.exceptions import exception_constants
from app.core.exceptions.local_exceptions import (
    ContextNotFoundError,
    DatabaseError
)
from models_src.dto.api_key import APIKeyResponseDTO
from models_src.dto.code_chunks import CodeChunksRequestDTO, CodeChunksResponseDTO
from models_src.dto.git_label import GitLabelResponseDTO
from models_src.dto.repo import RepoResponseDTO
from models_src.dto.user import UserRequestDTO, UserResponseDTO
from models_src.repositories.api_key import TortoiseApiKeyStore
from models_src.repositories.code_chunks import TortoiseCodeChunksStore
from models_src.repositories.git_label import TortoiseGitLabelStore
from models_src.repositories.repo import TortoiseRepoStore
from models_src.repositories.user import TortoiseUserStore

logger = logging.getLogger(__name__)


class UserRepositoryHelper:

    def __init__(self, repo=None):
        self._repo = repo if repo else TortoiseUserStore()

    async def find_by_user_id(self, user_id: str) -> Optional[UserResponseDTO]:
        try:
            return await self._repo.find_by_user_id(user_id)
        except Exception:
            logger.exception(
                exception_constants.ERROR_USER_NOT_FOUND_BY_ID.format(user_id=user_id)
            )
            return None

    async def update_token_usage(self, user_id: str, tokens_used: int) -> None:
        try:

            total_updated = await self._repo.increment_token_usage(user_id, tokens_used)

            if not total_updated or total_updated <= 0:
                raise DatabaseError(exception_constants.ERROR_USER_TOKEN_USAGE_UPDATE)

            logger.info(f"Updated token usage for user {user_id}: +{tokens_used}")
        except Exception as e:
            raise DatabaseError(
                user_message=exception_constants.DB_USER_TOKEN_UPDATE_FAILED,
                internal_context={"user_id": user_id},
            ) from e

    async def create_user(self, user_data: dict) -> UserResponseDTO:
        try:
            user = await self._repo.save(UserRequestDTO(**user_data))
            logger.info(f"Created new user: {user.user_id}")
            return user
        except Exception as e:
            raise DatabaseError(
                user_message=exception_constants.DB_USER_CREATION_FAILED
            ) from e


class APIKeyRepositoryHelper:

    def __init__(self, repo=None):
        self._repo = repo if repo else TortoiseApiKeyStore()

    async def find_active_by_key(self, api_key: str) -> Optional[APIKeyResponseDTO]:
        try:
            return await self._repo.find_by_active_api_key(api_key, is_active=True)
        except Exception:
            logger.exception(exception_constants.ERROR_FINDING_API_KEY)
            return None

    async def update_last_used(self, api_key_id: str) -> None:
        try:
            await self._repo.update_last_used_by_id(api_key_id)

        except Exception as e:
            raise DatabaseError(
                user_message=exception_constants.DB_API_KEY_UPDATE_FAILED
            ) from e


class RepoRepositoryHelper:

    def __init__(self, repo=None):
        self._repo = repo if repo else TortoiseRepoStore()

    async def find_by_repo_id_user_id(
        self, repo_id: str, user_id: str
    ) -> Optional[RepoResponseDTO]:
        try:
            return await self._repo.find_by_repo_id_user_id(repo_id, user_id)
        except Exception:
            logger.exception(exception_constants.ERROR_USER_NOT_FOUND_BY_ID)
            return None

    async def find_by_repo_id(self, repo_id: str) -> Optional[RepoResponseDTO]:
        try:
            return await self._repo.find_by_repo_id(repo_id)
        except Exception:
            logger.exception(
                exception_constants.ERROR_REPO_NOT_FOUND_BY_REPO_ID.format(
                    repo_id=repo_id
                )
            )
            return None

    async def find_repo_by_id(self, id: str) -> Optional[RepoResponseDTO]:
        try:
            return await self._repo.find_by_id(id)
        except Exception:
            logger.exception(
                exception_constants.ERROR_REPO_NOT_FOUND_BY_ID.format(id=id)
            )
            return None

    async def find_by_user_and_url(
        self, user_id: str, html_url: str
    ) -> Optional[RepoResponseDTO]:
        try:
            return await self._repo.find_by_user_id_and_html_url(
                user_id=user_id, html_url=html_url
            )
        except Exception:
            logger.exception(
                exception_constants.ERROR_FINDING_REPO.format(
                    user_id=user_id, html_url=html_url
                )
            )
            return None


class GitLabelRepositoryHelper:

    def __init__(self, repo=None):
        self._repo = repo if repo else TortoiseGitLabelStore()

    async def find_by_user_and_hosting(
        self, user_id: str, id: str, git_hosting: str
    ) -> Optional[GitLabelResponseDTO]:
        try:
            return await self._repo.find_by_id_and_user_id_and_git_hosting(
                id=id, user_id=user_id, git_hosting=git_hosting
            )
        except Exception:
            logger.exception(exception_constants.ERROR_FINDING_GIT_LABEL)
            return None


class ContextRepositoryHelper:
    def __init__(self, repo=None):
        self._repo = repo if repo else TortoiseRepoStore()

    async def create_context(
        self, repo_id: str, user_id: str, config: dict
    ) -> RepoResponseDTO:
        try:
            context = await self._repo.save_context(
                repo_id=repo_id, user_id=user_id, config=config
            )
            logger.info(f"Created context for repo {repo_id}")
            return context
        except Exception as e:
            raise DatabaseError(
                user_message=exception_constants.DB_CONTEXT_REPO_CREATE_FAILED
            ) from e

    async def update_status(
        self,
        context_id: str,
        status: str,
        processing_end_time: datetime.datetime,
        total_files: int,
        total_chunks: int,
        total_embeddings: int,
    ) -> None:
        try:
            context = await self._repo.update_analysis_metadata_by_id(
                id=context_id,
                status=status,
                processing_end_time=processing_end_time,
                total_files=total_files,
                total_chunks=total_chunks,
                total_embeddings=total_embeddings,
            )

            if not context or context <= 0:
                raise ContextNotFoundError(
                    user_message=exception_constants.CONTEXT_NOT_FOUND,
                    internal_context={"context_id": context_id},
                )

            logger.info(f"Updated context {context_id} status to {status}")
        except ContextNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                user_message=exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED
            ) from e

    async def update_repo_system_reference(
        self, context_id: str, repo_system_reference: str
    ) -> None:
        try:
            context = await self._repo.update_repo_system_reference_by_id(
                id=context_id, repo_system_reference=repo_system_reference
            )
            if not context or context <= 0:
                raise ContextNotFoundError(
                    user_message=exception_constants.CONTEXT_NOT_FOUND,
                    internal_context={"context_id": context_id},
                )

            logger.info(f"Updated context {context_id} ")

        except ContextNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error updating context status: {str(e)}")
            raise DatabaseError(
                user_message=exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED
            ) from e


class CodeChunksRepositoryHelper:

    def __init__(self, repo=None):
        self._repo = repo if repo else TortoiseCodeChunksStore()

    async def store_emebeddings(
        self, repo_id: str, user_id: str, data: List[dict], commit_number: str
    ) -> Optional[CodeChunksResponseDTO]:
        try:
            created_chunks = []
            for result in data:
                chunk = await self._repo.save(
                    CodeChunksRequestDTO(
                        repo_id=repo_id,
                        user_id=user_id,
                        content=result.get("encrypted_content"),
                        embedding=result.get("embedding"),
                        metadata=result.get("metadata"),
                        file_name=result.get("file_name"),
                        file_path=result.get("file_path"),
                        file_size=result.get("file_size"),
                        commit_number=commit_number,
                    )
                )
                created_chunks.append(chunk)

            count = len(created_chunks) if created_chunks else 0

            logger.info(f"Stored {len(created_chunks)} embeddings for repo {repo_id}")
            return created_chunks[0] if count else None
        except Exception as e:
            raise DatabaseError(
                user_message=exception_constants.DB_CODE_CHUNKS_CREATE_FAILED
            ) from e

    async def find_by_repo(
        self, repo_id: str, limit: int = 100
    ) -> List[CodeChunksResponseDTO]:
        try:
            return await self._repo.find_all_by_repo_id_with_limit(
                repo_id=repo_id, limit=limit
            )
        except Exception as e:
            logger.error(f"Error finding code chunks for repo {repo_id}: {str(e)}")
            return []
