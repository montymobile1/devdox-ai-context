from .service.email_service import (
    EmailDispatcher,
    EmailDispatchOptions,
    IEmailDispatcher,
)

from .exception import mail_exceptions
from .exception import exception_constants

from .models.base_models import (
    EmailEnvelope,
    OutgoingHtmlEmail,
    OutgoingTemplatedContextEmail,
    OutgoingTemplatedHTMLEmail,
    OutgoingTemplatedTextEmail,
    OutgoingTextEmail,
)
from .models.base_preview_models import (
    PreviewEmailEnvelope,
    PreviewOutgoingHtmlEmail,
    PreviewOutgoingTemplatedContextEmail,
    PreviewOutgoingTemplatedHTMLEmail,
    PreviewOutgoingTemplatedTextEmail,
    PreviewOutgoingTextEmail,
)

from .test_doubles.client import SpyMailClient
from .test_doubles.email_service import SpyEmailDispatcher


__all__ = [
    # service/
    "EmailDispatcher",
    "EmailDispatchOptions",
    "IEmailDispatcher",
    
    # exception/
    "mail_exceptions",
    "exception_constants",

    # models/
    "EmailEnvelope",
    "OutgoingHtmlEmail",
    "OutgoingTemplatedContextEmail",
    "OutgoingTemplatedHTMLEmail",
    "OutgoingTemplatedTextEmail",
    "OutgoingTextEmail",
    "PreviewEmailEnvelope",
    "PreviewOutgoingHtmlEmail",
    "PreviewOutgoingTemplatedContextEmail",
    "PreviewOutgoingTemplatedHTMLEmail",
    "PreviewOutgoingTemplatedTextEmail",
    "PreviewOutgoingTextEmail",
    
    # test_doubles/
    "SpyMailClient",
    "SpyEmailDispatcher"
]





