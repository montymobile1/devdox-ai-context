from abc import abstractmethod
from typing import Any, List, Optional, Protocol

from pydantic import BaseModel, EmailStr, Field

from app.infrastructure.mailing_service.client.client import IMailClient
from app.infrastructure.mailing_service.models.base_models import dedupe, normalize_email, OutgoingTemplatedHTMLEmail
from app.infrastructure.mailing_service.models.base_preview_models import PreviewOutgoingTemplatedHTMLEmail

class RecipientSet(BaseModel):
    to: list[EmailStr]
    cc: list[EmailStr] = Field(default_factory=list)
    bcc: list[EmailStr] = Field(default_factory=list)

class EmailDispatchOptions(BaseModel):
    """Shared knobs for all email services."""

    redirect_all_to: list[EmailStr] = Field(
        default_factory=list,
        description=(
            "Safety valve for non-production. When set to one or more addresses, every "
            "outbound email is hard-redirected: 'To' is replaced with this list, 'Cc' is "
            "cleared, and 'Bcc' retains 'always_bcc'. Use to prevent real customers from "
            "receiving test or staging emails."
        )
    )
    
    always_bcc: list[EmailStr] = Field(
        default_factory=list,
        description=(
            "Addresses that are silently added to BCC on every outgoing email "
            "(e.g., audit/archive inbox). The dispatcher de-duplicates and omits any "
            "address that is already present in To or Cc to keep recipients consistent "
            "and respect the no-overlap invariant."
        )
    )
    
    subject_prefix: Optional[str] = Field(
        default="[DevDox]",
        description=(
            "String prepended to the subject (e.g., environment tag). If None or empty, "
            "no prefix is applied. The dispatcher applies it idempotently and "
            "case-insensitively (won’t double-prefix)."
        ),
    )
    
    def rewrite_recipients(
            self,
            to: List[EmailStr],
            cc: List[EmailStr],
            bcc: List[EmailStr],
    ) -> RecipientSet:
        # 1) De-dupe within each bucket
        to  = dedupe(to)
        cc  = dedupe(cc)
        bcc = dedupe(bcc)
        
        # 2) Hard redirect (staging/dev safety)
        if self.redirect_all_to:
            redirected_to = dedupe(self.redirect_all_to)
            # Remove any always_bcc that collide with redirected To
            to_set = {normalize_email(x) for x in redirected_to}
            safe_bcc = [e for e in dedupe(self.always_bcc) if normalize_email(e) not in to_set]
            return RecipientSet(to=redirected_to, cc=[], bcc=safe_bcc)
        
        # 3) Merge always_bcc, then remove anything already in To/Cc
        tocc = {normalize_email(x) for x in [*to, *cc]}
        merged_bcc = dedupe([*bcc, *self.always_bcc])
        merged_bcc = [e for e in merged_bcc if normalize_email(e) not in tocc]
        
        return RecipientSet(to=to, cc=cc, bcc=merged_bcc)
    
    def prefix_subject(self, subject: str) -> str:
        """
        Make subject prefix check case-insensitive
        """
        p = self.subject_prefix
        if not p:
            return subject
        
        if subject.casefold().startswith((p or "").casefold()):
            return subject
        return f"{p} {subject}"

class IEmailDispatcher(Protocol):
    @abstractmethod
    async def send_templated_html(
            self,
            subject: str,
            to: List[EmailStr],
            template: str,
            context: dict[str, Any],
            text_fallback_template: Optional[str] = None,
            cc: Optional[List[EmailStr]] = None,
            bcc: Optional[List[EmailStr]] = None,
            reply_to: Optional[List[EmailStr]] = None,
            headers: Optional[dict[str, str]] = None,
    ) -> PreviewOutgoingTemplatedHTMLEmail | None: ...


class EmailDispatcher(IEmailDispatcher):

    def __init__(self, client: IMailClient, options: Optional[EmailDispatchOptions] = None):
        self.client = client
        self.options = options or EmailDispatchOptions()
    
    def _with_common_headers(self, headers: Optional[dict[str, str]]) -> dict[str, str]:
        """
          Merge caller-provided email headers with safe, organization-wide defaults.

          Purpose:
              Centralizes “always-on” headers (e.g., compliance/ESP hints) so every
              email gets them without each caller remembering to add them. This helps with:
                - deliverability (consistent metadata for ESPs),
                - compliance (e.g., List-Unsubscribe),
                - campaign tracking (e.g., X-Campaign-ID).

          Behavior:
              - Returns a new dict containing the caller’s headers plus defaults.
              - Never overwrites a header the caller already set (uses `setdefault`).
              - Safe to call with None.

          Args:
              headers: Optional mapping passed by the caller (may be None).

          Returns:
              A dict with merged headers suitable for the mail client.

          Example:
              h = self._with_common_headers({"X-Campaign-ID": "qna-2025-01"})
              # h now contains user headers plus any defaults (e.g., List-Unsubscribe).
          """
        h = {**(headers or {})}
        # Optional examples—enable only if real:
        # h.setdefault("List-Unsubscribe", "<mailto:unsubscribe@yourdomain>, <https://yourapp.com/unsub?token=XYZ>")
        # h.setdefault("X-Campaign-ID", "devdox-qna-v1")
        return h
    
    async def send_templated_html(
            self,
            subject: str,
            to: List[EmailStr],
            template: str,
            context: dict[str, Any],
            text_fallback_template: Optional[str] = None,
            cc: Optional[List[EmailStr]] = None,
            bcc: Optional[List[EmailStr]] = None,
            reply_to: Optional[List[EmailStr]] = None,
            headers: Optional[dict[str, str]] = None,
    ) -> PreviewOutgoingTemplatedHTMLEmail | None:
        recipients = self.options.rewrite_recipients(to, cc or [], bcc or [])
        subject = self.options.prefix_subject(subject)
        headers = self._with_common_headers(headers)
        
        email_model = OutgoingTemplatedHTMLEmail(
            subject=subject,
            recipients=recipients.to,
            cc=recipients.cc,
            bcc=recipients.bcc,
            reply_to=list(reply_to or []),
            headers=headers,
            template_context=context,
            html_template=template,
            plain_template_fallback=text_fallback_template,
        )
        
        return await self.client.send_templated_html_email(email_model)
    