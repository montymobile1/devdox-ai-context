import pytest
from pydantic_core import ValidationError

from app.infrastructure.mailing_service.models.base_models import (
    EmailEnvelope,
    OutgoingHtmlEmail,
    OutgoingTextEmail,
    OutgoingTemplatedContextEmail,
    OutgoingTemplatedHTMLEmail,
    OutgoingTemplatedTextEmail,
)
from app.infrastructure.mailing_service.models.base_preview_models import (
    PreviewEmailEnvelope,
    PreviewOutgoingHtmlEmail,
    PreviewOutgoingTextEmail,
    PreviewOutgoingTemplatedContextEmail,
    PreviewOutgoingTemplatedHTMLEmail,
    PreviewOutgoingTemplatedTextEmail,
)
from app.infrastructure.mailing_service.models.base_preview_router import make_preview


# -------------------------- Common builders --------------------------

@pytest.fixture
def base_headers():
    return {"X-ID": "123"}  # NonBlankStr-compatible (stripped, non-empty)

@pytest.fixture
def html_msg(base_headers):
    return OutgoingHtmlEmail(
        subject="HTML Subject",
        recipients=["to@example.com"],
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["reply@example.com"],
        headers=base_headers,
        html_body="<b>Hello</b>",
        text_fallback="Hello",
    )

@pytest.fixture
def text_msg(base_headers):
    return OutgoingTextEmail(
        subject="TEXT Subject",
        recipients=["to@example.com"],
        headers=base_headers,
        text_body="Hello",
    )

@pytest.fixture
def templ_html_msg(base_headers):
    return OutgoingTemplatedHTMLEmail(
        subject="TPL HTML Subject",
        recipients=["to@example.com"],
        headers=base_headers,
        html_template="welcome.html",
        plain_template_fallback="welcome.txt",
        template_context={"name": "Ada"},
    )

@pytest.fixture
def templ_text_msg(base_headers):
    return OutgoingTemplatedTextEmail(
        subject="TPL TEXT Subject",
        recipients=["to@example.com"],
        headers=base_headers,
        plain_template="notify.txt",
        template_context={"k": "v"},
    )

@pytest.fixture
def templ_ctx_msg(base_headers):
    return OutgoingTemplatedContextEmail(
        subject="CTX Subject",
        recipients=["to@example.com"],
        headers=base_headers,
        template_context={"x": 1},
    )

@pytest.fixture
def envelope_only(base_headers):
    return EmailEnvelope(
        subject="Bare Envelope",
        recipients=["a@example.com", "b@example.com"],
        headers=base_headers,
    )


# =========================== Tests ===========================

class TestMakePreviewConcreteTypes:
    def test_html_email_preview_type_and_fields(self, html_msg):
        # Act
        p = make_preview(
            html_msg,
            html_body_preview="RENDERED_HTML",
            text_fallback_preview="RENDERED_TEXT",
        )

        # Assert
        assert isinstance(p, PreviewOutgoingHtmlEmail)
        # model fields copied from source
        assert p.subject == html_msg.subject
        assert p.recipients == html_msg.recipients
        assert p.headers == html_msg.headers
        # preview fields set from kwargs
        assert p.html_body_preview == "RENDERED_HTML"
        assert p.text_fallback_preview == "RENDERED_TEXT"

    def test_text_email_preview_type_and_fields(self, text_msg):
        p = make_preview(text_msg, text_body_preview="RENDERED_TEXT")
        assert isinstance(p, PreviewOutgoingTextEmail)
        assert p.subject == text_msg.subject
        assert p.text_body_preview == "RENDERED_TEXT"

    def test_templated_html_email_preview_type_and_fields(self, templ_html_msg):
        p = make_preview(
            templ_html_msg,
            html_template_preview="<html>ok</html>",
            plain_template_fallback_preview="ok",
        )
        assert isinstance(p, PreviewOutgoingTemplatedHTMLEmail)
        assert p.html_template == "welcome.html"
        assert p.plain_template_fallback == "welcome.txt"
        assert p.html_template_preview == "<html>ok</html>"
        assert p.plain_template_fallback_preview == "ok"
        # context copied
        assert p.template_context == {"name": "Ada"}

    def test_templated_text_email_preview_type_and_fields(self, templ_text_msg):
        p = make_preview(templ_text_msg, plain_template_preview="RENDERED_TEXT")
        assert isinstance(p, PreviewOutgoingTemplatedTextEmail)
        assert p.plain_template == "notify.txt"
        assert p.plain_template_preview == "RENDERED_TEXT"
        assert p.template_context == {"k": "v"}


class TestMakePreviewGenericTypes:
    def test_templated_context_email_returns_context_preview(self, templ_ctx_msg):
        p = make_preview(templ_ctx_msg)
        assert isinstance(p, PreviewOutgoingTemplatedContextEmail)
        # Carries over base message fields & context
        assert p.subject == "CTX Subject"
        assert p.template_context == {"x": 1}

    def test_plain_envelope_returns_preview_envelope(self, envelope_only):
        p = make_preview(envelope_only)
        assert isinstance(p, PreviewEmailEnvelope)
        assert p.subject == "Bare Envelope"
        assert p.recipients == ["a@example.com", "b@example.com"]
        # No preview-only fields exist on this type
        assert not hasattr(p, "html_body_preview")
        assert not hasattr(p, "text_body_preview")


class TestPreviewImmutabilityAndKwargs:
    def test_preview_models_are_frozen_immutable(self, html_msg):
        p = make_preview(html_msg, html_body_preview="X")
        with pytest.raises(ValidationError):
            # All Preview* models are frozen (ConfigDict(frozen=True))
            p.html_body_preview = "Y"  # type: ignore[attr-defined]

    def test_extra_kwargs_are_ignored(self, text_msg):
        # make_preview only plumbs the expected preview keys for each type
        p = make_preview(text_msg, text_body_preview="T", unexpected="IGNORED")
        assert isinstance(p, PreviewOutgoingTextEmail)
        # ensure our unexpected kw is not present
        assert not hasattr(p, "unexpected")
        assert p.text_body_preview == "T"
