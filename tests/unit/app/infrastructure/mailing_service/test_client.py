# tests/unit/test_mailing_client.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from fastapi_mail import MessageType

from app.core.config import MailSettings
from app.infrastructure.mailing_service.client import FastAPIMailClient
from app.infrastructure.mailing_service.models import (
    OutgoingHtmlEmail,
    OutgoingTextEmail,
    OutgoingTemplatedHTMLEmail,
    OutgoingTemplatedTextEmail,
)

# ---------- Fixtures ----------

@pytest.fixture
def mail_settings(tmp_path):
    """Provide fake but valid mail settings with a temp template folder."""
    return MailSettings(
        MAIL_USERNAME="fakeuser",
        MAIL_PASSWORD="fakepass",
        MAIL_FROM="sender@example.com",
        MAIL_FROM_NAME="Sender",
        MAIL_PORT=587,
        MAIL_SERVER="smtp.example.com",
        MAIL_STARTTLS=True,
        MAIL_SSL_TLS=False,
        MAIL_USE_CREDENTIALS=True,
        MAIL_VALIDATE_CERTS=True,
        MAIL_SUPPRESS_SEND=True,  # ensures nothing is actually sent
        MAIL_DEBUG=0,
        MAIL_TEMPLATE_FOLDER=tmp_path,  # point to temp dir
    )

@pytest.fixture
def mail_settings_2(tmp_path):
    return MailSettings(
        MAIL_USERNAME="u",
        MAIL_PASSWORD="p",
        MAIL_FROM="a@b.com",
        MAIL_SERVER="smtp.example.com",
        MAIL_TEMPLATE_FOLDER=tmp_path,
    )

@pytest_asyncio.fixture
async def client(mail_settings):
    """System under test with FastMail replaced by a spy."""
    sut = FastAPIMailClient(mail_settings)
    sut._fm = AsyncMock()  # Spy on send_message & template rendering
    sut._fm.get_mail_template = AsyncMock(side_effect=lambda env, name: MagicMock(render=lambda **ctx: f"rendered-{name}-{ctx}"))
    return sut


# ---------- Tests ----------

class TestSendHtmlEmail:
    @pytest.mark.asyncio
    async def test_given_html_email_when_send_then_message_contains_html_and_optional_text(self, client):
        msg = OutgoingHtmlEmail(
            subject="Hello",
            recipients=["to@example.com"],
            html_body="<h1>Hi</h1>",
            text_fallback="Plain",
        )

        await client.send_html_email(msg)

        client._fm.send_message.assert_awaited_once()
        sent = client._fm.send_message.call_args[0][0]
        assert sent.subject == "Hello"
        assert sent.body == "<h1>Hi</h1>"
        assert sent.alternative_body == "Plain"
        assert sent.multipart_subtype.value == "alternative"

    @pytest.mark.asyncio
    async def test_given_html_email_without_fallback_when_send_then_only_html_is_sent(self, client):
        msg = OutgoingHtmlEmail(
            subject="Hi",
            recipients=["to@example.com"],
            html_body="<p>Only HTML</p>",
        )

        await client.send_html_email(msg)

        sent = client._fm.send_message.call_args[0][0]
        assert sent.alternative_body is None


class TestSendTextEmail:
    @pytest.mark.asyncio
    async def test_given_text_email_when_send_then_plain_body_is_used(self, client):
        msg = OutgoingTextEmail(
            subject="Text only",
            recipients=["to@example.com"],
            text_body="Plain content",
        )

        await client.send_text_email(msg)

        sent = client._fm.send_message.call_args[0][0]
        assert sent.body == "Plain content"


