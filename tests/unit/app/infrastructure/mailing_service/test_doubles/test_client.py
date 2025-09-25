import pytest

from app.infrastructure.mailing_service.test_doubles.client import SpyMailClient
from app.infrastructure.mailing_service.models.base_models import (
    OutgoingHtmlEmail,
    OutgoingTextEmail,
    OutgoingTemplatedHTMLEmail,
    OutgoingTemplatedTextEmail,
)
from app.infrastructure.mailing_service.models.base_preview_models import (
    PreviewOutgoingHtmlEmail,
    PreviewOutgoingTextEmail,
    PreviewOutgoingTemplatedHTMLEmail,
    PreviewOutgoingTemplatedTextEmail,
)


# ---------- Local fake IMailClient (preferred over mocks) ----------

class _FakeInnerMailClient:
    """
    A tiny in-memory fake implementing IMailClient's behavior surface.
    It records inputs and returns Preview* objects (or None if configured).
    """

    def __init__(
        self,
        return_none_html=False,
        return_none_text=False,
        return_none_tpl_html=False,
        return_none_tpl_text=False,
    ) -> None:
        self.return_none_html = return_none_html
        self.return_none_text = return_none_text
        self.return_none_tpl_html = return_none_tpl_html
        self.return_none_tpl_text = return_none_tpl_text

        # capture buckets for assertions
        self.captured_html: list[OutgoingHtmlEmail] = []
        self.captured_text: list[OutgoingTextEmail] = []
        self.captured_tpl_html: list[OutgoingTemplatedHTMLEmail] = []
        self.captured_tpl_text: list[OutgoingTemplatedTextEmail] = []

    # ---- IMailClient API ----
    async def send_html_email(self, message: OutgoingHtmlEmail, timeout: int | None = None):
        self.captured_html.append(message)
        if self.return_none_html:
            return None
        return PreviewOutgoingHtmlEmail(
            **message.model_dump(),
            html_body_preview=message.html_body,
            text_fallback_preview=message.text_fallback,
        )

    async def send_text_email(self, message: OutgoingTextEmail, timeout: int | None = None):
        self.captured_text.append(message)
        if self.return_none_text:
            return None
        return PreviewOutgoingTextEmail(
            **message.model_dump(),
            text_body_preview=message.text_body,
        )

    async def send_templated_html_email(self, message: OutgoingTemplatedHTMLEmail, timeout: int | None = None):
        self.captured_tpl_html.append(message)
        if self.return_none_tpl_html:
            return None
        return PreviewOutgoingTemplatedHTMLEmail(
            **message.model_dump(),
            html_template_preview="RENDERED_HTML",
            plain_template_fallback_preview="RENDERED_TEXT" if message.plain_template_fallback else None,
        )

    async def send_templated_plain_email(self, message: OutgoingTemplatedTextEmail, timeout: int | None = None):
        self.captured_tpl_text.append(message)
        if self.return_none_tpl_text:
            return None
        return PreviewOutgoingTemplatedTextEmail(
            **message.model_dump(),
            plain_template_preview="RENDERED_TEXT",
        )


# ---------- Common builders ----------

def _html_msg() -> OutgoingHtmlEmail:
    return OutgoingHtmlEmail(
        subject="S-HTML",
        recipients=["to@example.com"],
        html_body="<b>Hello</b>",
        text_fallback="Hello",
    )

def _text_msg() -> OutgoingTextEmail:
    return OutgoingTextEmail(
        subject="S-TEXT",
        recipients=["to@example.com"],
        text_body="Hello",
    )

def _tpl_html_msg() -> OutgoingTemplatedHTMLEmail:
    return OutgoingTemplatedHTMLEmail(
        subject="S-TPL-HTML",
        recipients=["to@example.com"],
        html_template="tpl.html",
        plain_template_fallback="tpl.txt",
        template_context={"k": "v"},
    )

def _tpl_text_msg() -> OutgoingTemplatedTextEmail:
    return OutgoingTemplatedTextEmail(
        subject="S-TPL-TEXT",
        recipients=["to@example.com"],
        plain_template="tpl.txt",
        template_context={"x": 1},
    )


# ===================== Tests =====================

