from dependency_injector import containers, providers

from app.core.config import settings
from app.infrastructure.mailing_service import EmailDispatcher, EmailDispatchOptions, FastAPIMailClient


class MailStackContainer(containers.DeclarativeContainer):
	"""Dependency injection container"""
	
	config = providers.Configuration()
	
	fast_mail_client = providers.Singleton(
		FastAPIMailClient,
		settings=settings.mail,
		dry_run=False
	)
	
	email_options = providers.Singleton(
		EmailDispatchOptions,
		subject_prefix=None,
		redirect_all_to=[],
		always_bcc=[],
	)
	
	email_dispatcher = providers.Singleton(
		EmailDispatcher,
		client=fast_mail_client,
		options=email_options,
	)


email_dispatcher_container = MailStackContainer()

def get_email_dispatcher() -> EmailDispatcher:
	# resolves on every call, so test overrides still work
	return email_dispatcher_container.email_dispatcher()