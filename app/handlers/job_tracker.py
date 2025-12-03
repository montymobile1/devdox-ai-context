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
import asyncio

from models_src import (
    get_active_qpr_store,
    JobAlreadyClaimed,
    QueueProcessingRegistryResponseDTO, QueueProcessingRegistryRequestDTO,
    QRegistryStat,
)
from pymongo.errors import OperationFailure

class JobLevels(str, Enum):
    """
    Enumerates the lifecycle steps of a background job.

    Each step represents a logical phase in the job processing pipeline.
    The values are persisted in the database for tracking progress.
    """

    START = "start"  # set on successful claim
    DISPATCH = "dispatch"  # worker is dispatching the job
    PROCESSING = "processing"  # message handler took over
    PRECHECKS = "prechecks"  # validating inputs / fetching repo record
    AUTH = "auth"  # building authenticated git client
    WORKDIR = "workdir"  # preparing local work directory
    SOURCE_FETCH = "source_fetch"  # cloning / loading repo contents
    CHUNKING = "chunking"  # splitting docs/files into chunks
    ANALYSIS = "analysis"  # repository analysis phase (README/deps/etc.)
    EMBEDDINGS = "embeddings"  # embedding generation phase
    VECTOR_STORE = "vector_store"  # persisting vectors/metadata
    CONTEXT_FINALIZE = "context_finalize"  # updating domain context (status, counts)
    QUEUE_ACK = "queue_ack"  # acknowledging/finishing the queue message
    AUDIT_NOTIFICATIONS = "audit_notifications"  # emails/audit notifications phase
    DONE = "done"  # terminal phase


