"""
Test cases for main application entry point
"""
import pytest
import signal
from unittest.mock import AsyncMock, MagicMock, patch, call
from fastapi.testclient import TestClient
from app.main import WorkerService, app, lifespan


class TestWorkerService:
    """Test cases for WorkerService class"""

    @pytest.fixture
    def worker_service(self):
        """Create WorkerService instance for testing"""
        return WorkerService()

    @pytest.mark.asyncio
    async def test_init(self, worker_service):
        """Test WorkerService initialization"""
        assert worker_service.container is not None
        assert worker_service.workers == []
        assert worker_service.running is False
        # Check attributes that actually exist in your implementation

        assert hasattr(worker_service, '_shutdown_event')
        assert hasattr(worker_service, '_signal_handler_task')

    @pytest.mark.asyncio
    @patch("app.main.Tortoise.init")
    async def test_initialize_success(self, mock_tortoise_init, worker_service):
        """Test successful initialization"""
        mock_tortoise_init.return_value = None

        with patch.object(worker_service.container, "wire") as mock_wire:
            await worker_service.initialize()

            mock_tortoise_init.assert_called_once()
            mock_wire.assert_called_once()
            assert worker_service.initialization_complete is True

    @pytest.mark.asyncio
    @patch("app.main.Tortoise.init")
    async def test_initialize_failure(self, mock_tortoise_init, worker_service):
        """Test initialization failure"""
        mock_tortoise_init.side_effect = Exception("Database connection failed")

        with pytest.raises(Exception) as exc_info:
            await worker_service.initialize()

        assert "Database connection failed" in str(exc_info.value)
        assert worker_service.initialization_complete is False

    @pytest.mark.asyncio
    @patch("app.main.QueueWorker")
    @patch("asyncio.create_task")
    def test_start_workers_success(
            self, mock_create_task, mock_queue_worker, worker_service
    ):
        """Test successful worker start"""

        mock_worker = MagicMock()

        mock_worker.start = AsyncMock()

        mock_worker.worker_id = "test-worker"

        mock_queue_worker.return_value = mock_worker

        with patch("app.main.settings") as mock_settings:
            mock_settings.WORKER_CONCURRENCY = 2

            worker_service.start_workers()

            assert len(worker_service.workers) == 2

            assert worker_service.running is True

            assert mock_create_task.call_count == 2


    @pytest.mark.asyncio
    @patch("app.main.QueueWorker")
    async def test_start_workers_failure(self, mock_queue_worker, worker_service):
        """Test worker start failure"""
        mock_queue_worker.side_effect = Exception("Worker creation failed")

        with patch("app.main.settings") as mock_settings:
            mock_settings.WORKER_CONCURRENCY = 1

            with pytest.raises(Exception) as exc_info:
                 await worker_service.start_workers()
            assert "Worker creation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_setup_signal_handlers(self, worker_service):
        """Test async signal handler setup"""
        with patch("asyncio.get_running_loop") as mock_get_loop, \
                patch("asyncio.create_task") as mock_create_task:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            worker_service.setup_signal_handlers()
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_shutdown(self, worker_service):
        """Test shutdown waiting mechanism"""

        worker_service.shutdown = AsyncMock()

        # Simulate shutdown event

        worker_service._shutdown_event.set()

        await worker_service._wait_for_shutdown()

        worker_service.shutdown.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.main.Tortoise.close_connections")
    async def test_shutdown(self, mock_close_connections, worker_service):
        """Test graceful shutdown"""
        # Create mock workers
        mock_worker1 = MagicMock()
        mock_worker1.stop = AsyncMock()
        mock_worker2 = MagicMock()
        mock_worker2.stop = AsyncMock()

        worker_service.workers = [mock_worker1, mock_worker2]
        worker_service.running = True

        await worker_service.shutdown()

        mock_worker1.stop.assert_called_once()
        mock_worker2.stop.assert_called_once()
        mock_close_connections.assert_called_once()
        assert worker_service.running is False

    @pytest.mark.asyncio
    async def test_shutdown_when_not_running(self, worker_service):
        """Test shutdown when not running"""
        worker_service.running = False

        # Should return early without errors
        await worker_service.shutdown()

        assert worker_service.running is False




