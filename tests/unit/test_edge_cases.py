"""
Edge case and error scenario tests
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.main import WorkerService
from app.handlers.queue_worker import QueueWorker
from app.services.processing_service import ProcessingService
from app.services.auth_service import AuthService
from app.infrastructure.queues.supabase_queue import SupabaseQueue
from app.core.exceptions.local_exceptions import TokenLimitExceededError
from tests.utils import TestDataFactory, MockFactory
import tempfile


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    @patch("app.main.settings")
    def test_worker_service_with_zero_workers(self, mock_settings):
        """Test worker service with zero worker concurrency"""
        service = WorkerService()

        mock_settings.WORKER_CONCURRENCY = 0

        # Should handle zero workers gracefully
        service.start_workers()

        assert len(service.workers) == 0

        assert service.running is True  # Service should still be considered running

    @pytest.mark.asyncio
    async def test_queue_worker_with_malformed_job_data(self):
        """Test queue worker handling malformed job data"""
        mock_handler = MagicMock()
        mock_handler.handle_processing_message = AsyncMock()

        mock_queue = MagicMock()
        mock_queue.dequeue = AsyncMock()
        mock_queue.complete_job = AsyncMock()
        mock_queue.fail_job = AsyncMock()

        worker = QueueWorker(
            worker_id="edge-test-worker",
            message_handler=mock_handler,
            queue_service=mock_queue,
        )

        # Test with various malformed job data
        malformed_jobs = [
            {},  # Empty job
            {"id": "job1"},  # Missing required fields
            {"id": "job2", "job_type": None, "payload": None},  # Null values
            {"id": "job3", "job_type": "", "payload": "invalid_json"},  # Invalid data
            {
                "id": "job4",
                "job_type": "analyze",
                "payload": {"nested": {"very": {"deep": {"data": "test"}}}},
            },  # Very nested
        ]

        for job_data in malformed_jobs:
            # Should handle malformed data gracefully
            await worker._process_job("processing", job_data)

            # Job should be completed even if malformed
            mock_queue.complete_job.assert_called()
            mock_queue.complete_job.reset_mock()

    @pytest.mark.asyncio
    async def test_auth_service_with_edge_case_token_limits(self):
        """Test authentication service with edge case token limits"""
        mock_user_repo = MagicMock()
        mock_api_key_repo = MagicMock()

        auth_service = AuthService(
            user_repository=mock_user_repo,
            api_key_repository=mock_api_key_repo,
            encryption_service=MagicMock(),
        )

        # Test cases with edge case token limits
        edge_cases = [
            # (current_used, limit, requested, should_pass)
            (0, 0, 1, False),  # Zero limit
            (999, 1000, 1, True),  # Exactly at limit
            (1000, 1000, 1, False),  # Exactly over limit
            (2**31 - 1, 2**31, 1, True),  # Large numbers
            (0, 1, 0, True),  # Zero tokens requested
        ]

        for used, limit, requested, should_pass in edge_cases:
            user = MockFactory.create_mock_user(
                {"token_used": used, "token_limit": limit}
            )
            mock_user_repo.find_by_user_id = AsyncMock(return_value=user)

            if should_pass:
                # Should not raise exception
                await auth_service.check_token_limit("test_user", requested)
            else:
                # Should raise TokenLimitExceededError
                with pytest.raises(TokenLimitExceededError):
                    await auth_service.check_token_limit("test_user", requested)

    @pytest.mark.asyncio
    async def test_queue_service_with_extreme_message_sizes(self):
        """Test queue service with extremely large messages"""
        queue_config = {
            "host": "localhost",
            "port": "5432",
            "user": "test_user",
            "password": "test_password",
            "db_name": "test_db",
        }

        with patch(
            "app.infrastructure.queues.supabase_queue.PGMQueue"
        ) as mock_pgmqueue_class:
            mock_queue = MagicMock()
            mock_queue.init = AsyncMock()
            mock_queue.send = AsyncMock(return_value="large_job_id")
            mock_pgmqueue_class.return_value = mock_queue

            queue = SupabaseQueue(**queue_config)

            # Test with extremely large payload
            large_payload = {
                "data": "x" * 1000000,  # 1MB of data
                "nested": {
                    "deep": {"very": {"nested": {"data": "y" * 500000}}}
                },  # Deeply nested
            }

            # Should handle large payloads
            job_id = await queue.enqueue("test", large_payload)

            assert job_id == "large_job_id"
            mock_queue.send.assert_called_once()


class TestErrorRecoveryScenarios:
    """Test error recovery and resilience scenarios"""

    @pytest.mark.asyncio
    async def test_worker_service_recovery_from_database_failure(self):
        """Test worker service recovery from database connection failure"""
        service = WorkerService()

        # First initialization fails
        with patch("app.main.Tortoise.init") as mock_tortoise_init:
            mock_tortoise_init.side_effect = [
                Exception("Database connection failed"),  # First attempt fails
                None,  # Second attempt succeeds
            ]

            # First attempt should fail
            with pytest.raises(Exception):
                await service.initialize()

            # Second attempt should succeed
            await service.initialize()

            assert mock_tortoise_init.call_count == 2

    @pytest.mark.asyncio
    async def test_processing_service_recovery_from_git_failures(self):
        """Test processing service recovery from git operation failures"""
        mock_repos = {
            "context": MagicMock(),
            "user": MagicMock(),
            "repo": MagicMock(),
            "git_label": MagicMock(),
            "code_chunks": MagicMock(),
        }

        for repo in mock_repos.values():
            repo.update_status = AsyncMock()
            repo.find_by_repo_id = AsyncMock()

        processing_service = ProcessingService(
            context_repository=mock_repos["context"],
            user_info=mock_repos["user"],
            repo_repository=mock_repos["repo"],
            git_label_repository=mock_repos["git_label"],
            encryption_service=MockFactory.create_mock_encryption_service(),
            code_chunks_repository=mock_repos["code_chunks"],
        )

        # Mock repository to exist
        mock_repos["repo"].find_by_repo_id.return_value = MockFactory.create_mock_repo()

        # Git operations fail in various ways
        git_failures = [
            Exception("Git clone failed"),
            Exception("Git authentication failed"),
            Exception("Repository not found"),
            Exception("Network timeout"),
        ]

        for failure in git_failures:
            processing_service._get_authenticated_git_client = AsyncMock(
                side_effect=failure
            )

            payload = TestDataFactory.create_job_payload()
            result = await processing_service.process_repository(payload)

            # Should handle failure gracefully
            assert result.success is False
            assert failure.args[0] in result.error_message

            # Should update context status to failed
            mock_repos["context"].update_status.assert_called()

    @pytest.mark.asyncio
    async def test_queue_service_recovery_from_connection_issues(self):
        """Test queue service recovery from connection issues"""
        queue_config = {
            "host": "localhost",
            "port": "5432",
            "user": "test_user",
            "password": "test_password",
            "db_name": "test_db",
        }

        with patch(
            "app.infrastructure.queues.supabase_queue.PGMQueue"
        ) as mock_pgmqueue_class:
            mock_queue = MagicMock()

            # Connection fails initially then succeeds
            mock_queue.init = AsyncMock(
                side_effect=[Exception("Connection failed"), None]  # Success on retry
            )
            mock_queue.send = AsyncMock(return_value="job_id")
            mock_pgmqueue_class.return_value = mock_queue

            queue = SupabaseQueue(**queue_config)

            # First initialization should fail
            with pytest.raises(Exception):
                await queue._ensure_initialized()

            # Reset the side effect for success
            mock_queue.init.side_effect = None
            mock_queue.init.return_value = None

            # Second attempt should succeed
            await queue._ensure_initialized()

            assert queue._initialized is True


class TestMemoryAndResourceManagement:
    """Test memory and resource management edge cases"""

    @pytest.mark.asyncio
    async def test_worker_memory_cleanup_after_processing(self):
        """Test that workers clean up memory after processing jobs"""
        mock_handler = MagicMock()
        mock_handler.handle_processing_message = AsyncMock()

        mock_queue = MagicMock()
        mock_queue.dequeue = AsyncMock(return_value=None)
        mock_queue.complete_job = AsyncMock()

        worker = QueueWorker(
            worker_id="memory-test-worker",
            message_handler=mock_handler,
            queue_service=mock_queue,
        )

        # Process a job that creates large objects
        large_job = {
            "id": "large_job",
            "job_type": "analyze",
            "payload": {
                "large_data": "x" * 1000000,  # 1MB string
                "nested": {"data": ["item"] * 100000},  # Large list
            },
        }

        initial_stats = worker.get_stats()

        await worker._process_job("processing", large_job)

        # Worker should clean up and not hold references to large objects
        final_stats = worker.get_stats()

        # Current job should be None (cleaned up)
        assert final_stats["current_job"] is None

        # Job should be marked as processed
        assert final_stats["jobs_processed"] == initial_stats["jobs_processed"] + 1

    @pytest.mark.asyncio
    async def test_processing_service_resource_cleanup_on_failure(self):
        """Test that processing service cleans up resources on failure"""
        mock_repos = {
            "context": MagicMock(),
            "user": MagicMock(),
            "repo": MagicMock(),
            "git_label": MagicMock(),
            "code_chunks": MagicMock(),
        }

        for repo in mock_repos.values():
            repo.update_status = AsyncMock()
            repo.find_by_repo_id = AsyncMock()

        processing_service = ProcessingService(
            context_repository=mock_repos["context"],
            user_info=mock_repos["user"],
            repo_repository=mock_repos["repo"],
            git_label_repository=mock_repos["git_label"],
            encryption_service=MockFactory.create_mock_encryption_service(),
            code_chunks_repository=mock_repos["code_chunks"],
        )

        # Mock failure during processing
        mock_repos["repo"].find_by_repo_id.return_value = MockFactory.create_mock_repo()
        processing_service._get_authenticated_git_client = AsyncMock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            processing_service.prepare_repository = AsyncMock(return_value=tmp_dir)

        processing_service.clone_and_process_repository = MagicMock(
            side_effect=Exception("Processing failed halfway")
        )

        payload = TestDataFactory.create_job_payload()

        # Processing should fail but clean up properly
        result = await processing_service.process_repository(payload)

        assert result.success is False
        assert "Processing failed halfway" in result.error_message

        # Should still update context status (cleanup action)
        mock_repos["context"].update_status.assert_called()

    @pytest.mark.asyncio
    async def test_queue_connection_cleanup(self):
        """Test that queue connections are properly cleaned up"""
        queue_config = {
            "host": "localhost",
            "port": "5432",
            "user": "test_user",
            "password": "test_password",
            "db_name": "test_db",
        }

        with patch(
            "app.infrastructure.queues.supabase_queue.PGMQueue"
        ) as mock_pgmqueue_class:
            mock_queue = MagicMock()
            mock_queue.init = AsyncMock()
            mock_queue.close = AsyncMock()
            mock_pgmqueue_class.return_value = mock_queue

            queue = SupabaseQueue(**queue_config)

            # Initialize connection
            await queue._ensure_initialized()
            assert queue._initialized is True

            # Close connection
            await queue.close()

            # Should clean up properly
            mock_queue.close.assert_called_once()
            assert queue._initialized is False


class TestRaceConditionSimulation:
    """Test race condition scenarios"""

    @pytest.mark.asyncio
    async def test_concurrent_worker_startup_and_shutdown(self):
        """Test concurrent worker startup and shutdown"""
        service = WorkerService()

        # Mock successful initialization
        with patch("app.main.Tortoise.init") as mock_tortoise_init:
            with patch("app.main.QueueWorker") as mock_worker_class:
                with patch("app.core.config.settings") as mock_settings:
                    mock_settings.WORKER_CONCURRENCY = 3
                    mock_tortoise_init.return_value = None

                    # Create mock workers
                    mock_workers = [MagicMock() for _ in range(3)]
                    for worker in mock_workers:
                        worker.start = AsyncMock()
                        worker.stop = AsyncMock()
                    mock_worker_class.side_effect = mock_workers

                    # Initialize service
                    await service.initialize()

                    # Start and shutdown concurrently
                    startup_task = asyncio.create_task(
                        asyncio.to_thread(service.start_workers)
                    )

                    # Small delay then shutdown
                    await asyncio.sleep(0.01)
                    shutdown_task = asyncio.create_task(service.shutdown())

                    # Wait for both to complete
                    await asyncio.gather(
                        startup_task, shutdown_task, return_exceptions=True
                    )

                    # Service should handle concurrent operations gracefully
                    assert service.running is False  # Should end up stopped

    @pytest.mark.asyncio
    async def test_concurrent_job_processing_same_queue(self):
        """Test concurrent job processing from same queue"""
        mock_handler = MagicMock()
        mock_handler.handle_processing_message = AsyncMock()

        mock_queue = MagicMock()

        # Queue returns different jobs for concurrent workers
        job_counter = 0

        async def mock_dequeue(*args, **kwargs):
            nonlocal job_counter
            job_counter += 1
            if job_counter <= 5:
                return {
                    "id": f"job_{job_counter}",
                    "job_type": "analyze",
                    "payload": {"repo_id": f"repo_{job_counter}"},
                }
            return None

        mock_queue.dequeue = mock_dequeue
        mock_queue.complete_job = AsyncMock()

        # Create multiple workers processing concurrently
        workers = []
        for i in range(3):
            worker = QueueWorker(
                worker_id=f"concurrent-worker-{i}",
                message_handler=mock_handler,
                queue_service=mock_queue,
            )
            workers.append(worker)

        # Start all workers concurrently
        tasks = []
        for worker in workers:
            worker.running = True
            task = asyncio.create_task(worker._worker_loop("processing", ["analyze"]))
            tasks.append(task)

        # Let them run briefly
        await asyncio.sleep(0.1)

        # Stop all workers
        for worker in workers:
            worker.running = False

        # Wait for completion
        await asyncio.gather(*tasks, return_exceptions=True)

        # Verify jobs were processed
        total_processed = sum(
            worker.get_stats()["jobs_processed"] for worker in workers
        )
        assert total_processed > 0
        assert total_processed <= 5  # Should not exceed available jobs
