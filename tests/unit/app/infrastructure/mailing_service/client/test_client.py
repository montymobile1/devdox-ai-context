import asyncio
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.core.config import MailSettings
from app.infrastructure.mailing_service.client.client import FastAPIMailClient
from app.infrastructure.mailing_service.exception import exception_constants
from app.infrastructure.mailing_service.exception.mail_exceptions import (
    MailConfigError,
    MailSendError,
    MailTemplateError,
)
from app.infrastructure.mailing_service.models.base_models import (
    OutgoingHtmlEmail,
    OutgoingTemplatedHTMLEmail,
    OutgoingTemplatedTextEmail,
    OutgoingTextEmail,
)
from app.infrastructure.mailing_service.models.base_preview_models import (
    PreviewOutgoingHtmlEmail,
    PreviewOutgoingTemplatedHTMLEmail,
    PreviewOutgoingTemplatedTextEmail,
    PreviewOutgoingTextEmail,
)


# --------------------------- Local Fake FastMail ---------------------------

class _FakeFastMail:
    """
    Minimal fake that mimics the FastMail surface our client uses:
    - send_message(message, template_name=None)
    - get_mail_template(env, template_name) -> Jinja2 Template
    - record_messages() -> context manager collecting sends
    """
    def __init__(self, conf):
        self.conf = conf
        self.sent = []
        self._raise_on_send: Exception | None = None

    def set_send_exception(self, exc: Exception | None):
        self._raise_on_send = exc

    async def send_message(self, message, template_name=None):
        if self._raise_on_send:
            raise self._raise_on_send
        # capture the exact object for assertions (MessageSchema instance)
        self.sent.append({"message": message, "template_name": template_name})

    async def get_mail_template(self, env, template_name):
        # Let Jinja resolve from the configured loader in ConnectionConfig.template_engine()
        return env.get_template(template_name)

    @contextmanager
    def record_messages(self):
        # Provide a list-like outbox similar to FastMail's helper
        outbox = self.sent
        try:
            yield outbox
        finally:
            # do not clear by default; tests can inspect after
            pass


# --------------------------- Common fixtures/builders ---------------------------

@pytest.fixture
def template_tree(tmp_path: Path):
    """
    Creates a valid template tree:
      <tmp>/parent/email/{greet.html, greet.txt}
    """
    parent = tmp_path / "parent"
    email_dir = parent / "email"
    email_dir.mkdir(parents=True, exist_ok=True)

    (email_dir / "greet.html").write_text("Hello {{ name }}!", encoding="utf-8")
    (email_dir / "greet.txt").write_text("Hi {{ name }}", encoding="utf-8")
    return parent


def _mk_settings_with_templates(parent: Path, suppress_send: bool = True) -> MailSettings:
    return MailSettings(
        MAIL_USERNAME="user",
        MAIL_PASSWORD="pwd",
        MAIL_FROM="noreply@example.com",
        MAIL_FROM_NAME="DevDox",
        MAIL_PORT=587,
        MAIL_SERVER="smtp.example.com",
        MAIL_STARTTLS=True,
        MAIL_SSL_TLS=False,
        MAIL_USE_CREDENTIALS=True,
        MAIL_VALIDATE_CERTS=True,
        MAIL_SUPPRESS_SEND=suppress_send,
        MAIL_DEBUG=0,
        MAIL_SEND_TIMEOUT=60,
        MAIL_TEMPLATES_PARENT_DIR=parent,
    )


def _mk_settings_without_templates(suppress_send: bool = True) -> MailSettings:
    # Disable templates by setting None/“none”
    return MailSettings(
        MAIL_USERNAME="user",
        MAIL_PASSWORD="pwd",
        MAIL_FROM="noreply@example.com",
        MAIL_FROM_NAME="DevDox",
        MAIL_PORT=587,
        MAIL_SERVER="smtp.example.com",
        MAIL_STARTTLS=True,
        MAIL_SSL_TLS=False,
        MAIL_USE_CREDENTIALS=True,
        MAIL_VALIDATE_CERTS=True,
        MAIL_SUPPRESS_SEND=suppress_send,
        MAIL_DEBUG=0,
        MAIL_SEND_TIMEOUT=60,
        MAIL_TEMPLATES_PARENT_DIR=None,
    )


def _html_msg():
    return OutgoingHtmlEmail(
        subject="HTML Subj",
        recipients=["to@example.com"],
        html_body="<b>Hello</b>",
        text_fallback="Hello",
    )


def _text_msg():
    return OutgoingTextEmail(
        subject="TEXT Subj",
        recipients=["to@example.com"],
        text_body="Hello",
    )