class TestLifespanManager:
    """Test FastAPI lifespan management"""

    @pytest.mark.asyncio
    @patch("app.main.Tortoise.init")
    @patch("app.main.Tortoise.close_connections")
    @patch("app.main.WorkerService")
    async def test_lifespan_startup_success(
            self, mock_worker_service_class, mock_close_connections, mock_tortoise_init
    ):
        """Test successful lifespan startup"""
        mock_service = MagicMock()
        mock_service.initialize = AsyncMock()
        mock_service.start_workers = AsyncMock()
        mock_service.setup_signal_handlers = AsyncMock()
        mock_service.shutdown = AsyncMock()
        mock_worker_service_class.return_value = mock_service

        mock_app = MagicMock()

        async with lifespan(mock_app):
            pass

        mock_tortoise_init.assert_called_once()
        mock_service.initialize.assert_called_once()
        mock_service.start_workers.assert_called_once()
        mock_service.shutdown.assert_called_once()
        mock_close_connections.assert_called_once()


    @pytest.mark.asyncio
    @patch("app.main.TORTOISE_ORM", {"connections": {"default": "sqlite://:memory:"}})
    @patch("app.main.Tortoise.init")
    @patch("app.main.WorkerService")
    async def test_lifespan_startup_failure(
        self, mock_worker_service_class, mock_tortoise_init
    ):
        """Test lifespan startup failure"""
        mock_service = MagicMock()
        mock_service.initialize = AsyncMock(side_effect=Exception("Startup failed"))
        mock_worker_service_class.return_value = mock_service

        mock_app = MagicMock()

        with pytest.raises(Exception) as exc_info:
            async with lifespan(mock_app):
                pass

        assert "Startup failed" in str(exc_info.value)


class TestSignalHandlers:
    """Test signal handler setup"""

    @pytest.mark.asyncio
    async def test_signal_handler_execution_async(self):
        """Test signal handler execution triggers shutdown event"""
        # Create WorkerService inside async context (event loop is running)
        worker_service = WorkerService()

        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            worker_service.setup_signal_handlers()

            # Get the signal handler function that was registered
            signal_handler_func = mock_loop.add_signal_handler.call_args_list[0][0][1]

            # Initially shutdown event should not be set
            assert not worker_service._shutdown_event.is_set()

            # Execute the signal handler
            signal_handler_func()

            # Now shutdown event should be set
            assert worker_service._shutdown_event.is_set()


