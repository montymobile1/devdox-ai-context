import asyncio
from typing import Any, Dict, List, Optional

from app.infrastructure.mailing_service.client import IMailClient
from app.infrastructure.mailing_service.models import (
    OutgoingHtmlEmail,
    OutgoingTextEmail,
    OutgoingTemplatedHTMLEmail,
    OutgoingTemplatedTextEmail,
)


class FakeMailClient(IMailClient):
    """A fake mail client that stores all sent emails in memory."""

    def __init__(self):
        self.sent_html: List[OutgoingHtmlEmail] = []
        self.sent_text: List[OutgoingTextEmail] = []
        self.sent_templated_html: List[OutgoingTemplatedHTMLEmail] = []
        self.sent_templated_text: List[OutgoingTemplatedTextEmail] = []
        self.previews: List[Dict[str, Optional[str]]] = []

    async def send_html_email(self, message: OutgoingHtmlEmail) -> None:
        self.sent_html.append(message)

    async def send_text_email(self, message: OutgoingTextEmail) -> None:
        self.sent_text.append(message)

    async def send_templated_html_email(self, message: OutgoingTemplatedHTMLEmail) -> None:
        self.sent_templated_html.append(message)

    async def send_templated_plain_email(self, message: OutgoingTemplatedTextEmail) -> None:
        self.sent_templated_text.append(message)

    async def render_templates_for_preview(
        self, html_template: str, context: dict[str, Any] | None, plain_template: Optional[str] = None
    ) -> dict[str, Optional[str]]:
        preview = {
            "html": f"<html>fake-render {html_template} ctx={context}</html>",
            "text": f"fake-render {plain_template} ctx={context}" if plain_template else None,
        }
        self.previews.append(preview)
        return preview


class StubMailClient(IMailClient):
    """A stub mail client with configurable return values or exceptions."""

    def __init__(self):
        self._responses: Dict[str, Any] = {}
        self._exceptions: Dict[str, Exception] = {}
        self.calls: List[tuple[str, tuple, dict]] = []

    def set_response(self, method_name: str, value: Any):
        self._responses[method_name] = value

    def set_exception(self, method_name: str, exc: Exception):
        self._exceptions[method_name] = exc

    async def _maybe(self, method_name: str, *args, **kwargs):
        self.calls.append((method_name, args, kwargs))
        if exc := self._exceptions.get(method_name):
            raise exc
        value = self._responses.get(method_name)
        if asyncio.iscoroutinefunction(value):
            return await value(*args, **kwargs)
        if callable(value):
            return value(*args, **kwargs)
        return value

    async def send_html_email(self, message: OutgoingHtmlEmail) -> None:
        return await self._maybe("send_html_email", message)

    async def send_text_email(self, message: OutgoingTextEmail) -> None:
        return await self._maybe("send_text_email", message)

    async def send_templated_html_email(self, message: OutgoingTemplatedHTMLEmail) -> None:
        return await self._maybe("send_templated_html_email", message)

    async def send_templated_plain_email(self, message: OutgoingTemplatedTextEmail) -> None:
        return await self._maybe("send_templated_plain_email", message)

    async def render_templates_for_preview(
        self, html_template: str, context: dict[str, Any] | None, plain_template: Optional[str] = None
    ) -> dict[str, Optional[str]]:
        return await self._maybe("render_templates_for_preview", html_template, context, plain_template)
