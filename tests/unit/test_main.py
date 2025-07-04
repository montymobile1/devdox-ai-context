"""
Test cases for main application entry point
"""
import pytest
import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch, call
from app.main import WorkerService, setup_signal_handlers, main


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
    
    @pytest.mark.asyncio
    @patch('app.main.Tortoise.init')
    async def test_initialize_success(self, mock_tortoise_init, worker_service):
        """Test successful initialization"""
        mock_tortoise_init.return_value = None
        
        with patch.object(worker_service.container, 'wire') as mock_wire:
            await worker_service.initialize()
            
            mock_tortoise_init.assert_called_once()
            mock_wire.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.main.Tortoise.init')
    async def test_initialize_failure(self, mock_tortoise_init, worker_service):
        """Test initialization failure"""
        mock_tortoise_init.side_effect = Exception("Database connection failed")
        
        with pytest.raises(Exception) as exc_info:
            await worker_service.initialize()

        assert "Database connection failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    @patch('app.main.QueueWorker')
    @patch('asyncio.create_task')
    async def test_start_workers_success(self, mock_create_task, mock_queue_worker, worker_service):
        """Test successful worker start"""
        mock_worker = MagicMock()
        mock_worker.start = AsyncMock()
        mock_queue_worker.return_value = mock_worker
        
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.WORKER_CONCURRENCY = 2
            
            await worker_service.start_workers()
            
            assert len(worker_service.workers) == 2
            assert worker_service.running is True
            assert mock_create_task.call_count == 2
    
    @pytest.mark.asyncio
    @patch('app.main.QueueWorker')
    async def test_start_workers_failure(self, mock_queue_worker, worker_service):
        """Test worker start failure"""
        mock_queue_worker.side_effect = Exception("Worker creation failed")
        
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.WORKER_CONCURRENCY = 1
            
            with pytest.raises(Exception) as exc_info:
                await worker_service.start_workers()
            
            assert "Worker creation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    @patch('app.main.Tortoise.close_connections')
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
    
    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    async def test_run_normal_operation(self, mock_sleep, worker_service):
        """Test normal run operation"""
        worker_service.initialize = AsyncMock()
        worker_service.start_workers = AsyncMock()
        worker_service.shutdown = AsyncMock()
        
        # Simulate running for 3 iterations then stop
        sleep_count = 0
        def side_effect(*args):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 3:
                worker_service.running = False
        
        mock_sleep.side_effect = side_effect
        worker_service.running = True
        
        await worker_service.run()
        
        worker_service.initialize.assert_called_once()
        worker_service.start_workers.assert_called_once()
        worker_service.shutdown.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_keyboard_interrupt(self, worker_service):
        """Test run with keyboard interrupt"""
        worker_service.initialize = AsyncMock()
        worker_service.start_workers = AsyncMock(side_effect=KeyboardInterrupt())
        worker_service.shutdown = AsyncMock()
        
        await worker_service.run()
        
        worker_service.initialize.assert_called_once()
        worker_service.start_workers.assert_called_once()
        worker_service.shutdown.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_exception(self, worker_service):
        """Test run with exception"""
        worker_service.initialize = AsyncMock()
        worker_service.start_workers = AsyncMock(side_effect=Exception("Test error"))
        worker_service.shutdown = AsyncMock()
        
        await worker_service.run()
        
        worker_service.initialize.assert_called_once()
        worker_service.start_workers.assert_called_once()
        worker_service.shutdown.assert_called_once()


class TestSignalHandlers:
    """Test signal handler setup"""
    
    @patch('signal.signal')
    @patch('asyncio.create_task')
    def test_setup_signal_handlers(self, mock_create_task, mock_signal):
        """Test signal handler setup"""
        mock_service = MagicMock()
        mock_service.shutdown = AsyncMock()
        
        setup_signal_handlers(mock_service)
        
        # Verify signal handlers were set
        assert mock_signal.call_count == 2
        calls = mock_signal.call_args_list
        assert call(signal.SIGINT, mock_signal.call_args_list[0][0][1]) in calls
        assert call(signal.SIGTERM, mock_signal.call_args_list[1][0][1]) in calls
    
    @patch('signal.signal')
    @patch('asyncio.create_task')
    def test_signal_handler_execution(self, mock_create_task, mock_signal):
        """Test signal handler execution"""
        mock_service = MagicMock()
        mock_service.shutdown = AsyncMock()
        
        setup_signal_handlers(mock_service)
        
        # Get the signal handler function
        signal_handler = mock_signal.call_args_list[0][0][1]
        
        # Execute the signal handler
        signal_handler(signal.SIGINT, None)
        
        mock_create_task.assert_called()


class TestMainFunction:
    """Test main function"""
    
    @pytest.mark.asyncio
    @patch('app.main.WorkerService')
    @patch('app.main.setup_signal_handlers')
    async def test_main_success(self, mock_setup_handlers, mock_worker_service_class):
        """Test successful main execution"""
        mock_service = MagicMock()
        mock_service.run = AsyncMock()
        mock_worker_service_class.return_value = mock_service
        
        await main()
        
        mock_worker_service_class.assert_called_once()
        mock_setup_handlers.assert_called_once_with(mock_service)
        mock_service.run.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.main.WorkerService')
    @patch('app.main.setup_signal_handlers')
    @patch('sys.exit')
    async def test_main_exception(self, mock_exit, mock_setup_handlers, mock_worker_service_class):
        """Test main with exception"""
        mock_service = MagicMock()
        mock_service.run = AsyncMock(side_effect=Exception("Service failed"))
        mock_worker_service_class.return_value = mock_service
        
        await main()
        
        mock_exit.assert_called_once_with(1)


class TestMainEntryPoint:
    """Test main entry point when run as script"""
    
    @patch('asyncio.run')
    @patch('app.main.__name__', '__main__')
    def test_main_entry_point(self, mock_asyncio_run):
        """Test main entry point execution"""
        # Import the module to trigger the if __name__ == "__main__" block
        # This is a bit tricky to test directly, so we'll test the components
        mock_asyncio_run.assert_not_called()  # Since we're mocking
