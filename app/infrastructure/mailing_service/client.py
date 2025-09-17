from abc import abstractmethod
from typing import Any, Optional, Protocol

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType, MultipartSubtypeEnum

from app.core.config import MailSettings
from app.infrastructure.mailing_service.models import EmailEnvelope, OutgoingHtmlEmail, OutgoingTemplatedHTMLEmail, \
	OutgoingTemplatedTextEmail, OutgoingTextEmail


class IMailClient(Protocol):
	@abstractmethod
	async def send_html_email(self, message: OutgoingHtmlEmail) -> None: ...
	
	@abstractmethod
	async def send_text_email(self, message: OutgoingTextEmail) -> None: ...
	
	@abstractmethod
	async def send_templated_html_email(self, message: OutgoingTemplatedHTMLEmail) -> None: ...
	
	@abstractmethod
	async def send_templated_plain_email(self, message: OutgoingTemplatedTextEmail) -> None: ...
	
	@abstractmethod
	async def render_templates_for_preview(
			self,
			*,
			html_template: str,
			context: dict[str, Any] | None,
			plain_template: Optional[str] = None,
	) -> dict[str, Optional[str]]: ...
	
class FastAPIMailClient(IMailClient):
	
	def __init__(self, settings: MailSettings):
		self.conf = ConnectionConfig(
			MAIL_USERNAME=settings.MAIL_USERNAME,
			MAIL_PASSWORD=settings.MAIL_PASSWORD,
			MAIL_FROM=settings.MAIL_FROM,
			MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
			MAIL_PORT=settings.MAIL_PORT,
			MAIL_SERVER=settings.MAIL_SERVER,
			MAIL_STARTTLS=settings.MAIL_STARTTLS,
			MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
			USE_CREDENTIALS=settings.MAIL_USE_CREDENTIALS,
			VALIDATE_CERTS=settings.MAIL_VALIDATE_CERTS,
			SUPPRESS_SEND=int(settings.MAIL_SUPPRESS_SEND),
			MAIL_DEBUG=settings.MAIL_DEBUG,
			TEMPLATE_FOLDER=settings.MAIL_TEMPLATE_FOLDER
		)
		self._fm = FastMail(self.conf)
	
	@property
	def fm(self) -> FastMail:
		return self._fm
	
	def _generate_message_schema(self, envelope:EmailEnvelope, subtype:MessageType) -> MessageSchema:
		return MessageSchema(
			subject=envelope.subject,
			recipients=envelope.recipients,
			cc=envelope.cc,
			bcc=envelope.bcc,
			reply_to=envelope.reply_to,
			headers=envelope.headers,
			subtype=subtype
		)
	
	async def send_html_email(self, message: OutgoingHtmlEmail) -> None:
		message_schema = self._generate_message_schema(envelope=message, subtype=MessageType.html)
		message_schema.body = message.html_body
		
		if message.text_fallback:
			message_schema.alternative_body = message.text_fallback
			message_schema.multipart_subtype= MultipartSubtypeEnum.alternative
		
		await self._fm.send_message(message_schema)
	
	async def send_text_email(self, message: OutgoingTextEmail) -> None:
		
		message_schema = self._generate_message_schema(envelope=message, subtype=MessageType.plain)
		message_schema.body=message.text_body

		await self._fm.send_message(message_schema)
	
	async def _render_text_template(
			self, template_name: str, context: dict[str, Any] | None
	) -> str:
		"""
		Render a *plain-text* Jinja template using the same engine FastMail uses.
		Mirrors FastMail.__template_message_builder behavior for dict/list bodies.
		"""
		self._ensure_templates_enabled()
		
		env = self.conf.template_engine()
		tmpl = await self._fm.get_mail_template(env, template_name)  # returns a Jinja Template
		
		data = context or {}
		if isinstance(data, list):
			# FastMail wraps lists under "body" when rendering templates
			return tmpl.render({"body": data})
		# FastMail.validate expects a dict
		if not isinstance(data, dict):
			raise ValueError("template_body must be a dict (or list).")
		return tmpl.render(**data)
	
	def _ensure_templates_enabled(self) -> None:
		if not self.conf.TEMPLATE_FOLDER:
			raise RuntimeError("TEMPLATE_FOLDER is not configured; cannot render templates.")
	
	async def send_templated_html_email(self, message: OutgoingTemplatedHTMLEmail) -> None:
		self._ensure_templates_enabled()
		
		message_schema = self._generate_message_schema(envelope=message, subtype=MessageType.html)
		message_schema.template_body=message.template_context or {}
		
		if message.plain_template_fallback:
			text_fallback = await self._render_text_template(
				message.plain_template_fallback, message.template_context
			)
			
			message_schema.alternative_body=text_fallback
			message_schema.multipart_subtype=MultipartSubtypeEnum.alternative
		
		
		await self._fm.send_message(message_schema, template_name=message.html_template)
	
	async def send_templated_plain_email(self, message: OutgoingTemplatedTextEmail) -> None:
		self._ensure_templates_enabled()
		
		message_schema = self._generate_message_schema(envelope=message, subtype=MessageType.plain)
		
		text_body = await self._render_text_template(
			message.plain_template, message.template_context
		)
		
		message_schema.body=text_body
		
		await self._fm.send_message(message_schema)
	
	async def _render_html_template(
			self, template_name: str, context: dict[str, Any] | None
	) -> str:
		"""Render an HTML Jinja template using FastMail's configured environment."""
		self._ensure_templates_enabled()
		env = self.conf.template_engine()
		tmpl = await self._fm.get_mail_template(env, template_name)  # Jinja2 Template
		
		data = context or {}
		if isinstance(data, list):
			# Keep parity with FastMail behavior for list bodies
			return tmpl.render({"body": data})
		if not isinstance(data, dict):
			raise ValueError("template_body must be a dict (or list).")
		return tmpl.render(**data)
	
	async def render_templates_for_preview(
			self,
			*,
			html_template: str,
			context: dict[str, Any] | None,
			plain_template: Optional[str] = None,
	) -> dict[str, Optional[str]]:
		"""Render templates without sending — used by dry_run previews."""
		html = await self._render_html_template(html_template, context)
		text = None
		if plain_template:
			text = await self._render_text_template(plain_template, context)
		return {"html": html, "text": text}