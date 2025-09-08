from typing import Any, Iterable, Optional

from pydantic import BaseModel, EmailStr

from app.core.config import MailSettings
from app.infrastructure.mailing_service.client import IMailClient
from app.infrastructure.mailing_service.models import OutgoingTemplatedHTMLEmail
from app.infrastructure.qna.qna_models import ProjectQnAPackage


class EmailDispatchOptions(BaseModel):
    """Shared knobs for all email services."""
    dry_run: bool = False
    redirect_all_to: list[EmailStr] = []
    always_bcc: list[EmailStr] = []
    subject_prefix: Optional[str] = "[DevDox]"  # None disables prefix


class RecipientSet(BaseModel):
    to: list[EmailStr]
    cc: list[EmailStr] = []
    bcc: list[EmailStr] = []


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

    def _rewrite_recipients(self, to: Iterable[EmailStr], cc: Iterable[EmailStr], bcc: Iterable[EmailStr]) -> RecipientSet:
        to = list(to or [])
        cc = list(cc or [])
        bcc = list(bcc or [])
        if self.options.redirect_all_to:
            # hard redirect for safety in dev
            return RecipientSet(to=self.options.redirect_all_to, cc=[], bcc=self.options.always_bcc)
        # merge always_bcc
        merged_bcc = list({*map(str, bcc), *map(str, self.options.always_bcc)})
        return RecipientSet(to=to, cc=cc, bcc=merged_bcc)

    def _prefix_subject(self, subject: str) -> str:
        if not self.options.subject_prefix:
            return subject
        if subject.startswith(self.options.subject_prefix):
            return subject
        return f"{self.options.subject_prefix} {subject}"
    
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
        
        email_model = OutgoingTemplatedHTMLEmail(
            subject=subject,
            recipients=recipients.to,
            cc=recipients.cc,
            bcc=recipients.bcc,
            reply_to=list(reply_to or []),
            headers=headers or {},
            template_context=context,
            html_template=template,
            plain_template_fallback=text_fallback_template,
        )
        
        if self.options.dry_run:
            html_preview = None
            text_preview = None
            render_error = None
            try:
                # Ask the client to render the templates (no SMTP)
                rendered = await self.client.render_templates_for_preview(
                    html_template=template,
                    context=context,
                    plain_template=text_fallback_template,
                )
                html_preview = rendered.get("html")
                text_preview = rendered.get("text")
            except Exception as e:
                render_error = f"{type(e).__name__}: {e}"
            
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
                "render_error": render_error,      # <- if rendering failed
            }
        
        await self.client.send_templated_html_email(email_model)
        return None

# IMPLEMENTATIONS

class QnAEmailService:
    def __init__(self, dispatcher: EmailDispatcher):
        self.dispatcher = dispatcher

    def _context_from_pkg(self, pkg: ProjectQnAPackage) -> dict[str, Any]:
        return {
            "project": {
                "name": pkg.project_name,
                "repo_url": pkg.repo_url,
                "repo_id": pkg.repo_id,
            },
            "pairs": [
                {
                    "id": p.id,
                    "question": p.question,
                    "answer": p.answer,
                    "confidence": p.confidence,
                    "insufficient_evidence": p.insufficient_evidence,
                    "evidence_snippets": p.evidence_snippets,
                }
                for p in pkg.pairs
            ],
            "meta": {
                "generated_at_iso": pkg.generated_at.isoformat(),
                "model": pkg.model or "",
                "prompt_version": pkg.prompt_version or "",
            },
        }

    async def send_qna_summary(
        self,
        *,
        pkg: ProjectQnAPackage,
        to: Iterable[EmailStr],
        cc: Optional[Iterable[EmailStr]] = None,
        bcc: Optional[Iterable[EmailStr]] = None,
        subject: Optional[str] = None,
        reply_to: Optional[Iterable[EmailStr]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict | None:
        
        HTML_TEMPLATE = "project_qna.html"
        TEXT_FALLBACK_TEMPLATE = "project_qna.txt"
        
        subject = subject or f"Project Q&A – {pkg.project_name}"
        context = self._context_from_pkg(pkg)
        
        return await self.dispatcher.send_templated_html(
            subject=subject,
            to=to,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            headers=headers,
            template=HTML_TEMPLATE,
            text_fallback_template=TEXT_FALLBACK_TEMPLATE,
            context=context,
        )