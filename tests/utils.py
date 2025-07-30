"""
Test utilities and helper functions for the test suite
"""
import asyncio
import uuid
import secrets
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, Any, List


class TestDataFactory:
    """Factory for creating test data objects"""
    
    @staticmethod
    def create_user_data(
        user_id: str = None,
        email: str = None,
        membership_level: str = "free",
        token_limit: int = 1000,
        token_used: int = 0,
        active: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Create user test data"""
        return {
            "user_id": user_id or f"user_{uuid.uuid4().hex[:8]}",
            "first_name": kwargs.get("first_name", "Test"),
            "last_name": kwargs.get("last_name", "User"),
            "email": email or f"test_{uuid.uuid4().hex[:8]}@example.com",
            "username": kwargs.get("username", ""),
            "role": kwargs.get("role", "developer"),
            "active": active,
            "membership_level": membership_level,
            "token_limit": token_limit,
            "token_used": token_used,
            "encryption_salt": kwargs.get("encryption_salt", "test_salt"),
            "created_at": kwargs.get("created_at", datetime.now(timezone.utc)),
            "updated_at": kwargs.get("updated_at", datetime.now(timezone.utc))
        }
    
    @staticmethod
    def create_repo_data(
        repo_id: str = None,
        user_id: str = None,
        repo_name: str = None,
        private: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Create repository test data"""
        repo_name = repo_name or f"test-repo-{uuid.uuid4().hex[:8]}"
        return {
            "id": kwargs.get("id", str(uuid.uuid4())),
            "repo_id": repo_id or f"repo_{uuid.uuid4().hex[:8]}",
            "user_id": user_id or f"user_{uuid.uuid4().hex[:8]}",
            "repo_name": repo_name,
            "description": kwargs.get("description", f"Test repository {repo_name}"),
            "html_url": kwargs.get("html_url", f"https://github.com/test/{repo_name}"),
            "default_branch": kwargs.get("default_branch", "main"),
            "forks_count": kwargs.get("forks_count", 0),
            "stargazers_count": kwargs.get("stargazers_count", 0),
            "is_private": private,
            "visibility": "private" if private else "public",
            "git_hosting": kwargs.get("git_hosting", "github"),
            "language": kwargs.get("language", "Python"),
            "size": kwargs.get("size", 1024),
            "repo_created_at": kwargs.get("repo_created_at", datetime.now(timezone.utc)),
            "repo_updated_at": kwargs.get("repo_updated_at", datetime.now(timezone.utc)),
            "created_at": kwargs.get("created_at", datetime.now(timezone.utc)),
            "updated_at": kwargs.get("updated_at", datetime.now(timezone.utc))
        }
    
    @staticmethod
    def create_api_key_data(
        user_id: str = None,
        key_name: str = None,
        is_active: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Create API key test data"""
        return {
            "id": kwargs.get("id", str(uuid.uuid4())),
            "user_id": user_id or f"user_{uuid.uuid4().hex[:8]}",
            "api_key": kwargs.get("api_key", f"key_{uuid.uuid4().hex}"),
            "key_name": key_name or f"Test Key {uuid.uuid4().hex[:8]}",
            "is_active": is_active,
            "permissions": kwargs.get("permissions", ["read", "write"]),
            "last_used_at": kwargs.get("last_used_at"),
            "expires_at": kwargs.get("expires_at"),
            "created_at": kwargs.get("created_at", datetime.now(timezone.utc)),
            "updated_at": kwargs.get("updated_at", datetime.now(timezone.utc))
        }
    
    @staticmethod
    def create_job_payload(
        context_id: str = None,
        repo_id: str = None,
        user_id: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create job payload test data"""
        return {
            "context_id": context_id or f"ctx_{uuid.uuid4().hex[:8]}",
            "repo_id": repo_id or f"repo_{uuid.uuid4().hex[:8]}",
            "user_id": user_id or f"user_{uuid.uuid4().hex[:8]}",
            "git_provider": kwargs.get("git_provider", "github"),
            "git_token": kwargs.get("git_token", f"token_{uuid.uuid4().hex[:16]}"),
            "branch": kwargs.get("branch", "main"),
            "callback_url": kwargs.get("callback_url"),
            "config": kwargs.get("config", {})
        }
    
    @staticmethod
    def create_processing_job_data(
        job_type: str = "process",
        status: str = "queued",
        user_id: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create processing job test data"""
        return {
            "id": kwargs.get("id", str(uuid.uuid4())),
            "job_type": job_type,
            "status": status,
            "priority": kwargs.get("priority", 1),
            "user_id": user_id or f"user_{uuid.uuid4().hex[:8]}",
            "repo_id": kwargs.get("repo_id"),
            "context_id": kwargs.get("context_id"),
            "payload": kwargs.get("payload", {}),
            "config": kwargs.get("config", {}),
            "attempts": kwargs.get("attempts", 0),
            "max_attempts": kwargs.get("max_attempts", 3),
            "scheduled_at": kwargs.get("scheduled_at", datetime.now(timezone.utc)),
            "started_at": kwargs.get("started_at"),
            "completed_at": kwargs.get("completed_at"),
            "error_message": kwargs.get("error_message"),
            "error_trace": kwargs.get("error_trace"),
            "result": kwargs.get("result")
        }
    
    @staticmethod
    def create_code_chunk_data(
        repo_id: str = None,
        user_id: str = None,
        content: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create code chunk test data"""
        return {
            "id": kwargs.get("id", str(uuid.uuid4())),
            "repo_id": repo_id or f"repo_{uuid.uuid4().hex[:8]}",
            "user_id": user_id or f"user_{uuid.uuid4().hex[:8]}",
            "content": content or "def hello_world():\n    print('Hello, World!')",
            "embedding": kwargs.get("embedding", [0.1, 0.2, 0.3, 0.4, 0.5]),
            "metadata": kwargs.get("metadata", {"language": "python"}),
            "file_name": kwargs.get("file_name", "hello.py"),
            "file_path": kwargs.get("file_path", "/src/hello.py"),
            "file_size": kwargs.get("file_size", 100),
            "commit_number": kwargs.get("commit_number", "abc123"),
            "created_at": kwargs.get("created_at", datetime.now(timezone.utc)),
            "updated_at": kwargs.get("updated_at", datetime.now(timezone.utc))
        }


class MockFactory:
    """Factory for creating mock objects"""
    
    @staticmethod
    def create_mock_user(user_data: Dict[str, Any] = None) -> MagicMock:
        """Create a mock user object"""
        data = user_data or TestDataFactory.create_user_data()
        
        user = MagicMock()
        for key, value in data.items():
            setattr(user, key, value)
        
        user.save = AsyncMock()
        return user
    
    @staticmethod
    def create_mock_repo(repo_data: Dict[str, Any] = None) -> MagicMock:
        """Create a mock repository object"""
        data = repo_data or TestDataFactory.create_repo_data()
        
        repo = MagicMock()
        for key, value in data.items():
            setattr(repo, key, value)
        
        repo.save = AsyncMock()
        return repo
    
    @staticmethod
    def create_mock_api_key(api_key_data: Dict[str, Any] = None) -> MagicMock:
        """Create a mock API key object"""
        data = api_key_data or TestDataFactory.create_api_key_data()
        
        api_key = MagicMock()
        for key, value in data.items():
            setattr(api_key, key, value)
        
        api_key.save = AsyncMock()
        return api_key
    
    @staticmethod
    def create_mock_queue_message(
        msg_id: str = None,
        message_data: Dict[str, Any] = None
    ) -> MagicMock:
        """Create a mock queue message"""
        message = MagicMock()
        message.msg_id = msg_id or f"msg_{uuid.uuid4().hex[:8]}"
        message.message = message_data or TestDataFactory.create_job_payload()
        return  [message]
    
    @staticmethod
    def create_mock_git_client() -> MagicMock:
        """Create a mock git client"""
        client = MagicMock()
        client.get_repo = MagicMock()
        client.get_user = MagicMock()
        return client
    
    @staticmethod
    def create_mock_encryption_service() -> MagicMock:
        """Create a mock encryption service"""
        service = MagicMock()
        service.encrypt = MagicMock(side_effect=lambda x: f"encrypted_{x}")
        service.decrypt = MagicMock(side_effect=lambda x: x.replace("encrypted_", ""))
        service.encrypt_for_user = MagicMock(side_effect=lambda x, salt: f"encrypted_{x}_{salt}")
        service.decrypt_for_user = MagicMock(side_effect=lambda x, salt: x.replace(f"encrypted_", "").replace(f"_{salt}", ""))
        return service


class AsyncTestHelper:
    """Helper functions for async testing"""
    
    @staticmethod
    async def run_with_timeout(coro, timeout: float = 5.0):
        """Run coroutine with timeout"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise AssertionError(f"Coroutine did not complete within {timeout} seconds")
    
    @staticmethod
    def create_async_mock_with_return_value(return_value):
        """Create async mock with specific return value"""
        mock = AsyncMock()
        mock.return_value = return_value
        return mock
    
    @staticmethod
    def create_async_mock_with_side_effect(side_effect):
        """Create async mock with side effect"""
        mock = AsyncMock()
        mock.side_effect = side_effect
        return mock
    
    @staticmethod
    async def collect_async_calls(async_mock: AsyncMock, max_calls: int = 10, timeout: float = 1.0):
        """Collect calls made to an async mock"""
        calls = []
        start_time = asyncio.get_event_loop().time()
        
        while len(calls) < max_calls:
            current_time = asyncio.get_event_loop().time()
            if current_time - start_time > timeout:
                break
            
            if async_mock.call_count > len(calls):
                calls.extend(async_mock.call_args_list[len(calls):])
            
            await asyncio.sleep(0.01)
        
        return calls


class DatabaseTestHelper:
    """Helper functions for database testing"""
    
    @staticmethod
    def create_mock_db_session():
        """Create a mock database session"""
        session = MagicMock()
        session.execute = AsyncMock()
        session.fetch = AsyncMock()
        session.fetchrow = AsyncMock()
        session.fetchval = AsyncMock()
        session.close = AsyncMock()
        return session
    
    @staticmethod
    def create_mock_connection_pool():
        """Create a mock connection pool"""
        pool = MagicMock()
        pool.acquire = AsyncMock()
        pool.close = AsyncMock()
        return pool
    
    @staticmethod
    def assert_database_call_made(mock_method, expected_query: str = None, expected_params: tuple = None):
        """Assert that a database call was made with expected parameters"""
        assert mock_method.called, "Expected database method was not called"
        
        if expected_query:
            call_args = mock_method.call_args
            actual_query = call_args[0][0] if call_args and call_args[0] else None
            assert expected_query in str(actual_query), f"Query '{expected_query}' not found in '{actual_query}'"
        
        if expected_params:
            call_args = mock_method.call_args
            actual_params = call_args[0][1] if call_args and len(call_args[0]) > 1 else None
            assert actual_params == expected_params, f"Expected params {expected_params}, got {actual_params}"


class QueueTestHelper:
    """Helper functions for queue testing"""
    
    @staticmethod
    def create_mock_queue():
        """Create a mock queue instance"""
        queue = MagicMock()
        queue.init = AsyncMock()
        queue.send = AsyncMock()
        queue.send_delay = AsyncMock()
        queue.read = AsyncMock()
        queue.delete = AsyncMock()
        queue.archive = AsyncMock()
        queue.metrics = AsyncMock()
        queue.close = AsyncMock()
        return queue
    
    @staticmethod
    def create_queue_metrics(
        queue_length: int = 0,
        total_messages: int = 0,
        newest_msg_age_sec: int = 0,
        oldest_msg_age_sec: int = 0
    ):
        """Create mock queue metrics"""
        metrics = MagicMock()
        metrics.queue_length = queue_length
        metrics.total_messages = total_messages
        metrics.newest_msg_age_sec = newest_msg_age_sec
        metrics.oldest_msg_age_sec = oldest_msg_age_sec
        return metrics
    
    @staticmethod
    def simulate_queue_with_jobs(jobs: List[Dict[str, Any]], queue_mock: MagicMock):
        """Simulate a queue with predefined jobs"""
        job_messages = [MockFactory.create_mock_queue_message(message_data=job) for job in jobs]
        queue_mock.read.side_effect = job_messages + [None] * 10  # Jobs then empty


class ErrorTestHelper:
    """Helper functions for error testing"""
    
    @staticmethod
    def create_database_error(message: str = "Database connection failed"):
        """Create a database error for testing"""
        from app.core.exceptions.local_exceptions import DatabaseError
        return DatabaseError(message)
    
    @staticmethod
    def create_authentication_error(message: str = "Authentication failed"):
        """Create an authentication error for testing"""
        from app.core.exceptions.local_exceptions import AuthenticationError
        return AuthenticationError(message)
    
    @staticmethod
    def create_processing_error(message: str = "Processing failed"):
        """Create a processing error for testing"""
        from app.core.exceptions.local_exceptions import ProcessingError
        return ProcessingError(message)
    
    @staticmethod
    def assert_error_logged(mock_logger, error_level: str, message_contains: str):
        """Assert that an error was logged"""
        log_method = getattr(mock_logger, error_level.lower())
        assert log_method.called, f"Expected {error_level} log was not called"
        
        # Check if any log call contains the expected message
        log_calls = log_method.call_args_list
        message_found = any(message_contains in str(call) for call in log_calls)
        assert message_found, f"Log message containing '{message_contains}' not found in {log_calls}"


class PerformanceTestHelper:
    """Helper functions for performance testing"""
    
    @staticmethod
    async def measure_execution_time(coro):
        """Measure execution time of a coroutine"""
        start_time = asyncio.get_event_loop().time()
        result = await coro
        end_time = asyncio.get_event_loop().time()
        execution_time = end_time - start_time
        return result, execution_time
    
    @staticmethod
    def assert_execution_time_under(execution_time: float, max_time: float):
        """Assert that execution time is under a maximum threshold"""
        assert execution_time < max_time, f"Execution took {execution_time:.3f}s, expected under {max_time}s"
    
    @staticmethod
    def create_load_test_data(count: int, data_factory_func):
        """Create test data for load testing"""
        return [data_factory_func() for _ in range(count)]
    
    @staticmethod
    async def run_concurrent_operations(operations: List, max_concurrency: int = 10):
        """Run operations concurrently with controlled concurrency"""
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def run_with_semaphore(operation):
            async with semaphore:
                return await operation
        
        tasks = [run_with_semaphore(op) for op in operations]
        return await asyncio.gather(*tasks, return_exceptions=True)


class ConfigTestHelper:
    """Helper functions for configuration testing"""
    
    @staticmethod
    def create_test_config(overrides: Dict[str, Any] = None):
        """Create test configuration with optional overrides"""
        base_config = {
            "app_name": "DevDox AI Context Queue Worker Test",
            "Environment": "test",
            "debug": True,
            "version": "0.0.1-test",
            "DB_MAX_CONNECTIONS": 5,
            "DB_MIN_CONNECTIONS": 1,
            "IS_PRODUCTION": False,
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_KEY": "test_key",
            "embedding_model": "test-embedding-model",
            "vector_dimensions": 512,
            "SUPABASE_REST_API": False,
            "SUPABASE_HOST": "localhost",
            "SUPABASE_USER": "postgres",
            "SUPABASE_PASSWORD": "test_password",
            "SUPABASE_PORT": 5432,
            "SUPABASE_DB_NAME": "test_db",
            "TOGETHER_API_KEY": "test_together_key",
            "SECRET_KEY": secrets.token_urlsafe(32),
            "WORKER_CONCURRENCY": 1,
            "QUEUE_BATCH_SIZE": 5,
            "QUEUE_POLLING_INTERVAL_SECONDS": 1,
            "JOB_TIMEOUT_MINUTES": 5
        }
        
        if overrides:
            print("overrides: ", overrides)
            base_config.update(overrides)
        
        return base_config
    
    @staticmethod
    def patch_settings(test_config: Dict[str, Any]):
        """Context manager to patch settings for testing"""
        from unittest.mock import patch
        return patch('app.core.config.settings', **test_config)


class ValidationTestHelper:
    """Helper functions for validation testing"""
    
    @staticmethod
    def assert_validation_error(func, *args, **kwargs):
        """Assert that a validation error is raised"""
        from pydantic import ValidationError
        try:
            func(*args, **kwargs)
            assert False, "Expected ValidationError was not raised"
        except ValidationError:
            pass  # Expected
        except Exception as e:
            assert False, f"Expected ValidationError, got {type(e).__name__}: {e}"
    
    @staticmethod
    def assert_required_field_validation(model_class, required_field: str):
        """Assert that a required field validation works"""
        from pydantic import ValidationError
        try:
            model_class()  # Create without required field
            assert False, f"Expected ValidationError for missing required field '{required_field}'"
        except ValidationError as e:
            error_messages = str(e)
            assert required_field in error_messages, f"Required field '{required_field}' not mentioned in validation error"
    
    @staticmethod
    def create_invalid_data_cases(valid_data: Dict[str, Any], field_name: str, invalid_values: List[Any]):
        """Create test cases with invalid data for a specific field"""
        test_cases = []
        for invalid_value in invalid_values:
            invalid_data = valid_data.copy()
            invalid_data[field_name] = invalid_value
            test_cases.append(invalid_data)
        return test_cases


class FileTestHelper:
    """Helper functions for file and I/O testing"""
    
    @staticmethod
    def create_mock_file_content(content: str = None, encoding: str = "utf-8"):
        """Create mock file content"""
        content = content or "def hello():\n    print('Hello, World!')"
        return content.encode(encoding) if encoding else content
    
    @staticmethod
    def create_temp_directory_mock():
        """Create a mock temporary directory"""
        from unittest.mock import MagicMock
        temp_dir = MagicMock()
        temp_dir.name = "/tmp/test_dir"
        temp_dir.__enter__ = MagicMock(return_value=temp_dir)
        temp_dir.__exit__ = MagicMock(return_value=None)
        return temp_dir
    
    @staticmethod
    def assert_file_operations(mock_fs, expected_operations: List[str]):
        """Assert that expected file operations were performed"""
        for operation in expected_operations:
            method = getattr(mock_fs, operation, None)
            assert method and method.called, f"Expected file operation '{operation}' was not called"


# Export commonly used helpers
__all__ = [
    'TestDataFactory',
    'MockFactory', 
    'AsyncTestHelper',
    'DatabaseTestHelper',
    'QueueTestHelper',
    'ErrorTestHelper',
    'PerformanceTestHelper',
    'ConfigTestHelper',
    'ValidationTestHelper',
    'FileTestHelper'
]
