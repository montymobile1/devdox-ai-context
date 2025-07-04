"""
Test cases for queue worker
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.handlers.queue_worker import QueueWorker, WorkerHealthMonitor


class TestQueueWorker:
    """Test cases for QueueWorker class"""
    
    @pytest.fixture
    def mock_message_handler(self):
        """Mock message handler"""
        handler = MagicMock()
        handler.handle_processing_message = AsyncMock()
        return handler
    
    @pytest.fixture
    def mock_queue_service(self):
        """Mock queue service"""
        queue = MagicMock()
        queue.dequeue = AsyncMock()
        queue.complete_job = AsyncMock()
        queue.fail_job = AsyncMock()
        return queue
    
    @pytest.fixture
    def queue_worker(self, mock_message_handler, mock_queue_service):
        """Create QueueWorker instance for testing"""
        return QueueWorker(
            worker_id="test-worker",
            message_handler=mock_message_handler,
            queue_service=mock_queue_service
        )
    
    def test_init(self, queue_worker, mock_message_handler, mock_queue_service):
        """Test QueueWorker initialization"""
        assert queue_worker.worker_id == "test-worker"
        assert queue_worker.message_handler == mock_message_handler
        assert queue_worker.queue_service == mock_queue_service
        assert queue_worker.running is False
        assert queue_worker.stats["jobs_processed"] == 0
        assert queue_worker.stats["jobs_failed"] == 0
        assert queue_worker.stats["start_time"] is None
        assert queue_worker.stats["last_job_time"] is None
        assert queue_worker.stats["current_job"] is None
    
    @pytest.mark.asyncio
    async def test_start_success(self, queue_worker):
        """Test successful worker start"""

        running_during_execution = None

        async def mock_worker_loop(*args, **kwargs):
            nonlocal running_during_execution
            running_during_execution = queue_worker.running  # Capture state during execution
            await asyncio.sleep(0.1)
            return

        queue_worker._worker_loop = mock_worker_loop

        await queue_worker.start()

        assert running_during_execution is True
        assert queue_worker.stats["start_time"] is not None
        # After completion, running should be False (this is expected!)
        assert queue_worker.running is False

    
    @pytest.mark.asyncio
    @patch('asyncio.create_task')
    @patch('asyncio.gather')
    async def test_start_with_exception(self, mock_gather, mock_create_task, queue_worker):
        """Test worker start with exception"""
        mock_task = MagicMock()
        mock_create_task.return_value = mock_task
        mock_gather.side_effect = Exception("Worker failed")
        
        queue_worker._worker_loop = AsyncMock()
        
        await queue_worker.start()
        
        assert queue_worker.running is False
    
    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    async def test_stop(self, mock_sleep, queue_worker):
        """Test worker stop"""
        queue_worker.running = True
        queue_worker.stats["current_job"] = "job-123"
        
        await queue_worker.stop()
        
        assert queue_worker.running is False
        mock_sleep.assert_called_once_with(5)
    
    @pytest.mark.asyncio
    async def test_stop_without_current_job(self, queue_worker):
        """Test worker stop without current job"""
        queue_worker.running = True
        queue_worker.stats["current_job"] = None
        
        await queue_worker.stop()
        
        assert queue_worker.running is False
    
    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    @patch('app.core.config.settings')
    async def test_worker_loop_with_jobs(self, mock_settings, mock_sleep, queue_worker):
        """Test worker loop processing jobs"""
        mock_settings.QUEUE_POLLING_INTERVAL_SECONDS = 1
        
        # Mock jobs
        job1 = {"id": "job-1", "job_type": "analyze", "payload": {"test": "data1"}}
        job2 = {"id": "job-2", "job_type": "process", "payload": {"test": "data2"}}
        
        # Queue returns jobs then None to exit loop
        queue_worker.queue_service.dequeue.side_effect = [job1, job2, None]
        queue_worker._process_job = AsyncMock()
        
        # Run for 3 iterations then stop
        call_count = 0
        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                queue_worker.running = False
        
        mock_sleep.side_effect = side_effect
        queue_worker.running = True
        
        await queue_worker._worker_loop("processing", ["analyze", "process"])
        
        assert queue_worker._process_job.call_count == 2
        queue_worker._process_job.assert_any_call("processing", job1)
        queue_worker._process_job.assert_any_call("processing", job2)
    
    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    @patch('app.core.config.settings')
    async def test_worker_loop_no_jobs(self, mock_settings, mock_sleep, queue_worker):
        """Test worker loop with no jobs available"""
        mock_settings.QUEUE_POLLING_INTERVAL_SECONDS = 2
        
        # Queue always returns None (no jobs)
        queue_worker.queue_service.dequeue.return_value = None
        
        # Run for 2 iterations then stop
        call_count = 0
        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                queue_worker.running = False
        
        mock_sleep.side_effect = side_effect
        queue_worker.running = True
        
        await queue_worker._worker_loop("processing", ["analyze"])
        print(" mock_sleep.call_count ",  mock_sleep.call_count)
        # Should sleep when no jobs available
        assert mock_sleep.call_count >= 2

    

    @pytest.mark.asyncio
    @patch('time.time')
    async def test_process_job_analyze_success(self, mock_time, queue_worker):
        """Test successful job processing for analyze type"""
        mock_time.side_effect = [100.0, 105.0]  # Start and end times
        
        job = {
            "id": "job-123",
            "job_type": "analyze",
            "payload": {"repo_id": "repo-456"}
        }
        
        await queue_worker._process_job("processing", job)
        
        # Verify handler was called
        queue_worker.message_handler.handle_processing_message.assert_called_once_with({"repo_id": "repo-456"})
        
        # Verify job was completed
        queue_worker.queue_service.complete_job.assert_called_once_with(job)
        
        # Verify stats updated
        assert queue_worker.stats["jobs_processed"] == 1
        assert queue_worker.stats["jobs_failed"] == 0
        assert queue_worker.stats["current_job"] is None
        assert queue_worker.stats["last_job_time"] is not None
    
    @pytest.mark.asyncio
    @patch('time.time')
    async def test_process_job_process_success(self, mock_time, queue_worker):
        """Test successful job processing for process type"""
        mock_time.side_effect = [100.0, 103.0]
        
        job = {
            "id": "job-456",
            "job_type": "process",
            "payload": {"context_id": "ctx-789"}
        }
        
        await queue_worker._process_job("processing", job)
        
        queue_worker.message_handler.handle_processing_message.assert_called_once_with({"context_id": "ctx-789"})
        queue_worker.queue_service.complete_job.assert_called_once_with(job)
        assert queue_worker.stats["jobs_processed"] == 1
    
    @pytest.mark.asyncio
    @patch('time.time')
    async def test_process_job_unknown_type(self, mock_time, queue_worker):
        """Test job processing with unknown job type"""
        mock_time.side_effect = [100.0, 102.0]
        
        job = {
            "id": "job-789",
            "job_type": "unknown",
            "payload": {"data": "test"}
        }
        
        await queue_worker._process_job("processing", job)
        
        # Handler should not be called for unknown type
        queue_worker.message_handler.handle_processing_message.assert_not_called()
        
        # Job should still be completed (no error occurred)
        queue_worker.queue_service.complete_job.assert_called_once_with(job)
        assert queue_worker.stats["jobs_processed"] == 1
    
    @pytest.mark.asyncio
    @patch('time.time')
    async def test_process_job_handler_failure(self, mock_time, queue_worker):
        """Test job processing with handler failure"""
        mock_time.side_effect = [100.0, 103.0]
        
        job = {
            "id": "job-fail",
            "job_type": "analyze",
            "payload": {"repo_id": "repo-456"}
        }
        
        # Make handler fail
        queue_worker.message_handler.handle_processing_message.side_effect = Exception("Handler error")
        
        await queue_worker._process_job("processing", job)
        
        # Verify job was marked as failed
        queue_worker.queue_service.fail_job.assert_called_once_with("job-fail", "Handler error")
        
        # Verify stats updated
        assert queue_worker.stats["jobs_processed"] == 0
        assert queue_worker.stats["jobs_failed"] == 1
        assert queue_worker.stats["current_job"] is None
    
    @pytest.mark.asyncio
    async def test_process_job_missing_id(self, queue_worker):
        """Test job processing with missing job ID"""
        job = {
            "job_type": "analyze",
            "payload": {"repo_id": "repo-456"}
        }
        
        await queue_worker._process_job("processing", job)
        
        # Should handle gracefully with "unknown" ID
        queue_worker.message_handler.handle_processing_message.assert_called_once()
        queue_worker.queue_service.complete_job.assert_called_once_with(job)
    
    def test_get_stats(self, queue_worker):
        """Test getting worker statistics"""
        # Set some test data
        start_time =datetime.now(timezone.utc)
        queue_worker.stats["start_time"] = start_time
        queue_worker.stats["jobs_processed"] = 5
        queue_worker.stats["jobs_failed"] = 2
        queue_worker.running = True
        
        stats = queue_worker.get_stats()
        
        assert stats["worker_id"] == "test-worker"
        assert stats["running"] is True
        assert stats["jobs_processed"] == 5
        assert stats["jobs_failed"] == 2
        assert stats["start_time"] == start_time
        assert "uptime_seconds" in stats
        assert stats["uptime_seconds"] is not None
    
    def test_get_stats_no_start_time(self, queue_worker):
        """Test getting stats when no start time set"""
        stats = queue_worker.get_stats()
        
        assert stats["uptime_seconds"] is None
        assert stats["start_time"] is None


class TestWorkerHealthMonitor:
    """Test cases for WorkerHealthMonitor class"""
    
    @pytest.fixture
    def mock_workers(self):
        """Create mock workers for testing"""
        worker1 = MagicMock()
        worker1.get_stats.return_value = {
            "worker_id": "worker-1",
            "running": True,
            "jobs_processed": 10,
            "jobs_failed": 1
        }
        
        worker2 = MagicMock()
        worker2.get_stats.return_value = {
            "worker_id": "worker-2", 
            "running": False,
            "jobs_processed": 5,
            "jobs_failed": 2
        }
        
        return [worker1, worker2]
    
    @pytest.fixture
    def health_monitor(self, mock_workers):
        """Create WorkerHealthMonitor instance for testing"""
        return WorkerHealthMonitor(mock_workers)
    
    def test_init(self, health_monitor, mock_workers):
        """Test WorkerHealthMonitor initialization"""
        assert health_monitor.workers == mock_workers
    
    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    async def test_start_monitoring(self, mock_sleep, health_monitor):
        """Test starting health monitoring"""
        health_monitor._check_worker_health = AsyncMock()
        
        # Run for 2 iterations then stop
        call_count = 0
        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt()  # Stop the loop
        
        mock_sleep.side_effect = side_effect
        
        try:
            await health_monitor.start_monitoring()
        except KeyboardInterrupt:
            pass
        
        assert health_monitor._check_worker_health.call_count == 2
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(60)
    
    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    async def test_start_monitoring_with_exception(self, mock_sleep, health_monitor):
        """Test monitoring with exception in health check"""
        health_monitor._check_worker_health = AsyncMock(side_effect=Exception("Health check error"))
        
        # Run for 1 iteration then stop
        call_count = 0
        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt()
        
        mock_sleep.side_effect = side_effect
        
        try:
            await health_monitor.start_monitoring()
        except KeyboardInterrupt:
            pass
        
        # Should continue monitoring despite exception
        assert health_monitor._check_worker_health.call_count == 1
    
    @pytest.mark.asyncio
    async def test_check_worker_health(self, health_monitor, mock_workers):
        """Test worker health checking"""
        await health_monitor._check_worker_health()
        
        # Verify all workers were checked
        for worker in mock_workers:
            worker.get_stats.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_worker_health_stats_aggregation(self, health_monitor, mock_workers):
        """Test health check statistics aggregation"""
        # The method doesn't return anything, but we can test it doesn't crash
        # and that it calls get_stats on all workers
        await health_monitor._check_worker_health()
        
        # Verify stats were gathered from all workers
        assert all(worker.get_stats.called for worker in mock_workers)
    
    def test_worker_health_monitor_with_empty_workers(self):
        """Test health monitor with no workers"""
        monitor = WorkerHealthMonitor([])
        assert monitor.workers == []
    
    @pytest.mark.asyncio
    async def test_check_worker_health_empty_workers(self):
        """Test health check with no workers"""
        monitor = WorkerHealthMonitor([])
        
        # Should not crash with empty worker list
        await monitor._check_worker_health()


class TestQueueWorkerIntegration:
    """Integration tests for QueueWorker"""
    
    @pytest.mark.asyncio
    async def test_full_worker_lifecycle(self):
        """Test complete worker lifecycle"""
        mock_handler = MagicMock()
        mock_handler.handle_processing_message = AsyncMock()
        
        mock_queue = MagicMock()
        mock_queue.dequeue = AsyncMock(return_value=None)  # No jobs
        mock_queue.complete_job = AsyncMock()
        mock_queue.fail_job = AsyncMock()
        
        worker = QueueWorker(
            worker_id="integration-test",
            message_handler=mock_handler,
            queue_service=mock_queue
        )
        
        # Test initialization
        assert not worker.running
        assert worker.stats["jobs_processed"] == 0
        
        # Test stats before start
        stats = worker.get_stats()
        assert stats["worker_id"] == "integration-test"
        assert stats["uptime_seconds"] is None
        
        # Test stop when not running
        await worker.stop()
        assert not worker.running
