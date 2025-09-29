import pytest
from pydantic_core import ValidationError

from app.infrastructure.mailing_service.models.base_models import (
    normalize_email,
    dedupe,
    EmailEnvelope,
)
from app.infrastructure.mailing_service.exception import exception_constants


# ===================== Helper functions =====================

class TestHelperFunctions:
    def test_normalize_email_lowercases_and_strips(self):
        assert normalize_email("  Alice@Example.COM  ") == "alice@example.com"

    def test_dedupe_is_order_preserving_and_case_insensitive(self):
        src = [
            "A@x.com",   # keep (first occurrence of a@x.com)
            "a@x.com",   # drop (duplicate by casefold)
            "B@x.com",   # keep
            "b@x.com",   # drop
            "C@x.com",   # keep
        ]
        out = dedupe(src)
        assert out == ["A@x.com", "B@x.com", "C@x.com"]

    def test_dedupe_handles_empty_list(self):
        assert dedupe([]) == []


# ===================== EmailEnvelope (happy paths) =====================

class TestEmailEnvelopeHappyPath:
    @pytest.fixture
    def base(self):
        return {
            "subject": "Hello",
            "recipients": ["TO@x.com", "to@x.com"],  # duplicates by case
            "cc": ["CC@x.com", "cc@x.com"],          # duplicates by case
            "bcc": ["B@x.com", "b@x.com"],           # duplicates by case
            "reply_to": ["reply@x.com", "REPLY@x.com"],  # duplicates by case
            "headers": {"X-ID": "  123  "},          # NonBlankStr should strip
        }

    def test_lists_are_deduped_independently_and_reply_to_is_deduped_too(self, base):
        env = EmailEnvelope(**base)
        assert env.recipients == ["TO@x.com"]
        assert env.cc == ["CC@x.com"]
        assert env.bcc == ["B@x.com"]
        assert env.reply_to == ["reply@x.com"]

    def test_headers_values_are_stripped_by_nonblankstr(self, base):
        env = EmailEnvelope(**base)
        # Mapping is accepted; value should be trimmed, non-empty
        assert dict(env.headers) == {"X-ID": "123"}


# ===================== EmailEnvelope (validation failures) =====================

class TestEmailEnvelopeValidationFailures:
    def test_subject_cannot_be_blank(self):
        with pytest.raises(ValidationError):
            EmailEnvelope(
                subject="   ",                      # NonBlankStr -> min_length=1 after strip
                recipients=["a@x.com"],
            )

    def test_recipients_cannot_be_empty(self):
        with pytest.raises(Exception):
            EmailEnvelope(
                subject="S",
                recipients=[],                      # min_length=1 on field
            )

    def test_headers_value_cannot_be_blank(self):
        with pytest.raises(Exception):
            EmailEnvelope(
                subject="S",
                recipients=["a@x.com"],
                headers={"X-Empty": "   "},         # NonBlankStr -> invalid after strip
            )

    def test_to_and_cc_cannot_overlap_case_insensitively(self):
        with pytest.raises(ValidationError) as exc:
            EmailEnvelope(
                subject="S",
                recipients=["a@x.com"],
                cc=["A@x.com"],                     # overlaps with To
            )
        assert exc.match(exception_constants.CANNOT_SHARE_ADDRESS.format(FROM="To", TO="Cc"))

    def test_to_and_bcc_cannot_overlap(self):
        with pytest.raises(ValidationError) as exc:
            EmailEnvelope(
                subject="S",
                recipients=["a@x.com"],
                bcc=["A@x.com"],                    # overlaps with To
            )
        assert exc.match(exception_constants.CANNOT_SHARE_ADDRESS.format(FROM="To", TO="Bcc"))
    
    def test_cc_and_bcc_cannot_overlap(self):
        with pytest.raises(ValidationError) as exc:
            EmailEnvelope(
                subject="S",
                recipients=["to@x.com"],
                cc=["cc@x.com"],
                bcc=["CC@x.com"],                   # overlaps with Cc
            )
        
        assert exc.match(exception_constants.CANNOT_SHARE_ADDRESS.format(FROM="Cc", TO="Bcc"))