def _tpl_html_msg():
    return OutgoingTemplatedHTMLEmail(
        subject="TPL HTML Subj",
        recipients=["to@example.com"],
        html_template="greet.html",
        plain_template_fallback="greet.txt",
        template_context={"name": "Ada"},
    )


def _tpl_text_msg():
    return OutgoingTemplatedTextEmail(
        subject="TPL TXT Subj",
        recipients=["to@example.com"],
        plain_template="greet.txt",
        template_context={"name": "Alan"},
    )


# ============================ Tests ============================

class TestInitAndConfig:
    def test_connection_config_is_wired_from_settings(self, template_tree):
        settings = _mk_settings_with_templates(template_tree, suppress_send=True)
        client = FastAPIMailClient(settings, dry_run=True)

        assert client.conf.MAIL_USERNAME == "user"
        assert client.conf.MAIL_SERVER == "smtp.example.com"
        # SUPPRESS_SEND should be int(...) as in the code
        assert client.conf.SUPPRESS_SEND == int(True)
        # Template folder should be <parent>/email
        assert client.conf.TEMPLATE_FOLDER == settings.templates_dir
        assert client.is_templates_enabled is True
        assert client.send_timeout_seconds == 60
        assert client.minimum_timeout_seconds == settings.MAIL_SEND_TIMEOUT_MIN

    def test_templates_disabled_flag(self):
        settings = _mk_settings_without_templates()
        client = FastAPIMailClient(settings, dry_run=True)
        assert client.is_templates_enabled is False
        assert client.conf.TEMPLATE_FOLDER is None


@pytest.mark.asyncio
class TestDryRunSends:
    @pytest.fixture
    def client(self, template_tree):
        settings = _mk_settings_with_templates(template_tree)
        return FastAPIMailClient(settings, dry_run=True)

    async def test_send_html_email_dry(self, client):
        out = await client.send_html_email(_html_msg())
        assert isinstance(out, PreviewOutgoingHtmlEmail)
        assert out.html_body_preview == "<b>Hello</b>"
        assert out.text_fallback_preview == "Hello"

    async def test_send_text_email_dry(self, client):
        out = await client.send_text_email(_text_msg())
        assert isinstance(out, PreviewOutgoingTextEmail)
        assert out.text_body_preview == "Hello"

    async def test_send_templated_html_email_dry(self, client):
        out = await client.send_templated_html_email(_tpl_html_msg())
        assert isinstance(out, PreviewOutgoingTemplatedHTMLEmail)
        assert out.html_template_preview == "Hello Ada!"
        assert out.plain_template_fallback_preview == "Hi Ada"

    async def test_send_templated_plain_email_dry(self, client):
        out = await client.send_templated_plain_email(_tpl_text_msg())
        assert isinstance(out, PreviewOutgoingTemplatedTextEmail)
        assert out.plain_template_preview == "Hi Alan"


@pytest.mark.asyncio
class TestTemplateGuardsAndErrors:
    async def test_templates_disabled_raises(self):
        settings = _mk_settings_without_templates()
        client = FastAPIMailClient(settings, dry_run=True)
        with pytest.raises(MailConfigError, match=exception_constants.TEMPLATE_FOLDER_NOT_CONFIGURED):
            await client.send_templated_html_email(_tpl_html_msg())

        with pytest.raises(MailConfigError, match=exception_constants.TEMPLATE_FOLDER_NOT_CONFIGURED):
            await client.send_templated_plain_email(_tpl_text_msg())

    async def test_template_not_found_maps_to_mailtemplateerror(self, template_tree):
        settings = _mk_settings_with_templates(template_tree)
        client = FastAPIMailClient(settings, dry_run=True)

        bad = OutgoingTemplatedHTMLEmail(
            subject="x",
            recipients=["a@b.com"],
            html_template="nope.html",                  # not present
            plain_template_fallback=None,
            template_context={"name": "X"},
        )
        with pytest.raises(MailTemplateError, match="Template not found: nope.html"):
            await client.send_templated_html_email(bad)
    
    async def test_template_render_failure_is_wrapped(self, template_tree, monkeypatch):
        settings = _mk_settings_with_templates(template_tree)
        client = FastAPIMailClient(settings, dry_run=True)
        
        # Build a valid message (the model must stay valid under Pydantic v2)
        msg = OutgoingTemplatedTextEmail(
            subject="x",
            recipients=["a@b.com"],
            plain_template="greet.txt",
            template_context={"name": "Ada"},  # valid dict
        )
        
        # Monkeypatch get_mail_template to return a template whose render() raises
        class _BoomTemplate:
            def render(self, *args, **kwargs):
                raise RuntimeError("boom")  # any non-syntax exception
        
        async def _fake_get_mail_template(env, template_name):
            return _BoomTemplate()
        
        monkeypatch.setattr(client.fm, "get_mail_template", _fake_get_mail_template)
        
        with pytest.raises(MailTemplateError, match=exception_constants.TEMPLATE_RENDER_FAILED.format(template_name="greet.txt")):
            await client.send_templated_plain_email(msg)


