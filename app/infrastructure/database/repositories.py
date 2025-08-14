import logging
from typing import List, Optional

from app.core.exceptions import exception_constants
from app.core.exceptions.local_exceptions import (ContextNotFoundError, DatabaseError, RepoNotFoundError)
from models_src.dto.api_key import APIKeyResponseDTO
from models_src.dto.code_chunks import CodeChunksRequestDTO, CodeChunksResponseDTO
from models_src.dto.git_label import GitLabelResponseDTO
from models_src.dto.repo import RepoResponseDTO
from models_src.dto.user import UserRequestDTO, UserResponseDTO
from models_src.models import CodeChunks, Repo, User
from models_src.repositories.api_key import TortoiseApiKeyStore
from models_src.repositories.code_chunks import TortoiseCodeChunksStore
from models_src.repositories.git_label import TortoiseGitLabelStore
from models_src.repositories.repo import TortoiseRepoStore
from models_src.repositories.user import TortoiseUserStore

logger = logging.getLogger(__name__)


class UserRepositoryHelper:
    
    def __init__(self, repo=None):
        self.__repo = repo if repo else TortoiseUserStore()

    async def find_by_user_id(self, user_id: str) -> Optional[User]:
        try:
            return await self.__repo.find_by_user_id(user_id)
        except Exception as e:
            logger.error(f"Error finding user by user_id {user_id}: {str(e)}")
            return None

    async def update_token_usage(self, user_id: str, tokens_used: int) -> None:
        try:
            
            total_updated = await self.__repo.increment_token_usage(user_id, tokens_used)
            
            if total_updated:
                raise Exception("Failed to update token usage")
            
            logger.info(f"Updated token usage for user {user_id}: +{tokens_used}")
        except Exception as e:
            raise DatabaseError(user_message=exception_constants.DB_USER_TOKEN_UPDATE_FAILED,
                                internal_context={"user_id": user_id}) from e

    async def create_user(self, user_data: dict) -> UserResponseDTO:
        try:
            user = await self.__repo.save(UserRequestDTO(**user_data))
            logger.info(f"Created new user: {user.user_id}")
            return user
        except Exception as e:
            raise DatabaseError(user_message=exception_constants.DB_USER_CREATION_FAILED) from e


class APIKeyRepositoryHelper:
    
    def __init__(self, repo=TortoiseApiKeyStore()):
        self.__repo = repo
    
    async def find_active_by_key(self, api_key: str) -> Optional[APIKeyResponseDTO]:
        try:
            return await self.__repo.find_first_by_api_key_and_is_active(api_key, is_active=True)
        except Exception as e:
            logger.error(f"Error finding API key: {str(e)}")
            return None

    async def update_last_used(self, api_key_id: str) -> None:
        try:
            await self.__repo.update_last_used_by_id(api_key_id)

        except Exception as e:
            raise DatabaseError(user_message=exception_constants.DB_API_KEY_UPDATE_FAILED) from e

class RepoRepositoryHelper:
    
    def __init__(self, repo=TortoiseRepoStore()):
        self.__repo = repo
    
    async def find_by_repo_id(self, repo_id: str) -> Optional[RepoResponseDTO]:
        try:
            return await self.__repo.find_by_repo_id(repo_id)
        except Exception as e:
            logger.error(f"Error finding repo by repo_id {repo_id}: {str(e)}")
            return None

    async def find_by_user_and_url(self, user_id: str, html_url: str) -> Optional[Repo]:
        try:
            return await self.__repo.find_by_user_id_and_html_url(user_id=user_id, html_url=html_url)
        except Exception as e:
            logger.error(
                f"Error finding repo for user {user_id} and URL {html_url}: {str(e)}"
            )
            return None

    async def update_processing_status(
        self, repo_id: str, status: str, **kwargs
    ) -> None:
        try:
            repo = await self.__repo.update_status_by_repo_id(
                repo_id=repo_id,
                status=status,
                **kwargs)
            
            if repo <=0 or not repo:
                raise RepoNotFoundError(user_message=exception_constants.REPOSITORY_NOT_FOUND, internal_context={"repo_id": repo_id})
            
            logger.info(f"Updated repo {repo_id} status to {status}")
        except RepoNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error updating repo status: {str(e)}")
            raise DatabaseError(user_message=exception_constants.DB_REPO_STATUS_UPDATE_FAILED) from e

