from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from models import User, Repo, APIKEY, GitLabel, CodeChunks
from app.core.exceptions.base import (
    RepoNotFoundError,
    DatabaseError,
    ContextNotFoundError,
)
import logging

logger = logging.getLogger(__name__)

class BaseRepository[T](ABC):
    """Base repository with common database operations"""

    @abstractmethod
    async def find_by_id(self, id: UUID) -> Optional[T]:
        pass

    @abstractmethod
    async def create(self, **kwargs) -> T:
        pass

    @abstractmethod
    async def update(self, id: UUID, **kwargs) -> Optional[T]:
        pass

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        pass


class UserRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_user_id(self, user_id: str) -> Optional[User]:
        pass

    @abstractmethod
    async def update_token_usage(self, user_id: str, tokens_used: int) -> None:
        pass

    @abstractmethod
    async def create_user(self, user_data: dict) -> User:
        pass


class TortoiseUserRepository(UserRepositoryInterface):
    async def find_by_user_id(self, user_id: str) -> Optional[User]:
        try:
            return await User.filter(user_id=user_id).first()
        except Exception as e:
            logger.error(f"Error finding user by user_id {user_id}: {str(e)}")
            return None

    async def update_token_usage(self, user_id: str, tokens_used: int) -> None:
        try:
            user = await User.get(user_id=user_id)
            user.token_used += tokens_used
            await user.save()
            logger.info(f"Updated token usage for user {user_id}: +{tokens_used}")
        except Exception as e:
            logger.error(f"Error updating token usage for user {user_id}: {str(e)}")
            raise DatabaseError(f"Failed to update token usage: {str(e)}")

    async def create_user(self, user_data: dict) -> User:
        try:
            user = await User.create(**user_data)
            logger.info(f"Created new user: {user.user_id}")
            return user
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise DatabaseError(f"Failed to create user: {str(e)}")


class APIKeyRepositoryInterface(ABC):
    @abstractmethod
    async def find_active_by_key(self, api_key: str) -> Optional[APIKEY]:
        pass

    @abstractmethod
    async def update_last_used(self, api_key_id: str) -> None:
        pass


class TortoiseAPIKeyRepository(APIKeyRepositoryInterface):
    async def find_active_by_key(self, api_key: str) -> Optional[APIKEY]:
        try:
            return await APIKEY.filter(api_key=api_key, is_active=True).first()
        except Exception as e:
            logger.error(f"Error finding API key: {str(e)}")
            return None

    async def update_last_used(self, api_key_id: str) -> None:
        try:
            api_key = await APIKEY.get(id=api_key_id)
            api_key.last_used_at = datetime.now(timezone.utc)
            await api_key.save()

        except Exception as e:
            logger.error(f"Error updating API key last used: {str(e)}")
            raise DatabaseError(f"Failed to update API key: {str(e)}")


class RepoRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_repo_id(self, repo_id: str) -> Optional[Repo]:
        pass

    @abstractmethod
    async def find_by_user_and_url(self, user_id: str, html_url: str) -> Optional[Repo]:
        pass

    @abstractmethod
    async def update_processing_status(
        self, repo_id: str, status: str, **kwargs
    ) -> None:
        pass


class TortoiseRepoRepository(RepoRepositoryInterface):
    async def find_by_repo_id(self, repo_id: str) -> Optional[Repo]:
        try:
            return await Repo.filter(repo_id=repo_id).first()
        except Exception as e:
            logger.error(f"Error finding repo by repo_id {repo_id}: {str(e)}")
            return None

    async def find_by_user_and_url(self, user_id: str, html_url: str) -> Optional[Repo]:
        try:
            return await Repo.filter(user_id=user_id, html_url=html_url).first()
        except Exception as e:
            logger.error(
                f"Error finding repo for user {user_id} and URL {html_url}: {str(e)}"
            )
            return None

    async def update_processing_status(
        self, repo_id: str, status: str, **kwargs
    ) -> None:
        try:
            repo = await Repo.filter(repo_id=repo_id).first()
            if not repo:
                raise RepoNotFoundError(f"Repository {repo_id} not found")

            repo.status = status
            for key, value in kwargs.items():
                if hasattr(repo, key):
                    setattr(repo, key, value)

            await repo.save()
            logger.info(f"Updated repo {repo_id} status to {status}")
        except RepoNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error updating repo status: {str(e)}")
            raise DatabaseError(f"Failed to update repo status: {str(e)}")


class GitLabelRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_user_and_hosting(
        self, user_id: str, id: str, git_hosting: str
    ) -> Optional[GitLabel]:
        pass


class TortoiseGitLabelRepository(GitLabelRepositoryInterface):
    async def find_by_user_and_hosting(
        self, user_id: str, id: str, git_hosting: str
    ) -> Optional[GitLabel]:
        try:
            return await GitLabel.filter(
                id=id, user_id=user_id, git_hosting=git_hosting
            ).first()
        except Exception as e:
            logger.error(f"Error finding git label: {str(e)}")
            return None


class ContextRepositoryInterface(ABC):
    @abstractmethod
    async def create_context(self, repo_id: str, user_id: str, config: dict) -> Repo:
        pass

    @abstractmethod
    async def update_status(self, context_id: str, status: str, **kwargs) -> None:
        pass


class TortoiseContextRepository(ContextRepositoryInterface):
    async def create_context(self, repo_id: str, user_id: str, config: dict) -> Repo:
        try:
            context = await Repo.create(
                repo_id=repo_id, user_id=user_id, config=config, status="pending"
            )
            logger.info(f"Created context for repo {repo_id}")
            return context
        except Exception as e:
            logger.error(f"Error creating context: {str(e)}")
            raise DatabaseError(f"Failed to create context: {str(e)}")

    async def update_status(self, context_id: str, status: str, **kwargs) -> None:
        try:
            context = await Repo.filter(id=context_id).first()
            if not context:
                raise ContextNotFoundError(f"Context {context_id} not found")

            context.status = status
            for key, value in kwargs.items():
                if hasattr(context, key):
                    setattr(context, key, value)
            await context.save()
            logger.info(f"Updated context {context_id} status to {status}")
        except ContextNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error updating context status: {str(e)}")
            raise DatabaseError(f"Failed to update context: {str(e)}")


class ContextCodeChunkInterface(ABC):
    @abstractmethod
    async def store_emebeddings(
        self, repo_id: str, user_id: str, data: dict, commit_number: str
    ) -> Optional[CodeChunks]:
        pass

    @abstractmethod
    async def find_by_repo(self, repo_id: str, limit: int = 100) -> List[CodeChunks]:
        pass


class TortoiseCodeChunks(ContextCodeChunkInterface):
    async def store_emebeddings(
        self, repo_id: str, user_id: str, data: dict, commit_number: str
    ) -> Optional[CodeChunks]:
        try:
            created_chunks = []
            for result in data:
                chunk = await CodeChunks.create(
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
                created_chunks.append(chunk)

            logger.info(f"Stored {len(created_chunks)} embeddings for repo {repo_id}")
            return created_chunks[0] if created_chunks else None
        except Exception as e:
            logger.error(f"Error storing embeddings: {str(e)}")
            raise DatabaseError(f"Failed to store embeddings: {str(e)}")

    async def find_by_repo(self, repo_id: str, limit: int = 100) -> List[CodeChunks]:
        try:
            return await CodeChunks.filter(repo_id=repo_id).limit(limit).all()
        except Exception as e:
            logger.error(f"Error finding code chunks for repo {repo_id}: {str(e)}")
            return []
