import pytest

from app.infrastructure.mailing_service.test_doubles.email_service import SpyEmailDispatcher
from app.infrastructure.mailing_service.models.base_preview_models import (
    PreviewOutgoingTemplatedHTMLEmail,
)
from app.infrastructure.mailing_service.service.template_resolver import Template


# -------------------- Local fake IEmailDispatcher --------------------

class _FakeInnerDispatcher:
    """
    Minimal in-memory fake of IEmailDispatcher to validate SpyEmailDispatcher behavior.
    Captures calls and returns a pre-configured value (or raises if configured).
    """
    def __init__(self, ret=None, exc: Exception | None = None):
        self.calls: list[dict] = []
        self._ret = ret
        self._exc = exc

    async def send_templated_html(
        self,
        to,
        template: Template,
        context: dict | None = None,
        subject: str | None = None,
        cc=None,
        bcc=None,
        reply_to=None,
        headers: dict[str, str] | None = None,
    ):
        self.calls.append({
            "to": to,
            "template": template,
            "context": context,
            "subject": subject,
            "cc": cc,
            "bcc": bcc,
            "reply_to": reply_to,
            "headers": headers,
        })
        if self._exc:
            raise self._exc
        return self._ret


def _make_preview() -> PreviewOutgoingTemplatedHTMLEmail:
    # Build a valid preview instance (plain strings; Pydantic v2 validates in the model)
    return PreviewOutgoingTemplatedHTMLEmail(
        subject="Repo Analysis",
        recipients=["to@example.com"],
        cc=["cc@example.com"],
        bcc=[],
        reply_to=[],
        headers=None,
        html_template="project_analysis_failure.html",
        plain_template_fallback="project_analysis_failure.txt",
        template_context={"x": 1},
        html_template_preview="<html>ok</html>",
        plain_template_fallback_preview="ok",
    )


# ===================== Tests =====================

@pytest.mark.asyncio
class TestSpyEmailDispatcherHappyPath:
    @pytest.fixture
    def preview(self):
        return _make_preview()

    @pytest.fixture
    def inner(self, preview):
        return _FakeInnerDispatcher(ret=preview)

    @pytest.fixture
    def sut(self, inner):
        return SpyEmailDispatcher(inner)

    @pytest.fixture
    def args(self):
        # Note: pass plain strings for emails (EmailStr is a type, not a constructor in Pydantic v2)
        return {
            "to": ["dev1@example.com", "dev2@example.com"],
            "template": Template.PROJECT_ANALYSIS_FAILURE,
            "context": {"k": "v"},
            "subject": "S",
            "cc": ["audit@example.com"],
            "bcc": ["secret@example.com"],
            "reply_to": ["reply@example.com"],
            "headers": {"X-Trace": "123"},
        }

    async def test_proxies_and_records_call(self, sut, inner, args, preview):
        # Act
        out = await sut.send_templated_html(**args)

        # Assert: return value and tracking
        assert out is preview
        assert sut.returned_previews == [preview]

        # Assert: inner received exactly what Spy forwarded (note: cc/bcc/reply_to as given)
        assert len(inner.calls) == 1
        call = inner.calls[0]
        assert call == {
            "to": args["to"],
            "template": args["template"],
            "context": args["context"],
            "subject": args["subject"],
            "cc": args["cc"],
            "bcc": args["bcc"],
            "reply_to": args["reply_to"],
            "headers": args["headers"],
        }

        # Assert: spy logged normalized copies for list-y args (so later mutation won’t affect logs)
        assert len(sut.received_calls) == 1
        name, _pos, kw = sut.received_calls[0]
        assert name == "send_templated_html"
        # Spy logs copies: list(to), list(cc or []), list(bcc or []), list(reply_to or [])
        assert kw["to"] == args["to"] and kw["to"] is not args["to"]
        assert kw["cc"] == args["cc"] and kw["cc"] is not args["cc"]
        assert kw["bcc"] == args["bcc"] and kw["bcc"] is not args["bcc"]
        assert kw["reply_to"] == args["reply_to"] and kw["reply_to"] is not args["reply_to"]
        # Non-list args logged as-is
        assert kw["subject"] == args["subject"]
        assert kw["template"] == args["template"]
        assert kw["context"] == args["context"]
        assert kw["headers"] == args["headers"]

    async def test_logs_empty_lists_when_optionals_are_none_but_forwards_none(self, sut, inner):
        # Arrange: cc/bcc/reply_to None
        args = {
            "to": ["dev@example.com"],
            "template": Template.PROJECT_ANALYSIS_FAILURE,
            "context": None,
            "subject": None,
            "cc": None,
            "bcc": None,
            "reply_to": None,
            "headers": None,
        }

        # Act
        await sut.send_templated_html(**args)

        # Assert: spy log shows [] for list fields
        name, _pos, kw = sut.received_calls[0]
        assert name == "send_templated_html"
        assert kw["cc"] == []
        assert kw["bcc"] == []
        assert kw["reply_to"] == []
        # But inner received None (pass-through semantics)
        call = inner.calls[0]
        assert call["cc"] is None
        assert call["bcc"] is None
        assert call["reply_to"] is None


@pytest.mark.asyncio
class TestSpyEmailDispatcherReturnNonePath:
    @pytest.fixture
    def inner(self):
        return _FakeInnerDispatcher(ret=None)

    @pytest.fixture
    def sut(self, inner):
        return SpyEmailDispatcher(inner)

    async def test_tracks_none_returns(self, sut):
        out = await sut.send_templated_html(
            to=["user@example.com"],
            template=Template.PROJECT_ANALYSIS_FAILURE,
            context={"x": 1},
            subject="S",
            cc=[],
            bcc=[],
            reply_to=[],
            headers={},
        )
        assert out is None
        assert sut.returned_previews == [None]


@pytest.mark.asyncio
class TestSpyEmailDispatcherPlannedException:
    @pytest.fixture
    def inner(self):
        return _FakeInnerDispatcher()

    @pytest.fixture
    def sut(self, inner):
        return SpyEmailDispatcher(inner)

    async def test_planned_exception_records_then_raises_and_blocks_inner(self, sut, inner):
        # Arrange
        sut.set_exception(SpyEmailDispatcher.send_templated_html, RuntimeError("boom"))

        # Act / Assert
        with pytest.raises(RuntimeError, match="boom"):
            await sut.send_templated_html(
                to=["dev@example.com"], template=Template.PROJECT_ANALYSIS_FAILURE
            )

        # Spy recorded the call
        assert len(sut.received_calls) == 1
        name, _pos, kw = sut.received_calls[0]
        assert name == "send_templated_html"
        assert kw["to"] == ["dev@example.com"]
        # No return captured
        assert sut.returned_previews == []
        # Inner not called
        assert inner.calls == []
