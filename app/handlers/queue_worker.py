import asyncio
import logging
import time
from typing import Dict, Any
from datetime import datetime, timezone
from dependency_injector.wiring import Provide, inject

from app.core.container import Container
from app.handlers.message_handler import MessageHandler
from app.infrastructure.queues.supabase_queue import SupabaseQueue
from app.core.config import settings


class QueueWorker:
    """Enhanced queue worker with improved reliability and monitoring"""

    @inject
    def __init__(
        self,
        worker_id: str = "worker-1",
        message_handler: MessageHandler = Provide[Container.message_handler],
        queue_service: SupabaseQueue = Provide[Container.queue_service],
    ):
        self.worker_id = worker_id
        self.message_handler = message_handler
        self.queue_service = queue_service
        self.running = False
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

    async def _worker_loop(self, queue_name: str, job_types: list):
        """Worker loop for processing specific queue with job types"""

        consecutive_failures = 0
        max_failures = 5

        while self.running:
            try:
                job = await self.queue_service.dequeue(queue_name, job_types=job_types)
                if job:
                    consecutive_failures = 0  # Reset failure counter
                    await self._process_job(queue_name, job)
                else:
                    # No jobs available, wait before checking again
                    await asyncio.sleep(settings.QUEUE_POLLING_INTERVAL_SECONDS or 5)

            except Exception:
                
                consecutive_failures += 1

                # Exponential backoff for consecutive failures
                if consecutive_failures >= max_failures:
                    break

                backoff_time = min(60, 2**consecutive_failures)
                await asyncio.sleep(backoff_time)

    async def _process_job(self, queue_name: str, job: Dict[str, Any]):
        """Process a single job with comprehensive error handling and monitoring"""
        job_id = job.get("id", "unknown")
        job_type = job.get("job_type", "unknown")
        payload = job.get("payload", {})

        _ = time.time()
        self.stats["current_job"] = job_id

        try:
            # Route job to appropriate handler based on queue and type
            if queue_name == "processing" and job_type in ["analyze", "process"]:
                await self.message_handler.handle_processing_message(payload)

            # Mark job as completed
            await self.queue_service.complete_job(job)

            # Update statistics
            self.stats["jobs_processed"] += 1
            self.stats["last_job_time"] = datetime.now(timezone.utc)

        except Exception as e:
            logging.error(
                f"Worker {self.worker_id} encountered an error processing job {job_id}: {e}"
            )
            self.stats["jobs_failed"] += 1

            # Mark job as failed with error details
            await self.queue_service.fail_job(job_id, str(e))

        finally:
            self.stats["current_job"] = None

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
