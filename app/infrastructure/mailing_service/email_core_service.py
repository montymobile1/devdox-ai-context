from typing import Any, Iterable, Optional

from pydantic import BaseModel, EmailStr, Field

from app.core.config import MailSettings
from app.infrastructure.mailing_service.client import IMailClient
from app.infrastructure.mailing_service.models import OutgoingTemplatedHTMLEmail


class EmailDispatchOptions(BaseModel):
    """Shared knobs for all email services."""
    
    """If True, render templates and return a preview payload instead of sending.
       Rendering follows the exact same code path as real sends and will raise on
       template/config errors (so dev/test behaves like prod, minus SMTP)."""
    dry_run: bool = False
    redirect_all_to: list[EmailStr] = Field(default_factory=list)
    always_bcc: list[EmailStr] = Field(default_factory=list)
    subject_prefix: Optional[str] = "[DevDox]"  # None disables prefix


class RecipientSet(BaseModel):
    to: list[EmailStr]
    cc: list[EmailStr] = Field(default_factory=list)
    bcc: list[EmailStr] = Field(default_factory=list)

class EmailDispatcher:
    """
    Common infrastructure:
    - dry run (returns preview dict instead of sending)
    - recipient redirect (dev safety)
    - always-bcc
    """
    def __init__(self, client: IMailClient, settings: MailSettings, options: Optional[EmailDispatchOptions] = None):
        self.client = client
        self.settings = settings
        self.options = options or EmailDispatchOptions()
    
    def _dedupe_preserve_order(self, seq: Iterable[EmailStr]) -> list[EmailStr]:
        """
            Handles the case where _rewrite_recipients() merges always_bcc but can duplicate addresses
            or put someone in BCC who’s already in To/CC.
        """
        seen: set[str] = set()
        out: list[EmailStr] = []
        for e in seq or []:
            s = str(e).strip().lower()
            if s in seen:
                continue
            seen.add(s)
            out.append(e)
        return out
    
    def _rewrite_recipients(self, to, cc, bcc) -> RecipientSet:
        to = self._dedupe_preserve_order(to)
        cc = self._dedupe_preserve_order(cc)
        bcc = self._dedupe_preserve_order(bcc)
        
        if self.options.redirect_all_to:
            return RecipientSet(
                to=self._dedupe_preserve_order(self.options.redirect_all_to),
                cc=[],
                bcc=self._dedupe_preserve_order(self.options.always_bcc),
            )
        
        merged_bcc = self._dedupe_preserve_order([*bcc, *self.options.always_bcc])
        # remove any BCC that appears in To/CC
        tocc = {str(x).lower() for x in [*to, *cc]}
        merged_bcc = [e for e in merged_bcc if str(e).lower() not in tocc]
        return RecipientSet(to=to, cc=cc, bcc=merged_bcc)
    
    def _prefix_subject(self, subject: str) -> str:
        """
        Make subject prefix check case-insensitive
        """
        p = self.options.subject_prefix
        if not p:
            return subject
        if subject.lower().startswith((p or "").lower()):
            return subject
        return f"{p} {subject}"
    
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
            *,
            subject: str,
            to: Iterable[EmailStr],
            template: str,
            context: dict[str, Any],
            text_fallback_template: Optional[str] = None,
            cc: Optional[Iterable[EmailStr]] = None,
            bcc: Optional[Iterable[EmailStr]] = None,
            reply_to: Optional[Iterable[EmailStr]] = None,
            headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any] | None:
        recipients = self._rewrite_recipients(to, cc or [], bcc or [])
        subject = self._prefix_subject(subject)
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
        
        if self.options.dry_run:
            # Ask the client to render the templates (no SMTP)
            rendered = await self.client.render_templates_for_preview(
                html_template=template,
                context=context,
                plain_template=text_fallback_template,
            )
            
            html_preview = rendered.get("html")
            text_preview = rendered.get("text")
            
            return {
                "subject": email_model.subject,
                "to": [str(x) for x in email_model.recipients],
                "cc": [str(x) for x in (email_model.cc or [])],
                "bcc": [str(x) for x in (email_model.bcc or [])],
                "template": template,
                "text_fallback_template": text_fallback_template,
                "context": context,
                "html_preview": html_preview,      # <- paste this into a browser
                "text_preview": text_preview,      # <- plain text version
            }
        
        await self.client.send_templated_html_email(email_model)
        return None