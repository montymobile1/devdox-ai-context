"""
Test cases for message handler
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.handlers.message_handler import MessageHandler
from app.schemas.processing_result import ProcessingResult


class TestMessageHandler:
    """Test cases for MessageHandler class"""
    
    @pytest.fixture
    def mock_auth_service(self):
        """Mock authentication service"""
        service = MagicMock()
        service.consume_tokens = AsyncMock()
        return service
    
    @pytest.fixture
    def mock_processing_service(self):
        """Mock processing service"""
        service = MagicMock()
        service.process_repository = AsyncMock()
        return service
    
    @pytest.fixture
    def mock_queue_service(self):
        """Mock queue service"""
        service = MagicMock()
        return service
    
    @pytest.fixture
    def message_handler(self, mock_auth_service, mock_processing_service, mock_queue_service):
        """Create MessageHandler instance for testing"""
        return MessageHandler(
            auth_service=mock_auth_service,
            processing_service=mock_processing_service,
            queue_service=mock_queue_service
        )
    
    def test_init(self, message_handler, mock_auth_service, mock_processing_service, mock_queue_service):
        """Test MessageHandler initialization"""
        assert message_handler.auth_service == mock_auth_service
        assert message_handler.processing_service == mock_processing_service
        assert message_handler.queue_service == mock_queue_service
    
    @pytest.mark.asyncio
    async def test_handle_processing_message_success_with_chunks(self, message_handler, mock_processing_service, mock_auth_service):
        """Test successful processing message handling with chunks created"""
        # Setup job payload
        job_payload = {
            "user_id": "user123",
            "repo_id": "repo456",
            "context_id": "ctx789",
            "git_provider": "github",
            "git_token": "token123",
            "branch": "main"
        }
        
        # Setup successful processing result
        processing_result = ProcessingResult(
            success=True,
            context_id="ctx789",
            processing_time=5.2,
            chunks_created=50,
            embeddings_created=50
        )
        mock_processing_service.process_repository.return_value = processing_result
        
        await message_handler.handle_processing_message(job_payload)
        
        # Verify processing service was called
        mock_processing_service.process_repository.assert_called_once_with(job_payload, None, job_tracer=None)
        
        # Verify tokens were consumed
        mock_auth_service.consume_tokens.assert_called_once_with("user123", 50)
    
    @pytest.mark.asyncio
    async def test_handle_processing_message_success_no_chunks(self, message_handler, mock_processing_service, mock_auth_service):
        """Test successful processing message handling with no chunks created"""
        job_payload = {
            "user_id": "user123",
            "repo_id": "repo456",
            "context_id": "ctx789",
            "git_provider": "github",
            "git_token": "token123"
        }
        
        # Setup successful processing result with no chunks
        processing_result = ProcessingResult(
            success=True,
            context_id="ctx789",
            processing_time=2.1,
            chunks_created=0,
            embeddings_created=0
        )
        mock_processing_service.process_repository.return_value = processing_result
        
        await message_handler.handle_processing_message(job_payload)
        
        # Verify processing service was called
        mock_processing_service.process_repository.assert_called_once_with(job_payload, None, job_tracer=None)
        
        # Verify tokens were NOT consumed since no chunks created
        mock_auth_service.consume_tokens.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_processing_message_success_with_callback(self, message_handler, mock_processing_service, mock_auth_service):
        """Test successful processing message handling with callback URL"""
        job_payload = {
            "user_id": "user123",
            "repo_id": "repo456", 
            "context_id": "ctx789",
            "git_provider": "github",
            "git_token": "token123",
            "callback_url": "https://example.com/callback"
        }
        
        processing_result = ProcessingResult(
            success=True,
            context_id="ctx789",
            processing_time=3.5,
            chunks_created=25,
            embeddings_created=25
        )
        mock_processing_service.process_repository.return_value = processing_result
        
        # Mock the callback method
        message_handler._send_completion_callback = AsyncMock()
        
        await message_handler.handle_processing_message(job_payload)
        
        # Verify callback was sent
        message_handler._send_completion_callback.assert_called_once_with(
            "https://example.com/callback", 
            processing_result
        )
        
        # Verify tokens were consumed
        mock_auth_service.consume_tokens.assert_called_once_with("user123", 25)
    
    @pytest.mark.asyncio
    async def test_handle_processing_message_failure(self, message_handler, mock_processing_service, mock_auth_service):
        """Test processing message handling when processing fails"""
        job_payload = {
            "user_id": "user123",
            "repo_id": "repo456",
            "context_id": "ctx789",
            "git_provider": "github",
            "git_token": "token123"
        }
        
        # Setup failed processing result
        processing_result = ProcessingResult(
            success=False,
            context_id="ctx789",
            error_message="Repository not found"
        )
        mock_processing_service.process_repository.return_value = processing_result
        
        await message_handler.handle_processing_message(job_payload)
        
        # Verify processing service was called
        mock_processing_service.process_repository.assert_called_once_with(job_payload, None, job_tracer=None)
        
        # Verify tokens were NOT consumed since processing failed
        mock_auth_service.consume_tokens.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_processing_message_exception(self, message_handler, mock_processing_service):
        """Test processing message handling when exception occurs"""
        job_payload = {
            "user_id": "user123",
            "repo_id": "repo456",
            "context_id": "ctx789",
            "git_provider": "github",
            "git_token": "token123"
        }
        
        # Make processing service raise an exception
        mock_processing_service.process_repository.side_effect = Exception("Processing service error")
        
        with pytest.raises(Exception) as exc_info:
            await message_handler.handle_processing_message(job_payload)
        
        assert "Processing service error" in str(exc_info.value)
        mock_processing_service.process_repository.assert_called_once_with(job_payload, None, job_tracer=None)
    
    @pytest.mark.asyncio
    async def test_handle_processing_message_auth_service_failure(self, message_handler, mock_processing_service, mock_auth_service):
        """Test processing message handling when auth service fails"""
        job_payload = {
            "user_id": "user123",
            "repo_id": "repo456",
            "context_id": "ctx789",
            "git_provider": "github",
            "git_token": "token123"
        }
        
        processing_result = ProcessingResult(
            success=True,
            context_id="ctx789",
            chunks_created=30
        )
        mock_processing_service.process_repository.return_value = processing_result
        
        # Make auth service fail
        mock_auth_service.consume_tokens.side_effect = Exception("Token consumption failed")
        
        with pytest.raises(Exception) as exc_info:
            await message_handler.handle_processing_message(job_payload)
        
        assert "Token consumption failed" in str(exc_info.value)
        mock_processing_service.process_repository.assert_called_once()
        mock_auth_service.consume_tokens.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_send_completion_callback_success(self, mock_httpx_client, message_handler):
        """Test successful callback notification"""
        callback_url = "https://example.com/webhook"
        result = ProcessingResult(
            success=True,
            context_id="ctx123",
            chunks_created=20
        )
        # Mock HTTP client
        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance
        
        await message_handler._send_completion_callback(callback_url, result)
        
        # Verify HTTP POST was made
        mock_client_instance.post.assert_called_once_with(
            callback_url,
            json=result.model_dump_json(),
            timeout=10.0
        )
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_send_completion_callback_failure(self, mock_httpx_client, message_handler):
        """Test callback notification failure"""
        callback_url = "https://example.com/webhook"
        result = ProcessingResult(
            success=True,
            context_id="ctx123",
            chunks_created=15
        )
        
        # Mock HTTP client to fail
        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=Exception("Network error"))
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance
        
        # Should not raise exception, just log error
        await message_handler._send_completion_callback(callback_url, result)
        
        mock_client_instance.post.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_send_completion_callback_timeout(self, mock_httpx_client, message_handler):
        """Test callback notification timeout"""
        callback_url = "https://example.com/webhook"
        result = ProcessingResult(
            success=False,
            context_id="ctx123",
            error_message="Processing failed"
        )
        
        # Mock HTTP client to timeout
        import httpx
        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance
        
        # Should not raise exception, just log error
        await message_handler._send_completion_callback(callback_url, result)
        
        mock_client_instance.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_processing_message_with_none_chunks(self, message_handler, mock_processing_service, mock_auth_service):
        """Test processing message handling when chunks_created is None"""
        job_payload = {
            "user_id": "user123",
            "repo_id": "repo456",
            "context_id": "ctx789",
            "git_provider": "github",
            "git_token": "token123"
        }
        
        # Setup processing result with None chunks_created
        processing_result = ProcessingResult(
            success=True,
            context_id="ctx789",
            chunks_created=None,
            embeddings_created=10
        )
        mock_processing_service.process_repository.return_value = processing_result
        
        await message_handler.handle_processing_message(job_payload)
        
        # Verify tokens were NOT consumed since chunks_created is None
        mock_auth_service.consume_tokens.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_processing_message_callback_failure_doesnt_affect_processing(self, message_handler, mock_processing_service, mock_auth_service):
        """Test that callback failure doesn't affect main processing"""
        job_payload = {
            "user_id": "user123",
            "repo_id": "repo456",
            "context_id": "ctx789",
            "git_provider": "github",
            "git_token": "token123",
            "callback_url": "https://example.com/callback"
        }
        
        processing_result = ProcessingResult(
            success=True,
            context_id="ctx789",
            chunks_created=40
        )
        mock_processing_service.process_repository.return_value = processing_result
        
        # Mock callback to fail
        message_handler._send_completion_callback = AsyncMock(side_effect=Exception("Callback failed"))
        
        # Should not raise exception
        await message_handler.handle_processing_message(job_payload)
        
        # Verify processing and token consumption still happened
        mock_processing_service.process_repository.assert_called_once()
        mock_auth_service.consume_tokens.assert_called_once_with("user123", 40)
        message_handler._send_completion_callback.assert_called_once()


