import pytest
import pytest_asyncio

from app.infrastructure.mailing_service.models import (
    OutgoingHtmlEmail,
    OutgoingTextEmail,
    OutgoingTemplatedHTMLEmail,
    OutgoingTemplatedTextEmail,
)
from test_doubles.mailing_service import FakeMailClient, StubMailClient


# ---------- Fixtures ----------

@pytest_asyncio.fixture
async def fake_client():
    return FakeMailClient()

@pytest_asyncio.fixture
async def stub_client():
    return StubMailClient()


# ---------- FakeMailClient Tests ----------

class TestFakeMailClient:
    @pytest.mark.asyncio
    async def test_given_html_email_when_send_then_stored_in_sent_html(self, fake_client):
        msg = OutgoingHtmlEmail(
            subject="sub",
            recipients=["to@example.com"],
            html_body="<h1>Hello</h1>",
            text_fallback="Plain",
        )
        await fake_client.send_html_email(msg)

        assert fake_client.sent_html == [msg]

    @pytest.mark.asyncio
    async def test_given_text_email_when_send_then_stored_in_sent_text(self, fake_client):
        msg = OutgoingTextEmail(
            subject="sub",
            recipients=["to@example.com"],
            text_body="Plain text",
        )
        await fake_client.send_text_email(msg)

        assert fake_client.sent_text == [msg]

    @pytest.mark.asyncio
    async def test_given_templated_html_when_send_then_stored(self, fake_client):
        msg = OutgoingTemplatedHTMLEmail(
            subject="sub",
            recipients=["to@example.com"],
            html_template="main.html",
            plain_template_fallback="plain.txt",
            template_context={"user": "Alice"},
        )
        await fake_client.send_templated_html_email(msg)

        assert fake_client.sent_templated_html == [msg]

    @pytest.mark.asyncio
    async def test_given_templated_text_when_send_then_stored(self, fake_client):
        msg = OutgoingTemplatedTextEmail(
            subject="sub",
            recipients=["to@example.com"],
            plain_template="plain.txt",
            template_context={"foo": "bar"},
        )
        await fake_client.send_templated_plain_email(msg)

        assert fake_client.sent_templated_text == [msg]

    @pytest.mark.asyncio
    async def test_given_preview_request_when_render_then_fake_html_and_text_returned(self, fake_client):
        result = await fake_client.render_templates_for_preview(
            html_template="main.html",
            plain_template="plain.txt",
            context={"k": "v"},
        )

        assert "fake-render main.html" in result["html"]
        assert "fake-render plain.txt" in result["text"]
        assert result in fake_client.previews


# ---------- StubMailClient Tests ----------

class TestStubMailClient:
    @pytest.mark.asyncio
    async def test_given_stubbed_response_when_called_then_returns_value(self, stub_client):
        msg = OutgoingTextEmail(
            subject="sub",
            recipients=["to@example.com"],
            text_body="plain",
        )
        stub_client.set_response("send_text_email", "OK")

        result = await stub_client.send_text_email(msg)
        assert result == "OK"

    @pytest.mark.asyncio
    async def test_given_stubbed_callable_response_when_called_then_executes_callable(self, stub_client):
        msg = OutgoingHtmlEmail(
            subject="sub",
            recipients=["to@example.com"],
            html_body="<h1></h1>",
        )
        stub_client.set_response("send_html_email", lambda m: f"processed-{m.subject}")

        result = await stub_client.send_html_email(msg)
        assert result == "processed-sub"

    @pytest.mark.asyncio
    async def test_given_stubbed_exception_when_called_then_raises(self, stub_client):
        msg = OutgoingTextEmail(
            subject="sub",
            recipients=["to@example.com"],
            text_body="plain",
        )
        stub_client.set_exception("send_text_email", RuntimeError("fail"))

        with pytest.raises(RuntimeError, match="fail"):
            await stub_client.send_text_email(msg)

    @pytest.mark.asyncio
    async def test_given_any_call_when_invoked_then_recorded_in_calls(self, stub_client):
        msg = OutgoingTemplatedTextEmail(
            subject="sub",
            recipients=["to@example.com"],
            plain_template="plain.txt",
        )
        stub_client.set_response("send_templated_plain_email", None)

        await stub_client.send_templated_plain_email(msg)

        assert stub_client.calls[0][0] == "send_templated_plain_email"
        assert isinstance(stub_client.calls[0][1][0], OutgoingTemplatedTextEmail)

    @pytest.mark.asyncio
    async def test_given_stubbed_preview_when_called_then_returns_value(self, stub_client):
        stub_client.set_response(
            "render_templates_for_preview",
            {"html": "<h1>fake</h1>", "text": "plain"},
        )

        result = await stub_client.render_templates_for_preview(
            html_template="main.html", context={"a": 1}, plain_template="plain.txt"
        )

        assert result["html"] == "<h1>fake</h1>"
        assert result["text"] == "plain"
