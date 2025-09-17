from typing import Annotated, Any, Mapping, Optional

from pydantic import BaseModel, EmailStr, Field, StringConstraints

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

class EmailEnvelope(BaseModel):
	subject: NonBlankStr = Field(default=..., description="The email’s title (what shows in the inbox). Keep it short and human (avoid ALL CAPS/spammy words).")
	recipients: list[EmailStr] = Field(default=..., min_length=1, description="A list of “To” addresses (the main people getting the email).")
	cc: Optional[list[EmailStr]] = Field(default_factory=list, description="Carbon copy recipients")
	bcc: Optional[list[EmailStr]] = Field(default_factory=list,  description="Blind carbon copy recipients")
	reply_to: Optional[list[EmailStr]] = Field(default_factory=list, description="If someone clicks “Reply”, messages go here instead of the “From” address. Useful when sending from a no-reply address but wanting replies to support@…")
	headers: Optional[Mapping[str, NonBlankStr]] = Field(default=None, description="Custom metadata for filters/automation (machines more than humans). (e.g., 'X-Campaign-ID': 'llm-summary-2025-08'")


class OutgoingTemplatedContextEmail(EmailEnvelope):
	template_context: dict[str, Any] = Field(
		default_factory=dict, description="Template context with variables for rendering (e.g., {'project_name': 'X', 'risks': [...]}))"
	)

class OutgoingHtmlEmail(EmailEnvelope):
	html_body: NonBlankStr = Field(default=..., description="Raw HTML body of the email")
	text_fallback: Optional[NonBlankStr] = Field(
		default=None, description="Optional text-only multipart fallback if HTML is not supported"
	)

class OutgoingTextEmail(EmailEnvelope):
	text_body: NonBlankStr = Field(default=..., description="Raw Plain text body of the email")

class OutgoingTemplatedHTMLEmail(OutgoingTemplatedContextEmail):
	
	html_template: NonBlankStr = Field(
		default=..., description="Name of the HTML template file name (e.g., analysis_summary.html)"
	)
	
	plain_template_fallback: Optional[NonBlankStr] = Field(
		default=None, description="Optional text-only multipart fallback template file name if HTML is not supported"
	)

class OutgoingTemplatedTextEmail(OutgoingTemplatedContextEmail):
	plain_template: NonBlankStr = Field(
		default=..., description="Name of the plain text template file name (e.g., analysis_summary.txt)"
	)

