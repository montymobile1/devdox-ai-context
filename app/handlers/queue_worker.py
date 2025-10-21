import asyncio
import logging
import time
import traceback
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from dependency_injector.wiring import Provide, inject

from app.core.container import Container
from app.handlers.message_handler import MessageHandler
from app.infrastructure.queues.supabase_queue import SupabaseQueue
from app.core.config import settings
from app.infrastructure.mailing_service import ProjectAnalysisFailure
from app.core.mail_container import get_email_dispatcher
from app.infrastructure.job_tracer.job_trace_metadata import JobTraceMetaData
from app.infrastructure.mailing_service import Template
from app.infrastructure.mailing_service.models.context_shapes import ProjectAnalysisSuccess
from app.handlers.job_tracker import JobLevels, JobTracker, JobTrackerManager


class QueueWorker:
    """Enhanced queue worker with improved reliability and monitoring"""

    @inject
    def __init__(
        self,
        worker_id: str = "worker-1",
        message_handler: MessageHandler = Provide[Container.message_handler],
        queue_service: SupabaseQueue = Provide[Container.queue_service],
        job_tracker_manager: Optional[JobTrackerManager] = Provide[Container.job_tracker_factory],
    ):
        self.worker_id = worker_id
        self.message_handler = message_handler
        self.queue_service = queue_service
        self.running = False
        self.job_tracker_manager = job_tracker_manager or None
        self.stats = {
            "jobs_processed": 0,
            "jobs_failed": 0,
            "start_time": None,
            "last_job_time": None,
            "current_job": None,
        }

    async def start(self):
        """Start the queue worker"""
        self.running = True
        self.stats["start_time"] = datetime.now(timezone.utc)
        # Start multiple worker loops for different queue types
        tasks = [
            asyncio.create_task(self._worker_loop("processing", ["analyze", "process"]))
        ]

        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logging.error(f"Worker {self.worker_id} encountered an error: {e}")
        finally:
            self.running = False

    async def stop(self):
        """Stop the queue worker gracefully"""

        self.running = False

        # Wait for current job to complete (with timeout)
        if self.stats["current_job"]:
            await asyncio.sleep(5)  # Grace period
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics"""
        uptime = None
        if self.stats["start_time"]:
            uptime = (
                datetime.now(timezone.utc) - self.stats["start_time"]
            ).total_seconds()

        return {
            **self.stats,
            "worker_id": self.worker_id,
            "running": self.running,
            "uptime_seconds": uptime,
        }
    
    # ---------------------------------------------
    # _worker_loop
    # ---------------------------------------------
    
    async def _worker_loop(self, queue_name: str, job_types: list[str], enable_job_tracer: bool = True):
        """Worker loop for processing specific queue with job types."""
        consecutive_failures = 0
        max_failures = 5
        poll_sleep = settings.QUEUE_POLLING_INTERVAL_SECONDS or 5
        
        while self.running:
            try:
                job = await self.queue_service.dequeue(queue_name, job_types=job_types)
                if not job:
                    await asyncio.sleep(poll_sleep)
                    continue
                
                tracker = await self._try_claim(job, queue_name)
                if not tracker:
                    break

                job_tracer = JobTraceMetaData() if enable_job_tracer else None
                
                await self._process_job(
                    queue_name,
                    job,
                    job_tracker_instance=(tracker or None),
                    job_tracer=job_tracer,
                )
                
                consecutive_failures = 0  # success → reset
            except Exception:
                consecutive_failures += 1
                if await self._backoff_or_stop(consecutive_failures, max_failures):
                    break
    
    async def _try_claim(self, job: dict, queue_name: str):
        """
        Returns:
          - tracker object if claimed & tracked,
          - None if no tracking manager (still allowed to run),
          - False if not allowed to run (failed claim).
        """
        if not self.job_tracker_manager:
            return None

        result = await self.job_tracker_manager.try_claim(
            worker_id=self.worker_id,
            queue_name=queue_name,
            message_id=job.get("id"),
        )
        return result.tracker if result.qualifies_for_tracking else False
    
    
    async def _backoff_or_stop(self, failures: int, max_failures: int) -> bool:
        """Sleep with exponential backoff. Return True if we should stop the loop."""
        if failures >= max_failures:
            return True
        await asyncio.sleep(min(60, 2 ** failures))
        return False
    
    # ---------------------------------------------
    # _process_job
    # ---------------------------------------------
    
    async def _process_job(
            self,
            queue_name: str,
            job: Dict[str, Any],
            job_tracker_instance: Optional[JobTracker] = None,
            job_tracer: Optional[JobTraceMetaData] = None,
    ) -> None:
        """Process a single job with comprehensive error handling and monitoring."""
        job_id = job.get("id", "unknown")
        job_type = job.get("job_type", "unknown")
        payload = job.get("payload") or {}
        
        self._seed_tracer(job_tracer, payload, job_type)

        self.stats["current_job"] = job_id
        
        try:
            
            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.DISPATCH)
            
            await self._dispatch_job(queue_name, job_type, payload, job_tracker_instance, job_tracer)
            
            # Always complete (matches your current behavior even when dispatch no-ops)
            
            if job_tracker_instance:
                await job_tracker_instance.update_step(JobLevels.QUEUE_ACK)
            
            await self.queue_service.complete_job(
                job,
                job_tracker_instance=job_tracker_instance,
                job_tracer=job_tracer,
            )
            
            self._mark_success()
        
        except Exception as e:
            logging.exception(f"Worker {self.worker_id} encountered an error processing job {job_id}")
            self.stats["jobs_failed"] += 1
            await self._fail_job_safe(job, err=e, tracker=job_tracker_instance, job_tracer=job_tracer)
        
        finally:
            self.stats["current_job"] = None
            
            if job_tracer:
                if job_tracker_instance:
                    await job_tracker_instance.update_step(JobLevels.AUDIT_NOTIFICATIONS)
                await self.send_audit_email(job_tracer)
    
    def _seed_tracer(self, job_tracer, payload: Dict[str, Any], job_type: str) -> None:
        if not job_tracer:
            return
        job_tracer.add_metadata(
            repo_id=payload.get("repo_id"),
            user_id=payload.get("user_id"),
            job_context_id=payload.get("context_id"),
            job_type=job_type,
            repository_branch=payload.get("branch"),
        )
    
    async def _dispatch_job(self, queue_name: str, job_type: str, payload: Dict[str, Any],
                            tracker, job_tracer) -> None:
        """No-ops when queue/type don’t match; keeps the main flow branch-free."""
        if queue_name != "processing" or job_type not in ("analyze", "process"):
            return
        if tracker:
            await tracker.start()
        await self.message_handler.handle_processing_message(
            payload, tracker, job_tracer=job_tracer
        )
    
    def _mark_success(self) -> None:
        self.stats["jobs_processed"] += 1
        self.stats["last_job_time"] = datetime.now(timezone.utc)
    
    async def _fail_job_safe(self, job: Dict[str, Any], err: Exception, tracker, job_tracer) -> None:
        """Fail the job if possible; log/tracer on any internal failure without nesting in the caller."""
        is_perma_failure = False
        pgmq_id = job.get("pgmq_msg_id")
        if not pgmq_id:
            logging.error("No pgmq_msg_id found in job data")
            # We can still record context for visibility
            if job_tracer:
                job_tracer.record_error(summary="Missing pgmq_msg_id", exc=err)
            return
        
        try:
            is_perma_failure, _ = await self.queue_service.fail_job(
                job,
                err,
                job_tracker_instance=tracker,
                job_tracer=job_tracer,
                error_trace=traceback.format_exc(),
            )
        except Exception as internal_fail_job_exception:
            logging.exception(f"Failed to fail job {job.get('id', 'unknown')}")
            if job_tracer and is_perma_failure:
                job_tracer.record_error(
                    summary="Failed while marking job as failed",
                    exc=internal_fail_job_exception,
                )
        
    async def send_audit_email(self, job_tracer):
        try:
            if job_tracer:
                if job_tracer.has_error:
                    is_failure_email = True
                    job_tracer.mark_job_settled()
                else:
                    if not job_tracer.user_email:
                        is_failure_email = True
                        job_tracer.record_error(
                            summary="No user email has been provided to send the email to",
                        )
                    else:
                        is_failure_email = False
                    
                    job_tracer.mark_job_settled()
                
                serialized_model = job_tracer.model_dump()
                
                if is_failure_email:
                    if not settings.mail.MAIL_AUDIT_RECIPIENTS:
                        raise RuntimeError("MAIL_AUDIT_RECIPIENTS is not configured")
                    
                    context = ProjectAnalysisFailure(
                        repository_html_url=serialized_model["repository_html_url"],
                        user_email=serialized_model["user_email"],
                        repository_branch=serialized_model["repository_branch"],
                        job_context_id=serialized_model["job_context_id"],
                        job_type=serialized_model["job_type"],
                        job_queued_at=serialized_model["job_queued_at"],
                        job_started_at=serialized_model["job_started_at"],
                        job_finished_at=serialized_model["job_finished_at"],
                        job_settled_at=serialized_model["job_settled_at"],
                        error_type=serialized_model["error_type"],
                        error_summary=serialized_model["error_summary"],
                        error_chain=serialized_model["error_chain"],
                        run_ms=serialized_model["run_ms"],
                        total_ms=serialized_model["total_ms"],
                        user_id=serialized_model["user_id"],
                        repo_id=serialized_model["repo_id"],
                    )
                    
                    email_dispatcher = get_email_dispatcher()
                    await email_dispatcher.send_templated_html(
                        to=settings.mail.MAIL_AUDIT_RECIPIENTS,
                        template=Template.PROJECT_ANALYSIS_FAILURE,
                        context=context,
                    )
                else:

                    context = ProjectAnalysisSuccess(
                        repository_html_url=serialized_model.get("repository_html_url"),
                        repository_branch=serialized_model.get("repository_branch"),
                        job_type=serialized_model.get("job_type"),
                        job_queued_at=serialized_model.get("job_queued_at"),
                    )

                    email_dispatcher = get_email_dispatcher()
                    await email_dispatcher.send_templated_html(
                        to=[job_tracer.user_email],
                        template=Template.PROJECT_ANALYSIS_SUCCESS,
                        context=context,
                    )
        except Exception:
            logging.exception("Error occurred while trying to send an email")
    
    


class WorkerHealthMonitor:
    """Monitor worker health and performance"""

    def __init__(self, workers: list[QueueWorker]):
        self.workers = workers

    async def start_monitoring(self):
        """Start health monitoring loop"""
        while True:
            try:
                self._check_worker_health()
                await asyncio.sleep(60)  # Check every minute
            except Exception:
                await asyncio.sleep(60)

    def _check_worker_health(self):
        """Check health of all workers"""
        total_stats = {
            "total_workers": len(self.workers),
            "healthy_workers": 0,
            "total_jobs_processed": 0,
            "total_jobs_failed": 0,
            "workers": [],
        }

        for worker in self.workers:
            stats = worker.get_stats()
            total_stats["workers"].append(stats)

            if stats["running"]:
                total_stats["healthy_workers"] += 1

            total_stats["total_jobs_processed"] += stats["jobs_processed"]
            total_stats["total_jobs_failed"] += stats["jobs_failed"]

        # Alert if too many workers are unhealthy send email later
        # if total_stats["healthy_workers"] < total_stats["total_workers"] * 0.5:
        #
