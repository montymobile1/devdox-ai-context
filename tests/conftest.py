import pytest
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from cryptography.fernet import Fernet

from app.core.container import Container
from utils import TestDataFactory, MockFactory

@pytest.fixture(autouse=True)
def _disable_mongo(monkeypatch):
    # Make settings.MONGO falsy so lifespan() skips Mongo init in tests
    import app.main as app_main
    monkeypatch.setattr(app_main.settings, "MONGO", None, raising=False)


# Environment setup for testing
os.environ['TESTING'] = 'true'
os.environ['ENVIRONMENT'] = 'test'
os.environ['LOG_LEVEL'] = 'DEBUG'


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()




@pytest.fixture
def test_config():
    """Test configuration with safe defaults"""
    return {
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
        "SECRET_KEY": Fernet.generate_key().decode(),
        "WORKER_CONCURRENCY": 1,
        "QUEUE_BATCH_SIZE": 5,
        "QUEUE_POLLING_INTERVAL_SECONDS": 1,
        "JOB_TIMEOUT_MINUTES": 5
    }




@pytest.fixture
def test_container(test_config):
    """Create test container with mocked dependencies"""
    container = Container()
    container.config.from_dict(test_config)
    return container


@pytest.fixture
def temp_directory():
    """Create temporary directory for test files"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return TestDataFactory.create_user_data()


@pytest.fixture
def sample_repo_data():
    """Sample repository data for testing"""
    return TestDataFactory.create_repo_data()


@pytest.fixture
def sample_api_key_data():
    """Sample API key data for testing"""
    return TestDataFactory.create_api_key_data()


@pytest.fixture
def sample_job_payload():
    """Sample job payload for testing"""
    return TestDataFactory.create_job_payload()


@pytest.fixture
def sample_processing_job_data():
    """Sample processing job data for testing"""
    return TestDataFactory.create_processing_job_data()


@pytest.fixture
def sample_code_chunk_data():
    """Sample code chunk data for testing"""
    return TestDataFactory.create_code_chunk_data()


@pytest.fixture
def mock_user():
    """Mock user object"""
    return MockFactory.create_mock_user()


@pytest.fixture
def mock_repo():
    """Mock repository object"""
    return MockFactory.create_mock_repo()


@pytest.fixture
def mock_api_key():
    """Mock API key object"""
    return MockFactory.create_mock_api_key()


@pytest.fixture
def mock_queue():
    """Mock queue instance"""
    return MockFactory.create_mock_queue()


@pytest.fixture
def mock_encryption_service():
    """Mock encryption service"""
    return MockFactory.create_mock_encryption_service()


@pytest.fixture
def mock_git_client():
    """Mock git client"""
    return MockFactory.create_mock_git_client()


@pytest.fixture
def mock_database_session():
    """Mock database session"""
    session = MagicMock()
    session.execute = AsyncMock()
    session.fetch = AsyncMock()
    session.fetchrow = AsyncMock()
    session.fetchval = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_queue_message():
    """Mock queue message"""
    return MockFactory.create_mock_queue_message()


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mocks between tests"""
    yield
    # Any cleanup if needed


@pytest.fixture
def freeze_time():
    """Freeze time for consistent testing"""
    frozen_time = datetime(2023, 1, 1, 12, 0, 0)
    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.utcnow.return_value = frozen_time
        mock_datetime.now.return_value = frozen_time
        yield frozen_time


@pytest.fixture
def capture_logs(caplog):
    """Capture logs for testing"""
    import logging
    caplog.set_level(logging.DEBUG)
    yield caplog


# Performance testing fixtures
@pytest.fixture
def performance_data():
    """Data for performance testing"""
    return {
        "small_dataset": list(range(100)),
        "medium_dataset": list(range(1000)),
        "large_dataset": list(range(10000)),
        "users": [TestDataFactory.create_user_data() for _ in range(100)],
        "repos": [TestDataFactory.create_repo_data() for _ in range(100)],
        "jobs": [TestDataFactory.create_job_payload() for _ in range(100)]
    }


# Database testing fixtures
@pytest.fixture
async def clean_database():
    """Ensure clean database state for each test"""
    # Setup
    yield
    # Cleanup - in a real scenario, you might truncate tables
    pass


# Configuration fixtures for different scenarios
@pytest.fixture
def production_config(test_config):
    """Production-like configuration"""
    config = test_config.copy()
    config.update({
        "Environment": "production",
        "debug": False,
        "IS_PRODUCTION": True,
        "DB_MAX_CONNECTIONS": 20,
        "DB_MIN_CONNECTIONS": 5,
        "WORKER_CONCURRENCY": 4
    })
    return config


@pytest.fixture
def minimal_config():
    """Minimal configuration for edge case testing"""
    return {
        "SUPABASE_URL": "https://minimal.supabase.co",
        "SUPABASE_KEY": "minimal_key",
        "TOGETHER_API_KEY": "minimal_together_key",
        "SECRET_KEY": Fernet.generate_key().decode(),
        "SUPABASE_PASSWORD": "minimal_password"
    }


# Error simulation fixtures
@pytest.fixture
def database_error():
    """Database error for testing error handling"""
    from app.core.exceptions.local_exceptions import DatabaseError
    return DatabaseError("Test database error")


@pytest.fixture
def authentication_error():
    """Authentication error for testing"""
    from app.core.exceptions.local_exceptions import AuthenticationError
    return AuthenticationError("Test authentication error")


@pytest.fixture
def processing_error():
    """Processing error for testing"""
    from app.core.exceptions.local_exceptions import ProcessingError
    return ProcessingError("Test processing error")


# Async testing helpers
@pytest.fixture
def async_timeout():
    """Timeout for async operations"""
    return 5.0  # 5 seconds


@pytest.fixture
def event_loop_policy():
    """Custom event loop policy for testing"""
    return asyncio.DefaultEventLoopPolicy()


# Marker-based fixtures
@pytest.fixture
def slow_operation_timeout():
    """Longer timeout for slow operations"""
    return 30.0  # 30 seconds


# Integration test fixtures
@pytest.fixture
def integration_test_data():
    """Complete dataset for integration testing"""
    return {
        "users": [TestDataFactory.create_user_data() for _ in range(5)],
        "repos": [TestDataFactory.create_repo_data() for _ in range(10)],
        "jobs": [TestDataFactory.create_job_payload() for _ in range(20)],
        "api_keys": [TestDataFactory.create_api_key_data() for _ in range(5)]
    }
