import pytest
import pytest_asyncio
from pydantic import EmailStr

from app.core.config import MailSettings
from app.services.email_service import (
    EmailDispatchOptions,
    EmailDispatcher,
    QnAEmailService,
)
from app.infrastructure.mailing_service.models import OutgoingTemplatedHTMLEmail
from app.infrastructure.qna.qna_models import ProjectQnAPackage
from app.infrastructure.qna.qna_models import QAPair
from test_doubles.mailing_service import FakeMailClient, StubMailClient


# ---------- Fixtures ----------

@pytest.fixture
def mail_settings(tmp_path):
    return MailSettings(
        MAIL_USERNAME="u",
        MAIL_PASSWORD="p",
        MAIL_FROM="a@b.com",
        MAIL_SERVER="smtp.example.com",
        MAIL_TEMPLATE_FOLDER=tmp_path,
    )

@pytest_asyncio.fixture
async def fake_client():
    return FakeMailClient()

@pytest_asyncio.fixture
async def stub_client():
    return StubMailClient()


# ---------- EmailDispatcher Tests ----------

class TestEmailDispatcherDryRun:
    @pytest.mark.asyncio
    async def test_given_dry_run_when_preview_success_then_returns_rendered(self, fake_client, mail_settings):
        dispatcher = EmailDispatcher(
            client=fake_client,
            settings=mail_settings,
            options=EmailDispatchOptions(dry_run=True),
        )
        result = await dispatcher.send_templated_html(
            subject="Report",
            to=["to@example.com"],
            template="main.html",
            context={"foo": "bar"},
        )

        assert result["subject"].startswith("[DevDox] Report")
        assert result["to"] == ["to@example.com"]
        assert "fake-render main.html" in result["html_preview"]
        assert result["text_preview"] is None
        assert result["render_error"] is None

    @pytest.mark.asyncio
    async def test_given_dry_run_when_render_raises_then_render_error_included(self, stub_client, mail_settings):
        stub_client.set_exception("render_templates_for_preview", RuntimeError("fail"))
        dispatcher = EmailDispatcher(
            client=stub_client,
            settings=mail_settings,
            options=EmailDispatchOptions(dry_run=True),
        )

        result = await dispatcher.send_templated_html(
            subject="Oops",
            to=["x@example.com"],
            template="bad.html",
            context={"a": 1},
        )

        assert result["render_error"].startswith("RuntimeError: fail")


class TestEmailDispatcherRecipients:
    def test_given_redirect_all_to_when_rewrite_recipients_then_all_go_to_redirect(self, fake_client, mail_settings):
        dispatcher = EmailDispatcher(
            client=fake_client,
            settings=mail_settings,
            options=EmailDispatchOptions(redirect_all_to=["dev@safe.com"]),
        )
        rs = dispatcher._rewrite_recipients(
            to=["a@b.com"], cc=["c@d.com"], bcc=["e@f.com"]
        )
        assert rs.to == ["dev@safe.com"]
        assert rs.cc == []
        assert "dev@safe.com" not in rs.bcc  # only always_bcc would add

    def test_given_always_bcc_when_rewrite_recipients_then_bcc_contains_merge(self, fake_client, mail_settings):
        dispatcher = EmailDispatcher(
            client=fake_client,
            settings=mail_settings,
            options=EmailDispatchOptions(always_bcc=["audit@corp.com"]),
        )
        rs = dispatcher._rewrite_recipients(
            to=["a@b.com"], cc=[], bcc=["b@c.com"]
        )
        assert "audit@corp.com" in rs.bcc
        assert "b@c.com" in rs.bcc

    def test_given_subject_prefix_disabled_when_prefix_subject_then_returns_as_is(self, fake_client, mail_settings):
        dispatcher = EmailDispatcher(
            client=fake_client,
            settings=mail_settings,
            options=EmailDispatchOptions(subject_prefix=None),
        )
        assert dispatcher._prefix_subject("Hello") == "Hello"

    def test_given_subject_already_prefixed_when_prefix_subject_then_no_duplicate(self, fake_client, mail_settings):
        dispatcher = EmailDispatcher(fake_client, mail_settings)
        result = dispatcher._prefix_subject("[DevDox] Hello")
        assert result == "[DevDox] Hello"


class TestEmailDispatcherSend:
    @pytest.mark.asyncio
    async def test_given_not_dry_run_when_send_then_client_invoked(self, stub_client, mail_settings):
        dispatcher = EmailDispatcher(
            client=stub_client,
            settings=mail_settings,
            options=EmailDispatchOptions(dry_run=False),
        )
        stub_client.set_response("send_templated_html_email", None)

        result = await dispatcher.send_templated_html(
            subject="Real",
            to=["to@example.com"],
            template="main.html",
            context={"foo": "bar"},
        )

        assert result is None
        method, args, kwargs = stub_client.calls[0]
        assert method == "send_templated_html_email"
        assert isinstance(args[0], OutgoingTemplatedHTMLEmail)


# ---------- QnAEmailService Tests ----------

@pytest.fixture
def qna_pkg():
    from datetime import datetime, timezone
    return ProjectQnAPackage(
        project_name="ProjX",
        repo_url="http://repo",
        repo_id="123",
        pairs=[
            QAPair(
                id="1",
                question="What is it?",
                answer="Answer text",
                confidence=0.9,
                insufficient_evidence=False,
                evidence_snippets=["Snippet1"],
            )
        ],
        generated_at=datetime.now(timezone.utc),
        model="gpt",
        prompt_version="v1",
    )


class TestQnAEmailService:
    @pytest.mark.asyncio
    async def test_given_pkg_when_send_summary_in_dry_run_then_returns_preview(self, fake_client, mail_settings, qna_pkg):
        dispatcher = EmailDispatcher(fake_client, mail_settings, options=EmailDispatchOptions(dry_run=True))
        svc = QnAEmailService(dispatcher)

        result = await svc.send_qna_summary(pkg=qna_pkg, to=["user@x.com"])

        assert "[DevDox]" in result["subject"]
        assert result["to"] == ["user@x.com"]
        assert result["template"] == "project_qna.html"
        assert result["text_fallback_template"] == "project_qna.txt"
        assert "ProjX" in result["html_preview"] or result["html_preview"] is not None

    @pytest.mark.asyncio
    async def test_given_explicit_subject_when_send_summary_then_prefix_applied(self, fake_client, mail_settings, qna_pkg):
        dispatcher = EmailDispatcher(fake_client, mail_settings, options=EmailDispatchOptions(dry_run=True))
        svc = QnAEmailService(dispatcher)

        result = await svc.send_qna_summary(
            pkg=qna_pkg,
            to=["u@x.com"],
            subject="Custom",
        )

        assert result["subject"].startswith("[DevDox] Custom")
