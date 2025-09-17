from app.services.email_service import EmailDispatcher, EmailDispatchOptions, QnAEmailService

from app.infrastructure.mailing_service.client import FastAPIMailClient
from dependency_injector import containers, providers

from app.infrastructure.database.repositories import (
    UserRepositoryHelper,
    RepoRepositoryHelper,
    ContextRepositoryHelper,
    APIKeyRepositoryHelper,
    GitLabelRepositoryHelper,
    CodeChunksRepositoryHelper,
)
from app.infrastructure.queues.supabase_queue import SupabaseQueue
from app.handlers.message_handler import MessageHandler
from app.services.auth_service import AuthService
from encryption_src.fernet.service import FernetEncryptionHelper
from app.services.processing_service import ProcessingService
from app.core.config import settings


class Container(containers.DeclarativeContainer):
    """Dependency injection container"""

    # Configuration
    config = providers.Configuration()

    # Infrastructure - Database Repositories
    user_repository = providers.Singleton(UserRepositoryHelper)
    repo_repository = providers.Singleton(RepoRepositoryHelper)
    context_repository = providers.Singleton(ContextRepositoryHelper)
    api_key_repository = providers.Singleton(APIKeyRepositoryHelper)
    git_label_repository = providers.Singleton(GitLabelRepositoryHelper)
    code_chunks_repository = providers.Singleton(CodeChunksRepositoryHelper)

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

    auth_service = providers.Factory(
        AuthService,
        user_repository=user_repository,
        api_key_repository=api_key_repository,
        encryption_service=encryption_service,
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
        auth_service=auth_service,
        processing_service=processing_service,
        queue_service=queue_service,
    )
    
    # -------------------------
    # Mail stack
    # -------------------------

    # small helper to ensure the template path is set
    init_mail_settings = providers.Callable(
        lambda s, d: (setattr(s, "MAIL_TEMPLATE_FOLDER", d), s)[1],
        s=settings.mail,
        d=settings.mail.MAIL_TEMPLATE_FOLDER,
    )

    mail_client = providers.Singleton(
        FastAPIMailClient,
        settings=init_mail_settings,
    )

    email_options = providers.Factory(
            EmailDispatchOptions,
            dry_run=True,
            subject_prefix=None,
            redirect_all_to=[],
            always_bcc=[],
        )

    email_dispatcher = providers.Factory(
        EmailDispatcher,
        client=mail_client,
        settings=settings.mail,
        options=email_options,
    )

    qna_email_service = providers.Factory(
        QnAEmailService,
        dispatcher=email_dispatcher,
    )