class JobTracker:
    """
    Represents a claimed job instance and provides operations to update its state.

    This class wraps a `QueueProcessingRegistry` record and exposes async methods
    to manage status transitions and job step updates.

    Instances are constructed only through `JobTrackerManager.try_claim`.
    """

    def __init__(
        self,
        worker_id: str,
        queue_name: str,
        tracked_claim: QueueProcessingRegistryResponseDTO,
        initial_step: Optional[JobLevels] = None,
        queue_processing_registry_store=None,
    ):
        """
        __tracked_claim: The ORM database Object of the claimed job.
        __worker_id: Name of the processing queue.
        __queue_name: The DB record representing the claimed job.
        __step: Current logical step in the job's lifecycle.
        __queue_processing_registry_store: Repository for queue job tracker
        """
        self.__tracked_claim: QueueProcessingRegistryResponseDTO = tracked_claim
        self.__queue_processing_registry_store = (
            queue_processing_registry_store or get_active_qpr_store()
        )
        self.__worker_id = worker_id
        self.__queue_name = queue_name
        self.__step = initial_step

    @property
    def tracked_claim(self) -> QueueProcessingRegistryResponseDTO:
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
        # As sometimes the self.tracked_claim  is False
        if self.tracked_claim and self.tracked_claim.id:
            await self.__queue_processing_registry_store.update_step_by_id(
                id=str(self.tracked_claim.id), step=step.value
            )

        self.__step = step

    async def start(self):
        """
        Marks the job as IN_PROGRESS in both memory and database.
        """

        await self.__queue_processing_registry_store.update_status_or_message_id_by_id(
            id=str(self.tracked_claim.id), status=QRegistryStat.IN_PROGRESS
        )

    async def fail(self, message_id: Optional[str] = None):
        """
        Marks the job as FAILED and optionally updates its message ID in database.

        Args:
            message_id (str): The ID of the failed message (if different from the original).
        """
        await self.__queue_processing_registry_store.update_status_or_message_id_by_id(
            id=str(self.tracked_claim.id),
            status=QRegistryStat.FAILED,
            message_id=message_id,
        )

    async def retry(self, message_id: str):
        """
        Marks the job as being RETRIED and optionally updates its message ID in the database.

        Args:
            message_id (str): The ID of the retried message (if different from the original).
        """
        await self.__queue_processing_registry_store.update_status_or_message_id_by_id(
            id=str(self.tracked_claim.id),
            status=QRegistryStat.RETRY,
            message_id=message_id,
        )

    async def completed(self):
        """
        Marks the job as COMPLETED and sets its step and statues to DONE in databsase.
        """
        await self.__queue_processing_registry_store.update_status_and_step_by_id(
            id=str(self.tracked_claim.id),
            status=QRegistryStat.COMPLETED,
            step=JobLevels.DONE.value,
        )

        self.__step = JobLevels.DONE


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

    def __init__(self, queue_processing_registry_store=None):
        self.__queue_processing_registry_store = (
            queue_processing_registry_store or get_active_qpr_store()
        )

    async def try_claim(
        self, worker_id: str, message_id: str, queue_name: str
    ) -> ClaimResult:
        """
        Attempts to claim a job from the queue.

        A job can be claimed if:
        - It was never claimed before
        - Or its latest state is FAILED or RETRY

        Returns:
            ClaimResult: whether the claim succeeded and a JobTracker if yes
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        try:
            # --- Step 1: Retrieve latest message status ---
            previous_latest_message = await self.__queue_processing_registry_store.find_previous_latest_message_by_message_id(
                message_id=message_id,
            )

            logging.debug(
                f"Previous latest message for {message_id}: {previous_latest_message}"
            )

            # --- Step 2: Check eligibility for claiming ---
            if previous_latest_message and previous_latest_message.status not in [
                QRegistryStat.FAILED,
                QRegistryStat.RETRY,
            ]:
                logging.info(
                    f"Job {message_id} already handled or in progress by another worker"
                )

                return ClaimResult(False, None)

            # --- Step 3: Attempt to create claim entry with retries ---
            initial_step = JobLevels.START
            dto = QueueProcessingRegistryRequestDTO(
                message_id=message_id,
                queue_name=queue_name,
                step=initial_step.value,
                status=QRegistryStat.PENDING,
                claimed_by=worker_id,
                claimed_at=now,
                previous_message_id=(
                    previous_latest_message.id if previous_latest_message else None
                ),
            )

            claim = await self._save_with_retries(dto)
            if claim is False:
                logging.warning(f"Failed to save claim for {message_id} after retries")
                return ClaimResult(False, None)

            logging.info(f"Worker {worker_id} successfully claimed job {message_id}")

            return ClaimResult(
                True,
                tracker=JobTracker(
                    worker_id,
                    queue_name,
                    tracked_claim=claim,
                    initial_step=initial_step,
                ),
            )

        except JobAlreadyClaimed:
            # Likely a race condition — someone else claimed first
            logging.warning(
                f"Worker {worker_id} failed to claim {message_id} — already claimed"
            )
            return ClaimResult(False, None)
        
        except (asyncio.TimeoutError, OperationFailure) as e:
            logging.error(
                f"Database connection timeout while claiming job {message_id}: {e}"
            )
            raise

        except Exception as e:
            logging.exception(
                f"Unexpected error while attempting to claim job {message_id}: {e}"
            )
            raise

    # ----------------------------------------------------------------------
    # Internal helper with retries for transient DB/network issues
    # ----------------------------------------------------------------------

    async def _save_with_retries(self, dto, max_retries: int = 3, delay: float = 1.0):
        """Attempts to save the claim record with limited retries."""
        for attempt in range(1, max_retries + 1):
            try:
                claim = await asyncio.wait_for(
                    self.__queue_processing_registry_store.save(dto),
                    timeout=15.0,  # hard cap per insert attempt
                )
                return claim
            except asyncio.TimeoutError:
                logging.warning(
                    f"[Attempt {attempt}/{max_retries}] Timeout while saving claim for {dto.message_id}"
                )

            except OperationFailure as e:

                logging.warning(
                    f"[Attempt {attempt}/{max_retries}] DB operation failed (possibly transient): {e}"
                )
            except Exception as e:

                logging.error(
                    f"[Attempt {attempt}/{max_retries}] Unexpected error during save: {e}"
                )

            if attempt < max_retries:
                await asyncio.sleep(delay * attempt)  # exponential backoff

        # If all retries fail, raise an explicit error
        return False
