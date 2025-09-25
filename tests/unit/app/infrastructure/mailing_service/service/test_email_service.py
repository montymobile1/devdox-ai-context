import pytest

from app.infrastructure.mailing_service.service.email_service import (
    EmailDispatcher,
    EmailDispatchOptions,
)
from app.infrastructure.mailing_service.service.template_resolver import Template
from app.infrastructure.mailing_service.models.context_shapes import (
    ProjectAnalysisFailure,
)
from app.infrastructure.mailing_service.models.base_preview_models import (
    PreviewOutgoingTemplatedHTMLEmail,
)
from app.infrastructure.mailing_service.test_doubles.client import SpyMailClient


# -------------------- minimal fake IMailClient the spy will wrap --------------------

class _FakeIMailClient:
    """
    Minimal in-memory IMailClient implementation:
    - captures templated HTML messages
    - returns a PreviewOutgoingTemplatedHTMLEmail
    """
    def __init__(self, return_none=False):
        self.return_none = return_none
        self.seen_tpl_html = []
        self.timeouts = []

    async def send_templated_html_email(self, message, timeout: int | None = None):
        self.seen_tpl_html.append(message)
        self.timeouts.append(timeout)
        if self.return_none:
            return None
        # Build a stable preview payload from the outgoing message
        data = message.model_dump()
        return PreviewOutgoingTemplatedHTMLEmail(
            **data,
            html_template_preview="<html>rendered</html>",
            plain_template_fallback_preview="rendered text" if message.plain_template_fallback else None,
        )

    # Interface completeness (unused in these tests)
    async def send_html_email(self, message, timeout: int | None = None):  # pragma: no cover
        raise NotImplementedError

    async def send_text_email(self, message, timeout: int | None = None):  # pragma: no cover
        raise NotImplementedError

    async def send_templated_plain_email(self, message, timeout: int | None = None):  # pragma: no cover
        raise NotImplementedError


# ===================== EmailDispatchOptions behavior =====================

class TestEmailDispatchOptions:
    @pytest.fixture
    def opts(self):
        return EmailDispatchOptions()

    def test_prefix_subject_applies_prefix_once_case_insensitively(self, opts):
        # default prefix is "[DevDox]"
        assert opts.prefix_subject("Hello") == "[DevDox] Hello"
        # already prefixed (different case) => no double prefix
        assert opts.prefix_subject("[devdox] Hello") == "[devdox] Hello"

    def test_rewrite_recipients_hard_redirect(self):
        opts = EmailDispatchOptions(
            redirect_all_to=["qa@example.com"],
            always_bcc=["audit@example.com", "qa@example.com"],  # collides with redirect target
        )
        rs = opts.rewrite_recipients(
            to=["real@example.com"],
            cc=["someone@example.com"],
            bcc=["invisible@example.com"],
        )
        assert rs.to == ["qa@example.com"]
        assert rs.cc == []                       # cleared
        assert rs.bcc == ["audit@example.com"]   # 'qa@' removed due to collision with redirected To


# ===================== EmailDispatcher: happy paths =====================

@pytest.mark.asyncio
class TestEmailDispatcherHappyPath:
    @pytest.fixture
    def inner(self):
        return _FakeIMailClient()

    @pytest.fixture
    def spy_client(self, inner):
        return SpyMailClient(inner)

    @pytest.fixture
    def dispatcher(self, spy_client):
        # Default EmailDispatchOptions uses "[DevDox]" prefix
        return EmailDispatcher(client=spy_client, options=EmailDispatchOptions())

    @pytest.fixture
    def addresses(self):
        return dict(
            to=["Dev1@example.com", "dev1@example.com", "dev2@example.com"],  # intentional dupes/casing
            cc=["audit@example.com"],
            bcc=["bcc@example.com", "Audit@example.com"],  # 'audit' overlaps CC; should be filtered by options
            reply_to=["reply@example.com"],
        )

    async def test_sends_templated_html_with_correct_model_and_prefix(self, dispatcher, spy_client, inner, addresses):
        # Arrange: proper context type for PROJECT_ANALYSIS_FAILURE
        ctx = ProjectAnalysisFailure(repository_html_url="http://repo", error_summary="x")
        # No explicit subject => uses template default then prefix
        out = await dispatcher.send_templated_html(
            to=addresses["to"],
            template=Template.PROJECT_ANALYSIS_FAILURE,
            context=ctx,
            subject=None,
            cc=addresses["cc"],
            bcc=addresses["bcc"],
            reply_to=addresses["reply_to"],
            headers={"X-Trace": "123"},
        )

        # A preview was returned by inner fake and tracked by spy
        assert isinstance(out, PreviewOutgoingTemplatedHTMLEmail)
        assert spy_client.returned_tpl_html == [out]
        assert len(spy_client.captured_tpl_html) == 1

        # Inspect the outgoing message the dispatcher built
        msg = spy_client.captured_tpl_html[0]

        # Recipients must be de-duped; 'audit@' removed from Bcc because it exists in Cc
        assert msg.recipients == ["Dev1@example.com", "dev2@example.com"]
        assert msg.cc == ["audit@example.com"]
        assert msg.bcc == ["bcc@example.com"]
        assert msg.reply_to == ["reply@example.com"]

        # Subject should be prefix + default template subject (idempotent prefix behavior tested elsewhere)
        assert msg.subject.startswith("[DevDox] ")
        assert "Repository Analysis Has Failed" in msg.subject

        # Correct template names resolved
        assert msg.html_template == "project_analysis_failure.html"
        assert msg.plain_template_fallback == "project_analysis_failure.txt"

        # Context stored as dict (model_dump)
        assert msg.template_context == ctx.model_dump()

        # Headers copied defensively (mutating caller's dict after call won't affect msg)
        # We also know _with_common_headers currently doesn't add defaults.
        assert msg.headers == {"X-Trace": "123"}

        # Inner received the same message and timeout defaulted to None here
        assert inner.seen_tpl_html == [msg]
        assert inner.timeouts == [None]

    async def test_respects_custom_subject_without_double_prefix(self, dispatcher, spy_client):
        ctx = ProjectAnalysisFailure()
        out = await dispatcher.send_templated_html(
            to=["user@example.com"],
            template=Template.PROJECT_ANALYSIS_FAILURE,
            context=ctx,
            subject="[devdox] Special Case",  # already prefixed (different case)
            cc=None, bcc=None, reply_to=None, headers=None,
        )
        assert isinstance(out, PreviewOutgoingTemplatedHTMLEmail)
        msg = spy_client.captured_tpl_html[0]
        assert msg.subject == "[devdox] Special Case"   # unchanged (no double prefix)

    async def test_headers_are_copied_not_aliased(self, dispatcher, spy_client):
        ctx = ProjectAnalysisFailure()
        headers = {"X-ID": "1"}
        await dispatcher.send_templated_html(
            to=["user@example.com"],
            template=Template.PROJECT_ANALYSIS_FAILURE,
            context=ctx,
            subject=None,
            headers=headers,
        )
        headers["X-ID"] = "2"  # mutate after call
        msg = spy_client.captured_tpl_html[0]
        assert msg.headers == {"X-ID": "1"}  # proves defensive copy


# ===================== EmailDispatcher: context validation =========
