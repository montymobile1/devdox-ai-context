import logging
from typing import Dict, Any, Optional
from dependency_injector.wiring import Provide, inject
import httpx

# Remove the Container import to avoid circular dependency
from app.services.auth_service import AuthService
from app.services.processing_service import ProcessingService
from app.infrastructure.queues.supabase_queue import SupabaseQueue
from app.infrastructure.job_tracer.job_trace_metadata import JobTraceMetaData
from app.handlers.job_tracker import JobTracker

logger = logging.getLogger(__name__)


class MessageHandler:
    @inject
    def __init__(
        self,
        # Use string references instead of Container.* to avoid circular import
        auth_service: AuthService = Provide["auth_service"],
        processing_service: ProcessingService = Provide["processing_service"],
        queue_service: SupabaseQueue = Provide["queue_service"],
    ):
        self.auth_service = auth_service
        self.processing_service = processing_service
        self.queue_service = queue_service

    async def handle_processing_message(self, job_payload: Dict[str, Any], job_tracker_instance:Optional[JobTracker]=None, job_tracer:Optional[JobTraceMetaData] = None) -> None:
        """Handle repository processing message"""

        try:
            # Process the repository
            if job_tracer:
                job_tracer.mark_job_started()
            
            result = await self.processing_service.process_repository(job_payload, job_tracker_instance, job_tracer=job_tracer)
            
            if result.success:
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

            else:
                
                log_message = f"Failed to process context {result.context_id}"
                
                logger.error(
                    f"{log_message}: {result.error_message}"
                )
                
                if job_tracer:
                    job_tracer.record_error(
                        summary=log_message,
                        exc=result.error_object
                    )
                
                
        except Exception as e:
            logger.error(f"Failed to handle processing message: {str(e)}")
            raise
        finally:
            if job_tracer:
                job_tracer.mark_job_finished()

    async def _send_completion_callback(self, callback_url: str, result) -> None:
        """Send completion notification to callback URL"""

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url, json=result.model_dump_json(), timeout=10.0
                )
        except Exception as e:
            logger.error(f"Failed to send callback to {callback_url}: {str(e)}")
