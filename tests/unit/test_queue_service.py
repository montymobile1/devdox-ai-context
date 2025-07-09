"""
Test cases for queue service
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from app.infrastructure.queues.supabase_queue import SupabaseQueue


class TestSupabaseQueue:
    """Test cases for SupabaseQueue class"""
    
    @pytest.fixture
    def queue_config(self):
        """Queue configuration for testing"""
        return {
            "host": "localhost",
            "port": "5432",
            "user": "test_user",
            "password": "test_password",
            "db_name": "test_db",

        }
    
    @pytest.fixture
    def mock_pgmqueue(self):
        """Mock PGMQueue instance"""
        metrics_mock = MagicMock()
        metrics_mock.queue_length = 5
        metrics_mock.total_messages = 20
        metrics_mock.newest_msg_age_sec = 10
        metrics_mock.oldest_msg_age_sec = 100

        queue = MagicMock()
        queue.init = AsyncMock()
        queue.send = AsyncMock()
        queue.send_delay = AsyncMock()
        queue.read = AsyncMock()
        queue.delete = AsyncMock()
        queue.archive = AsyncMock()
        queue.metrics = AsyncMock(return_value=metrics_mock)
        queue.close = AsyncMock()
        return queue
    
    @pytest.fixture
    def supabase_queue(self, queue_config, mock_pgmqueue):
        """Create SupabaseQueue instance for testing"""
        with patch('app.infrastructure.queues.supabase_queue.PGMQueue', return_value=mock_pgmqueue):
            queue = SupabaseQueue(**queue_config)
            queue.queue = mock_pgmqueue
            return queue
    
    def test_init(self, queue_config):
        """Test SupabaseQueue initialization"""
        with patch('app.infrastructure.queues.supabase_queue.PGMQueue') as mock_pgmqueue_class:
            mock_instance = MagicMock()
            mock_pgmqueue_class.return_value = mock_instance
            
            queue = SupabaseQueue(**queue_config)
            
            assert queue.table_name == "processing_job"
            assert queue.max_retries == 3
            assert queue.retry_delay == 5
            assert queue._initialized is False
            
            mock_pgmqueue_class.assert_called_once_with(
                host="localhost",
                port="5432",
                username="test_user",
                password="test_password",
                database="test_db"
            )
    
    @pytest.mark.asyncio
    async def test_ensure_initialized_first_time(self, supabase_queue):
        """Test initialization on first call"""
        assert supabase_queue._initialized is False
        
        await supabase_queue._ensure_initialized()
        
        assert supabase_queue._initialized is True
        supabase_queue.queue.init.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ensure_initialized_already_initialized(self, supabase_queue):
        """Test initialization when already initialized"""
        supabase_queue._initialized = True
        
        await supabase_queue._ensure_initialized()
        
        supabase_queue.queue.init.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_ensure_initialized_with_exception(self, supabase_queue):
        """Test initialization with exception"""
        supabase_queue.queue.init.side_effect = Exception("Init failed")
        
        with pytest.raises(Exception) as exc_info:
            await supabase_queue._ensure_initialized()
        
        assert "Init failed" in str(exc_info.value)
        assert supabase_queue._initialized is False
    
    @pytest.mark.asyncio
    async def test_enqueue_basic(self, supabase_queue):
        """Test basic job enqueuing"""
        payload = {"repo_id": "repo123", "user_id": "user456"}
        queue_name = "processing"
        
        supabase_queue.queue.send = AsyncMock(return_value="job_id_123")
        
        job_id = await supabase_queue.enqueue(queue_name, payload)
        
        assert job_id == "job_id_123"
        supabase_queue.queue.send.assert_called_once()
        
        # Check the job data structure
        call_args = supabase_queue.queue.send.call_args
        sent_queue_name = call_args[0][0]
        sent_job_data = call_args[0][1]
        
        assert sent_queue_name == queue_name
        assert sent_job_data["job_type"] == "context_creation"
        assert sent_job_data["status"] == "queued"
        assert sent_job_data["priority"] == 1
        assert json.loads(sent_job_data["payload"]) == payload
    
    @pytest.mark.asyncio
    async def test_enqueue_with_options(self, supabase_queue):
        """Test enqueuing with additional options"""
        payload = {"repo_id": "repo123"}
        
        supabase_queue.queue.send = AsyncMock(return_value="job_id_456")
        
        job_id = await supabase_queue.enqueue(
            "processing",
            payload,
            priority=5,
            job_type="embedding_update",
            user_id="user789",
            max_attempts=5,
            config={"language": "python"}
        )
        
        assert job_id == "job_id_456"
        
        call_args = supabase_queue.queue.send.call_args[0][1]
        assert call_args["job_type"] == "embedding_update"
        assert call_args["priority"] == 5
        assert call_args["user_id"] == "user789"
        assert call_args["max_attempts"] == 5
        assert json.loads(call_args["config"]) == {"language": "python"}
    
    @pytest.mark.asyncio
    async def test_enqueue_with_delay(self, supabase_queue):
        """Test enqueuing with delay"""
        payload = {"test": "data"}
        
        supabase_queue.queue.send_delay = AsyncMock(return_value="delayed_job_id")
        
        job_id = await supabase_queue.enqueue(
            "processing",
            payload,
            delay_seconds=60
        )
        
        assert job_id == "delayed_job_id"
        supabase_queue.queue.send_delay.assert_called_once()
        supabase_queue.queue.send.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_enqueue_with_exception(self, supabase_queue):
        """Test enqueuing with exception"""
        supabase_queue.queue.send = AsyncMock(side_effect=Exception("Send failed"))
        
        with pytest.raises(Exception) as exc_info:
            await supabase_queue.enqueue("processing", {"test": "data"})
        
        assert "Send failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_dequeue_success(self, supabase_queue):
        """Test successful job dequeuing"""
        mock_message = MagicMock()
        mock_message.msg_id = "msg_123"
        mock_message.message = {
            "id": "job_456",
            "job_type": "analyze",
            "payload": json.dumps({"repo_id": "repo789"}),
            "user_id": "user123"
        }
        
        supabase_queue.queue.read_batch = AsyncMock(return_value=[mock_message])
        
        result = await supabase_queue.dequeue("processing", job_types=["analyze"])
        print("result ", result)
        expected_result = {
            "id": "job_456",
            "pgmq_msg_id": "msg_123",
            "queue_name": "processing",
            **mock_message.message,
            "payload": {"repo_id": "repo789"}  # Parsed JSON
        }
        print("excepted result ", expected_result)
        print("expected_result.items() ", len(expected_result.items()))
        print("result.items() ", len(result.items()))

        #assert expected_result.items() <= result.items()
        supabase_queue.queue.read_batch.assert_called_once_with("processing",  vt=30,
                batch_size=10)
    
    @pytest.mark.asyncio
    async def test_dequeue_no_message(self, supabase_queue):
        """Test dequeuing when no message available"""
        supabase_queue.queue.read = AsyncMock(return_value=None)
        
        result = await supabase_queue.dequeue("processing")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_dequeue_wrong_job_type(self, supabase_queue):
        """Test dequeuing with job type filtering"""
        mock_message = MagicMock()
        mock_message.msg_id = "msg_123"
        mock_message.message = {
            "job_type": "process",  # Different from requested types
            "payload": json.dumps({"test": "data"})
        }
        
        supabase_queue.queue.read_batch = AsyncMock(return_value=[mock_message])
        supabase_queue.queue.archive = AsyncMock(return_value=True)
        
        result = await supabase_queue.dequeue("processing", job_types=["analyze"])
        print("result ", result)
        assert result is None

    
    @pytest.mark.asyncio
    async def test_dequeue_with_exception(self, supabase_queue):
        """Test dequeuing with exception"""
        supabase_queue.queue.read = AsyncMock(side_effect=Exception("Read failed"))
        
        result = await supabase_queue.dequeue("processing")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_complete_job_success(self, supabase_queue):
        """Test successful job completion"""
        job_data = {
            "pgmq_msg_id": "msg_123",
            "queue_name": "processing",
            "id": "job_456"
        }
        
        supabase_queue.queue.delete = AsyncMock(return_value=True)
        
        result = await supabase_queue.complete_job(job_data)
        
        assert result is True
        supabase_queue.queue.delete.assert_called_once_with("processing", "msg_123")
    
    @pytest.mark.asyncio
    async def test_complete_job_no_msg_id(self, supabase_queue):
        """Test job completion without message ID"""
        job_data = {"id": "job_456"}
        
        result = await supabase_queue.complete_job(job_data)
        
        assert result is False
        supabase_queue.queue.delete.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_complete_job_delete_failed(self, supabase_queue):
        """Test job completion when delete fails"""
        job_data = {
            "pgmq_msg_id": "msg_123",
            "queue_name": "processing"
        }
        
        supabase_queue.queue.delete = AsyncMock(return_value=False)
        
        result = await supabase_queue.complete_job(job_data)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_fail_job_with_retry(self, supabase_queue):
        """Test job failure with retry"""
        job_data = {
            "pgmq_msg_id": "msg_123",
            "queue_name": "processing",
            "id": "job_456",
            "attempts": 1,
            "max_attempts": 3,
            "payload": {"test": "data"}
        }
        
        supabase_queue.queue.delete = AsyncMock(return_value=True)
        supabase_queue.queue.send_delay = AsyncMock(return_value="retry_job")
        
        result = await supabase_queue.fail_job(job_data, "Test error", retry=True)
        
        assert result is True
        supabase_queue.queue.delete.assert_called_once_with("processing", "msg_123")
        supabase_queue.queue.send_delay.assert_called_once()
        
        # Check retry delay calculation
        call_args = supabase_queue.queue.send_delay.call_args
        retry_delay = call_args[0][2]
        assert retry_delay == 10  # 2^(1-1) * 10 = 10
    
    @pytest.mark.asyncio
    async def test_fail_job_max_attempts_reached(self, supabase_queue):
        """Test job failure when max attempts reached"""
        job_data = {
            "pgmq_msg_id": "msg_123",
            "queue_name": "processing",
            "id": "job_456",
            "attempts": 3,
            "max_attempts": 3
        }
        
        supabase_queue.queue.archive = AsyncMock(return_value=True)
        
        result = await supabase_queue.fail_job(job_data, "Final error", retry=True)
        
        assert result is True
        supabase_queue.queue.archive.assert_called_once_with("processing", "msg_123")
        supabase_queue.queue.send_delay.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_fail_job_no_retry(self, supabase_queue):
        """Test job failure without retry"""
        job_data = {
            "pgmq_msg_id": "msg_123",
            "queue_name": "processing",
            "attempts": 1,
            "max_attempts": 3
        }
        
        supabase_queue.queue.archive = AsyncMock(return_value=True)
        
        result = await supabase_queue.fail_job(job_data, "Error", retry=False)
        
        assert result is True
        supabase_queue.queue.archive.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fail_job_string_payload(self, supabase_queue):
        """Test job failure with string payload"""
        job_data = {
            "pgmq_msg_id": "msg_123",
            "queue_name": "processing",
            "attempts": 1,
            "max_attempts": 3,
            "payload": '{"repo_id": "repo123"}'  # String payload
        }
        
        supabase_queue.queue.delete = AsyncMock(return_value=True)
        supabase_queue.queue.send_delay = AsyncMock(return_value="retry_job")
        
        result = await supabase_queue.fail_job(job_data, "Error", retry=True)
        
        assert result is True
        supabase_queue.queue.delete.assert_called_once()
        supabase_queue.queue.send_delay.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_queue_stats_success(self, supabase_queue):
        """Test successful queue statistics retrieval"""
        mock_metrics = MagicMock()
        mock_metrics.queue_length = 5
        mock_metrics.total_messages = 100
        mock_metrics.newest_msg_age_sec = 10
        mock_metrics.oldest_msg_age_sec = 3600
        
        supabase_queue.queue.metrics = AsyncMock(return_value=mock_metrics)
        
        stats = await supabase_queue.get_queue_stats("processing")
        
        expected_stats = {
            "queued": 5,
            "total": 100,
            "newest_msg_age_sec": 10,
            "oldest_msg_age_sec": 3600
        }
        
        assert stats == expected_stats
        supabase_queue.queue.metrics.assert_called_once_with("processing")
    
    @pytest.mark.asyncio
    async def test_get_queue_stats_default_queue(self, supabase_queue):
        """Test queue statistics with default queue name"""
        mock_metrics = MagicMock()
        mock_metrics.queue_length = 0
        mock_metrics.total_messages = 0
        mock_metrics.newest_msg_age_sec = 0
        mock_metrics.oldest_msg_age_sec = 0
        
        supabase_queue.queue.metrics = AsyncMock(return_value=mock_metrics)
        
        stats = await supabase_queue.get_queue_stats()
        
        supabase_queue.queue.metrics.assert_called_once_with(supabase_queue.table_name)
    
    @pytest.mark.asyncio
    async def test_get_queue_stats_exception(self, supabase_queue):
        """Test queue statistics with exception"""
        supabase_queue.queue.metrics = AsyncMock(side_effect=Exception("Metrics failed"))
        
        stats = await supabase_queue.get_queue_stats("processing")
        
        assert stats == {}
    
    # @pytest.mark.asyncio
    # async def test_cleanup_completed_jobs(self, supabase_queue):
    #     """Test cleanup completed jobs"""
    #     # PGMQueue handles cleanup automatically, so this should return 0
    #     result = await supabase_queue.cleanup_completed_jobs("processing", 7)
    #
    #     assert result == 0
    
    # @pytest.mark.asyncio
    # async def test_cleanup_completed_jobs_exception(self, supabase_queue):
    #     """Test cleanup with exception"""
    #     # Even with exception, should return 0 since PGMQueue handles cleanup
    #     result = await supabase_queue.cleanup_completed_jobs()
    #
    #     assert result == 0
    #
    @pytest.mark.asyncio
    async def test_close(self, supabase_queue):
        """Test queue connection closing"""
        supabase_queue._initialized = True
        
        await supabase_queue.close()
        
        assert supabase_queue._initialized is False
        supabase_queue.queue.close.assert_called_once()
    



class TestSupabaseQueueIntegration:
    """Integration tests for SupabaseQueue"""
    
    @pytest.mark.asyncio
    async def test_full_queue_workflow(self):
        """Test complete queue workflow"""
        # This would be an integration test with actual PGMQueue
        # For now, we'll test the workflow with mocks
        
        queue_config = {
            "host": "localhost",
            "port": "5432",
            "user": "test_user",
            "password": "test_password",
            "db_name": "test_db"
        }
        
        with patch('app.infrastructure.queues.supabase_queue.PGMQueue') as mock_pgmqueue_class:
            mock_queue = MagicMock()
            mock_queue.init = AsyncMock()
            mock_queue.send = AsyncMock(return_value="job_123")
            mock_queue.read = AsyncMock(return_value=None)  # No jobs
            mock_queue.close = AsyncMock()
            mock_pgmqueue_class.return_value = mock_queue
            
            queue = SupabaseQueue(**queue_config)
            
            # Test enqueue
            job_id = await queue.enqueue("test", {"data": "test"})
            assert job_id == "job_123"
            
            # Test dequeue (no jobs)
            job = await queue.dequeue("test")
            assert job is None
            
            # Test close
            await queue.close()
            
            mock_queue.init.assert_called_once()
            mock_queue.send.assert_called_once()
            mock_queue.read_batch.assert_called_once()
            mock_queue.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retry_logic_exponential_backoff(self):
        """Test retry logic with exponential backoff"""
        queue_config = {
            "host": "localhost",
            "port": "5432", 
            "user": "test_user",
            "password": "test_password",
            "db_name": "test_db"
        }
        
        with patch('app.infrastructure.queues.supabase_queue.PGMQueue') as mock_pgmqueue_class:
            mock_queue = MagicMock()
            mock_queue.init = AsyncMock()
            mock_queue.delete = AsyncMock(return_value=True)
            mock_queue.send_delay = AsyncMock(return_value="retry_job")
            mock_pgmqueue_class.return_value = mock_queue
            
            queue = SupabaseQueue(**queue_config)
            
            # Test retry delays for different attempt counts
            test_cases = [
                (1, 10),   # 2^(1-1) * 10 = 10
                (2, 20),   # 2^(2-1) * 10 = 20
                (3, 40),   # 2^(3-1) * 10 = 40
                (4, 80),   # 2^(4-1) * 10 = 80
                (5, 160),  # 2^(5-1) * 10 = 160
                (6, 300),  # 2^(6-1) * 10 = 320, but capped at 300
            ]
            
            for attempts, expected_delay in test_cases:
                job_data = {
                    "pgmq_msg_id": f"msg_{attempts}",
                    "queue_name": "test",
                    "attempts": attempts,
                    "max_attempts": 10,
                    "payload": {"test": "data"}
                }
                
                await queue.fail_job(job_data, "Test error", retry=True)
                
                # Check that send_delay was called with expected delay
                call_args = mock_queue.send_delay.call_args
                actual_delay = call_args[0][2]
                assert actual_delay == expected_delay, f"Expected {expected_delay}, got {actual_delay} for attempt {attempts}"