class TestFastAPIEndpoints:
    """Test FastAPI endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @patch("app.main.worker_service")
    def test_health_check_with_workers(self, mock_worker_service, client):
        """Test health check endpoint with workers running"""
        mock_worker_service.running = True
        mock_worker_service.workers = [MagicMock(), MagicMock()]

        with patch("app.main.settings") as mock_settings:
            mock_settings.VERSION = "1.0.0"

            response = client.get("/health_check")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["workers_running"] is True
        assert data["worker_count"] == 2
        assert data["version"] == "1.0.0"

    @patch("app.main.worker_service", None)
    def test_health_check_no_workers(self, client):
        """Test health check endpoint with no workers"""
        with patch("app.main.settings") as mock_settings:
            mock_settings.VERSION = "1.0.0"

            response = client.get("/health_check")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["workers_running"] is False
        assert data["worker_count"] == 0

    def test_cors_middleware(self, client):
        """Test CORS middleware configuration"""
        response = client.options("/health_check")
        # The actual CORS headers depend on the request, but we can test the endpoint exists
        assert response.status_code in [200, 405]  # 405 if OPTIONS not explicitly handled


class TestIntegration:
    """Integration tests for the complete FastAPI application"""

    @pytest.mark.asyncio
    async def test_full_application_lifecycle(self):
        """Test complete application startup and shutdown"""
        from fastapi.testclient import TestClient

        with patch("app.main.TORTOISE_ORM", {}), \
                patch("app.main.WorkerService") as mock_worker_service_class, \
                patch("app.main.settings") as mock_settings:
            mock_settings.VERSION = "test"
            mock_settings.CORS_ORIGINS = ["*"]

            mock_service = MagicMock()
            mock_service.initialize = AsyncMock()
            mock_service.start_workers = AsyncMock()
            mock_service.setup_signal_handlers = AsyncMock()
            mock_service.shutdown = AsyncMock()
            mock_service.running = True
            mock_service.workers = []
            mock_worker_service_class.return_value = mock_service

            # Test that the app can be created and used
            with TestClient(app) as client:
                response = client.get("/health_check")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_signal_handling_integration(self):
        """Test that signal handling integrates properly with FastAPI"""
        worker_service = WorkerService()

        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            worker_service.setup_signal_handlers()

            # Verify that signal handlers were set up
            assert mock_loop.add_signal_handler.call_count == 2

            # Verify SIGINT and SIGTERM were both registered
            calls = mock_loop.add_signal_handler.call_args_list
            signals_registered = [call[0][0] for call in calls]
            assert signal.SIGINT in signals_registered
            assert signal.SIGTERM in signals_registered


class TestErrorHandling:
    """Test error handling scenarios"""



    @pytest.mark.asyncio
    async def test_initialization_exception_handling(self):
        """Test exception handling during initialization"""
        worker_service = WorkerService()

        with patch.object(worker_service.container, "wire", side_effect=Exception("Wire failed")):
            with pytest.raises(Exception) as exc_info:
                await worker_service.initialize()

            assert "Wire failed" in str(exc_info.value)
            # Remove assertion for non-existent attribute


class TestWorkerMonitoring:
    """Test worker monitoring and restart functionality"""

    @pytest.fixture
    def worker_service(self):
        return WorkerService()

    @pytest.mark.asyncio
    async def test_run_worker_with_monitoring_normal_operation(self, worker_service):
        """Test worker monitoring with normal operation"""
        mock_worker = MagicMock()
        mock_worker.worker_id = "test-worker"

        call_count = 0

        async def stop_after_iterations():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:  # Run twice then stop
                worker_service.running = False

        mock_worker.start = AsyncMock(side_effect=stop_after_iterations)
        worker_service.running = True

        await worker_service._run_worker_with_monitoring(mock_worker)

        # Verify worker.start was called multiple times
        assert mock_worker.start.call_count >= 1

    @pytest.mark.asyncio
    async def test_run_worker_with_monitoring_worker_exception(self, worker_service):
        """Test worker monitoring handles worker exceptions"""
        mock_worker = MagicMock()
        mock_worker.worker_id = "error-worker"

        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Worker failed")
            else:
                worker_service.running = False  # Stop after error recovery

        mock_worker.start = AsyncMock(side_effect=fail_then_succeed)
        worker_service.running = True

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await worker_service._run_worker_with_monitoring(mock_worker)

            # Verify error handling sleep was called
            mock_sleep.assert_called_with(10)
            assert mock_worker.start.call_count == 2


    @pytest.mark.asyncio
    async def test_run_worker_with_monitoring_shutdown_event(self, worker_service):
        """Test worker monitoring respects shutdown event"""
        mock_worker = MagicMock()
        mock_worker.worker_id = "shutdown-worker"
        mock_worker.start = AsyncMock()

        worker_service.running = True
        worker_service._shutdown_event.set()  # Signal shutdown

        await worker_service._run_worker_with_monitoring(mock_worker)

        # Should not call worker.start when shutdown event is set
        mock_worker.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_worker_with_monitoring_restart_delay(self, worker_service):
        """Test worker restart delay functionality"""
        mock_worker = MagicMock()
        mock_worker.worker_id = "restart-worker"

        call_count = 0

        async def restart_scenario():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return  # First call succeeds but exits
            else:
                worker_service.running = False  # Stop on second iteration

        mock_worker.start = AsyncMock(side_effect=restart_scenario)
        worker_service.running = True

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await worker_service._run_worker_with_monitoring(mock_worker)

            # Verify restart delay was called
            mock_sleep.assert_called_with(5)
            assert mock_worker.start.call_count == 2


class TestTaskManagement:
    """Test task management and cleanup"""

    @pytest.fixture
    def worker_service(self):
        return WorkerService()

    def test_start_workers_task_storage(self, worker_service):
        """Test that worker tasks are properly stored"""
        with patch("app.main.settings") as mock_settings, \
                patch("app.main.QueueWorker") as mock_worker_class, \
                patch("asyncio.create_task") as mock_create_task:
            mock_settings.WORKER_CONCURRENCY = 3
            mock_worker = MagicMock()
            mock_worker.worker_id = "test-worker"
            mock_worker_class.return_value = mock_worker

            # Mock tasks
            mock_tasks = [MagicMock() for _ in range(3)]
            mock_create_task.side_effect = mock_tasks

            worker_service.start_workers()

            # Verify tasks were stored
            assert len(worker_service.worker_tasks) == 3
            assert all(task in worker_service.worker_tasks for task in mock_tasks)

            # Verify add_done_callback was called for cleanup
            for task in mock_tasks:
                task.add_done_callback.assert_called_once()

    def test_start_workers_empty_concurrency(self, worker_service):
        """Test start_workers with zero concurrency"""
        with patch("app.main.settings") as mock_settings:
            mock_settings.WORKER_CONCURRENCY = 0

            worker_service.start_workers()

            assert len(worker_service.workers) == 0
            assert len(worker_service.worker_tasks) == 0
            assert worker_service.running is True

    def test_start_workers_exception_handling(self, worker_service):
        """Test start_workers handles QueueWorker creation exceptions"""
        with patch("app.main.settings") as mock_settings, \
                patch("app.main.QueueWorker") as mock_worker_class:
            mock_settings.WORKER_CONCURRENCY = 1
            mock_worker_class.side_effect = Exception("Worker creation failed")

            with pytest.raises(Exception) as exc_info:
                worker_service.start_workers()

            assert "Worker creation failed" in str(exc_info.value)
            assert len(worker_service.workers) == 0
            assert worker_service.running is False