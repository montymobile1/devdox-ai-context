import pytest
import uuid
import datetime

from models_src.test_doubles.repositories.queue_job_claim_registry import FakeQueueProcessingRegistryStore

from app.handlers.job_tracker import JobTracker, JobTrackerManager, JobLevels
from models_src.dto.queue_job_claim_registry import QueueProcessingRegistryResponseDTO
from models_src.models.queue_job_claim_registry import QRegistryStat


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

    async def test_start_marks_job_in_progress(self):
        store = FakeQueueProcessingRegistryStore()
        dto = make_dto()
        store.set_fake_data([dto])

        tracker = JobTracker("worker-1", "embed-jobs", dto, queue_processing_registry_store=store)
        await tracker.start()

        assert store.data_store[dto.id].status == QRegistryStat.IN_PROGRESS

    async def test_fail_marks_job_failed_and_updates_msg_id(self):
        store = FakeQueueProcessingRegistryStore()
        dto = make_dto()
        store.set_fake_data([dto])

        tracker = JobTracker("worker-1", "embed-jobs", dto, queue_processing_registry_store=store)
        await tracker.fail("new-msg-id")

        updated = store.data_store[dto.id]
        assert updated.status == QRegistryStat.FAILED
        assert updated.message_id == "new-msg-id"

    async def test_retry_sets_status_and_msg_id(self):
        store = FakeQueueProcessingRegistryStore()
        dto = make_dto()
        store.set_fake_data([dto])

        tracker = JobTracker("worker-1", "embed-jobs", dto, queue_processing_registry_store=store)
        await tracker.retry("retry-id")

        updated = store.data_store[dto.id]
        assert updated.status == QRegistryStat.RETRY
        assert updated.message_id == "retry-id"

    async def test_completed_sets_status_and_done_step(self):
        store = FakeQueueProcessingRegistryStore()
        dto = make_dto()
        store.set_fake_data([dto])

        tracker = JobTracker("worker-1", "embed-jobs", dto, queue_processing_registry_store=store)
        await tracker.completed()

        updated = store.data_store[dto.id]
        assert updated.status == QRegistryStat.COMPLETED
        assert updated.step == JobLevels.DONE.value

    async def test_update_step_only_changes_step(self):
        store = FakeQueueProcessingRegistryStore()
        dto = make_dto()
        store.set_fake_data([dto])

        tracker = JobTracker("worker-1", "embed-jobs", dto, queue_processing_registry_store=store)
        await tracker.update_step(JobLevels.FILE_CLONED)

        updated = store.data_store[dto.id]
        assert updated.step == JobLevels.FILE_CLONED.value


@pytest.mark.asyncio
class TestJobTrackerManager:

    async def test_claim_succeeds_when_no_previous(self):
        store = FakeQueueProcessingRegistryStore()
        store.set_fake_data([])

        manager = JobTrackerManager(queue_processing_registry_store=store)

        result = await manager.try_claim("worker-1", "msg-123", "embed-jobs")

        assert result.qualifies_for_tracking is True
        assert isinstance(result.tracker, JobTracker)

    async def test_claim_succeeds_when_previous_failed_or_retry(self):
        for status in [QRegistryStat.FAILED, QRegistryStat.RETRY]:
            store = FakeQueueProcessingRegistryStore()
            previous = make_dto(status=status)
            store.set_fake_data([previous])
            
            manager = JobTrackerManager(queue_processing_registry_store=store)
            
            result = await manager.try_claim("worker-1", previous.message_id, "embed-jobs")

            assert result.qualifies_for_tracking
            assert result.tracker is not None

    async def test_claim_fails_if_previous_is_handled(self):
        for status in [QRegistryStat.PENDING, QRegistryStat.IN_PROGRESS, QRegistryStat.COMPLETED]:
            store = FakeQueueProcessingRegistryStore()
            previous = make_dto(status=status)
            store.set_fake_data([previous])
            
            manager = JobTrackerManager(queue_processing_registry_store=store)
            
            result = await manager.try_claim("worker-1", previous.message_id, "embed-jobs")

            assert not result.qualifies_for_tracking
            assert result.tracker is None

    async def test_claim_fails_on_integrity_error(self):
        from tortoise.exceptions import IntegrityError

        store = FakeQueueProcessingRegistryStore()
        store.set_exception(store.save, IntegrityError("queue_processing_registry_message_id_idx"))
        
        manager = JobTrackerManager(queue_processing_registry_store=store)
        
        result = await manager.try_claim("worker-1", "duplicate-id", "embed-jobs")

        assert result.qualifies_for_tracking is False
        assert result.tracker is None

    async def test_claim_raises_on_unknown_exception(self):
        store = FakeQueueProcessingRegistryStore()
        store.set_exception(store.save, ValueError("bad stuff"))
        
        manager = JobTrackerManager(queue_processing_registry_store=store)
        
        with pytest.raises(ValueError):
            await manager.try_claim("worker-1", "msg-x", "embed-jobs")
