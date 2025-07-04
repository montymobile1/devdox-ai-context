from dependency_injector import containers, providers

from app.infrastructure.database.repositories import (
    TortoiseUserRepository,
    TortoiseRepoRepository,
    TortoiseContextRepository,
    TortoiseAPIKeyRepository,
    TortoiseGitLabelRepository,
    TortoiseCodeChunks,
)
from app.infrastructure.queues.supabase_queue import SupabaseQueue
from app.handlers.message_handler import MessageHandler
from encryption_src.fernet.service import FernetEncryptionHelper
from app.services.processing_service import ProcessingService
from app.core.config import settings


class Container(containers.DeclarativeContainer):
    """Dependency injection container"""

    # Configuration
    config = providers.Configuration()

    # Infrastructure - Database Repositories
    user_repository = providers.Singleton(TortoiseUserRepository)
    repo_repository = providers.Singleton(TortoiseRepoRepository)
    context_repository = providers.Singleton(TortoiseContextRepository)
    api_key_repository = providers.Singleton(TortoiseAPIKeyRepository)
    git_label_repository = providers.Singleton(TortoiseGitLabelRepository)
    code_chunks_repository = providers.Singleton(TortoiseCodeChunks)

    # Infrastructure - External Services
    queue_service = providers.Singleton(
        SupabaseQueue,
        host=settings.SUPABASE_HOST,
        port=settings.SUPABASE_PORT,
        user=settings.SUPABASE_USER,
        password=settings.SUPABASE_PASSWORD,
        db_name=settings.SUPABASE_DB_NAME,
    )

    encryption_service = providers.Singleton(
        FernetEncryptionHelper, secret_key=settings.SECRET_KEY
    )

    # Application Services
    processing_service = providers.Factory(
        ProcessingService,
        user_info=user_repository,
        context_repository=context_repository,
        repo_repository=repo_repository,
        git_label_repository=git_label_repository,
        encryption_service=encryption_service,
        code_chunks_repository=code_chunks_repository,
    )

    message_handler = providers.Factory(
        MessageHandler,
        processing_service=processing_service,
        queue_service=queue_service,
    )
