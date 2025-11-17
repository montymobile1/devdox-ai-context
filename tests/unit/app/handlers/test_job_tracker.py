import pytest
import uuid
import datetime

from models_src import (
    GenericFakeStore, InMemoryQueueProcessingRegistryBackend, JobAlreadyClaimed, QueueProcessingRegistryResponseDTO, QRegistryStat, QueueProcessingRegistryStore,
)
from pymongo.errors import OperationFailure

from app.handlers.job_tracker import JobTracker, JobTrackerManager, JobLevels


def make_dto(**overrides):
    base = dict(
        id=uuid.uuid4(),
        message_id="msg-123",
        queue_name="embed-jobs",
        step="start",
        status=QRegistryStat.PENDING,
        claimed_by="worker-1",
        previous_message_id=None,
        claimed_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc),
    )
    base.update(overrides)
    return QueueProcessingRegistryResponseDTO(**base)


@pytest.mark.asyncio
class TestJobTracker:
    
    InMemo = InMemoryQueueProcessingRegistryBackend
    FakeStore = QueueProcessingRegistryStore
    
    async def test_start_marks_job_in_progress(self):
        
        in_mem = self.InMemo()
        dto = make_dto()
        in_mem.set_fake_data([dto])
        
        fake = GenericFakeStore(
            base_store=self.FakeStore(storage_backend=in_mem)
        )
        
        tracker = JobTracker(
            "worker-1", "embed-jobs", dto, queue_processing_registry_store=fake
        )
        await tracker.start()

        assert in_mem.data_store[dto.id].status == QRegistryStat.IN_PROGRESS

    async def test_fail_marks_job_failed_and_updates_msg_id(self):
        
        in_mem = self.InMemo()
        dto = make_dto()
        in_mem.set_fake_data([dto])
        
        fake = GenericFakeStore(
            base_store=self.FakeStore(storage_backend=in_mem)
        )
        
        tracker = JobTracker(
            "worker-1", "embed-jobs", dto, queue_processing_registry_store=fake
        )
        await tracker.fail("new-msg-id")

        updated = in_mem.data_store[dto.id]
        assert updated.status == QRegistryStat.FAILED
        assert updated.message_id == "new-msg-id"

    async def test_retry_sets_status_and_msg_id(self):
        
        in_mem = self.InMemo()
        dto = make_dto()
        in_mem.set_fake_data([dto])
        
        fake = GenericFakeStore(
            base_store=self.FakeStore(storage_backend=in_mem)
        )
        
        tracker = JobTracker(
            "worker-1", "embed-jobs", dto, queue_processing_registry_store=fake
        )
        await tracker.retry("retry-id")

        updated = in_mem.data_store[dto.id]
        assert updated.status == QRegistryStat.RETRY
        assert updated.message_id == "retry-id"

    async def test_completed_sets_status_and_done_step(self):
        
        
        in_mem = self.InMemo()
        dto = make_dto()
        in_mem.set_fake_data([dto])
        
        fake = GenericFakeStore(
            base_store=self.FakeStore(storage_backend=in_mem)
        )
        
        tracker = JobTracker(
            "worker-1", "embed-jobs", dto, queue_processing_registry_store=fake
        )
        await tracker.completed()

        updated = in_mem.data_store[dto.id]
        assert updated.status == QRegistryStat.COMPLETED
        assert updated.step == JobLevels.DONE.value


@pytest.mark.asyncio
class TestJobTrackerManager:
    
    
    InMemo = InMemoryQueueProcessingRegistryBackend
    FakeStore = QueueProcessingRegistryStore

    async def test_claim_succeeds_when_no_previous(self):
        
        
        in_mem = self.InMemo()
        in_mem.set_fake_data([])
        
        fake = GenericFakeStore(
            base_store=self.FakeStore(storage_backend=in_mem)
        )

        manager = JobTrackerManager(queue_processing_registry_store=fake)

        result = await manager.try_claim("worker-1", "msg-123", "embed-jobs")

        assert result.qualifies_for_tracking is True
        assert isinstance(result.tracker, JobTracker)

    async def test_claim_succeeds_when_previous_failed_or_retry(self):
        for status in [QRegistryStat.FAILED, QRegistryStat.RETRY]:
            
            in_mem = self.InMemo()
            previous = make_dto(status=status)
            in_mem.set_fake_data([previous])
            
            fake = GenericFakeStore(
                base_store=self.FakeStore(storage_backend=in_mem)
            )

            manager = JobTrackerManager(queue_processing_registry_store=fake)

            result = await manager.try_claim(
                "worker-1", previous.message_id, "embed-jobs"
            )

            assert result.qualifies_for_tracking
            assert result.tracker is not None

    async def test_claim_fails_if_previous_is_handled(self):
        for status in [
            QRegistryStat.PENDING,
            QRegistryStat.IN_PROGRESS,
            QRegistryStat.COMPLETED,
        ]:
            
            in_mem = self.InMemo()
            previous = make_dto(status=status)
            in_mem.set_fake_data([previous])
            
            fake = GenericFakeStore(
                base_store=self.FakeStore(storage_backend=in_mem)
            )

            manager = JobTrackerManager(queue_processing_registry_store=fake)

            result = await manager.try_claim(
                "worker-1", previous.message_id, "embed-jobs"
            )

            assert not result.qualifies_for_tracking
            assert result.tracker is None

    async def test_claim_fails_on_integrity_error(self):
        
        fake = GenericFakeStore(
            base_store=self.FakeStore(storage_backend=self.InMemo())
        )

        fake.set_exception(
            self.FakeStore.save, OperationFailure("queue_processing_registry_message_id_idx")
        )

        manager = JobTrackerManager(queue_processing_registry_store=fake)

        result = await manager.try_claim("worker-1", "duplicate-id", "embed-jobs")
        assert result.qualifies_for_tracking is False
        assert result.tracker is None

    async def test_claim_raises_on_unknown_exception(self):
        
        fake = GenericFakeStore(
            base_store=self.FakeStore(storage_backend=self.InMemo())
        )
        
        fake.set_exception(self.FakeStore.save, ValueError("bad stuff"))

        manager = JobTrackerManager(queue_processing_registry_store=fake)

        result = await manager.try_claim("worker-1", "msg-x", "embed-jobs")
        assert result.qualifies_for_tracking is False
        assert result.tracker is None
    
    async def test_already_claimed(self):
        
        fake = GenericFakeStore(
            base_store=self.FakeStore(storage_backend=self.InMemo())
        )
        
        fake.set_exception(
            self.FakeStore.save, JobAlreadyClaimed()
        )

        manager = JobTrackerManager(queue_processing_registry_store=fake)

        result = await manager.try_claim("worker-1", "duplicate-id", "embed-jobs")
        assert result.qualifies_for_tracking is False
        assert result.tracker is None