class GitLabelRepositoryHelper:
    
    def __init__(self, repo=TortoiseGitLabelStore()):
        self.__repo = repo
    
    
    async def find_by_user_and_hosting(
        self, user_id: str, id: str, git_hosting: str
    ) -> Optional[GitLabelResponseDTO]:
        try:
            return await self.__repo.find_by_id_and_user_id_and_git_hosting(
                id=id, user_id=user_id, git_hosting=git_hosting
            )
        except Exception as e:
            logger.error(f"Error finding git label: {str(e)}")
            return None


class ContextRepositoryHelper:
    def __init__(self, repo=TortoiseRepoStore()):
        self.__repo = repo
    
    async def create_context(self, repo_id: str, user_id: str, config: dict) -> RepoResponseDTO:
        try:
            context = await self.__repo.save_context(repo_id=repo_id, user_id=user_id, config=config)
            logger.info(f"Created context for repo {repo_id}")
            return context
        except Exception as e:
            raise DatabaseError(user_message=exception_constants.DB_CONTEXT_REPO_CREATE_FAILED) from e

    async def update_status(self, context_id: str, status: str, **kwargs) -> None:
        try:
            context = await self.__repo.update_status_by_repo_id(id=context_id, status=status, **kwargs)
            if not context or context<= 0:
                raise ContextNotFoundError(user_message=exception_constants.CONTEXT_NOT_FOUND, internal_context={"context_id": context_id})
            
            logger.info(f"Updated context {context_id} status to {status}")
        except ContextNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(user_message=exception_constants.DB_CONTEXT_REPO_UPDATE_FAILED) from e

    async def update_repo_repo_system_reference(self, context_id: str, repo_system_reference:str) -> None:
        try:
            context = await self.__repo.update_repo_system_reference_by_id(id=context_id, repo_system_reference=repo_system_reference)
            if not context or context <= 0:
                raise ContextNotFoundError(f"Context {context_id} not found")
            
            logger.info(f"Updated context {context_id} ")

        except ContextNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error updating context status: {str(e)}")
            raise DatabaseError(f"Failed to update context: {str(e)}")


class CodeChunksRepositoryHelper:
    
    def __init__(self, repo=TortoiseCodeChunksStore()):
        self.__repo = repo
    
    async def store_emebeddings(
        self, repo_id: str, user_id: str, data: dict, commit_number: str
    ) -> Optional[CodeChunks]:
        try:
            created_chunks = []
            for result in data:
                chunk = await self.__repo.save(
                    CodeChunksRequestDTO(
                        repo_id=repo_id,
                        user_id=user_id,
                        content=result["content"],
                        embedding=result["embedding"],
                        metadata=result["metadata"],
                        file_name=result["file_name"],
                        file_path=result["file_path"],
                        file_size=result["file_size"],
                        commit_number=commit_number,
                    )
                )
                created_chunks.append(chunk)

            logger.info(f"Stored {len(created_chunks)} embeddings for repo {repo_id}")
            return created_chunks[0] if created_chunks else None
        except Exception as e:
            raise DatabaseError(user_message=exception_constants.DB_CODE_CHUNKS_CREATE_FAILED) from e

    async def find_by_repo(self, repo_id: str, limit: int = 100) -> List[CodeChunksResponseDTO]:
        try:
            return await self.__repo.find_all_by_repo_id_with_limit(repo_id=repo_id, limit=limit)
        except Exception as e:
            logger.error(f"Error finding code chunks for repo {repo_id}: {str(e)}")
            return []
