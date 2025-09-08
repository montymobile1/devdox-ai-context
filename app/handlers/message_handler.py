import logging
from typing import Dict, Any

from app.infrastructure.database.repositories import UserRepositoryHelper
from dependency_injector.wiring import Provide, inject
import httpx

# Remove the Container import to avoid circular dependency
from app.services.auth_service import AuthService
from app.services.processing_service import ProcessingService
from app.infrastructure.queues.supabase_queue import SupabaseQueue
from services.email_service import QnAEmailService

logger = logging.getLogger(__name__)


class MessageHandler:
    @inject
    def __init__(
        self,
        # Use string references instead of Container.* to avoid circular import
        auth_service: AuthService = Provide["auth_service"],
        user_handler: UserRepositoryHelper = Provide["user_repository"],
        processing_service: ProcessingService = Provide["processing_service"],
        queue_service: SupabaseQueue = Provide["queue_service"],
        qna_email_service: QnAEmailService = Provide["qna_email_service"]
    ):
        self.auth_service = auth_service
        self.processing_service = processing_service
        self.queue_service = queue_service
        self.qna_email_service = qna_email_service
        self.user_handler = user_handler
        
    async def handle_processing_message(self, job_payload: Dict[str, Any]) -> None:
        """Handle repository processing message"""

        try:
            # Process the repository
            
            
            
            result = await self.processing_service.process_repository(job_payload)
            if result.success:
                
                retrieved_user = await self.user_handler.find_by_user_id(job_payload["user_id"])
                
                logger.info(f"Successfully processed context {result.context_id}")

                # Consume tokens based on actual usage
                if result.chunks_created:
                    # Rough calculation: 1 token per chunk
                    await self.auth_service.consume_tokens(
                        job_payload["user_id"], result.chunks_created
                    )
                # Send callback notification if provided
                if job_payload.get("callback_url"):
                    try:
                        await self._send_completion_callback(
                            job_payload["callback_url"], result
                        )
                    except Exception as callback_error:
                        logger.error(
                            f"Callback failed for {job_payload['callback_url']}: {str(callback_error)}"
                        )
                
                # ---- Send the Q&A email if we have a package + recipients ----
                if result.qna_summary and retrieved_user.email:
                    logger.info("Sending question and answer summary to user")
                    await self._send_notification_mail(
                        qna_pkg=result.qna_summary,
                        notify_to=[retrieved_user.email]
                    )
                
            else:
                logger.error(
                    f"Failed to process context {result.context_id}: {result.error_message}"
                )

        except Exception as e:
            logger.error(f"Failed to handle processing message: {str(e)}")
            raise
    
    async def _send_notification_mail(self, qna_pkg, notify_to:list, notify_cc:list|None=None, notify_bcc:list|None=None):
        
        if not qna_pkg:
            return None
        
        if not notify_to:
            logger.error("No notify_to provided")
        
        if qna_pkg and notify_to:
            try:
                preview_or_none = await self.qna_email_service.send_qna_summary(
                    pkg=qna_pkg,
                    to=notify_to,
                    cc=notify_cc,
                    bcc=notify_bcc,
                )
                
                # If EmailDispatchOptions(dry_run=True), you get a preview dict back
                if isinstance(preview_or_none, dict):
                    logger.info("EMAIL PREVIEW (dry_run): %s", preview_or_none)
                    return preview_or_none
                
                return None
            
            except Exception:
                logger.exception("Failed to send Q&A summary email")
                return None
        
        return None
    
    async def _send_completion_callback(self, callback_url: str, result) -> None:
        """Send completion notification to callback URL"""

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url, json=result.model_dump_json(), timeout=10.0
                )
        except Exception as e:
            logger.error(f"Failed to send callback to {callback_url}: {str(e)}")
