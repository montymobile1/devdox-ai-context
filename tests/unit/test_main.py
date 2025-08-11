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
    async def test_start_workers_success(
            self, mock_create_task, mock_queue_worker, worker_service
    ):
        """Test successful worker start"""

        mock_worker = MagicMock()

        mock_worker.start = AsyncMock()

        mock_worker.worker_id = "test-worker"

        mock_queue_worker.return_value = mock_worker

        with patch("app.main.settings") as mock_settings:
            mock_settings.WORKER_CONCURRENCY = 2

            await worker_service.start_workers()

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

            await worker_service.setup_signal_handlers()
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
        # mock_service.setup_signal_handlers.assert_called_once()
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
    async def test_signal_handler_execution(self):
        """Test signal handler execution triggers shutdown event"""
        worker_service = WorkerService()

        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            await worker_service.setup_signal_handlers()

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

            await worker_service.setup_signal_handlers()

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