@pytest.mark.asyncio
class TestLiveSendsViaFakeFastMail:
    """
    Exercise the "real send" code path (_send_fast_mail) using an in-memory fake FastMail.
    SUPPRESS_SEND is True so no network is touched. We assert that:
      - MessageSchema fields are populated
      - alternative body + multipart subtype are set when fallback exists
      - send_message() is awaited
    """

    @pytest.fixture
    def client(self, template_tree, monkeypatch):
        settings = _mk_settings_with_templates(template_tree)
        client = FastAPIMailClient(settings, dry_run=False)

        # Swap the real FastMail with a fake one
        fake = _FakeFastMail(client.conf)
        # Attach fake to client
        client._fm = fake  # type: ignore[attr-defined]
        return client

    async def test_send_html_email_live_records_and_sets_alternative(self, client: FastAPIMailClient):
        fake: _FakeFastMail = client.fm  # type: ignore[assignment]
        msg = _html_msg()

        with fake.record_messages() as outbox:
            await client.send_html_email(msg)

        assert len(outbox) == 1
        payload = outbox[0]["message"]
        assert payload.subject == "HTML Subj"
        assert payload.recipients == ["to@example.com"]
        # alternative set because text_fallback present
        assert payload.alternative_body == "Hello"

    async def test_send_text_email_live_records(self, client: FastAPIMailClient):
        fake: _FakeFastMail = client.fm  # type: ignore[assignment]
        with fake.record_messages() as outbox:
            await client.send_text_email(_text_msg())

        assert len(outbox) == 1
        payload = outbox[0]["message"]
        assert payload.body == "Hello"
        assert payload.subtype.name.lower() == "plain"

    async def test_send_templated_html_email_live_with_text_fallback(self, client: FastAPIMailClient):
        fake: _FakeFastMail = client.fm  # type: ignore[assignment]
        with fake.record_messages() as outbox:
            await client.send_templated_html_email(_tpl_html_msg())

        assert len(outbox) == 1
        payload = outbox[0]["message"]
        # template name passed through to the fake
        assert outbox[0]["template_name"] == "greet.html"
        # alternative from rendered fallback (client renders before sending)
        assert payload.alternative_body == "Hi Ada"

    async def test_send_templated_plain_email_live(self, client: FastAPIMailClient):
        fake: _FakeFastMail = client.fm  # type: ignore[assignment]
        with fake.record_messages() as outbox:
            await client.send_templated_plain_email(_tpl_text_msg())

        assert len(outbox) == 1
        payload = outbox[0]["message"]
        assert payload.body == "Hi Alan"
        assert payload.subtype.name.lower() == "plain"


@pytest.mark.asyncio
class TestTimeoutsAndFailures:
    @pytest.fixture
    def client(self, template_tree):
        settings = _mk_settings_with_templates(template_tree)
        c = FastAPIMailClient(settings, dry_run=False)
        # Use a fake FastMail under the hood
        c._fm = _FakeFastMail(c.conf)  # type: ignore[attr-defined]
        return c

    async def test_timeout_raises_mailsenderror_with_effective_timeout_in_message(self, client, monkeypatch):
        # Force asyncio.wait_for to raise TimeoutError regardless of timeout value
        async def _boom(*args, **kwargs):
            raise asyncio.TimeoutError

        monkeypatch.setattr(asyncio, "wait_for", _boom)

        with pytest.raises(MailSendError) as exc:
            await client.send_text_email(_text_msg(), timeout=1)  # whatever value

        assert "SMTP send timed out" in str(exc.value)
        # server:port included
        assert "smtp.example.com:587" in str(exc.value)

    async def test_generic_send_failure_is_wrapped_with_context(self, client):
        fake: _FakeFastMail = client.fm  # type: ignore[assignment]
        fake.set_send_exception(RuntimeError("SMTP down"))

        with pytest.raises(MailSendError) as exc:
            await client.send_html_email(_html_msg())

        msg = str(exc.value)
        assert "SMTP send failed" in msg
        assert "subject='HTML Subj'" in msg
        assert "server='smtp.example.com:587'" in msg