@pytest.mark.asyncio
class TestSpyMailClientHappyPath:
    @pytest.fixture
    def inner(self):
        return _FakeInnerMailClient()

    @pytest.fixture
    def sut(self, inner):
        return SpyMailClient(inner)

    @pytest.fixture
    def msgs(self):
        return {
            "html": _html_msg(),
            "text": _text_msg(),
            "tpl_html": _tpl_html_msg(),
            "tpl_text": _tpl_text_msg(),
        }

    async def test_send_html_email_records_and_proxies(self, sut, inner, msgs):
        # Act
        out = await sut.send_html_email(msgs["html"], timeout=5)

        # Assert spy call capture + identity
        assert sut.received_calls == [
            ("send_html_email", (), {"message": msgs["html"], "timeout": 5})
        ]
        assert sut.captured_html == [msgs["html"]]
        # Inner got the message
        assert inner.captured_html == [msgs["html"]]
        # Return value is propagated and tracked
        assert isinstance(out, PreviewOutgoingHtmlEmail)
        assert sut.returned_html == [out]

    async def test_send_text_email_records_and_proxies(self, sut, inner, msgs):
        out = await sut.send_text_email(msgs["text"], timeout=None)

        assert sut.received_calls == [
            ("send_text_email", (), {"message": msgs["text"], "timeout": None})
        ]
        assert sut.captured_text == [msgs["text"]]
        assert inner.captured_text == [msgs["text"]]
        assert isinstance(out, PreviewOutgoingTextEmail)
        assert sut.returned_text == [out]

    async def test_send_templated_html_email_records_and_proxies(self, sut, inner, msgs):
        out = await sut.send_templated_html_email(msgs["tpl_html"], timeout=15)

        assert sut.received_calls == [
            ("send_templated_html_email", (), {"message": msgs["tpl_html"], "timeout": 15})
        ]
        assert sut.captured_tpl_html == [msgs["tpl_html"]]
        assert inner.captured_tpl_html == [msgs["tpl_html"]]
        assert isinstance(out, PreviewOutgoingTemplatedHTMLEmail)
        assert sut.returned_tpl_html == [out]

    async def test_send_templated_plain_email_records_and_proxies(self, sut, inner, msgs):
        out = await sut.send_templated_plain_email(msgs["tpl_text"], timeout=0)

        assert sut.received_calls == [
            ("send_templated_plain_email", (), {"message": msgs["tpl_text"], "timeout": 0})
        ]
        assert sut.captured_tpl_text == [msgs["tpl_text"]]
        assert inner.captured_tpl_text == [msgs["tpl_text"]]
        assert isinstance(out, PreviewOutgoingTemplatedTextEmail)
        assert sut.returned_tpl_text == [out]

    async def test_accumulates_multiple_calls_in_order_across_methods(self, sut, inner, msgs):
        # Act
        await sut.send_html_email(msgs["html"], timeout=1)
        await sut.send_text_email(msgs["text"], timeout=2)
        await sut.send_templated_html_email(msgs["tpl_html"], timeout=3)

        # Assert order of call log
        assert sut.received_calls == [
            ("send_html_email", (), {"message": msgs["html"], "timeout": 1}),
            ("send_text_email", (), {"message": msgs["text"], "timeout": 2}),
            ("send_templated_html_email", (), {"message": msgs["tpl_html"], "timeout": 3}),
        ]
        # Assert capture buckets
        assert sut.captured_html == [msgs["html"]]
        assert sut.captured_text == [msgs["text"]]
        assert sut.captured_tpl_html == [msgs["tpl_html"]]
        # Inner also saw them
        assert inner.captured_html == [msgs["html"]]
        assert inner.captured_text == [msgs["text"]]
        assert inner.captured_tpl_html == [msgs["tpl_html"]]
        # Return tracking
        assert len(sut.returned_html) == 1
        assert len(sut.returned_text) == 1
        assert len(sut.returned_tpl_html) == 1


@pytest.mark.asyncio
class TestSpyMailClientReturnNonePaths:
    async def test_return_none_is_recorded(self):
        inner = _FakeInnerMailClient(return_none_html=True, return_none_text=True,
                                     return_none_tpl_html=True, return_none_tpl_text=True)
        sut = SpyMailClient(inner)

        # Act
        out1 = await sut.send_html_email(_html_msg(), timeout=9)
        out2 = await sut.send_text_email(_text_msg(), timeout=None)
        out3 = await sut.send_templated_html_email(_tpl_html_msg(), timeout=11)
        out4 = await sut.send_templated_plain_email(_tpl_text_msg(), timeout=12)

        # Assert: all None returns properly tracked
        assert out1 is None and sut.returned_html == [None]
        assert out2 is None and sut.returned_text == [None]
        assert out3 is None and sut.returned_tpl_html == [None]
        assert out4 is None and sut.returned_tpl_text == [None]


@pytest.mark.asyncio
class TestSpyMailClientExceptionPlanning:
    @pytest.fixture
    def inner(self):
        return _FakeInnerMailClient()

    @pytest.fixture
    def sut(self, inner):
        return SpyMailClient(inner)

    async def test_planned_exception_raises_after_recording_and_prevents_inner_call(self, sut, inner):
        # Arrange
        sut.set_exception(SpyMailClient.send_html_email, RuntimeError("boom"))

        # Act / Assert
        msg = _html_msg()
        with pytest.raises(RuntimeError, match="boom"):
            await sut.send_html_email(msg, timeout=7)

        # Recorded on spy (before raising)
        assert sut.received_calls == [
            ("send_html_email", (), {"message": msg, "timeout": 7})
        ]
        assert sut.captured_html == []          # capture happens after _before; exception prevented it
        assert sut.returned_html == []          # no return recorded

        # Inner never called
        assert inner.captured_html == []
