import datetime
import logging
from enum import Enum

from app.core.exceptions.custom_exceptions import DevDoxAPIException
from models.queue_job_claim_registry import QRegistryStat, queue_processing_registry_one_claim_unique, QueueProcessingRegistry
from tortoise.exceptions import IntegrityError


class JobLevels(str, Enum):
    START = "start"
    FILE_CLONED = "file_cloned"
    GENERATE_EMBEDS= "generate_embeddings"
    STORE_EMBEDS= "store_embeds_db"
    DB_SAVED = "db_saved"
    DONE = "done"


class JobTrackerManager:
    def create_tracker(self, worker_id:str, queue_name: str) -> 'JobTracker':
        return JobTracker(worker_id, queue_name)


class JobTracker:
    def __init__(self, worker_id: str, queue_name: str):
        self.tracked_claim:QueueProcessingRegistry = None
        self.worker_id= worker_id
        self.queue_name = queue_name
        self.step = None
        
    async def try_claim(self, message_id) -> bool:
        """
        Attempt to claim the job. If already claimed for active status, return False.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        try:
            
            # Get the last message attached to this message_id if present
            previous_latest_message = await QueueProcessingRegistry.filter(message_id=message_id) \
                .order_by("-updated_at") \
                .first()
            
            if not previous_latest_message or (previous_latest_message and  previous_latest_message.status in [QRegistryStat.FAILED, QRegistryStat.RETRY]):
                
                additional_kwargs = {}
                
                if previous_latest_message:
                    additional_kwargs["previous_message_id"] = previous_latest_message.id
                
                claim = await QueueProcessingRegistry.create(
                    message_id=message_id,
                    queue_name=self.queue_name,
                    step=JobLevels.START.value,
                    status=QRegistryStat.PENDING,
                    claimed_by=self.worker_id,
                    claimed_at=now,
                    updated_at=now,
                    **additional_kwargs
                )
            
                self.step = JobLevels.START.value
                
                self.tracked_claim = claim
                
                return True
            else:
                # Already Handled or being handled
                return False
        
        except IntegrityError as e:
            
            if queue_processing_registry_one_claim_unique in str(e):
                return False  # Someone else already claimed it
            
            raise
        except Exception:
            logging.exception("Exception occurred while attempted to try_claim")
            raise
        
    async def update_step(self, step: JobLevels):
        """
        Update the job step
        """
        update_fields = []
        
        self.step = step.value
        
        self.tracked_claim.step = step.value
        update_fields.append("step")
        
        self.tracked_claim.updated_at=datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")

        await self.tracked_claim.save(update_fields=update_fields)

    async def start(self):
        """
        Mark the job as started.
        """
        update_fields = []
        
        self.tracked_claim.status = QRegistryStat.IN_PROGRESS
        update_fields.append("status")
        
        self.tracked_claim.updated_at=datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")
        
        await self.tracked_claim.save(update_fields=update_fields)
    
    async def fail(self, message_id:str):
        """
        Mark the job as failed.
        """
        update_fields = []
        
        self.tracked_claim.status = QRegistryStat.FAILED
        update_fields.append("status")
        
        self.tracked_claim.updated_at = datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")
        
        if message_id:
            self.tracked_claim.message_id = message_id
            update_fields.append("message_id")
        
        await self.tracked_claim.save(update_fields=update_fields)
    
    async def retry(self, message_id: str):
        """
        Mark the job as being retried.
        """
        update_fields = []
        
        self.tracked_claim.status = QRegistryStat.RETRY
        update_fields.append("status")
        
        self.tracked_claim.updated_at = datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")
        
        if message_id:
            self.tracked_claim.message_id = message_id
            update_fields.append("message_id")
        
        await self.tracked_claim.save(update_fields=update_fields)
    
    async def completed(self):
        """
        Mark the job as completed.
        """
        update_fields = []
        
        self.tracked_claim.status = QRegistryStat.COMPLETED
        update_fields.append("status")

        self.tracked_claim.step = JobLevels.DONE.value
        update_fields.append("step")

        self.tracked_claim.updated_at = datetime.datetime.now(datetime.timezone.utc)
        update_fields.append("updated_at")
        
        await self.tracked_claim.save(update_fields=update_fields)