class TestMessageHandlerIntegration:
    """Integration tests for MessageHandler"""
    
    @pytest.mark.asyncio
    async def test_full_message_processing_workflow(self):
        """Test complete message processing workflow"""
        # Setup mocks
        mock_auth = MagicMock()
        mock_auth.consume_tokens = AsyncMock()
        
        mock_processing = MagicMock()
        mock_processing.process_repository = AsyncMock(
            return_value=ProcessingResult(
                success=True,
                context_id="ctx123",
                processing_time=4.5,
                chunks_created=35,
                embeddings_created=35
            )
        )
        
        mock_queue = MagicMock()
        
        handler = MessageHandler(
            auth_service=mock_auth,
            processing_service=mock_processing,
            queue_service=mock_queue
        )
        
        # Test payload
        payload = {
            "user_id": "user456",
            "repo_id": "repo789",
            "context_id": "ctx123",
            "git_provider": "gitlab",
            "git_token": "token456",
            "branch": "develop"
        }
        
        # Process message
        await handler.handle_processing_message(payload)
        
        # Verify workflow
        mock_processing.process_repository.assert_called_once_with(payload, None, job_tracer=None)
        mock_auth.consume_tokens.assert_called_once_with("user456", 35)
    
    @pytest.mark.asyncio
    async def test_message_handler_with_minimal_payload(self):
        """Test message handler with minimal required payload"""
        mock_auth = MagicMock()
        mock_auth.consume_tokens = AsyncMock()
        
        mock_processing = MagicMock()
        mock_processing.process_repository = AsyncMock(
            return_value=ProcessingResult(
                success=True,
                context_id="ctx999",
                chunks_created=0  # No chunks created
            )
        )
        
        handler = MessageHandler(
            auth_service=mock_auth,
            processing_service=mock_processing,
            queue_service=MagicMock()
        )
        
        # Minimal payload
        payload = {
            "user_id": "user123",
            "repo_id": "repo123",
            "context_id": "ctx999"
        }
        
        await handler.handle_processing_message(payload)
        
        # Verify processing happened but no tokens consumed
        mock_processing.process_repository.assert_called_once()
        mock_auth.consume_tokens.assert_not_called()