class TestSendTemplatedHtmlEmail:
    @pytest.mark.asyncio
    async def test_given_template_with_plain_fallback_when_send_then_both_bodies_are_rendered(self, client):
        msg = OutgoingTemplatedHTMLEmail(
            subject="Templated",
            recipients=["x@example.com"],
            html_template="main.html",
            plain_template_fallback="plain.txt",
            template_context={"user": "Ada"},
        )
        
        await client.send_templated_html_email(msg)
        
        client._fm.send_message.assert_awaited_once()
        args, kwargs = client._fm.send_message.call_args
        
        # Unpack correctly
        sent = args[0]  # the MessageSchema
        template_name = kwargs["template_name"]
        
        assert template_name == "main.html"
        assert sent.template_body == {"user": "Ada"}
        assert "rendered-plain.txt" in sent.alternative_body
        assert sent.multipart_subtype.value == "alternative"

    @pytest.mark.asyncio
    async def test_given_missing_template_folder_when_send_then_runtime_error_is_raised(self, mail_settings):
        mail_settings.MAIL_TEMPLATE_FOLDER = None
        client = FastAPIMailClient(mail_settings)

        with pytest.raises(RuntimeError):
            await client.send_templated_html_email(
                OutgoingTemplatedHTMLEmail(
                    subject="Fail",
                    recipients=["y@example.com"],
                    html_template="missing.html",
                )
            )


class TestSendTemplatedTextEmail:
    @pytest.mark.asyncio
    async def test_given_plain_template_when_send_then_body_is_rendered(self, client):
        msg = OutgoingTemplatedTextEmail(
            subject="Plain template",
            recipients=["z@example.com"],
            plain_template="plain.txt",
            template_context={"foo": "bar"},
        )

        await client.send_templated_plain_email(msg)

        sent = client._fm.send_message.call_args[0][0]
        assert "rendered-plain.txt" in sent.body


class TestPreviewRendering:
    @pytest.mark.asyncio
    async def test_given_html_and_plain_templates_when_preview_then_both_rendered(self, client):
        result = await client.render_templates_for_preview(
            html_template="main.html",
            plain_template="plain.txt",
            context={"name": "Bob"},
        )
        assert "rendered-main.html" in result["html"]
        assert "rendered-plain.txt" in result["text"]

    @pytest.mark.asyncio
    async def test_given_only_html_template_when_preview_then_only_html_rendered(self, client):
        result = await client.render_templates_for_preview(
            html_template="only.html",
            context={"key": "val"},
        )
        assert "rendered-only.html" in result["html"]
        assert result["text"] is None


class TestRenderTemplates:
    @pytest.mark.asyncio
    async def test_given_list_context_when_render_text_then_wraps_body(self, client):
        client._fm.get_mail_template = AsyncMock(
            side_effect=lambda env, name: MagicMock(render=lambda body=None: f"wrapped-{body}")
        )
        result = await client._render_text_template("plain.txt", ["a", "b"])
        assert result == "wrapped-{'body': ['a', 'b']}"

    @pytest.mark.asyncio
    async def test_given_non_dict_or_list_context_when_render_text_then_raise_value_error(self, client):
        with pytest.raises(ValueError):
            await client._render_text_template("plain.txt", "bad-type")

    @pytest.mark.asyncio
    async def test_given_non_dict_or_list_context_when_render_html_then_raise_value_error(self, client):
        with pytest.raises(ValueError):
            await client._render_html_template("main.html", 123)

class TestPrivateHelpers:
    @pytest.mark.asyncio
    async def test_given_missing_template_folder_when_render_text_then_raises(self, mail_settings):
        mail_settings.MAIL_TEMPLATE_FOLDER = None
        client = FastAPIMailClient(mail_settings)
        with pytest.raises(RuntimeError):
            await client._render_text_template("plain.txt", {"a": 1})

    @pytest.mark.asyncio
    async def test_given_html_email_without_fallback_when_send_then_multipart_subtype_is_not_set(self, client):
        msg = OutgoingTemplatedTextEmail(
            subject="No subtype",
            recipients=["a@b.com"],
            plain_template="plain.txt",
        )
        # patch template renderer to return a string
        client._fm.get_mail_template = AsyncMock(
            side_effect=lambda env, name: MagicMock(render=lambda **ctx: "plain-body")
        )
        await client.send_templated_plain_email(msg)
        sent = client._fm.send_message.call_args[0][0]
        assert sent.subtype.name is MessageType.plain.name