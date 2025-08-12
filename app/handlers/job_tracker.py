"""
Job Tracking Module for Queue-Based Processing

This module provides a robust system for tracking the lifecycle of background jobs
claimed from a distributed queue. It manages status transitions, step updates, and
ensures single-claim integrity using the `QueueProcessingRegistry` model.

Main entry point:
-----------------
- `JobTrackerManager`: Is the main entry point for claiming jobs and producing a ready-to-use
  `JobTracker` instance if the claim is successful.

Usage Example:
--------------
```python
claim_result = await JobTrackerManager.try_claim(worker_id, message_id, queue_name)
if claim_result.qualifies_for_tracking:
    tracker = claim_result.tracker
    await tracker.start()
    await tracker.update_step(JobLevels.FILE_CLONED)
    ...
```
"""
import datetime
import logging
from enum import Enum
from typing import NamedTuple, Optional

from models.queue_job_claim_registry import QRegistryStat, queue_processing_registry_one_claim_unique, QueueProcessingRegistry
from tortoise.exceptions import IntegrityError


class JobLevels(str, Enum):
    """
    Enumerates the lifecycle steps of a background job.

    Each step represents a logical phase in the job processing pipeline.
    The values are persisted in the database for tracking progress.
    """
    START = "start"
    FILE_CLONED = "file_cloned"
    GENERATE_EMBEDS = "generate_embeddings"
    STORE_EMBEDS = "store_embeds_db"
    DB_SAVED = "db_saved"
    DONE = "done"


class JobTracker:
    """
    Represents a claimed job and provides operations to update its state.

    This class wraps a `QueueProcessingRegistry` record and exposes async methods
    to manage status transitions and job step updates.

    Instances are constructed only through `JobTrackerManager.try_claim`.
    """
    def __init__(
        self, worker_id: str, queue_name: str, tracked_claim:QueueProcessingRegistry, initial_step: Optional[JobLevels] = None
    ):
        """
        __tracked_claim: The ORM database Object of the claimed job.
        __worker_id: Name of the processing queue.
        __queue_name: The DB record representing the claimed job.
        __step: Current logical step in the job's lifecycle.
        """
        self.__tracked_claim: QueueProcessingRegistry = tracked_claim
        self.__worker_id = worker_id
        self.__queue_name = queue_name
        self.__step = initial_step
    
    @property
    def tracked_claim(self) -> QueueProcessingRegistry:
        return self.__tracked_claim

    @property
    def worker_id(self) -> str:
        return self.__worker_id

    @property
    def queue_name(self) -> str:
        return self.__queue_name

    @property
    def step(self) -> Optional[JobLevels]:
        return self.__step
    
    async def update_step(self, step: JobLevels):
        """
        Updates the job's current step in both memory and database.

        Args:
            step (JobLevels): The new step to assign.
        """
        update_fields = []
        
        self.__step = step

        self.__tracked_claim.step = step.value
        update_fields.append("step")

        self.__tracked_claim.updated_at = datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")

        await self.__tracked_claim.save(update_fields=update_fields)

    async def start(self):
        """
        Marks the job as IN_PROGRESS in both memory and database.
        """
        update_fields = []

        self.__tracked_claim.status = QRegistryStat.IN_PROGRESS
        update_fields.append("status")

        self.__tracked_claim.updated_at = datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")

        await self.__tracked_claim.save(update_fields=update_fields)

    async def fail(self, message_id: Optional[str]=None):
        """
        Marks the job as FAILED and optionally updates its message ID in database.

        Args:
            message_id (str): The ID of the failed message (if different from the original).
        """
        update_fields = []

        self.__tracked_claim.status = QRegistryStat.FAILED
        update_fields.append("status")

        self.__tracked_claim.updated_at = datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")

        if message_id:
            self.__tracked_claim.message_id = message_id
            update_fields.append("message_id")

        await self.__tracked_claim.save(update_fields=update_fields)

    async def retry(self, message_id: str):
        """
        Marks the job as being RETRIED and optionally updates its message ID in the database.

        Args:
            message_id (str): The ID of the retried message (if different from the original).
        """
        update_fields = []

        self.__tracked_claim.status = QRegistryStat.RETRY
        update_fields.append("status")

        self.__tracked_claim.updated_at = datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")

        if message_id:
            self.__tracked_claim.message_id = message_id
            update_fields.append("message_id")

        await self.__tracked_claim.save(update_fields=update_fields)

    async def completed(self):
        """
        Marks the job as COMPLETED and sets its step and statues to DONE in databsase.
        """
        update_fields = []

        self.__tracked_claim.status = QRegistryStat.COMPLETED
        update_fields.append("status")

        self.__tracked_claim.step = JobLevels.DONE.value
        update_fields.append("step")

        self.__tracked_claim.updated_at = datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")

        await self.__tracked_claim.save(update_fields=update_fields)

class ClaimResult(NamedTuple):
    """
    Represents the result of an attempted job claim.

    Attributes:
        qualifies_for_tracking (bool): Indicates whether the job was successfully claimed.
        tracker (Optional[JobTracker]): The tracker for the claimed job, or None if claim failed.
    """
    qualifies_for_tracking: bool
    tracker: Optional[JobTracker]

class JobTrackerManager:
    """
    Entry point for claiming jobs and producing JobTracker instances.

    This is the main entry point of the module. It ensures that jobs are only claimed
    when eligible, and enforces single-worker ownership per job.
    """
    @staticmethod
    async def try_claim(worker_id:str, message_id:str, queue_name:str) -> ClaimResult:
        """
        Attempts to claim a job from the queue.

        A job can only be claimed if:
        - It was never claimed before
        - Or its latest state is FAILED or RETRY

        Returns:
            ClaimResult: Whether the claim was successful, and a tracker if it was.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        try:

            # Get the last message attached to this message_id if present
            previous_latest_message = (
                await QueueProcessingRegistry.filter(message_id=message_id)
                .order_by("-message_id", "-updated_at")
                .first()
            )

            if not previous_latest_message or (
                previous_latest_message
                and previous_latest_message.status
                in [QRegistryStat.FAILED, QRegistryStat.RETRY]
            ):

                additional_kwargs = {}

                if previous_latest_message:
                    additional_kwargs["previous_message_id"] = (
                        previous_latest_message.id
                    )

                initial_step = JobLevels.START

                claim = await QueueProcessingRegistry.create(
                    message_id=message_id,
                    queue_name=queue_name,
                    step=initial_step.value,
                    status=QRegistryStat.PENDING,
                    claimed_by=worker_id,
                    claimed_at=now,
                    updated_at=now,
                    **additional_kwargs,
                )

                return ClaimResult(True, JobTracker(worker_id, queue_name, tracked_claim=claim, initial_step=initial_step))
            else:
                # Already Handled or being handled
                return ClaimResult(False, None)

        except IntegrityError as e:

            if queue_processing_registry_one_claim_unique in str(e):
                return ClaimResult(False, None)  # Someone else already claimed it

            raise
        except Exception:
            logging.exception("Exception occurred while attempted to try_claim")
            raise
