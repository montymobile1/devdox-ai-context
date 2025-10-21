import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from tembo_pgmq_python.async_queue import PGMQueue
from tembo_pgmq_python.messages import Message

from app.infrastructure.job_tracer.job_trace_metadata import JobTraceMetaData

from app.handlers.job_tracker import JobLevels, JobTracker

logger = logging.getLogger(__name__)


class SupabaseQueue:
    """
    Queue implementation using PGMQueue as the backend storage.
    Uses PostgreSQL tables to implement a reliable job queue system.
    """

    def __init__(
        self,
        host: str,
        port: str,
        user: str,
        password: str,
        db_name: str,
        table_name: str = "processing_job",
    ):
        """
        Initialize PGMQueue client

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            user: PostgreSQL username
            password: PostgreSQL password
            db_name: PostgreSQL database name
            table_name: Name of the queue to use for job storage
        """
        self.queue = PGMQueue(
            host=host,
            port=port,
            username=user,
            password=password,
            database=db_name,
        )
        self.table_name = table_name
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure the queue is initialized"""
        if not self._initialized:
            try:
                await self.queue.init()
            except Exception as e:
                logger.error(f"Failed to initialize queue: {str(e)}")
                raise e

            self._initialized = True

    async def enqueue(
        self,
        queue_name: str,
        payload: Dict[str, Any],
        priority: int = 1,
        job_type: str = "context_creation",
        user_id: str = None,
        delay_seconds: int = 0,
        **kwargs,
    ) -> str:
        """
        Add a job to the queue

        Args:
            queue_name: Name of the queue (used for routing)
            payload: Job payload data
            priority: Job priority (higher = more important)
            job_type: Type of job for categorization
            user_id: User who initiated the job
            delay_seconds: Delay before job becomes available
            **kwargs: Additional job metadata

        Returns:
            str: Job ID
        """
        try:
            await self._ensure_initialized()
            scheduled_at = datetime.now(timezone.utc)
            if delay_seconds > 0:
                scheduled_at += timedelta(seconds=delay_seconds)

            job_data = {
                "job_type": job_type,
                "status": "queued",
                "priority": priority,
                "user_id": user_id,
                "payload": json.dumps(payload)
                if isinstance(payload, dict)
                else payload,
                "config": json.dumps(kwargs.get("config", {})),
                "scheduled_at": scheduled_at.isoformat(),
                "attempts": 0,
                "max_attempts": kwargs.get("max_attempts", self.max_retries),
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k not in ["config", "max_attempts"]
                },
            }

            # Send job to queue with delay if specified
            if delay_seconds > 0:
                result: int = await self.queue.send(
                    queue_name, job_data, delay_seconds
                )
            else:
                result: int = await self.queue.send(queue_name, job_data)

            job_id = str(result)
            logger.info(
                f"Job {job_id} enqueued successfully",
                extra={
                    "job_id": job_id,
                    "job_type": job_type,
                    "queue_name": queue_name,
                    "priority": priority,
                    "user_id": user_id,
                },
            )
            return job_id

        except Exception as e:
            logger.error(
                f"Failed to enqueue job: {str(e)}",
                extra={"queue_name": queue_name, "job_type": job_type, "error": str(e)},
            )
            raise

    async def _process_messages(
            self,
            messages: List[Message],
            queue_name: str,
            job_types: List[str],
            worker_id: str
    ) -> Optional[Dict[str, Any]]:
        """Process messages and return the first valid job"""
        for message in messages:
            try:
                job_data = await self._process_single_message(message, queue_name, job_types, worker_id)
                if job_data:
                    return job_data
            except Exception as e:
                logger.error(f"Error processing message {message.msg_id}: {str(e)}")
                continue
        return None

    async def _process_single_message(
            self,
            message: Message,
            queue_name: str,
            job_types: List[str],
            worker_id: str
    ) -> Optional[Dict[str, Any]]:
        """Process a single message and return job data if valid"""
        message_data = message.message

        # Early return if job type doesn't match filter
        if not self._is_job_type_allowed(message_data, job_types):
            return None

        # Handle jobs that exceeded max attempts
        if await self._handle_max_attempts_exceeded(
            message_data, message.msg_id, queue_name
        ):
            return None

        # Skip jobs that aren't ready to be processed yet
        if not self._is_job_ready_for_processing(message_data):
            return None

        # Parse and construct job data
        return self._construct_job_data(message, message_data, queue_name, worker_id)

    def _parse_json_field(self, field_value: Any) -> Any:
        """Parse JSON field, returning original value if parsing fails"""
        if not isinstance(field_value, str):
            return field_value

        try:
            return json.loads(field_value)
        except json.JSONDecodeError:
            return field_value

    def _construct_job_data(
            self,
            message: Message,
            message_data: Dict[str, Any],
            queue_name: str,
            worker_id: str
    ) -> Dict[str, Any]:
        """Construct job data from message"""
        payload = self._parse_json_field(message_data.get("payload"))
        config = self._parse_json_field(message_data.get("config", "{}"))
        attempts = message_data.get("attempts", 0)

        job_data = {
            "id": str(message.msg_id),
            "pgmq_msg_id": message.msg_id,
            "job_type": message_data.get("job_type"),
            "payload": payload,
            "config": config,
            "priority": message_data.get("priority", 1),
            "attempts": attempts + 1,
            "max_attempts": message_data.get("max_attempts", self.max_retries),
            "user_id": message_data.get("user_id"),
            "scheduled_at": message_data.get("scheduled_at"),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "worker_id": worker_id,
            "queue_name": queue_name,
        }

        logger.info(
            f"Job {job_data['id']} dequeued for processing",
            extra={
                "job_id": job_data["id"],
                "job_type": job_data["job_type"],
                "attempts": job_data["attempts"],
                "worker_id": worker_id,
            },
        )

        return job_data


    def _is_job_type_allowed(self, message_data: Dict[str, Any], job_types: List[str]) -> bool:
        """Check if job type is in the allowed list"""
        if not job_types:
            return True
        return message_data.get("job_type") in job_types

    async def _handle_max_attempts_exceeded(
            self,
            message_data: Dict[str, Any],
            msg_id: int,
            queue_name: str
    ) -> bool:
        """Handle jobs that exceeded max attempts. Returns True if job was archived"""
        attempts = message_data.get("attempts", 0)
        max_attempts = message_data.get("max_attempts", self.max_retries)

        if attempts >= max_attempts:
            await self.queue.archive(queue_name, msg_id)
            return True
        return False

    def _is_job_ready_for_processing(self, message_data: Dict[str, Any]) -> bool:
        """Check if job is ready to be processed based on scheduled_at"""
        scheduled_at_str = message_data.get("scheduled_at")
        if not scheduled_at_str:
            return True

        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
            return scheduled_at <= datetime.now(timezone.utc)
        except ValueError:
            logger.error(f"Invalid scheduled_at format: {scheduled_at_str}, processing anyway.")
            return True


    async def dequeue(
        self,
        queue_name: str = None,
        job_types: List[str] = None,
        worker_id: str = None,
        visibility_timeout: int = 30,
        batch_size: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the next available job from the queue

        Args:
            queue_name: Specific queue to dequeue from (optional, uses table_name if None)
            job_types: List of job types to process (optional filtering)
            worker_id: Identifier for the worker processing the job
            visibility_timeout: How long the message is invisible to other consumers (seconds)
            batch_size: Number of messages to read (default 1)

        Returns:
            Dict containing job data or None if no jobs available
        """
        try:
            await self._ensure_initialized()

            # Use provided queue_name or default to table_name
            effective_queue_name = queue_name or self.table_name
            # Read messages from queue
            messages: List[Message] = await self.queue.read_batch(
                effective_queue_name, vt=visibility_timeout, batch_size=batch_size
            )
            if not messages:
                return None
            return await self._process_messages(messages, effective_queue_name, job_types, worker_id)


        except Exception as e:
            logger.error(
                f"Failed to dequeue job: {str(e)}",
                extra={"queue_name": queue_name, "error": str(e)},
            )
            return None

    async def complete_job(self, job_data: Dict[str, Any], job_tracker_instance:Optional[JobTracker]=None, job_tracer:Optional[JobTraceMetaData] = None, result: Dict[str, Any] = None) -> bool:
        """
        Mark a job as completed

        Args:
            job_data: Job data returned from dequeue (contains pgmq_msg_id and queue_name)
            result: Optional result data to store

        Returns:
            bool: True if job was successfully marked as completed
        """
        try:
            await self._ensure_initialized()
            msg_id = job_data.get("pgmq_msg_id")
            queue_name = job_data.get("queue_name", self.table_name)
            if not msg_id:
                log_summary = "No pgmq_msg_id found in job data"
                logger.error(log_summary)
                
                if job_tracer:
                    job_tracer.record_error(
                        summary = log_summary,
                    )
                
                return False

            # Delete the message from the queue (marks as completed)
            success = await self.queue.delete(queue_name, msg_id)
            if success:
                logger.info(f"Job {job_data.get('id')} marked as completed")
                
                if job_tracker_instance:
                    try:
                        await job_tracker_instance.completed()
                    except Exception:
                        logger.exception("Job completed, but JobTracker.completed() failed; continuing.")
                    
                return True
            else:
                log_summary = f"Failed to mark job {job_data.get('id')} as completed"
                logger.error(log_summary)
                
                if job_tracer:
                    job_tracer.record_error(
                        summary = log_summary,
                    )
                
                return False

        except Exception as e:
            log_summary = f"Failed to complete job {job_data.get('id')}"
            logger.exception(log_summary)
            
            if job_tracer:
                job_tracer.record_error(
                    summary = log_summary,
                    exc=e
                )
            
            return False
    
    
    async def fail_job(
            self,
            job_data: Dict[str, Any],
            error: BaseException,
            job_tracker_instance: Optional[JobTracker] = None,
            job_tracer: Optional[JobTraceMetaData] = None,
            error_trace: Optional[str] = None,
            retry: bool = True,
    ) -> Tuple[bool, bool]:
        """
        Mark a job as failed.
        
        Args:
            job_data: Job data returned from dequeue
            job_tracer: An optional job tracer for tracing the state of the job
            error: Error message
            job_tracker_instance: Optional job tracker to handle claim and tracking
            error_trace: Full error traceback
            retry: Whether to retry the job if attempts remain
        
        Returns:
            (perma_failure, handled_ok)
            - perma_failure: True if the job is now permanently failed/archived.
            - handled_ok:     True if we successfully requeued OR archived; False if we couldn’t act.
        """
        await self._ensure_initialized()
        
        queue_name = job_data.get("queue_name", self.table_name)
        msg_id = job_data.get("pgmq_msg_id")
        attempts = int(job_data.get("attempts", 1))
        max_attempts = int(job_data.get("max_attempts", self.max_retries))
        
        # Guard: without msg_id we can't delete/archive; log and record
        if not msg_id:
            return self._handle_missing_msg_id(job_data, error, job_tracer)
        
        # Retry path (early return)
        if self._should_retry(retry, attempts, max_attempts):
            return await self._retry_job(
                queue_name=queue_name,
                msg_id=msg_id,
                job_data=job_data,
                attempts=attempts,
                max_attempts=max_attempts,
                error=error,
                error_trace=error_trace,
                job_tracker_instance=job_tracker_instance,
            )
        
        # Permanent failure path
        return await self._archive_permanently(
            queue_name=queue_name,
            msg_id=msg_id,
            job_data=job_data,
            attempts=attempts,
            error=error,
            job_tracker_instance=job_tracker_instance,
            job_tracer=job_tracer,
        )
    
    def _should_retry(self, retry_flag: bool, attempts: int, max_attempts: int) -> bool:
        return bool(retry_flag) and attempts < max_attempts
    
    def _retry_delay_secs(self, attempts: int) -> int:
        # Exponential backoff: 10, 20, 40, ... capped at 300s (5m)
        return min(300, (2 ** max(0, attempts - 1)) * 10)
    
    def _build_retry_payload(
            self,
            job_data: Dict[str, Any],
            *,
            attempts: int,
            error: BaseException,
            error_trace: Optional[str],
    ) -> Dict[str, Any]:
        # Start from existing job_data to retain original fields/context
        retry_job_data = dict(job_data)
        retry_job_data.update(
            {
                "attempts": attempts,                 # keep current attempts as-is
                "retry_count": attempts,              # explicit retry counter (mirrors attempts)
                "error_message": str(error),
                "last_error_trace": error_trace,
            }
        )
        # Strip queue-generated IDs; we’re re-inserting a fresh message
        retry_job_data.pop("pgmq_msg_id", None)
        retry_job_data.pop("id", None)
        return retry_job_data
    
    async def _retry_job(
            self,
            *,
            queue_name: str,
            msg_id: Any,
            job_data: Dict[str, Any],
            attempts: int,
            max_attempts: int,
            error: BaseException,
            error_trace: Optional[str],
            job_tracker_instance: Optional[JobTracker],
    ) -> Tuple[bool, bool]:
        delay = self._retry_delay_secs(attempts)
        retry_payload = self._build_retry_payload(
            job_data, attempts=attempts, error=error, error_trace=error_trace
        )
        
        # Remove current message then re-send with delay
        await self.queue.delete(queue_name, msg_id)
        new_msg_id = await self.queue.send(queue=queue_name, message=retry_payload, delay=delay)
        
        logger.info(
            "Job %s scheduled for retry %d/%d in %ds",
            job_data.get("id"),
            attempts,
            max_attempts,
            delay,
        )

        # as job_tracker_instance can be False
        if job_tracker_instance and job_tracker_instance.id:
            try:
                await job_tracker_instance.retry(message_id=str(new_msg_id))
            except Exception:
                logger.exception("Job re-queued, but JobTracker.retry() failed; continuing.")
        
        return (False, True)  # not permanent, handled OK
    
    async def _archive_permanently(
            self,
            *,
            queue_name: str,
            msg_id: Any,
            job_data: Dict[str, Any],
            attempts: int,
            error: BaseException,
            job_tracker_instance: Optional[JobTracker],
            job_tracer: Optional[JobTraceMetaData],
    ) -> Tuple[bool, bool]:
        # Try to archive the failed message
        success = await self.queue.archive(queue_name, msg_id)
        
        if job_tracker_instance:
            try:
                await job_tracker_instance.fail(message_id=str(msg_id))
            except Exception:
                logger.exception("JobTracker.fail() threw; continuing.")
        
        if success:
            log_summary = f"Job {job_data.get('id')} permanently failed after {attempts} attempts"
            handled_ok = True
        else:
            log_summary = f"Failed to archive permanently failed job {job_data.get('id')}"
            handled_ok = False
        
        logger.error(log_summary)
        
        if job_tracer:
            # Attach context to tracer; include original exception
            job_tracer.record_error(summary=log_summary, exc=error)
        
        return (True, handled_ok)  # permanent, maybe handled_ok False if archive failed
    
    def _handle_missing_msg_id(
            self,
            job_data: Dict[str, Any],
            error: BaseException,
            job_tracer: Optional[JobTraceMetaData],
    ) -> Tuple[bool, bool]:
        logger.error("No pgmq_msg_id found in job data (job id: %s); cannot retry/archive.", job_data.get("id"))
        if job_tracer:
            job_tracer.record_error(summary="Missing pgmq_msg_id", exc=error)
        # Treat as permanently failed but unhandled (we couldn't mutate queue state)
        return (True, False)
    
    
    
    async def get_queue_stats(self, queue_name: str = None) -> Dict[str, int]:
        """
        Get queue statistics

        Args:
            queue_name: Queue name to get stats for (uses table_name if None)

        Returns:
            Dict with queue statistics
        """
        try:
            await self._ensure_initialized()

            effective_queue_name = queue_name or self.table_name

            # Get queue metrics from PGMQueue
            metrics = await self.queue.metrics(effective_queue_name)

            stats = {
                "queued": metrics.queue_length,
                "total": metrics.total_messages,
                "newest_msg_age_sec": metrics.newest_msg_age_sec,
                "oldest_msg_age_sec": metrics.oldest_msg_age_sec,
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to get queue stats: {str(e)}")
            return {}

    # async def cleanup_completed_jobs(
    #     self, queue_name: str = None
    # ) -> int:
    #     """
    #     Clean up archived jobs older than specified days
    #     Note: PGMQueue handles message lifecycle differently than traditional queues
    #
    #     Args:
    #         queue_name: Queue to clean up (uses table_name if None)
    #         older_than_days: Remove jobs older than this many days
    #
    #     Returns:
    #         Number of jobs cleaned up
    #     """
    #     try:
    #         await self._ensure_initialized()
    #
    #         effective_queue_name = queue_name or self.table_name
    #         #metrics = await self.queue.metrics(effective_queue_name)
    #         # PGMQueue doesn't have a direct cleanup method for old messages
    #         # This would typically be handled by database maintenance or custom queries
    #         # For now, we'll return 0 and log that cleanup is not implemented
    #
    #         logger.info(
    #             f"Cleanup for queue {effective_queue_name} - PGMQueue handles message lifecycle automatically"
    #         )
    #         return 0
    #
    #     except Exception as e:
    #         logger.error(f"Failed to cleanup jobs: {str(e)}")
    #         return -1

    async def close(self):
        """Close the queue connection"""
        if self._initialized and self.queue:
            await self.queue.close()
            self._initialized = False
